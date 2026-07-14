from django.core.management.base import BaseCommand

from apps.users.backups import r2_check


class Command(BaseCommand):
    help = "Check Cloudflare R2 connectivity using the configured R2_* env vars."

    def handle(self, *args, **options):
        ok, msg = r2_check()
        self.stdout.write(("OK: " if ok else "FAIL: ") + msg)
