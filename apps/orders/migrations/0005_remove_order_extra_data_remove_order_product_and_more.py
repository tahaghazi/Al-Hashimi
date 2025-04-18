# Generated by Django 4.2.17 on 2025-03-11 00:35

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("products", "0004_alter_product_price"),
        ("orders", "0004_alter_order_supplement"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="order",
            name="extra_data",
        ),
        migrations.RemoveField(
            model_name="order",
            name="product",
        ),
        migrations.RemoveField(
            model_name="order",
            name="quantity",
        ),
        migrations.CreateModel(
            name="OrderItem",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("quantity", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("extra_data", models.JSONField(blank=True, null=True)),
                (
                    "total",
                    models.DecimalField(decimal_places=2, default=0, max_digits=20),
                ),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="products.product",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddField(
            model_name="order",
            name="order_items",
            field=models.ManyToManyField(to="orders.orderitem"),
        ),
    ]
