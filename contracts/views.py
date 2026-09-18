from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Q, Sum
from django.http import FileResponse, Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.clickjacking import xframe_options_sameorigin

from .forms import (
    AttachmentForm,
    ContractForm,
    DecisionForm,
    EscalateForm,
    TargetFormSet,
    safe_original_name,
    validate_attachment_file,
)
from .models import (
    AlertSeverity,
    AlertType,
    ApprovalDecision,
    ApproverRole,
    Contract,
    ContractAlert,
    ContractAttachment,
    ContractStatus,
    ContractType,
    ShelfRate,
)
from .services import (
    WorkflowError,
    complete_legal_review,
    decide_approval,
    escalate_to_contracts_manager,
    mark_signed,
    refresh_all_alerts,
    remove_contract,
    submit_for_workflow,
    write_audit,
)
from .utils import amount_to_arabic_words


def _profile(user):
    return getattr(user, "profile", None)


def _assert_upload_kind(contract, profile, kind):
    if kind == ContractAttachment.Kind.LEGAL_REVIEW:
        if not (profile and profile.can_legal_review):
            raise ValidationError("رفع نسخة المراجعة القانونية مقصور على الشؤون القانونية.")
        if contract.status != ContractStatus.UNDER_REVIEW:
            raise ValidationError("نسخة المراجعة القانونية تُرفع أثناء المراجعة فقط.")
    elif kind == ContractAttachment.Kind.SIGNED:
        if not (profile and profile.is_contracts_staff):
            raise ValidationError("رفع النسخة الموقعة مقصور على قسم العقود.")
        if contract.status != ContractStatus.PENDING_SIGNATURE:
            raise ValidationError("النسخة الموقعة تُرفع بعد الاعتماد فقط.")
    elif not (profile and (profile.is_contracts_staff or (profile.can_legal_review and contract.status == ContractStatus.UNDER_REVIEW))):
        raise ValidationError("رفع المرفقات غير مسموح لدورك.")


def _apply_deviation_flag(contract):
    if contract.contract_type == ContractType.SHELF_RENT and contract.has_shelf_price_deviation:
        contract.has_non_standard_terms = True


@login_required
def contract_list(request):
    refresh_all_alerts()
    qs = Contract.objects.select_related("vendor", "department", "commercial_owner")
    status = request.GET.get("status")
    ctype = request.GET.get("type")
    q = request.GET.get("q", "").strip()
    if status:
        qs = qs.filter(status=status)
    if ctype:
        qs = qs.filter(contract_type=ctype)
    if q:
        qs = qs.filter(
            Q(contract_number__icontains=q)
            | Q(vendor__legal_name__icontains=q)
            | Q(vendor__trade_name__icontains=q)
            | Q(vendor__vendor_number__icontains=q)
        )
    all_contracts = Contract.objects.all()
    action_needed = all_contracts.filter(
        status__in=[ContractStatus.PENDING_APPROVAL, ContractStatus.UNDER_REVIEW, ContractStatus.PENDING_SIGNATURE]
    ).count()
    return render(
        request,
        "contracts/list.html",
        {
            "contracts": qs,
            "status_choices": ContractStatus.choices,
            "type_choices": ContractType.choices,
            "selected_status": status,
            "selected_type": ctype,
            "q": q,
            "nav": "register",
            "kpi_total": all_contracts.count(),
            "kpi_active": all_contracts.filter(status=ContractStatus.ACTIVE).count(),
            "kpi_action": action_needed,
            "kpi_value": all_contracts.aggregate(total=Sum("actual_value"))["total"] or 0,
            "can_manage_contracts": bool(_profile(request.user) and _profile(request.user).is_contracts_staff),
        },
    )


