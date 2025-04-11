from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import UserBalance


@receiver(post_save, sender=get_user_model())
def create_user_balance(sender, instance, created, **kwargs):
    """
    Signal to create UserBalance when a new CustomUser is created
    """
    if created:
        UserBalance.objects.create(user=instance)
