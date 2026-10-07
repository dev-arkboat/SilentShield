from django import template
from django.core.cache import caches

register = template.Library()


@register.inclusion_tag("ads/_slot.html")
def render_ad_slot(slot_key):
    """Render one (weighted-random live) campaign for a placement slot."""
    from ads.models import AdSlot

    try:
        slot = AdSlot.objects.get(key=slot_key, is_active=True)
    except AdSlot.DoesNotExist:
        return {"slot": None, "ad": None}
    return {"slot": slot, "ad": slot.pick_ad()}
