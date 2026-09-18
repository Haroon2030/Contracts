from datetime import timedelta

from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from .models import (
    AlertSeverity,
    AlertType,
    ApprovalDecision,
    ApproverRole,
    ApprovalStep,
    AuditLog,
    Contract,
    ContractAlert,
    ContractAttachment,
    ContractStatus,
)


ALLOWED_TRANSITIONS = {
    ContractStatus.DRAFT: {ContractStatus.UNDER_REVIEW, ContractStatus.PENDING_APPROVAL, ContractStatus.CANCELLED},
    ContractStatus.UNDER_REVIEW: {ContractStatus.PENDING_APPROVAL, ContractStatus.DRAFT, ContractStatus.CANCELLED},
    ContractStatus.PENDING_APPROVAL: {ContractStatus.PENDING_SIGNATURE, ContractStatus.DRAFT, ContractStatus.CANCELLED},
    ContractStatus.PENDING_SIGNATURE: {ContractStatus.ACTIVE, ContractStatus.CANCELLED},
    ContractStatus.ACTIVE: {ContractStatus.EXPIRED, ContractStatus.CANCELLED},
    ContractStatus.EXPIRED: set(),
    ContractStatus.CANCELLED: set(),
}


class WorkflowError(Exception):
    pass


def pending_approval_step(contract):
    steps = [step for step in contract.approval_steps.all() if step.decision == ApprovalDecision.PENDING]
    steps.sort(key=lambda step: step.sequence)
    return steps[0] if steps else None


def row_action(contract, user):
    """الإجراء التالي الظاهر في الجداول حسب الحالة وصلاحية المستخدم."""
    profile = getattr(user, "profile", None)
    detail = reverse("contracts:detail", args=[contract.pk])
    if contract.status == ContractStatus.DRAFT and profile and profile.is_contracts_staff:
        return {"label": "تعديل", "url": reverse("contracts:edit", args=[contract.pk]), "primary": True}
    if contract.status == ContractStatus.UNDER_REVIEW and profile and profile.can_legal_review:
        return {"label": "مراجعة قانونية", "url": detail, "primary": True}
    if contract.status == ContractStatus.PENDING_APPROVAL:
        step = pending_approval_step(contract)
        can_approve = False
        if step and profile:
            if step.role == ApproverRole.DEPARTMENT_HEAD and profile.can_approve_as_head:
                can_approve = True
            if step.role == ApproverRole.CONTRACTS_MANAGER and profile.can_approve_as_contracts_manager:
                can_approve = True
        if can_approve:
            return {"label": "اعتماد", "url": detail, "primary": True}
        return {"label": "عرض التفاصيل", "url": detail, "primary": False}
    if (
        contract.status == ContractStatus.PENDING_SIGNATURE
        and profile
        and profile.is_contracts_staff
        and not contract.both_parties_signed
    ):
        return {"label": "تثبيت التوقيع", "url": detail, "primary": True}
    return {"label": "عرض التفاصيل", "url": detail, "primary": False}


def remove_contract(contract, actor, reason=""):
    """حذف المسودات نهائياً، وإلغاء العقود الجارية مع الإبقاء على السجل."""
    profile = getattr(actor, "profile", None)
    if not (profile and profile.is_contracts_staff):
        raise WorkflowError("حذف العقود مقصور على قسم العقود.")
    if contract.status == ContractStatus.DRAFT:
        contract.delete()
        return "deleted"
    if contract.status == ContractStatus.CANCELLED:
        raise WorkflowError("العقد ملغى مسبقاً.")
    if contract.status == ContractStatus.EXPIRED:
        raise WorkflowError("لا يمكن حذف عقد منتهٍ.")
    contract.cancelled_at = timezone.now()
    contract.cancellation_reason = reason or "حذف من سجل العقود"
    contract.save(update_fields=["cancelled_at", "cancellation_reason", "updated_at"])
    transition(contract, ContractStatus.CANCELLED, actor, "إلغاء العقد", {"reason": contract.cancellation_reason})
    return "cancelled"


