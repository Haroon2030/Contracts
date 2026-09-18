from django.conf import settings
from django.db import models


class Role(models.TextChoices):
    CONTRACTS_OFFICER = "contracts_officer", "موظف قسم العقود"
    PURCHASING_OFFICER = "purchasing_officer", "موظف المشتريات"
    PURCHASING_HEAD = "purchasing_head", "رئيس قسم المشتريات"
    CONTRACTS_MANAGER = "contracts_manager", "مدير إدارة العقود"
    LEGAL = "legal", "الشؤون القانونية"
    ADMIN = "admin", "مدير النظام"


class Department(models.Model):
    name = models.CharField("اسم القسم", max_length=120, unique=True)
    code = models.CharField("الرمز", max_length=20, unique=True)
    is_active = models.BooleanField("نشط", default=True)

    class Meta:
        verbose_name = "قسم"
        verbose_name_plural = "الأقسام"
        ordering = ["name"]

    def __str__(self):
        return self.name


class UserProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
        verbose_name="المستخدم",
    )
    role = models.CharField("الدور", max_length=32, choices=Role.choices)
    department = models.ForeignKey(
        Department,
        on_delete=models.PROTECT,
        related_name="members",
        verbose_name="القسم",
        null=True,
        blank=True,
    )
    job_title = models.CharField("المسمى الوظيفي", max_length=120, blank=True)
    phone = models.CharField("الجوال", max_length=20, blank=True)

    class Meta:
        verbose_name = "ملف مستخدم"
        verbose_name_plural = "ملفات المستخدمين"

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} — {self.get_role_display()}"

    @property
    def is_contracts_staff(self):
        return self.role in {Role.CONTRACTS_OFFICER, Role.CONTRACTS_MANAGER, Role.ADMIN}

    @property
    def is_purchasing_staff(self):
        return self.role in {Role.PURCHASING_OFFICER, Role.PURCHASING_HEAD, Role.ADMIN}

    @property
    def can_approve_as_head(self):
        return self.role in {Role.PURCHASING_HEAD, Role.ADMIN}

    @property
    def can_approve_as_contracts_manager(self):
        return self.role in {Role.CONTRACTS_MANAGER, Role.ADMIN}

    @property
    def can_legal_review(self):
        return self.role in {Role.LEGAL, Role.ADMIN}
