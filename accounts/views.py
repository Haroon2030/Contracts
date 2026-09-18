from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from django.contrib.auth import get_user_model

from .forms import DepartmentForm, UserForm
from .models import Department, Role
from .services import (
    PermissionDeniedError,
    create_user,
    filter_users,
    require_user_admin,
    update_user,
    users_queryset,
)

LOCK_LIMIT = 8
LOCK_SECONDS = 15 * 60


class RateLimitedLoginView(LoginView):
    template_name = "registration/login.html"

    def _cache_key(self):
        forwarded = self.request.META.get("HTTP_X_FORWARDED_FOR", "")
        ip = (forwarded.split(",")[0] if forwarded else self.request.META.get("REMOTE_ADDR", "")).strip()
        return f"login-throttle:{ip or 'unknown'}"

    def dispatch(self, request, *args, **kwargs):
        if request.method == "POST" and cache.get(self._cache_key(), 0) >= LOCK_LIMIT:
            messages.error(request, "تجاوزت عدد محاولات الدخول. حاول بعد ربع ساعة.")
            return self.get(request, *args, **kwargs)
        return super().dispatch(request, *args, **kwargs)

    def form_invalid(self, form):
        key = self._cache_key()
        cache.set(key, cache.get(key, 0) + 1, LOCK_SECONDS)
        return super().form_invalid(form)

    def form_valid(self, form):
        cache.delete(self._cache_key())
        return super().form_valid(form)


def _forbidden():
    return HttpResponseForbidden("إدارة المستخدمين مقصورة على مدير النظام.")


def _require_admin(request):
    try:
        return require_user_admin(request.user)
    except PermissionDeniedError:
        return None


def _apply_service_errors(form, error):
    if hasattr(error, "message_dict"):
        for field, messages_list in error.message_dict.items():
            if field in form.fields:
                for item in messages_list:
                    form.add_error(field, item)
            else:
                form.add_error(None, messages_list[0] if messages_list else error)
        return
    form.add_error(None, error.messages[0] if getattr(error, "messages", None) else error)


@login_required
def user_list(request):
    if _require_admin(request) is None:
        return _forbidden()
    User = get_user_model()
    q = (request.GET.get("q") or "").strip()
    selected_role = request.GET.get("role") or ""
    selected_department = request.GET.get("department") or ""
    selected_status = request.GET.get("status") or ""
    users = filter_users(
        users_queryset(),
        q=q,
        role=selected_role,
        department=selected_department,
        status=selected_status,
    )
    all_users = User.objects.all()
    return render(
        request,
        "accounts/user_list.html",
        {
            "users": users,
            "kpi_total": all_users.count(),
            "kpi_heads": all_users.filter(is_active=True, profile__role=Role.PURCHASING_HEAD).count(),
            "kpi_active": all_users.filter(is_active=True).count(),
            "kpi_inactive": all_users.filter(is_active=False).count(),
            "q": q,
            "selected_role": selected_role,
            "selected_department": selected_department,
            "selected_status": selected_status,
            "role_choices": Role.choices,
            "departments": Department.objects.filter(is_active=True),
            "all_departments": Department.objects.all(),
            "department_form": DepartmentForm(),
            "nav": "users",
        },
    )


@login_required
def user_create(request):
    if _require_admin(request) is None:
        return _forbidden()
    form = UserForm(request.POST or None, actor=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            create_user(
                actor=request.user,
                username=form.cleaned_data["username"],
                first_name=form.cleaned_data["first_name"],
                last_name=form.cleaned_data.get("last_name") or "",
                password=form.cleaned_data["password"],
                role=form.cleaned_data["role"],
                department=form.cleaned_data.get("department"),
                job_title=form.cleaned_data.get("job_title") or "",
                phone=form.cleaned_data.get("phone") or "",
                is_active=form.cleaned_data.get("is_active", True),
            )
        except ValidationError as exc:
            _apply_service_errors(form, exc)
        else:
            messages.success(request, "تم إنشاء المستخدم.")
            return redirect("accounts:user_list")
    return render(
        request,
        "accounts/user_form.html",
        {"form": form, "title": "مستخدم جديد", "nav": "users", "is_create": True},
    )


@login_required
def user_edit(request, pk):
    if _require_admin(request) is None:
        return _forbidden()
    User = get_user_model()
    user = get_object_or_404(User.objects.select_related("profile", "profile__department"), pk=pk)
    form = UserForm(request.POST or None, instance=user, actor=request.user)
    if request.method == "POST" and form.is_valid():
        if form.fields["is_active"].disabled:
            is_active = user.is_active
        else:
            is_active = form.cleaned_data.get("is_active", True)
        try:
            update_user(
                actor=request.user,
                user=user,
                username=form.cleaned_data["username"],
                first_name=form.cleaned_data["first_name"],
                last_name=form.cleaned_data.get("last_name") or "",
                password=form.cleaned_data.get("password") or "",
                role=form.cleaned_data["role"],
                department=form.cleaned_data.get("department"),
                job_title=form.cleaned_data.get("job_title") or "",
                phone=form.cleaned_data.get("phone") or "",
                is_active=is_active,
            )
        except ValidationError as exc:
            _apply_service_errors(form, exc)
        else:
            messages.success(request, "تم تحديث المستخدم.")
            return redirect("accounts:user_list")
    return render(
        request,
        "accounts/user_form.html",
        {"form": form, "title": "تعديل المستخدم", "nav": "users", "is_create": False, "edited_user": user},
    )


@login_required
def department_create(request):
    if _require_admin(request) is None:
        return _forbidden()
    if request.method != "POST":
        return redirect("accounts:user_list")
    form = DepartmentForm(request.POST)
    if form.is_valid():
        form.save()
        messages.success(request, "تم إضافة القسم.")
    else:
        messages.error(request, "تعذر إضافة القسم. تحقق من الاسم والرمز.")
    return redirect("accounts:user_list")
