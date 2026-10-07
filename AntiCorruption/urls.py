from django.contrib import admin
from django.urls import include, path

from core.views_ops import server_settings

urlpatterns = [
    path("admin/server-settings/", server_settings, name="server_settings"),
    path("admin/", admin.site.urls),
    path("ads/", include("ads.urls")),
    path("guardians/", include("marketplace.urls")),
    path("", include("core.urls")),
]