def write_audit(contract, actor, action, from_status="", to_status="", details=None):
    AuditLog.objects.create(
        contract=contract,
        actor=actor,
        action=action,
        from_status=from_status,
        to_status=to_status,
        details=details or {},
    )


def transition(contract, to_status, actor, action, details=None):
    allowed = ALLOWED_TRANSITIONS.get(contract.status, set())
    if to_status not in allowed:
        raise WorkflowError(f"لا يمكن الانتقال من {contract.get_status_display()} إلى الحالة المطلوبة.")
    from_status = contract.status
    contract.status = to_status
    contract.save(update_fields=["status", "updated_at"])
    write_audit(contract, actor, action, from_status, to_status, details)
    return contract


def _has_attachment(contract, kind):
    return contract.attachments.filter(kind=kind).exists()


@transaction.atomic
def submit_for_workflow(contract, actor):
    profile = getattr(actor, "profile", None)
    if not (profile and profile.is_contracts_staff):
        raise WorkflowError("إرسال العقود مقصور على قسم العقود.")
    if contract.status != ContractStatus.DRAFT:
        raise WorkflowError("لا يمكن إرسال العقد إلا من حالة المسودة.")
    if not _has_attachment(contract, ContractAttachment.Kind.ORIGINAL):
        raise WorkflowError("ارفق النسخة الأصلية أولاً ثم أرسل العقد في مسار العمل.")
    if contract.has_shelf_price_deviation:
        contract.has_non_standard_terms = True
        contract.save(update_fields=["has_non_standard_terms", "updated_at"])
        _upsert_alert(
            contract,
            AlertType.SHELF_PRICE_DEVIATION,
            AlertSeverity.WARNING,
            "السعر الفعلي لإيجار الأرفف يختلف عن السعر المعياري المعتمد.",
        )
    if contract.needs_legal_review():
        return transition(contract, ContractStatus.UNDER_REVIEW, actor, "إرسال للمراجعة القانونية")
    _create_approval_steps(contract)
    return transition(contract, ContractStatus.PENDING_APPROVAL, actor, "إرسال للاعتماد")


@transaction.atomic
def complete_legal_review(contract, actor, approved, comment=""):
    profile = getattr(actor, "profile", None)
    if not (profile and profile.can_legal_review):
        raise WorkflowError("المراجعة القانونية مقصورة على الشؤون القانونية.")
    if contract.status != ContractStatus.UNDER_REVIEW:
        raise WorkflowError("العقد ليس في قائمة المراجعة القانونية.")
    if approved and not _has_attachment(contract, ContractAttachment.Kind.LEGAL_REVIEW):
        raise WorkflowError("راجع النسخة الأصلية ثم أرفق نسخة المراجعة القانونية قبل الاعتماد.")
    write_audit(
        contract,
        actor,
        "مراجعة قانونية — اعتماد" if approved else "مراجعة قانونية — إعادة للمسودة",
        contract.status,
        details={"comment": comment},
    )
    if not approved:
        return transition(contract, ContractStatus.DRAFT, actor, "إعادة للمسودة بعد المراجعة القانونية", {"comment": comment})
    _create_approval_steps(contract)
    return transition(contract, ContractStatus.PENDING_APPROVAL, actor, "اعتماد قانوني ثم إحالة للموافقة")


def _create_approval_steps(contract):
    contract.approval_steps.all().delete()
    role = contract.required_approver_role()
    ApprovalStep.objects.create(contract=contract, role=role, sequence=1)


