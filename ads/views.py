from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from ads.models import Ad, AdEvent


def _record(pk: int, kind: str):
    ad = get_object_or_404(Ad, pk=pk)
    ad.record(kind)
    return ad


@require_POST
def impression(request, pk: int):
    from django.http import JsonResponse

    _record(pk, AdEvent.Kind.IMPRESSION)
    return JsonResponse({"ok": True})


def click(request, pk: int):
    ad = _record(pk, AdEvent.Kind.CLICK)
    return redirect(ad.target_url)


@require_POST
def dismiss(request, pk: int):
    from django.http import JsonResponse

    _record(pk, AdEvent.Kind.DISMISS)
    return JsonResponse({"ok": True})
