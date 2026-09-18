from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class ContractType(models.TextChoices):
    SUPPLY = "supply", "توريد"
    SHELF_RENT = "shelf_rent", "إيجار أرفف"
    MARKETING = "marketing", "تسويق"
    SERVICES = "services", "خدمات"


class ContractSubtype(models.TextChoices):
    FRESH = "fresh", "فريش"
    FOOD = "food", "غذائي"
    NON_FOOD = "non_food", "لا غذائي"
    ACCOUNT_OPENING = "account_opening", "فتح حساب"


class ContractStatus(models.TextChoices):
    DRAFT = "draft", "مسودة"
    UNDER_REVIEW = "under_review", "تحت المراجعة"
    PENDING_APPROVAL = "pending_approval", "بانتظار الموافقة"
    PENDING_SIGNATURE = "pending_signature", "بانتظار التوقيع"
    ACTIVE = "active", "نشط"
    EXPIRED = "expired", "منتهي"
    CANCELLED = "cancelled", "ملغى"


class AlertType(models.TextChoices):
    EXPIRY_90 = "expiry_90", "انتهاء خلال 90 يوماً"
    EXPIRY_60 = "expiry_60", "انتهاء خلال 60 يوماً"
    EXPIRY_30 = "expiry_30", "انتهاء خلال 30 يوماً"
    RENEWAL_NOTICE = "renewal_notice", "آخر يوم للإشعار بعدم التجديد"
    UNSIGNED_APPROVED = "unsigned_approved", "معتمد بدون توقيع"
    EXPIRED_STILL_ACTIVE = "expired_still_active", "منتهٍ وما زال نشطاً"
    SHELF_PRICE_DEVIATION = "shelf_price_deviation", "انحراف سعر إيجار الأرفف"


class AlertSeverity(models.TextChoices):
    INFO = "info", "معلومة"
    WARNING = "warning", "تحذير"
    CRITICAL = "critical", "حرج"


class ApprovalDecision(models.TextChoices):
    PENDING = "pending", "معلق"
    APPROVED = "approved", "معتمد"
    REJECTED = "rejected", "مرفوض"
    ESCALATED = "escalated", "مصعّد"


class ApproverRole(models.TextChoices):
    DEPARTMENT_HEAD = "department_head", "رئيس القسم"
    CONTRACTS_MANAGER = "contracts_manager", "إدارة العقود"
    LEGAL = "legal", "الشؤون القانونية"


class Vendor(models.Model):
    vendor_number = models.CharField("رقم المورد", max_length=30, unique=True)
    legal_name = models.CharField("الاسم القانوني", max_length=200)
    trade_name = models.CharField("الاسم التجاري", max_length=200, blank=True)
    cr_number = models.CharField("السجل التجاري", max_length=40, blank=True)
    contact_name = models.CharField("جهة الاتصال", max_length=120, blank=True)
    phone = models.CharField("الهاتف", max_length=30, blank=True)
    email = models.EmailField("البريد", blank=True)
    is_active = models.BooleanField("نشط", default=True)

    class Meta:
        verbose_name = "مورد"
        verbose_name_plural = "الموردون"
        ordering = ["legal_name"]

    def __str__(self):
        return f"{self.vendor_number} — {self.legal_name}"


class ShelfRate(models.Model):
    """الأسعار المعيارية المعتمدة لأنواع الأرفف."""

    code = models.CharField("الرمز", max_length=40, unique=True)
    name = models.CharField("نوع الرف / الوحدة", max_length=120)
    unit = models.CharField("وحدة القياس", max_length=40, default="شهرياً")
    standard_price = models.DecimalField("السعر المعياري", max_digits=12, decimal_places=2)
    is_active = models.BooleanField("نشط", default=True)

    class Meta:
        verbose_name = "سعر رف معياري"
        verbose_name_plural = "أسعار الأرفف المعيارية"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} — {self.standard_price}"


