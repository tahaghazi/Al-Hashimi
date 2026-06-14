import decimal

from django.contrib.auth import get_user_model
from django.db import models, transaction


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


class UserBalance(models.Model):
    orders_total = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    paid_amount = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    user = models.OneToOneField("users.CustomUser", on_delete=models.CASCADE)

    def get_user_balances_queryset(self):
        return UserBalance.objects.filter(id=self.id)

    @transaction.atomic(using="default")
    def deposit(self, amount, balance):
        """
        The balance withdrawal function should be used instead of manually adjusting the balance and saving.
        When making a withdrawal process, the user will not be able to modify until after it is completed,
        and the process will not be saved until after its success.
        """
        amount = decimal.Decimal(amount)
        obj = self.get_user_balances_queryset().select_for_update().get()
        amount = getattr(obj, balance) + amount
        setattr(obj, balance, amount)
        obj.save()

    def amount_to_pay(self):
        return self.orders_total - self.paid_amount