@login_required
def contract_detail(request, pk):
    contract = get_object_or_404(
        Contract.objects.select_related(
            "vendor", "department", "shelf_rate", "commercial_owner", "created_by", "purchasing_manager"
        ),
        pk=pk,
    )
    profile = _profile(request.user)
    pending_step = contract.approval_steps.filter(decision=ApprovalDecision.PENDING).order_by("sequence").first()
    can_submit = contract.status == ContractStatus.DRAFT and profile and profile.is_contracts_staff
    can_legal = contract.status == ContractStatus.UNDER_REVIEW and profile and profile.can_legal_review
    can_approve = False
    if pending_step and profile:
        if pending_step.role == ApproverRole.DEPARTMENT_HEAD and profile.can_approve_as_head:
            can_approve = True
        if pending_step.role == ApproverRole.CONTRACTS_MANAGER and profile.can_approve_as_contracts_manager:
            can_approve = True
    can_sign = contract.status == ContractStatus.PENDING_SIGNATURE and profile and profile.is_contracts_staff
    can_escalate = (
        profile
        and (profile.is_contracts_staff or profile.is_purchasing_staff)
        and contract.status in {ContractStatus.DRAFT, ContractStatus.PENDING_APPROVAL}
        and not contract.manually_escalated
    )
    has_original = contract.attachments.filter(kind=ContractAttachment.Kind.ORIGINAL).exists()
    has_legal_review = contract.attachments.filter(kind=ContractAttachment.Kind.LEGAL_REVIEW).exists()
    attachment_form = AttachmentForm()
    if contract.status == ContractStatus.DRAFT:
        attachment_form.fields["kind"].initial = ContractAttachment.Kind.ORIGINAL
    elif contract.status == ContractStatus.UNDER_REVIEW:
        attachment_form.fields["kind"].initial = ContractAttachment.Kind.LEGAL_REVIEW
    elif contract.status == ContractStatus.PENDING_SIGNATURE:
        attachment_form.fields["kind"].initial = ContractAttachment.Kind.SIGNED
    return render(
        request,
        "contracts/detail.html",
        {
            "contract": contract,
            "pending_step": pending_step,
            "can_submit": can_submit,
            "can_legal": can_legal,
            "can_approve": can_approve,
            "can_sign": can_sign,
            "can_escalate": can_escalate,
            "has_original": has_original,
            "has_legal_review": has_legal_review,
            "decision_form": DecisionForm(),
            "escalate_form": EscalateForm(),
            "attachment_form": attachment_form,
            "nav": "register",
        },
    )


@login_required
@xframe_options_sameorigin
def contract_print(request, pk):
    contract = get_object_or_404(
        Contract.objects.select_related(
            "vendor",
            "department",
            "shelf_rate",
            "commercial_owner",
            "created_by",
            "purchasing_manager",
        ).prefetch_related("targets"),
        pk=pk,
    )
    return render(
        request,
        "contracts/print.html",
        {
            "contract": contract,
            "organization": getattr(settings, "ORGANIZATION", {}),
            "issued_at": timezone.localdate(),
            "amount_words": amount_to_arabic_words(contract.actual_value),
        },
    )


@login_required
def contract_create(request):
    profile = _profile(request.user)
    if not (profile and profile.is_contracts_staff):
        return HttpResponseForbidden("إنشاء العقود مقصور على قسم العقود.")
    form = ContractForm(request.POST or None)
    formset = TargetFormSet(request.POST or None)
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        contract = form.save(commit=False)
        contract.created_by = request.user
        contract.status = ContractStatus.DRAFT
        contract.save()
        form.save_m2m()
        _apply_deviation_flag(contract)
        contract.save()
        formset.instance = contract
        formset.save()
        write_audit(contract, request.user, "إنشاء مسودة عقد", to_status=ContractStatus.DRAFT)
        messages.success(request, f"تم إنشاء العقد {contract.contract_number} كمسودة.")
        return redirect("contracts:detail", pk=contract.pk)
    return render(
        request,
        "contracts/form.html",
        {"form": form, "formset": formset, "nav": "create", "title": "إنشاء عقد تجاري جديد"},
    )


@login_required
def contract_edit(request, pk):
    contract = get_object_or_404(Contract, pk=pk)
    profile = _profile(request.user)
    if contract.status != ContractStatus.DRAFT or not (profile and profile.is_contracts_staff):
        messages.error(request, "يمكن تعديل المسودات فقط ومن قبل قسم العقود.")
        return redirect("contracts:detail", pk=pk)
    form = ContractForm(request.POST or None, instance=contract)
    formset = TargetFormSet(request.POST or None, instance=contract)
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        contract = form.save(commit=False)
        _apply_deviation_flag(contract)
        contract.save()
        formset.save()
        write_audit(contract, request.user, "تعديل مسودة العقد")
        messages.success(request, "تم حفظ التعديلات.")
        return redirect("contracts:detail", pk=pk)
    return render(
        request,
        "contracts/form.html",
        {"form": form, "formset": formset, "contract": contract, "nav": "register", "title": "تعديل العقد"},
    )


