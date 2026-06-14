import decimal
import uuid

from django.contrib.auth import get_user_model
from django.db import models, transaction
from django.db.models import Sum


# Create your models here.

class OrderItem(models.Model):
    product = models.ForeignKey("products.Product", on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    extra_data = models.JSONField(null=True, blank=True, default=dict)
    total = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    fixed_price = models.DecimalField(max_digits=20, decimal_places=2, default=0)

    def __str__(self):
        return f"OrderItem {self.id} "

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        # Computing the line total and locking in the price at order time is
        # idempotent, so it is safe to do on every save. Stock is intentionally
        # NOT adjusted here: it used to be decremented on every save() call,
        # which double-counted whenever an item was re-saved. Stock changes now
        # live in the serializer/viewset where they happen exactly once, inside
        # a transaction, with an availability check.
        self.total = self.product.price * self.quantity
        if self.fixed_price == 0:
            self.fixed_price = self.product.price
        self.extra_data = self.extra_data or {}
        self.extra_data["product_name"] = str(self.product)
        super().save(*args, **kwargs)


class Order(models.Model):
    user = models.ForeignKey("users.CustomUser", on_delete=models.CASCADE)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    order_items = models.ManyToManyField(OrderItem)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    supplement = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    # Client-generated idempotency key. An order created offline carries this
    # UUID so that replaying the request when connectivity returns finds the
    # existing order instead of charging the customer (and stock) twice.
    client_uuid = models.UUIDField(null=True, blank=True, unique=True)

    def __str__(self):
        return f"Order {self.id} "

    class Meta:
        ordering = ["-created_at"]

    def recalculate_total(self):
        """Recompute and persist `total` from the attached order items.

        Kept out of save() on purpose: the old save() recomputed the total and
        recursively re-saved itself while also poking the user's balance, which
        made every save risk double-counting a customer's debt. Balance changes
        are now driven explicitly from the serializer/viewset.
        """
        self.total = sum((item.total for item in self.order_items.all()), decimal.Decimal("0"))
        self.save(update_fields=["total"])
        return self.total

    def amount_to_pay(self):
        return self.total + self.supplement


class BalanceNote(models.Model):
    user = models.ForeignKey(get_user_model(), on_delete=models.CASCADE, related_name='notes')
    note = models.TextField()
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Note for {self.user}: {self.amount}"


class LedgerEntry(models.Model):
    """Append-only audit trail of every balance-affecting event.

    `orders_total` and `paid_amount` on UserBalance are fast cached aggregates;
    the ledger is the source of truth that can rebuild them (see
    `UserBalance.recompute_from_ledger`). Every entry is written in the same
    transaction as the cached-balance update.

    `amount` is the signed effect on the two running totals via `field`:
    an ORDER entry adds to `orders_total`, a PAYMENT entry adds to
    `paid_amount`. Reversals (e.g. editing an order) are negative entries.
    """

    class Kind(models.TextChoices):
        ORDER = "order", "Order"
        ORDER_REVERSAL = "order_reversal", "Order reversal"
        PAYMENT = "payment", "Payment"
        ADJUSTMENT = "adjustment", "Adjustment"

    user = models.ForeignKey(
        "users.CustomUser", on_delete=models.CASCADE, related_name="ledger_entries"
    )
    kind = models.CharField(max_length=20, choices=Kind.choices)
    # Which cached balance field this entry rolls up into.
    field = models.CharField(max_length=20)  # "orders_total" | "paid_amount"
    amount = models.DecimalField(max_digits=20, decimal_places=2)
    order = models.ForeignKey(
        Order, null=True, blank=True, on_delete=models.SET_NULL, related_name="ledger_entries"
    )
    note = models.TextField(blank=True, default="")
    # Idempotency key for replayed (e.g. offline) payment requests.
    client_uuid = models.UUIDField(null=True, blank=True, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.kind} {self.amount} for {self.user}"


class UserBalance(models.Model):
    orders_total = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    paid_amount = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    user = models.OneToOneField("users.CustomUser", on_delete=models.CASCADE)

    def get_user_balances_queryset(self):
        return UserBalance.objects.filter(id=self.id)

    @transaction.atomic(using="default")
    def deposit(self, amount, balance, *, kind=None, order=None, note="", client_uuid=None):
        """Adjust a cached balance field and append a matching ledger entry.

        `balance` is the field name ("orders_total" or "paid_amount"). The row
        is locked for the duration so concurrent updates serialize. Passing
        ledger metadata records the event for audit; omitting it (legacy calls)
        still updates the cached total.
        """
        amount = decimal.Decimal(amount)
        obj = self.get_user_balances_queryset().select_for_update().get()
        setattr(obj, balance, getattr(obj, balance) + amount)
        obj.save(update_fields=[balance])

        LedgerEntry.objects.create(
            user=obj.user,
            kind=kind or (LedgerEntry.Kind.PAYMENT if balance == "paid_amount" else LedgerEntry.Kind.ORDER),
            field=balance,
            amount=amount,
            order=order,
            note=note or "",
            client_uuid=client_uuid,
        )

    def recompute_from_ledger(self):
        """Rebuild the cached totals from the ledger (audit / repair helper)."""
        totals = {"orders_total": decimal.Decimal("0"), "paid_amount": decimal.Decimal("0")}
        rows = (
            LedgerEntry.objects.filter(user=self.user)
            .values("field")
            .annotate(total=Sum("amount"))
        )
        for row in rows:
            if row["field"] in totals:
                totals[row["field"]] = row["total"] or decimal.Decimal("0")
        return totals

    def amount_to_pay(self):
        return self.orders_total - self.paid_amount
