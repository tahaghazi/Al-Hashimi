from rest_framework import serializers

from apps.orders.models import Order, OrderItem
from apps.products.api.serializers import ProductSerializer
from apps.users.api.serializers import UserSerializer


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = "__all__"
    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["product"] = ProductSerializer(instance.product).data
        return data


class OrderSerializer(serializers.ModelSerializer):
    order_items = OrderItemSerializer(many=True, )

    class Meta:
        model = Order
        fields = "__all__"
        read_only_fields = ('id', 'created_at', "updated_at")

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["amount_to_pay"] = instance.amount_to_pay()
        data["user"]=UserSerializer(instance.user).data
        return data


    def create(self, validated_data):
        order_items_data = validated_data.pop("order_items", [])  # Extract order_items data
        order = Order.objects.create(**validated_data)

        # Create OrderItem instances and associate them with the order
        order_items = []
        for item_data in order_items_data:
            order_item = OrderItem.objects.create(**item_data)
            order_items.append(order_item)

        # Add the created order items to the ManyToMany field
        order.order_items.set(order_items)
        order.save()
        return order
