import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from accounts.models import Department, Role, UserProfile


class Command(BaseCommand):
    help = "إنشاء أو تحديث مدير النظام من متغيرات البيئة أثناء النشر"

    def handle(self, *args, **options):
        username = os.environ.get("DJANGO_ADMIN_USERNAME", "").strip()
        password = os.environ.get("DJANGO_ADMIN_PASSWORD", "")
        if not username or not password:
            raise CommandError("Set DJANGO_ADMIN_USERNAME and DJANGO_ADMIN_PASSWORD.")

        User = get_user_model()
        user, created = User.objects.get_or_create(
            username=username,
            defaults={"first_name": "خالد", "last_name": "الإدارة", "is_staff": True, "is_superuser": True},
        )
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user.set_password(password)
        user.save()

        department, _ = Department.objects.get_or_create(code="CNT", defaults={"name": "إدارة العقود"})
        UserProfile.objects.update_or_create(
            user=user,
            defaults={"role": Role.ADMIN, "department": department, "job_title": "مدير النظام"},
        )
        action = "created" if created else "updated"
        self.stdout.write(self.style.SUCCESS(f"Admin {action}: {username}"))
