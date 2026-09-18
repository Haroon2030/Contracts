from django.urls import path

from . import views

app_name = "contracts"

urlpatterns = [
    path("", views.contract_list, name="list"),
    path("new/", views.contract_create, name="create"),
    path("approvals/", views.approval_queue, name="approvals"),
    path("legal/", views.legal_queue, name="legal"),
    path("alerts/", views.alerts_list, name="alerts"),
    path("shelf-rates/", views.shelf_rates, name="shelf_rates"),
    path("<int:pk>/print/", views.contract_print, name="print"),
    path("<int:pk>/", views.contract_detail, name="detail"),
    path("<int:pk>/edit/", views.contract_edit, name="edit"),
    path("<int:pk>/submit/", views.contract_submit, name="submit"),
    path("<int:pk>/legal/", views.contract_legal, name="legal_decide"),
    path("<int:pk>/approve/", views.contract_approve, name="approve"),
    path("<int:pk>/escalate/", views.contract_escalate, name="escalate"),
    path("<int:pk>/upload/", views.contract_upload, name="upload"),
    path("<int:pk>/attachments/<int:attachment_id>/", views.attachment_download, name="attachment"),
    path("<int:pk>/delete/", views.contract_delete, name="delete"),
]
