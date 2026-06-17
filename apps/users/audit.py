"""Audit-trail helpers: capture who did what, with before/after snapshots."""
import json

from django.core.serializers.json import DjangoJSONEncoder
from django.forms.models import model_to_dict

from apps.users.models import AuditLog


def client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def client_device(request):
    # The frontend sends a stable per-device id; fall back to the user agent.
    return (request.META.get("HTTP_X_DEVICE_ID")
            or request.META.get("HTTP_USER_AGENT", ""))[:255]


def safe_snapshot(instance, fields=None):
    """JSON-safe dict of an instance's fields (FKs as ids)."""
    if instance is None:
        return None
    try:
        data = model_to_dict(instance, fields=fields)
        data.pop("password", None)
        return json.loads(json.dumps(data, cls=DjangoJSONEncoder))
    except Exception:
        return None


def log_action(request, action, *, entity="", object_id="", object_repr="",
               before=None, after=None):
    user = getattr(request, "user", None)
    authed = bool(user and getattr(user, "is_authenticated", False))
    AuditLog.objects.create(
        actor=user if authed else None,
        actor_username=(getattr(user, "username", "") or "") if authed else "",
        action=action,
        entity=entity,
        object_id=str(object_id or ""),
        object_repr=str(object_repr or "")[:200],
        before=before,
        after=after,
        ip=client_ip(request),
        device=client_device(request),
    )


class AuditMixin:
    """Logs create/update/destroy for a DRF ModelViewSet.

    ViewSets with fully-custom create/update/destroy methods should call
    `log_action` explicitly instead of (or in addition to) relying on this.
    """
    audit_entity = None

    def _entity(self):
        return self.audit_entity or self.queryset.model.__name__

    def perform_create(self, serializer):
        instance = serializer.save()
        log_action(self.request, AuditLog.Action.CREATE, entity=self._entity(),
                   object_id=instance.pk, object_repr=str(instance),
                   after=safe_snapshot(instance))
        return instance

    def perform_update(self, serializer):
        before = safe_snapshot(serializer.instance)
        instance = serializer.save()
        log_action(self.request, AuditLog.Action.UPDATE, entity=self._entity(),
                   object_id=instance.pk, object_repr=str(instance),
                   before=before, after=safe_snapshot(instance))
        return instance

    def perform_destroy(self, instance):
        log_action(self.request, AuditLog.Action.DELETE, entity=self._entity(),
                   object_id=instance.pk, object_repr=str(instance),
                   before=safe_snapshot(instance))
        instance.delete()
