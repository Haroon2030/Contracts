from django import template

register = template.Library()

STATUS_STYLES = {
    "draft": "bg-slate-100 text-slate-700 border-slate-200",
    "under_review": "bg-indigo-50 text-indigo-700 border-indigo-200",
    "pending_approval": "bg-amber-50 text-amber-800 border-amber-200",
    "pending_signature": "bg-sky-50 text-sky-800 border-sky-200",
    "active": "bg-emerald-50 text-emerald-800 border-emerald-200",
    "expired": "bg-rose-50 text-rose-700 border-rose-200",
    "cancelled": "bg-slate-200 text-slate-600 border-slate-300",
}

SEVERITY_STYLES = {
    "info": "bg-slate-50 text-slate-700 border-slate-200",
    "warning": "bg-amber-50 text-amber-800 border-amber-200",
    "critical": "bg-rose-50 text-rose-700 border-rose-200",
}


@register.filter
def status_chip(status):
    return STATUS_STYLES.get(status, "bg-slate-100 text-slate-700 border-slate-200")


@register.filter
def severity_chip(severity):
    return SEVERITY_STYLES.get(severity, "bg-slate-100 text-slate-700 border-slate-200")


@register.filter
def initials(user):
    if not user:
        return "—"
    name = (user.get_full_name() or user.username).strip()
    parts = [p for p in name.split() if p]
    if len(parts) >= 2:
        return f"{parts[0][0]}{parts[1][0]}"
    return name[:2]


@register.filter
def percent_of(value, total):
    try:
        total = float(total)
        if total <= 0:
            return 0
        return int(round((float(value) / total) * 100))
    except (TypeError, ValueError):
        return 0
