from contracts.models import AlertSeverity, Contract, ContractAlert, ContractStatus


def nav_counts(request):
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {}
    return {
        "nav_pending_approvals": Contract.objects.filter(status=ContractStatus.PENDING_APPROVAL).count(),
        "nav_legal_count": Contract.objects.filter(status=ContractStatus.UNDER_REVIEW).count(),
        "nav_critical_alerts": ContractAlert.objects.filter(is_open=True, severity=AlertSeverity.CRITICAL).count(),
        "nav_open_alerts": ContractAlert.objects.filter(is_open=True).count(),
        "nav_contract_count": Contract.objects.count(),
    }
