from django.core.management.base import BaseCommand

from core.models import Report


class Command(BaseCommand):
    help = "Release investigatory claims older than CLAIM_TTL_DAYS (10 months) back to pending. Run daily via cron."

    def handle(self, *args, **options):
        n = Report.objects.release_stale_claims()
        self.stdout.write(self.style.SUCCESS(f"Released {n} stale claim(s) back to Awaiting Justice."))
