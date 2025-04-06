import uuid

from django.contrib.auth.models import User, AbstractUser
from django.db import models


def generate_username():
    """Generate a random username with a unique identifier."""
    return f"user_{uuid.uuid4().hex[:8]}"

# Create your models here.
class CustomUser(AbstractUser):
    phone = models.CharField(max_length=20, null=True, blank=True)
    deleted = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if not self.username:
            self.username = generate_username()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.first_name

