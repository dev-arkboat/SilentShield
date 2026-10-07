from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from ads.models import Ad, AdSlot


class AdsTests(TestCase):
    def test_weighted_pick_only_live(self):
        slot = AdSlot.objects.create(key="feed-inline", name="Feed", width=728, height=90)
        live = Ad.objects.create(slot=slot, title="Live", sponsor="S", target_url="https://example.com", weight=1)
        Ad.objects.create(
            slot=slot, title="Expired", sponsor="S", target_url="https://example.com",
            ends_at=timezone.now() - timedelta(days=1),
        )
        for _ in range(10):
            self.assertEqual(slot.pick_ad(), live)

    def test_impression_and_click_counters(self):
        slot = AdSlot.objects.create(key="sidebar-box", name="Box", width=300, height=600)
        ad = Ad.objects.create(slot=slot, title="A", sponsor="S", target_url="https://example.com")
        self.client.post(f"/ads/imp/{ad.id}/")
        ad.refresh_from_db()
        self.assertEqual(ad.impressions, 1)
        r = self.client.get(f"/ads/click/{ad.id}/")
        self.assertEqual(r.status_code, 302)
        ad.refresh_from_db()
        self.assertEqual(ad.clicks, 1)
