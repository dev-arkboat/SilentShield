from django.contrib.auth.models import User
from django.test import TestCase

from marketplace.models import HackerProfile


class MarketplaceTests(TestCase):
    def test_only_verified_listed(self):
        HackerProfile.objects.create(nickname="ghost", is_verified=True, is_listed=True)
        HackerProfile.objects.create(nickname="unvetted", is_verified=False, is_listed=True)
        r = self.client.get("/guardians/")
        self.assertContains(r, "ghost")
        self.assertNotContains(r, "unvetted")

    def test_team_rating_updates_average(self):
        staff = User.objects.create_user("lead", password="x" * 12, is_staff=True)
        h = HackerProfile.objects.create(nickname="lantern", is_verified=True, is_listed=True)
        h.ratings.create(score=5, comment="Great", created_by=staff)
        h.ratings.create(score=3, comment="OK", created_by=staff)
        h.refresh_from_db()
        self.assertEqual(float(h.rating), 4.0)
        self.assertEqual(h.ratings_count, 2)
