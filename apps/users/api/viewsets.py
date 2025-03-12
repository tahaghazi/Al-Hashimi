from django.contrib.auth import get_user_model
from rest_framework import permissions
from rest_framework import viewsets

from apps.users.api.serializers import UserSerializer


class UserViewSet(viewsets.ModelViewSet):
    queryset = get_user_model().objects.exclude(is_staff=True)
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]
    search_fields = ['username', 'email', "first_name", ]
