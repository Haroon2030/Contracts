from django.contrib.auth import authenticate, get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from accounts.forms import UserForm
from accounts.models import Department, Role, UserProfile
from accounts.services import create_user, update_user


class UserManagementTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.dept = Department.objects.create(name="المشروبات الساخنة", code="PUR")
        self.contracts_dept = Department.objects.create(name="إدارة العقود", code="CNT")
        self.admin = User.objects.create_user(
            username="admin1",
            password="AdminPass123",
            first_name="خالد",
            last_name="الإدارة",
        )
        UserProfile.objects.create(
            user=self.admin,
            role=Role.ADMIN,
            department=self.contracts_dept,
            job_title="مدير النظام",
        )
        self.admin.is_staff = True
        self.admin.is_superuser = True
        self.admin.save()
        self.officer = User.objects.create_user(
            username="officer1",
            password="OfficerPass123",
            first_name="نورة",
        )
        UserProfile.objects.create(
            user=self.officer,
            role=Role.CONTRACTS_OFFICER,
            department=self.contracts_dept,
        )

    def test_admin_creates_department_head_with_department(self):
        user = create_user(
            actor=self.admin,
            username="head1",
            first_name="سلطان",
            last_name="القحطاني",
            password="HeadPass123",
            role=Role.PURCHASING_HEAD,
            department=self.dept,
            job_title="رئيس القسم",
        )
        self.assertEqual(user.profile.role, Role.PURCHASING_HEAD)
        self.assertEqual(user.profile.department, self.dept)
        self.assertTrue(authenticate(username="head1", password="HeadPass123"))
        self.assertFalse(user.is_superuser)

    def test_department_head_without_department_is_rejected(self):
        form = UserForm(
            data={
                "username": "head2",
                "first_name": "سلطان",
                "password": "HeadPass123",
                "role": Role.PURCHASING_HEAD,
                "is_active": "on",
            },
            actor=self.admin,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("department", form.errors)
        with self.assertRaises(ValidationError):
            create_user(
                actor=self.admin,
                username="head2",
                first_name="سلطان",
                password="HeadPass123",
                role=Role.PURCHASING_HEAD,
                department=None,
            )

    def test_anonymous_users_page_redirects_to_login(self):
        response = self.client.get(reverse("accounts:user_list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_non_admin_cannot_view_users(self):
        self.client.force_login(self.officer)
        response = self.client.get(reverse("accounts:user_list"))
        self.assertEqual(response.status_code, 403)

    def test_unauthorized_post_create_is_rejected(self):
        self.client.force_login(self.officer)
        response = self.client.post(
            reverse("accounts:user_create"),
            {
                "username": "intruder",
                "first_name": "مهاجم",
                "password": "BadPass123",
                "role": Role.PURCHASING_HEAD,
                "department": self.dept.pk,
            },
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(get_user_model().objects.filter(username="intruder").exists())

    def test_admin_cannot_deactivate_self(self):
        with self.assertRaises(ValidationError):
            update_user(
                actor=self.admin,
                user=self.admin,
                username=self.admin.username,
                first_name=self.admin.first_name,
                role=Role.ADMIN,
                department=self.contracts_dept,
                is_active=False,
            )
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_last_admin_cannot_be_demoted(self):
        with self.assertRaises(ValidationError):
            update_user(
                actor=self.admin,
                user=self.admin,
                username=self.admin.username,
                first_name=self.admin.first_name,
                role=Role.CONTRACTS_OFFICER,
                department=self.contracts_dept,
                is_active=True,
            )
        self.admin.profile.refresh_from_db()
        self.assertEqual(self.admin.profile.role, Role.ADMIN)

    def test_admin_can_create_department_via_post(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("accounts:department_create"),
            {"name": "الألبان", "code": "dry"},
        )
        self.assertEqual(response.status_code, 302)
        created = Department.objects.get(code="DRY")
        self.assertEqual(created.name, "الألبان")

    def test_admin_can_create_user_via_post(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("accounts:user_create"),
            {
                "username": "head3",
                "first_name": "سلطان",
                "last_name": "القحطاني",
                "password": "HeadPass123",
                "role": Role.PURCHASING_HEAD,
                "department": self.dept.pk,
                "job_title": "رئيس القسم",
                "is_active": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        created = get_user_model().objects.get(username="head3")
        self.assertEqual(created.profile.role, Role.PURCHASING_HEAD)
        self.assertTrue(authenticate(username="head3", password="HeadPass123"))
