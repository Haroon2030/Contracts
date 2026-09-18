import re

from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Q

from .models import Department, Role

INPUT = (
    "w-full px-3.5 py-2.5 rounded-xl border border-slate-200 bg-slate-50/50 hover:bg-white "
    "text-xs font-bold text-slate-800 focus:bg-white focus:outline-none focus:ring-2 "
    "focus:ring-teal/30 focus:border-teal transition"
)
CHECK = "rounded border-slate-300 text-teal focus:ring-teal"


class UserForm(forms.Form):
    username = forms.CharField(label="اسم المستخدم", max_length=150)
    first_name = forms.CharField(label="الاسم الأول", max_length=150)
    last_name = forms.CharField(label="اسم العائلة", max_length=150, required=False)
    password = forms.CharField(label="كلمة المرور", widget=forms.PasswordInput, required=False)
    role = forms.ChoiceField(label="الدور", choices=Role.choices)
    department = forms.ModelChoiceField(
        label="القسم",
        queryset=Department.objects.none(),
        required=False,
        empty_label="— بدون قسم —",
    )
    job_title = forms.CharField(label="المسمى الوظيفي", max_length=120, required=False)
    phone = forms.CharField(label="الجوال", max_length=20, required=False)
    is_active = forms.BooleanField(label="حساب نشط", required=False, initial=True)

    def __init__(self, *args, instance=None, actor=None, **kwargs):
        self.instance = instance
        self.actor = actor
        super().__init__(*args, **kwargs)
        self.label_suffix = ""
        current_dept_id = None
        if instance:
            profile = getattr(instance, "profile", None)
            current_dept_id = getattr(profile, "department_id", None)
        dept_filter = Q(is_active=True)
        if current_dept_id:
            dept_filter |= Q(pk=current_dept_id)
        self.fields["department"].queryset = Department.objects.filter(dept_filter).order_by("name")
        for name, field in self.fields.items():
            if name == "is_active":
                field.widget.attrs["class"] = CHECK
            else:
                field.widget.attrs["class"] = INPUT
        if instance:
            profile = getattr(instance, "profile", None)
            self.fields["username"].initial = instance.username
            self.fields["first_name"].initial = instance.first_name
            self.fields["last_name"].initial = instance.last_name
            self.fields["role"].initial = getattr(profile, "role", "")
            self.fields["department"].initial = getattr(profile, "department_id", None)
            self.fields["job_title"].initial = getattr(profile, "job_title", "")
            self.fields["phone"].initial = getattr(profile, "phone", "")
            self.fields["is_active"].initial = instance.is_active
            self.fields["password"].required = False
            self.fields["password"].help_text = "اترك الحقل فارغاً للإبقاء على كلمة السر الحالية."
            if actor and instance.pk == actor.pk:
                self.fields["is_active"].disabled = True
        else:
            self.fields["password"].required = True
            self.fields["is_active"].initial = True

    def clean_username(self):
        username = (self.cleaned_data.get("username") or "").strip()
        if not username:
            raise forms.ValidationError("اسم المستخدم مطلوب.")
        User = get_user_model()
        qs = User.objects.filter(username__iexact=username)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("اسم المستخدم مستخدم مسبقاً.")
        return username

    def clean_password(self):
        password = self.cleaned_data.get("password") or ""
        if not self.instance and not password:
            raise forms.ValidationError("كلمة المرور مطلوبة.")
        return password

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("role") == Role.PURCHASING_HEAD and not cleaned.get("department"):
            self.add_error("department", "مسؤول الإدارة يجب ربطه بقسم.")
        return cleaned


class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ["name", "code"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.label_suffix = ""
        for field in self.fields.values():
            field.widget.attrs["class"] = INPUT
        self.fields["name"].widget.attrs["placeholder"] = "مثال: المشروبات الساخنة"
        self.fields["code"].widget.attrs["placeholder"] = "PUR"

    def clean_code(self):
        code = (self.cleaned_data.get("code") or "").strip().upper()
        if not re.fullmatch(r"[A-Z0-9_-]{1,20}", code):
            raise forms.ValidationError("الرمز حروف إنجليزية وأرقام وشرطة فقط، حتى 20 حرفاً.")
        return code
