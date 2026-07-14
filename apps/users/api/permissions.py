from rest_framework.permissions import BasePermission


class IsSuperAdmin(BasePermission):
    message = "هذه العملية متاحة للمدير العام فقط."

    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and getattr(u, "is_super_admin", False))
