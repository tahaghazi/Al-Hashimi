import uuid

from django.contrib.auth.models import User, AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _


def generate_username():
    """Generate a random username with a unique identifier."""
    return f"user_{uuid.uuid4().hex[:8]}"

# Create your models here.
class CustomUser(AbstractUser):
    phone = models.CharField(max_length=20, null=True, blank=True)
    deleted = models.BooleanField(default=False)
    first_name = models.CharField(_("first name"), max_length=150, blank=True, unique=True,
                                  error_messages={
                                      'unique': _("يوجد مستخدم بنفس الاسم بالفعل."),
                                  })



    def save(self, *args, **kwargs):
        if not self.username:
            self.username = generate_username()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.first_name

