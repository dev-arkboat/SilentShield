"""Superuser-only ops views mounted under /admin/ (project urls, before admin/)."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render

from core.server_config import current_state, write_debug_value


@staff_member_required
def server_settings(request):
    if not request.user.is_superuser:
        raise PermissionDenied("Server settings are superuser-only.")
    if request.method == "POST":
        want = request.POST.get("debug") == "on"
        path = write_debug_value(want)
        messages.warning(
            request,
            f"Saved DJANGO_DEBUG={'True' if want else 'False'} to {path}. "
            "Restart the server to apply — the running process still uses the old value.",
        )
        return redirect("server_settings")
    return render(request, "admin/server_settings.html", {"state": current_state()})