@transaction.atomic
def decide_approval(contract, actor, approved, comment=""):
    if contract.status != ContractStatus.PENDING_APPROVAL:
        raise WorkflowError("العقد ليس بانتظار الموافقة.")
    step = contract.approval_steps.filter(decision=ApprovalDecision.PENDING).order_by("sequence").first()
    if not step:
        raise WorkflowError("لا توجد خطوة موافقة معلّقة.")
    profile = getattr(actor, "profile", None)
    if step.role == ApproverRole.DEPARTMENT_HEAD and not (profile and profile.can_approve_as_head):
        raise WorkflowError("هذه الخطوة تتطلب اعتماد رئيس القسم.")
    if step.role == ApproverRole.CONTRACTS_MANAGER and not (profile and profile.can_approve_as_contracts_manager):
        raise WorkflowError("هذه الخطوة تتطلب اعتماد إدارة العقود.")
    step.decision = ApprovalDecision.APPROVED if approved else ApprovalDecision.REJECTED
    step.decided_by = actor
    step.decided_at = timezone.now()
    step.comment = comment
    step.save()
    write_audit(
        contract,
        actor,
        "اعتماد العقد" if approved else "رفض العقد",
        contract.status,
        details={"role": step.role, "comment": comment},
    )
    if not approved:
        return transition(contract, ContractStatus.DRAFT, actor, "رفض وإعادة للمسودة", {"comment": comment})
    remaining = contract.approval_steps.filter(decision=ApprovalDecision.PENDING).exists()
    if remaining:
        return contract
    return transition(contract, ContractStatus.PENDING_SIGNATURE, actor, "اكتمال الاعتماد — بانتظار التوقيع")


@transaction.atomic
def escalate_to_contracts_manager(contract, actor, reason):
    profile = getattr(actor, "profile", None)
    if not (profile and (profile.is_contracts_staff or profile.is_purchasing_staff)):
        raise WorkflowError("التصعيد مقصور على العقود أو المشتريات.")
    if contract.status not in {ContractStatus.DRAFT, ContractStatus.PENDING_APPROVAL}:
        raise WorkflowError("لا يمكن التصعيد في الحالة الحالية.")
    contract.manually_escalated = True
    contract.save(update_fields=["manually_escalated", "updated_at"])
    if contract.status == ContractStatus.PENDING_APPROVAL:
        contract.approval_steps.filter(decision=ApprovalDecision.PENDING).delete()
        ApprovalStep.objects.get_or_create(
            contract=contract,
            role=ApproverRole.CONTRACTS_MANAGER,
            sequence=99,
            defaults={"decision": ApprovalDecision.PENDING},
        )
    write_audit(contract, actor, "تصعيد يدوي لإدارة العقود", contract.status, details={"reason": reason})
    return contract


@transaction.atomic
def mark_signed(contract, actor, attachment=None):
    profile = getattr(actor, "profile", None)
    if not (profile and profile.is_contracts_staff):
        raise WorkflowError("تثبيت التوقيع مقصور على قسم العقود.")
    if contract.status != ContractStatus.PENDING_SIGNATURE:
        raise WorkflowError("لا يمكن تثبيت التوقيع إلا في حالة بانتظار التوقيع.")
    if attachment is None:
        has_signed = contract.attachments.filter(kind=ContractAttachment.Kind.SIGNED).exists()
        if not has_signed:
            raise WorkflowError("يجب رفع النسخة الموقعة قبل تحديث حالة التوقيع.")
    contract.both_parties_signed = True
    contract.signed_at = timezone.now()
    contract.save(update_fields=["both_parties_signed", "signed_at", "updated_at"])
    write_audit(contract, actor, "اكتمال توقيع الطرفين", contract.status)
    refresh_activation(contract, actor)
    return contract


def refresh_activation(contract, actor=None):
    """يتحول إلى نشط في تاريخ بدء النفاذ بعد اكتمال التوقيع، وليس بتاريخ التوقيع وحده."""
    today = timezone.localdate()
    if (
        contract.status == ContractStatus.PENDING_SIGNATURE
        and contract.both_parties_signed
        and contract.start_date <= today
    ):
        contract.activated_at = timezone.now()
        contract.save(update_fields=["activated_at", "updated_at"])
        if actor:
            transition(contract, ContractStatus.ACTIVE, actor, "تفعيل العقد في تاريخ النفاذ")
        else:
            from django.contrib.auth import get_user_model

            system = get_user_model().objects.filter(is_superuser=True).first()
            if system:
                transition(contract, ContractStatus.ACTIVE, system, "تفعيل تلقائي في تاريخ النفاذ")
    if contract.status == ContractStatus.ACTIVE and contract.end_date < today:
        _upsert_alert(
            contract,
            AlertType.EXPIRED_STILL_ACTIVE,
            AlertSeverity.CRITICAL,
            "العقد تجاوز تاريخ انتهائه وما زالت حالته نشطاً.",
        )