def _run_workflow(request, pk, fn, success_msg):
    contract = get_object_or_404(Contract, pk=pk)
    try:
        fn(contract, request.user)
        messages.success(request, success_msg)
    except WorkflowError as exc:
        messages.error(request, str(exc))
    return redirect("contracts:detail", pk=pk)


@login_required
def contract_submit(request, pk):
    if request.method != "POST":
        return redirect("contracts:detail", pk=pk)
    return _run_workflow(request, pk, submit_for_workflow, "تم إرسال العقد في مسار العمل.")


@login_required
def contract_legal(request, pk):
    if request.method != "POST":
        return redirect("contracts:detail", pk=pk)
    contract = get_object_or_404(Contract, pk=pk)
    profile = _profile(request.user)
    if not (profile and profile.can_legal_review):
        return HttpResponseForbidden("المراجعة القانونية مقصورة على الشؤون القانونية.")
    form = DecisionForm(request.POST)
    form.is_valid()
    approved = request.POST.get("decision") == "approve"
    comment = form.cleaned_data.get("comment", "") if form.is_valid() else ""
    upload = request.FILES.get("file")
    if upload:
        try:
            validate_attachment_file(upload)
            _assert_upload_kind(contract, profile, ContractAttachment.Kind.LEGAL_REVIEW)
        except ValidationError as exc:
            messages.error(request, exc.messages[0] if getattr(exc, "messages", None) else "تعذر رفع الملف.")
            return redirect("contracts:detail", pk=pk)
        att = ContractAttachment.objects.create(
            contract=contract,
            kind=ContractAttachment.Kind.LEGAL_REVIEW,
            file=upload,
            original_name=safe_original_name(upload.name),
            uploaded_by=request.user,
        )
        write_audit(contract, request.user, "رفع مرفق", details={"kind": att.kind, "name": att.original_name})
    return _run_workflow(
        request,
        pk,
        lambda c, u: complete_legal_review(c, u, approved, comment),
        "تم تسجيل قرار المراجعة القانونية.",
    )


@login_required
def contract_approve(request, pk):
    if request.method != "POST":
        return redirect("contracts:detail", pk=pk)
    form = DecisionForm(request.POST)
    form.is_valid()
    approved = request.POST.get("decision") == "approve"
    comment = form.cleaned_data.get("comment", "") if form.is_valid() else ""
    return _run_workflow(
        request,
        pk,
        lambda c, u: decide_approval(c, u, approved, comment),
        "تم تسجيل قرار الاعتماد.",
    )


@login_required
def contract_escalate(request, pk):
    if request.method != "POST":
        return redirect("contracts:detail", pk=pk)
    form = EscalateForm(request.POST)
    if not form.is_valid():
        messages.error(request, "أدخل سبب التصعيد.")
        return redirect("contracts:detail", pk=pk)
    reason = form.cleaned_data["reason"]
    return _run_workflow(
        request,
        pk,
        lambda c, u: escalate_to_contracts_manager(c, u, reason),
        "تم تصعيد العقد لإدارة العقود.",
    )


