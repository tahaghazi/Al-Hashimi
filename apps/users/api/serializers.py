from dj_rest_auth.serializers import JWTSerializer
from django.contrib.auth import get_user_model
from rest_framework import serializers


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        fields = ('id', 'first_name', 'date_joined', 'phone')
        read_only_fields = ('id', 'date_joined')


class CustomJWTSerializer(JWTSerializer):
    """Preserve the historical login response shape.

    dj-rest-auth 7.x renamed the JWT response keys to `access`/`refresh`. The
    Nuxt frontend reads `access_token`, so we expose both names to keep the
    login contract stable across the upgrade.
    """
    access_token = serializers.CharField(source="access")
    refresh_token = serializers.CharField(source="refresh")
