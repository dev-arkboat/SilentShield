from django.apps import apps


def ad_slots(request):
    """Expose active slot keys for nav/footer housekeeping (cheap, cached per request)."""
    if not apps.is_installed("ads"):
        return {}
    try:
        from ads.models import AdSlot

        keys = list(AdSlot.objects.filter(is_active=True).values_list("key", flat=True)[:12])
        return {"active_ad_slots": keys}
    except Exception:
        return {}
