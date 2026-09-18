from pathlib import Path
import re

from django import forms
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory

from .models import Contract, ContractAttachment, ContractTarget, ContractType

ALLOWED_ATTACHMENT_EXTS = {".pdf", ".doc", ".docx", ".png", ".jpg", ".jpeg", ".xlsx", ".xls"}
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024


def safe_original_name(name):
    base = Path(name or "").name
    cleaned = re.sub(r"[^\w.\-()\u0600-\u06FF ]+", "_", base).strip("._ ")[:180]
    return cleaned or "file"


def validate_attachment_file(uploaded):
    name = getattr(uploaded, "name", "") or ""
    ext = Path(name).suffix.lower()
    if ext not in ALLOWED_ATTACHMENT_EXTS:
        raise ValidationError("يُسمح بملفات PDF وWord وExcel والصور فقط.")
    size = getattr(uploaded, "size", 0) or 0
    if size > MAX_ATTACHMENT_BYTES:
        raise ValidationError("حجم الملف يتجاوز 10 ميغابايت.")
    header = b""
    if hasattr(uploaded, "read"):
        pos = uploaded.tell() if hasattr(uploaded, "tell") else 0
        header = uploaded.read(8) or b""
        if hasattr(uploaded, "seek"):
            uploaded.seek(pos)
    if ext == ".pdf" and not header.startswith(b"%PDF"):
        raise ValidationError("ملف PDF غير صالح.")
    if ext == ".png" and not header.startswith(b"\x89PNG"):
        raise ValidationError("ملف الصورة غير صالح.")
    if ext in {".jpg", ".jpeg"} and not header.startswith(b"\xff\xd8\xff"):
        raise ValidationError("ملف الصورة غير صالح.")
    if ext in {".docx", ".xlsx"} and not header.startswith(b"PK"):
        raise ValidationError("ملف Office غير صالح.")
    if ext in {".doc", ".xls"} and not header.startswith(b"\xd0\xcf\x11\xe0"):
        raise ValidationError("ملف Office غير صالح.")


INPUT = (
    "w-full px-3.5 py-2.5 rounded-xl border border-slate-200 bg-slate-50/50 hover:bg-white "
    "text-xs font-bold text-slate-800 focus:bg-white focus:outline-none focus:ring-2 "
    "focus:ring-teal/30 focus:border-teal transition"
)
CHECK = "rounded border-slate-300 text-teal focus:ring-teal"


class ContractForm(forms.ModelForm):
    class Meta:
        model = Contract
        fields = [
            "contract_type",
            "subtype",
            "internal_classification",
            "vendor",
            "department",
            "start_date",
            "end_date",
            "auto_renewal",
            "notice_period_days",
            "actual_value",
            "has_non_standard_terms",
            "commercial_owner",
            "purchasing_manager",
            "notes",
            "shelf_rate",
            "shelf_actual_price",
        ]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date", "lang": "ar"}),
            "end_date": forms.DateInput(attrs={"type": "date", "lang": "ar"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
            "internal_classification": forms.TextInput(attrs={"placeholder": "مثال: تأجير رؤوس ممرات"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if name in {"auto_renewal", "has_non_standard_terms"}:
                field.widget.attrs["class"] = CHECK
            else:
                field.widget.attrs["class"] = INPUT
        for name in ("commercial_owner", "purchasing_manager"):
            self.fields[name].label_from_instance = lambda user: user.get_full_name() or user.username

    def clean(self):
        cleaned = super().clean()
        contract_type = cleaned.get("contract_type")
        if cleaned.get("auto_renewal") and not cleaned.get("notice_period_days"):
            self.add_error("notice_period_days", "فترة الإشعار إلزامية عند التجديد التلقائي.")
        if contract_type == ContractType.SHELF_RENT:
            if not cleaned.get("shelf_rate"):
                self.add_error("shelf_rate", "حدد نوع الرف المعياري.")
            if cleaned.get("shelf_actual_price") is None:
                self.add_error("shelf_actual_price", "أدخل السعر الفعلي لإيجار الأرفف.")
        return cleaned


class AttachmentForm(forms.ModelForm):
    class Meta:
        model = ContractAttachment
        fields = ["kind", "file"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.label_suffix = ""
        self.fields["kind"].widget.attrs["class"] = INPUT
        self.fields["file"].widget.attrs["class"] = INPUT
        self.fields["file"].help_text = "PDF أو Word أو صورة، حتى 10 ميجا."

    def clean_file(self):
        uploaded = self.cleaned_data.get("file")
        if uploaded:
            validate_attachment_file(uploaded)
        return uploaded


class DecisionForm(forms.Form):
    comment = forms.CharField(
        label="التعليق",
        required=False,
        max_length=2000,
        widget=forms.Textarea(attrs={"rows": 3, "class": INPUT, "placeholder": "ملاحظة اختيارية على القرار"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.label_suffix = ""


class EscalateForm(forms.Form):
    reason = forms.CharField(
        label="سبب التصعيد التجاري",
        max_length=2000,
        widget=forms.Textarea(attrs={"rows": 3, "class": INPUT, "placeholder": "سبب إحالة العقد لإدارة العقود"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.label_suffix = ""


TargetFormSet = inlineformset_factory(
    Contract,
    ContractTarget,
    fields=["title", "target_value", "discount_percent", "sort_order"],
    extra=2,
    can_delete=True,
    widgets={
        "title": forms.TextInput(attrs={"class": INPUT, "placeholder": "وصف الشريحة"}),
        "target_value": forms.NumberInput(attrs={"class": INPUT}),
        "discount_percent": forms.NumberInput(attrs={"class": INPUT, "step": "0.01"}),
        "sort_order": forms.NumberInput(attrs={"class": INPUT}),
    },
)
