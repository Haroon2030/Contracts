from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import Department, Role, UserProfile
from contracts.models import (
    ApprovalDecision,
    ApproverRole,
    ApprovalStep,
    Contract,
    ContractStatus,
    ContractSubtype,
    ContractTarget,
    ContractType,
    ShelfRate,
    Vendor,
)
from contracts.services import refresh_all_alerts, write_audit


class Command(BaseCommand):
    help = "إنشاء بيانات تجريبية لنظام إدارة العقود"

    @transaction.atomic
    def handle(self, *args, **options):
        User = get_user_model()
        purchasing = Department.objects.get_or_create(code="PUR", defaults={"name": "المشروبات الساخنة والحلويات"})[0]
        dairy = Department.objects.get_or_create(code="DRY", defaults={"name": "الألبان والمنتجات المبردة"})[0]
        nonfood = Department.objects.get_or_create(code="NFD", defaults={"name": "المنظفات ومستلزمات العناية"})[0]
        contracts_dept = Department.objects.get_or_create(code="CNT", defaults={"name": "إدارة العقود"})[0]
        legal_dept = Department.objects.get_or_create(code="LEG", defaults={"name": "الشؤون القانونية"})[0]

        users = {
            "contracts": ("نورة", "العتيبي", Role.CONTRACTS_OFFICER, contracts_dept, "موظفة قسم العقود والامتياز", "Contracts@123"),
            "head": ("سلطان", "القحطاني", Role.PURCHASING_HEAD, purchasing, "المالك التجاري / رئيس القسم", "Head@123"),
            "manager": ("فهد", "الدوسري", Role.CONTRACTS_MANAGER, contracts_dept, "مدير إدارة العقود والمشتريات", "Manager@123"),
            "legal": ("سارة", "الحربي", Role.LEGAL, legal_dept, "مستشارة الشؤون القانونية", "Legal@123"),
            "buyer": ("ماجد", "الشهري", Role.PURCHASING_OFFICER, purchasing, "موظف مشتريات", "Buyer@123"),
            "1": ("خالد", "الإدارة", Role.ADMIN, contracts_dept, "مدير النظام", "526400"),
        }
        created_users = {}
        for username, (first, last, role, dept, title, password) in users.items():
            user, _made = User.objects.get_or_create(username=username, defaults={"first_name": first, "last_name": last})
            user.first_name = first
            user.last_name = last
            user.set_password(password)
            if role == Role.ADMIN:
                user.is_staff = True
                user.is_superuser = True
            user.save()
            UserProfile.objects.update_or_create(
                user=user,
                defaults={"role": role, "department": dept, "job_title": title},
            )
            created_users[username] = user

        rates = [
            ("SHELF_M1", "رف بطول متر واحد", Decimal("1000.00")),
            ("SHELF_END", "رف نهاية الممر (End-Cap)", Decimal("1500.00")),
            ("BOARD_AD", "لوحة إعلانية", Decimal("750.00")),
        ]
        rate_objs = {}
        for code, name, price in rates:
            rate_objs[code] = ShelfRate.objects.update_or_create(
                code=code, defaults={"name": name, "standard_price": price, "unit": "شهرياً"}
            )[0]

        vendors_data = [
            ("V-2201", "شركة الأغذية المتحدة", "United Foods"),
            ("V-0881", "نسكافيه السعودية", "Nescafé"),
            ("V-0912", "شركة نستله الشرق الأوسط للتجارة", "Nestlé"),
            ("V-1044", "مؤسسة النور للخدمات", "Al Noor"),
            ("V-0550", "المراعي", "Almarai"),
            ("V-0330", "يونيلفر", "Unilever"),
        ]
        vendors = {}
        for number, legal, trade in vendors_data:
            vendors[number] = Vendor.objects.update_or_create(
                vendor_number=number, defaults={"legal_name": legal, "trade_name": trade}
            )[0]

        today = timezone.localdate()
        officer = created_users["contracts"]
        head = created_users["head"]
        buyer = created_users["buyer"]

        def upsert_contract(number, **kwargs):
            obj, _ = Contract.objects.update_or_create(contract_number=number, defaults=kwargs)
            return obj

        c1 = upsert_contract(
            "V-2201-01",
            contract_type=ContractType.SUPPLY,
            subtype=ContractSubtype.FOOD,
            vendor=vendors["V-2201"],
            department=purchasing,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            auto_renewal=True,
            notice_period_days=30,
            actual_value=Decimal("48000"),
            has_non_standard_terms=False,
            commercial_owner=buyer,
            purchasing_manager=head,
            status=ContractStatus.ACTIVE,
            both_parties_signed=True,
            created_by=officer,
        )
        ContractTarget.objects.update_or_create(
            contract=c1,
            sort_order=1,
            defaults={"title": "الشريحة الأساسية", "target_value": Decimal("100000"), "discount_percent": Decimal("3")},
        )

        c2 = upsert_contract(
            "V-0881-01",
            contract_type=ContractType.MARKETING,
            vendor=vendors["V-0881"],
            department=purchasing,
            start_date=today + timedelta(days=10),
            end_date=date(2027, 3, 31),
            auto_renewal=False,
            notice_period_days=30,
            actual_value=Decimal("22500"),
            has_non_standard_terms=False,
            commercial_owner=buyer,
            purchasing_manager=head,
            status=ContractStatus.PENDING_SIGNATURE,
            both_parties_signed=False,
            created_by=officer,
        )

        c3 = upsert_contract(
            "V-0912-01",
            contract_type=ContractType.SHELF_RENT,
            internal_classification="تأجير رؤوس ممرات (End-Cap Display)",
            vendor=vendors["V-0912"],
            department=nonfood,
            start_date=date(2026, 5, 1),
            end_date=date(2027, 4, 30),
            auto_renewal=True,
            notice_period_days=60,
            actual_value=Decimal("28800"),
            has_non_standard_terms=True,
            commercial_owner=head,
            purchasing_manager=head,
            status=ContractStatus.PENDING_APPROVAL,
            shelf_rate=rate_objs["SHELF_M1"],
            shelf_actual_price=Decimal("1200"),
            created_by=officer,
        )
        ContractTarget.objects.update_or_create(
            contract=c3,
            sort_order=1,
            defaults={"title": "الشريحة الأساسية", "target_value": Decimal("100000"), "discount_percent": Decimal("3")},
        )
        ContractTarget.objects.update_or_create(
            contract=c3,
            sort_order=2,
            defaults={"title": "الشريحة المتقدمة", "target_value": Decimal("250000"), "discount_percent": Decimal("5")},
        )

        c4 = upsert_contract(
            "V-1044-02",
            contract_type=ContractType.SERVICES,
            subtype=ContractSubtype.ACCOUNT_OPENING,
            vendor=vendors["V-1044"],
            department=purchasing,
            start_date=date(2025, 8, 1),
            end_date=date(2026, 8, 1),
            auto_renewal=False,
            notice_period_days=30,
            actual_value=Decimal("7800"),
            has_non_standard_terms=False,
            commercial_owner=buyer,
            purchasing_manager=head,
            status=ContractStatus.ACTIVE,
            both_parties_signed=True,
            created_by=officer,
        )

        c5 = upsert_contract(
            "V-0550-04",
            contract_type=ContractType.SUPPLY,
            subtype=ContractSubtype.FRESH,
            vendor=vendors["V-0550"],
            department=dairy,
            start_date=today,
            end_date=date(2027, 9, 18),
            auto_renewal=True,
            notice_period_days=30,
            actual_value=Decimal("31200"),
            has_non_standard_terms=True,
            commercial_owner=buyer,
            purchasing_manager=head,
            status=ContractStatus.UNDER_REVIEW,
            created_by=officer,
        )

        c6 = upsert_contract(
            "V-0330-02",
            contract_type=ContractType.SUPPLY,
            subtype=ContractSubtype.NON_FOOD,
            vendor=vendors["V-0330"],
            department=nonfood,
            start_date=date(2025, 1, 1),
            end_date=date(2026, 1, 1),
            auto_renewal=False,
            notice_period_days=30,
            actual_value=Decimal("15000"),
            commercial_owner=buyer,
            purchasing_manager=head,
            status=ContractStatus.EXPIRED,
            both_parties_signed=True,
            created_by=officer,
        )

        c7 = upsert_contract(
            "V-2201-02",
            contract_type=ContractType.SUPPLY,
            subtype=ContractSubtype.FOOD,
            vendor=vendors["V-2201"],
            department=purchasing,
            start_date=today,
            end_date=today + timedelta(days=25),
            auto_renewal=True,
            notice_period_days=30,
            actual_value=Decimal("18500"),
            commercial_owner=buyer,
            purchasing_manager=head,
            status=ContractStatus.ACTIVE,
            both_parties_signed=True,
            created_by=officer,
        )

        c8 = upsert_contract(
            "V-0912-02",
            contract_type=ContractType.SHELF_RENT,
            vendor=vendors["V-0912"],
            department=nonfood,
            start_date=today,
            end_date=date(2027, 9, 18),
            auto_renewal=False,
            notice_period_days=30,
            actual_value=Decimal("12000"),
            has_non_standard_terms=False,
            commercial_owner=buyer,
            purchasing_manager=head,
            status=ContractStatus.DRAFT,
            shelf_rate=rate_objs["BOARD_AD"],
            shelf_actual_price=Decimal("750"),
            created_by=officer,
        )

        for contract in (c1, c2, c3, c4, c5, c6, c7, c8):
            if not contract.audit_logs.exists():
                write_audit(contract, officer, "تحميل بيانات تجريبية", to_status=contract.status)

        ApprovalStep.objects.all().delete()
        ApprovalStep.objects.create(
            contract=c3,
            role=ApproverRole.CONTRACTS_MANAGER,
            sequence=1,
            decision=ApprovalDecision.PENDING,
        )
        ApprovalStep.objects.create(
            contract=c2,
            role=ApproverRole.CONTRACTS_MANAGER,
            sequence=1,
            decision=ApprovalDecision.APPROVED,
            decided_by=created_users["manager"],
        )

        refresh_all_alerts()
        self.stdout.write(self.style.SUCCESS("تم إنشاء البيانات التجريبية."))
        self.stdout.write("حسابات الدخول:")
        self.stdout.write("  contracts / Contracts@123  — موظفة العقود")
        self.stdout.write("  head / Head@123            — رئيس المشتريات")
        self.stdout.write("  manager / Manager@123      — مدير إدارة العقود")
        self.stdout.write("  legal / Legal@123          — الشؤون القانونية")
        self.stdout.write("  buyer / Buyer@123          — موظف مشتريات")
        self.stdout.write("  1 / 526400                 — مدير النظام")