class Contract(models.Model):
    HIGH_VALUE_THRESHOLD = Decimal("15000")

    contract_number = models.CharField("رقم العقد", max_length=40, unique=True, blank=True)
    contract_type = models.CharField("نوع العقد", max_length=20, choices=ContractType.choices)
    subtype = models.CharField("النوع الفرعي", max_length=30, choices=ContractSubtype.choices, blank=True)
    internal_classification = models.CharField("التصنيف الداخلي", max_length=160, blank=True)
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, related_name="contracts", verbose_name="المورد")
    department = models.ForeignKey(
        "accounts.Department",
        on_delete=models.PROTECT,
        related_name="contracts",
        verbose_name="القسم المسؤول",
    )
    start_date = models.DateField("تاريخ البدء")
    end_date = models.DateField("تاريخ الانتهاء")
    auto_renewal = models.BooleanField("تجديد تلقائي", default=False)
    notice_period_days = models.PositiveIntegerField("فترة الإشعار (يوم)", default=30)
    actual_value = models.DecimalField("القيمة الفعلية", max_digits=14, decimal_places=2)
    has_non_standard_terms = models.BooleanField("شروط غير معيارية", default=False)
    commercial_owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="owned_contracts",
        verbose_name="مسؤول العقد التجاري",
    )
    purchasing_manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="purchasing_managed_contracts",
        verbose_name="مدير المشتريات",
        null=True,
        blank=True,
    )
    status = models.CharField("الحالة", max_length=24, choices=ContractStatus.choices, default=ContractStatus.DRAFT)
    both_parties_signed = models.BooleanField("توقيع الطرفين مكتمل", default=False)
    signed_at = models.DateTimeField("تاريخ اكتمال التوقيع", null=True, blank=True)
    activated_at = models.DateTimeField("تاريخ التفعيل", null=True, blank=True)
    cancelled_at = models.DateTimeField("تاريخ الإلغاء", null=True, blank=True)
    cancellation_reason = models.TextField("سبب الإلغاء", blank=True)
    notes = models.TextField("ملاحظات", blank=True)
    shelf_rate = models.ForeignKey(
        ShelfRate,
        on_delete=models.PROTECT,
        related_name="contracts",
        verbose_name="نوع الرف المعياري",
        null=True,
        blank=True,
    )
    shelf_actual_price = models.DecimalField("سعر الرف الفعلي", max_digits=12, decimal_places=2, null=True, blank=True)
    manually_escalated = models.BooleanField("تصعيد يدوي لإدارة العقود", default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_contracts",
        verbose_name="أنشئ بواسطة",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "عقد"
        verbose_name_plural = "العقود"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "end_date"]),
            models.Index(fields=["contract_type", "status"]),
        ]
        permissions = [
            ("approve_as_head", "يمكنه الاعتماد كرئيس قسم"),
            ("approve_as_contracts_manager", "يمكنه الاعتماد كإدارة عقود"),
            ("legal_review_contract", "يمكنه المراجعة القانونية"),
        ]

    def __str__(self):
        return self.contract_number or f"مسودة-{self.pk}"

    def clean(self):
        if self.end_date and self.start_date and self.end_date <= self.start_date:
            raise ValidationError({"end_date": "تاريخ الانتهاء يجب أن يكون بعد تاريخ البدء."})
        if self.contract_type == ContractType.SUPPLY and self.subtype not in {
            ContractSubtype.FRESH,
            ContractSubtype.FOOD,
            ContractSubtype.NON_FOOD,
        }:
            raise ValidationError({"subtype": "عقود التوريد تتطلب نوعاً فرعياً: فريش / غذائي / لا غذائي."})
        if self.contract_type == ContractType.SERVICES and self.subtype and self.subtype != ContractSubtype.ACCOUNT_OPENING:
            raise ValidationError({"subtype": "لعقود الخدمات استخدم «فتح حساب» أو اترك النوع الفرعي فارغاً."})
        if self.auto_renewal and not self.notice_period_days:
            raise ValidationError({"notice_period_days": "فترة الإشعار إلزامية للعقود ذات التجديد التلقائي."})
        if self.contract_type == ContractType.SHELF_RENT and not self.shelf_rate_id:
            raise ValidationError({"shelf_rate": "عقود إيجار الأرفف تتطلب نوع الرف المعياري."})

    def save(self, *args, **kwargs):
        creating = self.pk is None
        if creating and not self.contract_number:
            super().save(*args, **kwargs)
            seq = Contract.objects.filter(vendor_id=self.vendor_id).count()
            self.contract_number = f"{self.vendor.vendor_number}-{seq:02d}"
            super().save(update_fields=["contract_number"])
            return
        super().save(*args, **kwargs)

    @property
    def days_remaining(self):
        if not self.end_date:
            return None
        return (self.end_date - timezone.localdate()).days

    @property
    def last_notice_date(self):
        if not self.auto_renewal or not self.end_date:
            return None
        return self.end_date - timedelta(days=self.notice_period_days or 0)

    @property
    def is_high_value(self):
        return self.actual_value > self.HIGH_VALUE_THRESHOLD

    @property
    def has_shelf_price_deviation(self):
        if self.contract_type != ContractType.SHELF_RENT or not self.shelf_rate_id:
            return False
        if self.shelf_actual_price is None:
            return False
        return self.shelf_actual_price != self.shelf_rate.standard_price

    @property
    def shelf_deviation_percent(self):
        if not self.has_shelf_price_deviation or not self.shelf_rate.standard_price:
            return Decimal("0")
        base = self.shelf_rate.standard_price
        return ((self.shelf_actual_price - base) / base) * Decimal("100")

    @property
    def is_standard_shelf_rent(self):
        return (
            self.contract_type == ContractType.SHELF_RENT
            and not self.has_shelf_price_deviation
            and not self.has_non_standard_terms
        )

    def required_approver_role(self):
        """مصفوفة الموافقات: حد 15,000 + إيجار معياري + انحراف سعر + شروط غير معيارية."""
        if self.has_non_standard_terms or self.manually_escalated:
            return ApproverRole.CONTRACTS_MANAGER
        if self.is_standard_shelf_rent:
            return ApproverRole.DEPARTMENT_HEAD
        if self.is_high_value:
            return ApproverRole.CONTRACTS_MANAGER
        return ApproverRole.DEPARTMENT_HEAD

    def required_approver_label(self):
        return ApproverRole(self.required_approver_role()).label

    def needs_legal_review(self):
        return self.has_non_standard_terms


