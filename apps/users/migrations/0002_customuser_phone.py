# Generated by Django 4.2.17 on 2025-03-10 23:43

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="customuser",
            name="phone",
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
    ]
