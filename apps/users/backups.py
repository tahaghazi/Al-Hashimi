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


def r2_configured():
    return bool(os.getenv("R2_ACCESS_KEY_ID") and os.getenv("R2_SECRET_ACCESS_KEY")
                and os.getenv("R2_ENDPOINT") and os.getenv("R2_BUCKET"))


def _r2_client():
    import boto3  # only imported when R2 is configured
    return boto3.client(
        "s3",
        endpoint_url=os.getenv("R2_ENDPOINT"),
        aws_access_key_id=os.getenv("R2_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY"),
        region_name="auto",
    )


def r2_check():
    """Return (ok, message) describing whether R2 is reachable."""
    if not r2_configured():
        return False, "R2 غير مُعد — المفاتيح مفقودة"
    try:
        _r2_client().list_objects_v2(Bucket=os.getenv("R2_BUCKET"), MaxKeys=1)
        return True, f"متصل بنجاح بـ {os.getenv('R2_BUCKET')}"
    except Exception as e:
        return False, str(e)[:300]


def _maybe_upload_r2(path, filename):
    """Upload to Cloudflare R2 if configured. Returns (provider, error|None)."""
    if not r2_configured():
        return "local", None
    try:
        s3 = _r2_client()
        bucket = os.getenv("R2_BUCKET")
        s3.upload_file(str(path), bucket, f"backups/{filename}")
        # Remote retention: keep the newest RETENTION objects under backups/.
        try:
            objs = s3.list_objects_v2(Bucket=bucket, Prefix="backups/").get("Contents", [])
            for o in sorted(objs, key=lambda x: x["LastModified"], reverse=True)[RETENTION:]:
                s3.delete_object(Bucket=bucket, Key=o["Key"])
        except Exception:
            pass
        return "r2", None
    except Exception as e:
        return "local", str(e)[:300]


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
        provider, r2_error = _maybe_upload_r2(path, filename)
        note = ""
        if r2_configured() and provider != "r2":
            note = f"R2 upload failed: {r2_error}"
        backup = Backup.objects.create(
            filename=filename, path=str(path), size=size,
            provider=provider, status="ok", kind=kind, note=note,
        )
        _apply_retention()
        return backup
    except Exception as e:
        return Backup.objects.create(filename=filename, status="failed", kind=kind, note=str(e)[:500])
