from django.db import transaction
from rest_framework import serializers

from apps.orders.models import Order, OrderItem, UserBalance
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
    order_items = OrderItemSerializer(many=True)

    class Meta:
        model = Order
        fields = "__all__"
        read_only_fields = ('id', 'created_at', "updated_at")

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["amount_to_pay"] = instance.amount_to_pay()
        data["user"] = UserSerializer(instance.user).data
        return data

    def create(self, validated_data):
        order_items_data = validated_data.pop("order_items", [])  # Extract order_items data
        with transaction.atomic():
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

    def update(self, instance, validated_data):
        order_items_data = validated_data.pop('order_items', None)

        # Update Order fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        # Handle order items if provided
        if order_items_data is not None:
            # Get current order items
            current_items = {item.id: item for item in instance.order_items.all()}

            # Track which items we've processed
            processed_items = set()

            # Items to add to the order
            items_to_add = []

            for item_data in order_items_data:
                item_id = item_data.get('id', None)

                if item_id and item_id in current_items:
                    # Update existing item
                    item = current_items[item_id]

                    # Store original quantity for stock adjustment
                    original_quantity = item.quantity

                    # Update fields
                    for attr, value in item_data.items():
                        if attr != 'id':
                            setattr(item, attr, value)

                    # Manually adjust stock difference
                    quantity_diff = original_quantity - item.quantity
                    if quantity_diff != 0:
                        item.product.stock += quantity_diff
                        item.product.save()

                    item.save()
                    processed_items.add(item_id)
                else:
                    # Create new item (product stock handled in OrderItem.save())
                    if 'id' in item_data:
                        item_data.pop('id')
                    new_item = OrderItem.objects.create(**item_data)
                    items_to_add.append(new_item)

            # Handle removed items
            for item_id, item in current_items.items():
                if item_id not in processed_items:
                    # Return stock for removed item
                    item.product.stock += item.quantity
                    item.product.save()
                    instance.order_items.remove(item)
                    item.delete()

            # Add new items
            for item in items_to_add:
                instance.order_items.add(item)

        instance.save()
        return instance

class UserBalanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserBalance
        fields = ['id', 'orders_total', 'paid_amount', 'user', 'amount_to_pay']
        read_only_fields = ['orders_total', 'paid_amount']

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['amount_to_pay'] = instance.amount_to_pay()
        return representation


class UserBalanceDepositSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=20, decimal_places=2, min_value=0.01)
    balance_type = serializers.ChoiceField(choices=['paid_amount'])
