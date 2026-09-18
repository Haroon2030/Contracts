from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

from .models import Role, UserProfile


class PermissionDeniedError(PermissionError):
    pass


def require_user_admin(user):
    profile = getattr(user, "profile", None) if user else None
    if not (user and getattr(user, "is_authenticated", False) and profile and profile.can_manage_users):
        raise PermissionDeniedError("إدارة المستخدمين مقصورة على مدير النظام.")
    return profile


def _apply_staff_flags(user, role):
    is_admin = role == Role.ADMIN
    user.is_staff = is_admin
    user.is_superuser = is_admin


def _active_admin_qs(exclude_user=None):
    User = get_user_model()
    qs = User.objects.filter(is_active=True, profile__role=Role.ADMIN)
    if exclude_user is not None:
        qs = qs.exclude(pk=exclude_user.pk)
    return qs


def _guard_last_admin(*, target, new_role, new_active):
    was_admin = getattr(getattr(target, "profile", None), "role", None) == Role.ADMIN
    remains_admin = new_role == Role.ADMIN and new_active
    if was_admin and not remains_admin and not _active_admin_qs(exclude_user=target).exists():
        raise ValidationError("لا يمكن تعطيل أو تنزيل آخر مدير نظام نشط.")


@transaction.atomic
def create_user(
    *,
    actor,
    username,
    first_name,
    last_name="",
    password,
    role,
    department=None,
    job_title="",
    phone="",
    is_active=True,
):
    require_user_admin(actor)
    if role == Role.PURCHASING_HEAD and department is None:
        raise ValidationError({"department": "مسؤول الإدارة يجب ربطه بقسم."})
    if not password:
        raise ValidationError({"password": "كلمة المرور مطلوبة."})
    User = get_user_model()
    username = (username or "").strip()
    if User.objects.filter(username__iexact=username).exists():
        raise ValidationError({"username": "اسم المستخدم مستخدم مسبقاً."})
    user = User(
        username=username,
        first_name=first_name or "",
        last_name=last_name or "",
        is_active=bool(is_active),
    )
    _apply_staff_flags(user, role)
    user.set_password(password)
    user.save()
    UserProfile.objects.create(
        user=user,
        role=role,
        department=department,
        job_title=job_title or "",
        phone=phone or "",
    )
    return user


@transaction.atomic
def update_user(
    *,
    actor,
    user,
    username,
    first_name,
    last_name="",
    password="",
    role,
    department=None,
    job_title="",
    phone="",
    is_active=True,
):
    require_user_admin(actor)
    User = get_user_model()
    target = User.objects.select_for_update().select_related("profile").get(pk=user.pk)
    if role == Role.PURCHASING_HEAD and department is None:
        raise ValidationError({"department": "مسؤول الإدارة يجب ربطه بقسم."})
    if actor.pk == target.pk and not is_active:
        raise ValidationError("لا يمكنك تعطيل حسابك أثناء الجلسة.")
    _guard_last_admin(target=target, new_role=role, new_active=bool(is_active))
    username = (username or "").strip()
    if User.objects.filter(username__iexact=username).exclude(pk=target.pk).exists():
        raise ValidationError({"username": "اسم المستخدم مستخدم مسبقاً."})
    target.username = username
    target.first_name = first_name or ""
    target.last_name = last_name or ""
    target.is_active = bool(is_active)
    _apply_staff_flags(target, role)
    if password:
        target.set_password(password)
    target.save()
    UserProfile.objects.update_or_create(
        user=target,
        defaults={
            "role": role,
            "department": department,
            "job_title": job_title or "",
            "phone": phone or "",
        },
    )
    return target


def users_queryset():
    User = get_user_model()
    return User.objects.select_related("profile", "profile__department").order_by("username")


def filter_users(qs, *, q="", role="", department="", status=""):
    if q:
        qs = qs.filter(
            Q(username__icontains=q)
            | Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
        )
    if role:
        qs = qs.filter(profile__role=role)
    if department:
        qs = qs.filter(profile__department_id=department)
    if status == "active":
        qs = qs.filter(is_active=True)
    elif status == "inactive":
        qs = qs.filter(is_active=False)
    return qs
