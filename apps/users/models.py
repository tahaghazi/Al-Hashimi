import uuid

from django.contrib.auth.models import User, AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _


def generate_username():
    """Generate a random username with a unique identifier."""
    return f"user_{uuid.uuid4().hex[:8]}"

# Create your models here.
class CustomUser(AbstractUser):
    class Role(models.TextChoices):
        SUPER_ADMIN = "super_admin", "مدير عام"
        MANAGER = "manager", "مدير"
        STAFF = "staff", "موظف"

    phone = models.CharField(max_length=20, null=True, blank=True)
    deleted = models.BooleanField(default=False)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.STAFF)
    first_name = models.CharField(_("first name"), max_length=150, blank=True, unique=True,
                                  error_messages={
                                      'unique': _("يوجد مستخدم بنفس الاسم بالفعل."),
                                  })

    def save(self, *args, **kwargs):
        if not self.username:
            self.username = generate_username()
        super().save(*args, **kwargs)

    @property
    def is_super_admin(self):
        return self.is_superuser or self.role == self.Role.SUPER_ADMIN

    @property
    def is_manager(self):
        return self.is_super_admin or self.role == self.Role.MANAGER

    def __str__(self):
        return self.first_name


class Backup(models.Model):
    """Metadata for a database+media backup archive."""
    filename = models.CharField(max_length=255)
    path = models.CharField(max_length=500, blank=True, default="")
    provider = models.CharField(max_length=20, default="local")  # local / r2 / b2 ...
    size = models.BigIntegerField(default=0)
    status = models.CharField(max_length=20, default="ok")       # ok / failed
    kind = models.CharField(max_length=20, default="manual")     # manual / scheduled
    note = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.filename} ({self.status})"


class AuditLog(models.Model):
    """Append-only record of every staff action for accountability."""

    class Action(models.TextChoices):
        CREATE = "create", "إنشاء"
        UPDATE = "update", "تعديل"
        DELETE = "delete", "حذف"
        PAYMENT = "payment", "دفعة"
        LOGIN = "login", "تسجيل دخول"
        LOGOUT = "logout", "تسجيل خروج"
        PRINT = "print", "طباعة"
        EXPORT = "export", "تصدير"
        SYNC = "sync", "مزامنة"

    actor = models.ForeignKey("users.CustomUser", null=True, blank=True,
                              on_delete=models.SET_NULL, related_name="audit_logs")
    actor_username = models.CharField(max_length=150, blank=True, default="")
    action = models.CharField(max_length=20, choices=Action.choices)
    entity = models.CharField(max_length=60, blank=True, default="")     # model name
    object_id = models.CharField(max_length=60, blank=True, default="")
    object_repr = models.CharField(max_length=200, blank=True, default="")
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    device = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.actor_username} {self.action} {self.entity}#{self.object_id}"

