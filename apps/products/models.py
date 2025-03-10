from django.db import models

# Create your models here.

class Brand(models.Model):
    name = models.CharField(max_length=255)

    def __str__(self):
        return self.name


class Product(models.Model):
    name = models.CharField(max_length=255)
    brand = models.ForeignKey(Brand, on_delete=models.CASCADE)
    description = models.TextField(null=True, blank=True)
    sku  = models.CharField(max_length=255, null=True, blank=True)
    price = models.DecimalField(max_digits=5, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    image = models.ImageField(upload_to="products", null=True, blank=True)
    stock = models.PositiveIntegerField(default=0)


    def __str__(self):
        return self.name

    class Meta:
        ordering = ["-created_at"]


