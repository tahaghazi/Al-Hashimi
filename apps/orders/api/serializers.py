import decimal

from django.db import transaction
from rest_framework import serializers

from apps.orders.models import Order, OrderItem, UserBalance, BalanceNote, LedgerEntry, OrderRevision
from apps.products.api.serializers import ProductSerializer
from apps.products.models import Product
from apps.users.api.serializers import UserSerializer


class OrderRevisionSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderRevision
        fields = ("id", "snapshot", "editor_username", "reason", "created_at")


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
    # Drop the default UniqueValidator so a replayed offline order (same UUID)
    # is handled idempotently in create() instead of being rejected as a 400.
    client_uuid = serializers.UUIDField(required=False, allow_null=True, validators=[])

    class Meta:
        model = Order
        fields = "__all__"
        read_only_fields = ('id', 'created_at', "updated_at")

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["amount_to_pay"] = instance.amount_to_pay()
        data["user"] = UserSerializer(instance.user).data
        # Invoices are now editable indefinitely (revisions preserve history).
        data["allow_edit"] = True
        data["revisions_count"] = instance.revisions.count()
        return data


    def create(self, validated_data):
        order_items_data = validated_data.pop("order_items", [])
        client_uuid = validated_data.get("client_uuid")

        with transaction.atomic():
            # Idempotency: a replayed offline order (same client_uuid) must not
            # charge stock or balance again — return the order already recorded.
            if client_uuid:
                existing = Order.objects.filter(client_uuid=client_uuid).first()
                if existing is not None:
                    return existing

            order = Order.objects.create(**validated_data)

            order_items = []
            for item_data in order_items_data:
                product = item_data["product"]
                quantity = item_data["quantity"]

                # Lock the product row and verify availability so two concurrent
                # withdrawals can't oversell, and stock never goes negative.
                locked = Product.objects.select_for_update().get(pk=product.pk)
                if quantity > locked.stock:
                    raise serializers.ValidationError(
                        {"order_items": f"المخزون غير كافٍ للمنتج {locked}. المتاح: {locked.stock}"}
                    )
                locked.stock -= quantity
                locked.save(update_fields=["stock"])

                order_items.append(OrderItem.objects.create(**item_data))

            order.order_items.set(order_items)
            order.recalculate_total()
            # The final amount (goods + scrap - discount) must stay above zero.
            if order.amount_to_pay() <= 0:
                raise serializers.ValidationError(
                    {"discount": "المبلغ النهائي للفاتورة يجب أن يكون أكبر من صفر"}
                )
            # Add what the customer now owes to their balance, exactly once,
            # inside this transaction, and record it in the ledger.
            order.user.userbalance.deposit(
                order.amount_to_pay(), "orders_total",
                kind=LedgerEntry.Kind.ORDER, order=order,
            )
        return order


class UserBalanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserBalance
        fields = ['id', 'orders_total', 'paid_amount', 'amount_to_pay']
        read_only_fields = ['orders_total', 'paid_amount']

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['amount_to_pay'] = instance.amount_to_pay()
        return representation

class UserBalanceDepositSerializer(serializers.Serializer):
    amount = serializers.DecimalField(
        max_digits=20, decimal_places=2, min_value=decimal.Decimal("0.01")
    )
    balance_type = serializers.ChoiceField(choices=['paid_amount'])
    note = serializers.CharField(write_only=True, required=False, allow_blank=True)
    source = serializers.ChoiceField(
        choices=BalanceNote.PaymentSource.choices, required=False, allow_blank=True
    )
    # Idempotency key so a replayed offline payment is applied at most once.
    client_uuid = serializers.UUIDField(required=False, allow_null=True)


class UserBalanceNoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = BalanceNote
        fields = "__all__"
