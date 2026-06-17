from django.apps import apps as django_apps
from django.contrib import admin, messages
from django.http import FileResponse, HttpResponseRedirect
from django.urls import path, reverse
from django.utils.html import format_html

from apps.users.backups import create_backup
from apps.users.models import AuditLog, Backup


@admin.register(Backup)
class BackupAdmin(admin.ModelAdmin):
    list_display = ("created_at", "filename", "provider", "size_mb", "status", "kind", "download_link")
    list_filter = ("status", "provider", "kind")
    change_list_template = "admin/users/backup/change_list.html"

    def has_add_permission(self, request):
        return False

    @admin.display(description="الحجم")
    def size_mb(self, obj):
        return f"{obj.size / 1048576:.2f} MB"

    @admin.display(description="تنزيل")
    def download_link(self, obj):
        if obj.status != "ok":
            return "—"
        return format_html('<a href="{}">تنزيل</a>', reverse("admin:backup-download", args=[obj.id]))

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path("backup-now/", self.admin_site.admin_view(self.backup_now), name="backup-now"),
            path("<int:pk>/download/", self.admin_site.admin_view(self.download), name="backup-download"),
        ]
        return custom + urls

    def backup_now(self, request):
        b = create_backup("manual")
        level = messages.SUCCESS if b.status == "ok" else messages.ERROR
        self.message_user(request, f"النسخة: {b.filename} — {b.status}", level=level)
        return HttpResponseRedirect("../")

    def download(self, request, pk):
        b = Backup.objects.get(pk=pk)
        return FileResponse(open(b.path, "rb"), as_attachment=True, filename=b.filename)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor_username", "action", "entity", "object_repr", "ip", "device")
    list_filter = ("action", "entity")
    search_fields = ("actor_username", "object_repr", "ip")
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# Auto-register the remaining users-app models (CustomUser, etc.).
_app = django_apps.get_app_config("users")
for _model in _app.get_models():
    if _model in (Backup, AuditLog):
        continue
    try:
        admin.site.register(_model)
    except admin.sites.AlreadyRegistered:
        pass
