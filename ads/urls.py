from django.urls import path

from ads.views import click, dismiss, impression

urlpatterns = [
    path("imp/<int:pk>/", impression, name="ad_imp"),
    path("click/<int:pk>/", click, name="ad_click"),
    path("dismiss/<int:pk>/", dismiss, name="ad_dismiss"),
]