def _upsert_alert(contract, alert_type, severity, message):
    alert, _created = ContractAlert.objects.update_or_create(
        contract=contract,
        alert_type=alert_type,
        defaults={"severity": severity, "message": message, "is_open": True, "resolved_at": None},
    )
    return alert


def refresh_all_alerts():
    """حسابات يومية للتنبيهات — لا تعتمد على إدخال يدوي."""
    today = timezone.localdate()
    open_keep = set()

    for contract in Contract.objects.select_related("vendor", "shelf_rate"):
        if contract.status == ContractStatus.CANCELLED:
            contract.alerts.filter(is_open=True).update(is_open=False, resolved_at=timezone.now())
            continue

        days = contract.days_remaining
        if contract.status in {ContractStatus.ACTIVE, ContractStatus.PENDING_SIGNATURE} and days is not None:
            if 0 <= days <= 30:
                _upsert_alert(contract, AlertType.EXPIRY_30, AlertSeverity.CRITICAL, f"متبقٍ {days} يوماً على انتهاء العقد.")
                open_keep.add((contract.pk, AlertType.EXPIRY_30))
            elif 30 < days <= 60:
                _upsert_alert(contract, AlertType.EXPIRY_60, AlertSeverity.WARNING, f"متبقٍ {days} يوماً على انتهاء العقد.")
                open_keep.add((contract.pk, AlertType.EXPIRY_60))
            elif 60 < days <= 90:
                _upsert_alert(contract, AlertType.EXPIRY_90, AlertSeverity.INFO, f"متبقٍ {days} يوماً على انتهاء العقد.")
                open_keep.add((contract.pk, AlertType.EXPIRY_90))

        notice = contract.last_notice_date
        if contract.auto_renewal and notice and contract.status == ContractStatus.ACTIVE:
            if today <= notice <= today + timedelta(days=14) or (notice <= today < contract.end_date):
                _upsert_alert(
                    contract,
                    AlertType.RENEWAL_NOTICE,
                    AlertSeverity.WARNING,
                    f"آخر يوم للإشعار بعدم التجديد: {notice:%Y-%m-%d}.",
                )
                open_keep.add((contract.pk, AlertType.RENEWAL_NOTICE))

        if contract.status == ContractStatus.PENDING_SIGNATURE and not contract.both_parties_signed:
            _upsert_alert(
                contract,
                AlertType.UNSIGNED_APPROVED,
                AlertSeverity.WARNING,
                "العقد معتمد ولم يكتمل توقيع الطرفين.",
            )
            open_keep.add((contract.pk, AlertType.UNSIGNED_APPROVED))

        if contract.status == ContractStatus.ACTIVE and contract.end_date < today:
            _upsert_alert(
                contract,
                AlertType.EXPIRED_STILL_ACTIVE,
                AlertSeverity.CRITICAL,
                "خطأ إداري: العقد منتهٍ وحالته ما زالت نشطاً.",
            )
            open_keep.add((contract.pk, AlertType.EXPIRED_STILL_ACTIVE))

        if contract.has_shelf_price_deviation:
            _upsert_alert(
                contract,
                AlertType.SHELF_PRICE_DEVIATION,
                AlertSeverity.WARNING,
                "فرق بين السعر الفعلي لإيجار الأرفف والسعر المعياري.",
            )
            open_keep.add((contract.pk, AlertType.SHELF_PRICE_DEVIATION))

        refresh_activation(contract)

    auto_types = {
        AlertType.EXPIRY_90,
        AlertType.EXPIRY_60,
        AlertType.EXPIRY_30,
        AlertType.RENEWAL_NOTICE,
        AlertType.UNSIGNED_APPROVED,
        AlertType.EXPIRED_STILL_ACTIVE,
    }
    stale = ContractAlert.objects.filter(is_open=True, alert_type__in=auto_types)
    for alert in stale:
        if (alert.contract_id, alert.alert_type) not in open_keep:
            alert.is_open = False
            alert.resolved_at = timezone.now()
            alert.save(update_fields=["is_open", "resolved_at"])
