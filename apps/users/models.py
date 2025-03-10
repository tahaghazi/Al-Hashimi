import uuid

from django.contrib.auth.models import User, AbstractUser
from django.db import models
def generate_username():
    """Generate a random username with a unique identifier."""
    return f"user_{uuid.uuid4().hex[:8]}"

# Create your models here.
class CustomUser(AbstractUser):

    def save(self, *args, **kwargs):
        self.username =generate_username()
        super().save(*args, **kwargs)