@login_required
def contract_upload(request, pk):
    contract = get_object_or_404(Contract, pk=pk)
    if request.method != "POST":
        return redirect("contracts:detail", pk=pk)
    profile = _profile(request.user)
    can_upload = bool(profile and profile.is_contracts_staff)
    if contract.status == ContractStatus.UNDER_REVIEW and profile and profile.can_legal_review:
        can_upload = True
    if not can_upload:
        return HttpResponseForbidden("رفع المرفقات مقصور على الأدوار المخوّلة.")
    form = AttachmentForm(request.POST, request.FILES)
    if form.is_valid():
        try:
            _assert_upload_kind(contract, profile, form.cleaned_data["kind"])
        except ValidationError as exc:
            messages.error(request, exc.messages[0] if getattr(exc, "messages", None) else "نوع المرفق غير مسموح.")
            return redirect("contracts:detail", pk=pk)
        att = form.save(commit=False)
        att.contract = contract
        att.uploaded_by = request.user
        att.original_name = safe_original_name(att.file.name)
        att.save()
        write_audit(contract, request.user, "رفع مرفق", details={"kind": att.kind, "name": att.original_name})
        if att.kind == ContractAttachment.Kind.SIGNED and contract.status == ContractStatus.PENDING_SIGNATURE:
            try:
                mark_signed(contract, request.user, attachment=att)
                messages.success(request, "تم رفع النسخة الموقعة وتثبيت توقيع الطرفين.")
            except WorkflowError as exc:
                messages.error(request, str(exc))
        else:
            messages.success(request, "تم رفع المرفق.")
    else:
        messages.error(request, "تعذر رفع الملف. تحقق من النوع والحجم.")
    return redirect("contracts:detail", pk=pk)


@login_required
def contract_delete(request, pk):
    contract = get_object_or_404(Contract, pk=pk)
    if request.method != "POST":
        return redirect("contracts:list")
    number = contract.contract_number
    try:
        result = remove_contract(contract, request.user, reason=request.POST.get("reason", ""))
    except WorkflowError as exc:
        messages.error(request, str(exc))
        return redirect("contracts:list")
    if result == "deleted":
        messages.success(request, f"تم حذف المسودة {number} نهائياً.")
    else:
        messages.success(request, f"تم إلغاء العقد {number} مع الإبقاء على السجل.")
    return redirect("contracts:list")


@login_required
def attachment_download(request, pk, attachment_id):
    attachment = get_object_or_404(ContractAttachment, pk=attachment_id, contract_id=pk)
    if not attachment.file:
        raise Http404()
    try:
        handle = attachment.file.open("rb")
    except FileNotFoundError:
        raise Http404()
    filename = safe_original_name(attachment.original_name or attachment.file.name)
    return FileResponse(handle, as_attachment=True, filename=filename)


@login_required
def approval_queue(request):
    profile = _profile(request.user)
    qs = Contract.objects.filter(status=ContractStatus.PENDING_APPROVAL).select_related("vendor", "department")
    if profile and profile.can_approve_as_head and not profile.can_approve_as_contracts_manager:
        qs = qs.filter(approval_steps__role=ApproverRole.DEPARTMENT_HEAD, approval_steps__decision=ApprovalDecision.PENDING)
    elif profile and profile.can_approve_as_contracts_manager and not profile.can_approve_as_head:
        qs = qs.filter(approval_steps__role=ApproverRole.CONTRACTS_MANAGER, approval_steps__decision=ApprovalDecision.PENDING)
    return render(
        request,
        "contracts/queue.html",
        {
            "contracts": qs.distinct(),
            "nav": "approvals",
            "title": "طابور الموافقات",
            "subtitle": "القرارات المعلقة حسب مصفوفة الصلاحيات",
        },
    )


@login_required
def legal_queue(request):
    profile = _profile(request.user)
    if not (profile and (profile.can_legal_review or profile.is_contracts_staff)):
        return HttpResponseForbidden("طابور المراجعة القانونية غير متاح لدورك.")
    qs = Contract.objects.filter(status=ContractStatus.UNDER_REVIEW).select_related("vendor", "department")
    return render(
        request,
        "contracts/queue.html",
        {
            "contracts": qs,
            "nav": "legal",
            "title": "المراجعة القانونية",
            "subtitle": "عقود ذات شروط غير معيارية بانتظار الرأي القانوني",
        },
    )


@login_required
def alerts_list(request):
    refresh_all_alerts()
    qs = ContractAlert.objects.filter(is_open=True).select_related("contract", "contract__vendor")
    severity = request.GET.get("severity")
    if severity:
        qs = qs.filter(severity=severity)
    return render(
        request,
        "contracts/alerts.html",
        {
            "alerts": qs,
            "nav": "alerts",
            "alert_types": AlertType.choices,
            "severity_choices": AlertSeverity.choices,
            "selected_severity": severity,
        },
    )


@login_required
def shelf_rates(request):
    return render(
        request,
        "contracts/shelf_rates.html",
        {"rates": ShelfRate.objects.filter(is_active=True), "nav": "rates"},
    )
