import decimal

from django.db import models, transaction


# Create your models here.

class OrderItem(models.Model):
    product = models.ForeignKey("products.Product", on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    extra_data = models.JSONField(null=True, blank=True, default=dict)
    total = models.DecimalField(max_digits=20, decimal_places=2, default=0)

    def __str__(self):
        return f"OrderItem {self.id} "

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        # Calculate total
        self.total = self.product.price * self.quantity
        self.extra_data["product_name"] = self.product.__str__()

        is_new = not self.pk

        if is_new:
            # New item - deduct stock
            self.product.stock -= self.quantity
            self.product.save()

        # For updates, stock is handled in the OrderSerializer.update method

        # Save the OrderItem
        super().save(*args, **kwargs)

    def amount_to_pay(self):
        return self.total

class Order(models.Model):
    user = models.ForeignKey("users.CustomUser", on_delete=models.CASCADE)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    order_items = models.ManyToManyField(OrderItem)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    supplement = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    _original_total = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_total = self.total

    def __str__(self):
        return f"Order {self.id} "

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        is_new = not self.pk
        super().save(*args, **kwargs)

        if is_new:
            # Only calculate and update balance for new orders
            # For updates, we'll handle this separately in recalculate_total_and_update_balance
            self.recalculate_total_and_update_balance()

    def recalculate_total_and_update_balance(self):
        """Recalculate order total and update user balance accordingly"""
        # Store original total
        original_total = self.total

        # Calculate new total
        new_total = sum([item.total for item in self.order_items.all()])

        if original_total != new_total:
            # Update total
            self.total = new_total
            super().save(update_fields=['total'])

            # Update user balance with the difference
            total_diff = new_total - original_total
            if total_diff != 0:
                self.user.userbalance.deposit(total_diff, "orders_total")

    def amount_to_pay(self):
        return self.total + self.supplement


class UserBalance(models.Model):
    orders_total = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    paid_amount = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    user = models.OneToOneField("users.CustomUser", on_delete=models.CASCADE)

    def get_user_balances_queryset(self):
        return UserBalance.objects.filter(id=self.id)

    @transaction.atomic(using="default")
    def deposit(self, amount, balance):
        """
        The balance deposit function should be used instead of manually adjusting the balance and saving.
        When making a deposit process, the user will not be able to modify until after it is completed,
        and the process will not be saved until after its success.

        Raises ValueError if deposit would result in negative balance.
        """
        amount = decimal.Decimal(amount)
        obj = self.get_user_balances_queryset().select_for_update().get()

        # Calculate the new balance value
        new_balance_value = getattr(obj, balance) + amount

        # Check if this would result in negative balance
        if new_balance_value < 0:
            raise ValueError(f"Deposit would result in negative {balance}")

        # Update the balance
        setattr(obj, balance, new_balance_value)
        obj.save()

    def amount_to_pay(self):
        return self.orders_total - self.paid_amount