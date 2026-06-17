"""Backup service: archive the DB + media, store it, apply retention.

Storage is provider-pluggable. Local storage works out of the box; Cloudflare
R2 (S3-compatible) is used automatically when R2 env vars are present.
"""
import os
import zipfile

from django.conf import settings
from django.utils import timezone

from apps.users.models import Backup

RETENTION = 30  # keep the last N successful backups


def _backups_dir():
    d = settings.BASE_DIR / "backups"
    d.mkdir(exist_ok=True)
    return d


def _maybe_upload_r2(path, filename):
    """Upload to Cloudflare R2 if configured; returns provider name used."""
    if not os.getenv("R2_ACCESS_KEY_ID"):
        return "local"
    try:
        import boto3  # only needed/imported when R2 is configured
        s3 = boto3.client(
            "s3",
            endpoint_url=os.getenv("R2_ENDPOINT"),
            aws_access_key_id=os.getenv("R2_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY"),
            region_name="auto",
        )
        s3.upload_file(str(path), os.getenv("R2_BUCKET"), filename)
        return "r2"
    except Exception:
        return "local"


def _apply_retention():
    keep_ids = list(
        Backup.objects.filter(status="ok").order_by("-created_at")
        .values_list("id", flat=True)[:RETENTION]
    )
    for b in Backup.objects.filter(status="ok").exclude(id__in=keep_ids):
        try:
            if b.path and os.path.exists(b.path):
                os.remove(b.path)
        except Exception:
            pass
        b.delete()


def create_backup(kind="manual"):
    stamp = timezone.localtime(timezone.now()).strftime("%Y%m%d-%H%M%S")
    filename = f"backup-{stamp}.zip"
    path = _backups_dir() / filename
    try:
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            db = settings.DATABASES["default"]["NAME"]
            if db and os.path.exists(db):
                z.write(db, "db.sqlite3")
            media = settings.MEDIA_ROOT
            if media and os.path.isdir(media):
                for root, _, files in os.walk(media):
                    for f in files:
                        full = os.path.join(root, f)
                        z.write(full, os.path.join("media", os.path.relpath(full, media)))
        size = os.path.getsize(path)
        provider = _maybe_upload_r2(path, filename)
        backup = Backup.objects.create(
            filename=filename, path=str(path), size=size,
            provider=provider, status="ok", kind=kind,
        )
        _apply_retention()
        return backup
    except Exception as e:
        return Backup.objects.create(filename=filename, status="failed", kind=kind, note=str(e)[:500])
