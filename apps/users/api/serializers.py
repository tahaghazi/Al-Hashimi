from dj_rest_auth.serializers import JWTSerializer
from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.users.models import AuditLog


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        fields = ('id', 'first_name', 'date_joined', 'phone')
        read_only_fields = ('id', 'date_joined')


class UserDetailsSerializer(serializers.ModelSerializer):
    """Returned by /api/authentication/user/ so the app knows the role."""
    is_super_admin = serializers.BooleanField(read_only=True)

    class Meta:
        model = get_user_model()
        fields = ('id', 'username', 'first_name', 'phone', 'role',
                  'is_staff', 'is_superuser', 'is_super_admin')
        read_only_fields = fields


class StaffSerializer(serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        fields = ('id', 'first_name', 'phone', 'username', 'role', 'is_active', 'date_joined')
        read_only_fields = ('id', 'username', 'date_joined')


class AuditLogSerializer(serializers.ModelSerializer):
    action_display = serializers.CharField(source="get_action_display", read_only=True)

    class Meta:
        model = AuditLog
        fields = ('id', 'actor', 'actor_username', 'action', 'action_display',
                  'entity', 'object_id', 'object_repr', 'before', 'after',
                  'ip', 'device', 'created_at')


class CustomJWTSerializer(JWTSerializer):
    """Preserve the historical login response shape.

    dj-rest-auth 7.x renamed the JWT response keys to `access`/`refresh`. The
    Nuxt frontend reads `access_token`, so we expose both names to keep the
    login contract stable across the upgrade.
    """
    access_token = serializers.CharField(source="access")
    refresh_token = serializers.CharField(source="refresh")
