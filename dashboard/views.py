from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum
from django.shortcuts import render
from django.utils import timezone

from contracts.models import Contract, ContractAlert, ContractStatus, ContractType
from contracts.services import refresh_all_alerts, row_action


def _recent_with_actions(qs, user):
    recent = list(qs.prefetch_related("approval_steps").order_by("-updated_at")[:8])
    for contract in recent:
        contract.row_action = row_action(contract, user)
    return recent


@login_required
def home(request):
    refresh_all_alerts()
    qs = Contract.objects.select_related("vendor", "department")
    by_status = dict(qs.values("status").annotate(c=Count("id")).values_list("status", "c"))
    type_counts = dict(qs.values("contract_type").annotate(c=Count("id")).values_list("contract_type", "c"))
    by_type_rows = [(label, type_counts.get(key, 0)) for key, label in ContractType.choices]
    today = timezone.localdate()
    expiring_90 = qs.filter(status=ContractStatus.ACTIVE, end_date__lte=today + timedelta(days=90), end_date__gte=today)
    expiring_30 = qs.filter(status=ContractStatus.ACTIVE, end_date__lte=today + timedelta(days=30), end_date__gte=today)
    exposed_value = expiring_90.aggregate(total=Sum("actual_value"))["total"] or 0
    open_alerts = ContractAlert.objects.filter(is_open=True).select_related("contract", "contract__vendor")
    type_total = sum(count for _, count in by_type_rows) or 1
    return render(
        request,
        "dashboard/home.html",
        {
            "by_status": by_status,
            "by_type_rows": by_type_rows,
            "type_total": type_total,
            "status_choices": ContractStatus.choices,
            "active_count": by_status.get(ContractStatus.ACTIVE, 0),
            "expiring_count": expiring_30.count(),
            "expiring_90_count": expiring_90.count(),
            "exposed_value": exposed_value,
            "open_alerts_count": open_alerts.count(),
            "open_alerts": open_alerts[:8],
            "recent": _recent_with_actions(qs, request.user),
            "nav": "dashboard",
            "now": timezone.localtime(),
        },
    )
