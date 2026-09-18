from django.core.management.base import BaseCommand

from contracts.services import refresh_all_alerts


class Command(BaseCommand):
    help = "إعادة حساب تنبيهات العقود تلقائياً"

    def handle(self, *args, **options):
        refresh_all_alerts()
        self.stdout.write(self.style.SUCCESS("تم تحديث التنبيهات."))
