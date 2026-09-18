from django.contrib import admin
from django.contrib.auth.views import LogoutView
from django.urls import include, path

from accounts.views import RateLimitedLoginView

admin.site.site_header = "نظام إدارة العقود — أسواق الرشيد"
admin.site.site_title = "أسواق الرشيد"
admin.site.index_title = "لوحة الإدارة"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("login/", RateLimitedLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("", include("dashboard.urls")),
    path("contracts/", include("contracts.urls")),
]

handler404 = "cms.views.page_not_found"
handler500 = "cms.views.server_error"
