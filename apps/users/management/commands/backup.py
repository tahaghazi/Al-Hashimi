from django.core.management.base import BaseCommand

from apps.users.backups import create_backup


class Command(BaseCommand):
    help = "Create a database + media backup (used by the daily cron)."

    def add_arguments(self, parser):
        parser.add_argument("--kind", default="scheduled")

    def handle(self, *args, **options):
        b = create_backup(options["kind"])
        self.stdout.write(f"backup {b.status}: {b.filename} ({b.size} bytes) [{b.provider}]")
