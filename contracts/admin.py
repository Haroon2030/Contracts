from django.contrib import admin

from .models import (
    ApprovalStep,
    AuditLog,
    Contract,
    ContractAlert,
    ContractAttachment,
    ContractTarget,
    ShelfRate,
    Vendor,
)


class TargetInline(admin.TabularInline):
    model = ContractTarget
    extra = 0


class AttachmentInline(admin.TabularInline):
    model = ContractAttachment
    extra = 0
    readonly_fields = ("uploaded_by", "uploaded_at")


class ApprovalInline(admin.TabularInline):
    model = ApprovalStep
    extra = 0
    readonly_fields = ("decided_by", "decided_at", "decision", "role")


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ("vendor_number", "legal_name", "trade_name", "is_active")
    search_fields = ("vendor_number", "legal_name", "trade_name", "cr_number")


@admin.register(ShelfRate)
class ShelfRateAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "standard_price", "unit", "is_active")


@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = (
        "contract_number",
        "contract_type",
        "vendor",
        "status",
        "actual_value",
        "start_date",
        "end_date",
        "has_non_standard_terms",
    )
    list_filter = ("status", "contract_type", "has_non_standard_terms", "auto_renewal")
    search_fields = ("contract_number", "vendor__legal_name")
    inlines = [TargetInline, AttachmentInline, ApprovalInline]
    readonly_fields = ("contract_number", "created_at", "updated_at", "signed_at", "activated_at")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "contract", "actor", "action", "from_status", "to_status")
    readonly_fields = ("contract", "actor", "action", "from_status", "to_status", "details", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ContractAlert)
class ContractAlertAdmin(admin.ModelAdmin):
    list_display = ("contract", "alert_type", "severity", "is_open", "created_at")
    list_filter = ("alert_type", "severity", "is_open")
