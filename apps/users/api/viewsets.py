from django.contrib.auth import get_user_model
from rest_framework import permissions, status
from rest_framework import viewsets
from rest_framework.response import Response

from apps.users.api.serializers import UserSerializer


class UserViewSet(viewsets.ModelViewSet):
    queryset = get_user_model().objects.filter(deleted=False).exclude(is_staff=True)
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]
    search_fields = ['username', 'email', "first_name", ]
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.deleted = True
        instance.save()
        return Response(status=status.HTTP_204_NO_CONTENT)
