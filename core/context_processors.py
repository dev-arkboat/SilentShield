from core.models import SiteNotice


def site_notice(request):
    """Inject the current admin-controlled headline (None if unset/inactive)."""
    try:
        return {"site_notice": SiteNotice.objects.current()}
    except Exception:
        # Table missing before first migrate — render without a notice.
        return {"site_notice": None}
