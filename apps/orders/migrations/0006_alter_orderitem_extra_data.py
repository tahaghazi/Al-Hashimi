# Generated by Django 4.2.17 on 2025-03-29 10:13

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0005_remove_order_extra_data_remove_order_product_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='orderitem',
            name='extra_data',
            field=models.JSONField(blank=True, default=dict, null=True),
        ),
    ]