class ContractTarget(models.Model):
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name="targets", verbose_name="العقد")
    title = models.CharField("وصف الهدف", max_length=200)
    target_value = models.DecimalField("قيمة الهدف", max_digits=14, decimal_places=2)
    discount_percent = models.DecimalField("نسبة الخصم %", max_digits=5, decimal_places=2)
    sort_order = models.PositiveSmallIntegerField("الترتيب", default=1)

    class Meta:
        verbose_name = "هدف / شريحة خصم"
        verbose_name_plural = "أهداف الخصم"
        ordering = ["sort_order", "id"]

    def __str__(self):
        return f"{self.title} ({self.discount_percent}%)"


class ContractAttachment(models.Model):
    class Kind(models.TextChoices):
        ORIGINAL = "original", "النسخة الأصلية"
        LEGAL_REVIEW = "legal_review", "نسخة المراجعة القانونية"
        SIGNED = "signed", "النسخة الموقعة"
        ADDENDUM = "addendum", "ملحق"
        RENEWAL_LETTER = "renewal_letter", "خطاب تجديد"
        TERMINATION_LETTER = "termination_letter", "خطاب إنهاء"
        OTHER = "other", "أخرى"

    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name="attachments", verbose_name="العقد")
    kind = models.CharField("النوع", max_length=24, choices=Kind.choices, default=Kind.ORIGINAL)
    file = models.FileField("الملف", upload_to="contracts/%Y/%m/")
    original_name = models.CharField("اسم الملف", max_length=255, blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name="رفع بواسطة")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "مرفق"
        verbose_name_plural = "المرفقات"
        ordering = ["-uploaded_at"]

    def __str__(self):
        return self.original_name or self.file.name


class ApprovalStep(models.Model):
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name="approval_steps", verbose_name="العقد")
    role = models.CharField("جهة الاعتماد", max_length=32, choices=ApproverRole.choices)
    sequence = models.PositiveSmallIntegerField("الترتيب", default=1)
    decision = models.CharField("القرار", max_length=16, choices=ApprovalDecision.choices, default=ApprovalDecision.PENDING)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name="المعتمد",
    )
    decided_at = models.DateTimeField("وقت القرار", null=True, blank=True)
    comment = models.TextField("تعليق", blank=True)

    class Meta:
        verbose_name = "خطوة موافقة"
        verbose_name_plural = "خطوات الموافقة"
        ordering = ["sequence", "id"]
        constraints = [
            models.UniqueConstraint(fields=["contract", "role", "sequence"], name="uniq_approval_step"),
        ]

    def __str__(self):
        return f"{self.contract} — {self.get_role_display()} ({self.get_decision_display()})"


class AuditLog(models.Model):
    """سجل تدقيق غير قابل للتعديل من الواجهة."""

    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name="audit_logs", verbose_name="العقد")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name="المنفّذ")
    action = models.CharField("الإجراء", max_length=80)
    from_status = models.CharField("من حالة", max_length=24, blank=True)
    to_status = models.CharField("إلى حالة", max_length=24, blank=True)
    details = models.JSONField("التفاصيل", default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "سجل تدقيق"
        verbose_name_plural = "سجل التدقيق"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.action}"

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("سجل التدقيق غير قابل للتعديل.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("سجل التدقيق غير قابل للحذف.")


class ContractAlert(models.Model):
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name="alerts", verbose_name="العقد")
    alert_type = models.CharField("نوع التنبيه", max_length=32, choices=AlertType.choices)
    severity = models.CharField("الحدة", max_length=12, choices=AlertSeverity.choices)
    message = models.CharField("الرسالة", max_length=255)
    is_open = models.BooleanField("مفتوح", default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "تنبيه"
        verbose_name_plural = "التنبيهات"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["contract", "alert_type"], name="uniq_contract_alert_type"),
        ]
        indexes = [
            models.Index(fields=["is_open", "severity"]),
        ]

    def __str__(self):
        return f"{self.contract} — {self.get_alert_type_display()}"
