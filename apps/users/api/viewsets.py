import secrets

import django_filters
from django.contrib.auth import get_user_model
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.orders.models import UserBalance
from apps.users.api.permissions import IsSuperAdmin
from apps.users.api.serializers import (AuditLogSerializer, StaffSerializer, UserSerializer)
from apps.users.audit import AuditMixin, log_action
from apps.users.models import AuditLog

User = get_user_model()


class UserViewSet(AuditMixin, viewsets.ModelViewSet):
    """Customers (and the four stores). Audited create/update; soft delete."""
    queryset = User.objects.filter(deleted=False).exclude(is_staff=True)
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]
    search_fields = ['username', 'email', "first_name", ]
    audit_entity = "Customer"

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        log_action(request, AuditLog.Action.DELETE, entity="Customer",
                   object_id=instance.pk, object_repr=str(instance))
        instance.deleted = True
        instance.save()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def get_object(self):
        user = super().get_object()
        UserBalance.objects.get_or_create(user=user)
        return user


def _unique_username():
    while True:
        candidate = "staff_" + secrets.token_hex(3)
        if not User.objects.filter(username=candidate).exists():
            return candidate


class StaffViewSet(viewsets.ModelViewSet):
    """Super-admin staff management: create from name+phone with auto credentials."""
    serializer_class = StaffSerializer
    permission_classes = [IsSuperAdmin]
    http_method_names = ["get", "post", "delete"]

    def get_queryset(self):
        return User.objects.filter(is_staff=True, deleted=False).order_by("-date_joined")

    def create(self, request, *args, **kwargs):
        first_name = (request.data.get("first_name") or "").strip()
        phone = (request.data.get("phone") or "").strip()
        role = request.data.get("role") or User.Role.STAFF
        if role not in dict(User.Role.choices):
            role = User.Role.STAFF
        if not first_name:
            return Response({"first_name": ["الاسم مطلوب"]}, status=400)
        if User.objects.filter(first_name=first_name).exists():
            return Response({"first_name": ["يوجد مستخدم بنفس الاسم بالفعل"]}, status=400)

        password = secrets.token_urlsafe(8)
        user = User(first_name=first_name, phone=phone, role=role,
                    is_staff=True, username=_unique_username())
        user.set_password(password)
        user.save()
        log_action(request, AuditLog.Action.CREATE, entity="Staff", object_id=user.pk,
                   object_repr=str(user),
                   after={"first_name": first_name, "role": role, "username": user.username})
        # Plaintext password is returned ONCE for the admin to hand over.
        return Response({
            "id": user.id, "first_name": first_name, "phone": phone, "role": role,
            "username": user.username, "password": password,
        }, status=201)

    @action(detail=True, methods=["post"], url_path="reset-password")
    def reset_password(self, request, pk=None):
        user = self.get_object()
        password = secrets.token_urlsafe(8)
        user.set_password(password)
        user.save()
        log_action(request, AuditLog.Action.UPDATE, entity="Staff", object_id=user.pk,
                   object_repr=str(user), after={"password_reset": True})
        return Response({"username": user.username, "password": password})

    def destroy(self, request, *args, **kwargs):
        user = self.get_object()
        log_action(request, AuditLog.Action.DELETE, entity="Staff",
                   object_id=user.pk, object_repr=str(user))
        user.deleted = True
        user.is_active = False
        user.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


class AuditFilter(django_filters.FilterSet):
    start = django_filters.DateFilter(field_name="created_at", lookup_expr="date__gte")
    end = django_filters.DateFilter(field_name="created_at", lookup_expr="date__lte")

    class Meta:
        model = AuditLog
        fields = ["actor", "action", "entity", "start", "end"]


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """Super-admin audit trail with filtering by user/action/date."""
    serializer_class = AuditLogSerializer
    permission_classes = [IsSuperAdmin]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = AuditFilter
    search_fields = ["actor_username", "entity", "object_repr"]

    def get_queryset(self):
        return AuditLog.objects.select_related("actor").all()
