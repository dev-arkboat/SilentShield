from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth.views import LogoutView
from django.urls import path

from core.views import (
    CorpsLoginView,
    about,
    advertise,
    claim_report,
    dashboard,
    home,
    release_report,
    report_create,
    report_detail,
    report_list,
    resolve_report,
    safety,
)

urlpatterns = [
    path("", home, name="home"),
    path("reports/", report_list, name="report_list"),
    path("reports/<str:public_id>/", report_detail, name="report_detail"),
    path("file-report/", report_create, name="report_create"),
    path("dashboard/", dashboard, name="dashboard"),
    path("reports/<str:public_id>/claim/", claim_report, name="claim_report"),
    path("reports/<str:public_id>/release/", release_report, name="release_report"),
    path("reports/<str:public_id>/resolve/", resolve_report, name="resolve_report"),
    path("corps/login/", CorpsLoginView.as_view(), name="login"),
    path("corps/logout/", LogoutView.as_view(), name="logout"),
    path("how-it-protects-you/", safety, name="safety"),
    path("about/", about, name="about"),
    path("advertise/", advertise, name="advertise"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
