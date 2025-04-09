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
        self.total = self.product.price * self.quantity
        self.extra_data["product_name"] = self.product.__str__()

        self.product.stock -= self.quantity
        self.product.save()

        super().save(*args, **kwargs)

    def amount_to_pay(self):
        return self.total - self.supplement


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

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        total = sum([item.total for item in self.order_items.all()])

        if not self.total == total:
            self.total = total
            self.save()

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
