from django.urls import path

from marketplace.views import hacker_detail, hacker_list

urlpatterns = [
    path("", hacker_list, name="hacker_list"),
    path("<str:nickname>/", hacker_detail, name="hacker_detail"),
]
