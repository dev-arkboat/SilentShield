"""Self-hosted, privacy-safe ad system (like famous sites, minus the surveillance).

How it mirrors real ad platforms:
- AdSlot  ≈ placement (leaderboard / in-feed / sidebar box), with IAB-ish sizes.
- Ad      ≈ campaign creative with scheduling, weight (priority), caps.
- AdEvent ≈ impression / click / dismiss log — aggregate counts only.
- Rotation is weighted-random among *live* campaigns for a slot.
- Viewability via IntersectionObserver beacon; frequency capping via
  localStorage (client-side, no personal profile server-side).
- Every unit is labelled "Advertisement" and is dismissible — FTC-style
  disclosure + UX best practice.
- Optional `embed_html` allows an AdSense-style third-party snippet per
  campaign, but the default/seeded path is first-party creatives only
  (no third-party trackers → preserves reporter anonymity).
"""

from __future__ import annotations

import random

from django.db import models
from django.db.models import F
from django.utils import timezone


class AdSlot(models.Model):
    key = models.SlugField(unique=True, help_text="e.g. header-leaderboard, feed-inline, sidebar-box")
    name = models.CharField(max_length=80)
    description = models.CharField(max_length=200, blank=True)
    width = models.PositiveIntegerField(default=970)
    height = models.PositiveIntegerField(default=250)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["key"]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.name} ({self.key})"

    def pick_ad(self) -> Ad | None:
        live = list(self.campaigns.filter(is_active=True).select_related("slot"))
        live = [a for a in live if a.is_live()]
        if not live:
            return None
        weights = [max(1, a.weight) for a in live]
        return random.choices(live, weights=weights, k=1)[0]


class Ad(models.Model):
    slot = models.ForeignKey(AdSlot, on_delete=models.CASCADE, related_name="campaigns")
    title = models.CharField(max_length=120)
    sponsor = models.CharField(max_length=120)
    tagline = models.CharField(max_length=160, blank=True)
    image = models.ImageField(upload_to="sponsors/%Y/", blank=True, null=True)
    target_url = models.URLField()
    embed_html = models.TextField(
        blank=True, help_text="Optional third-party embed (e.g. AdSense). Prefer first-party image creatives."
    )
    weight = models.PositiveIntegerField(default=1, help_text="Higher = served more often.")
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    max_impressions = models.PositiveIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    impressions = models.PositiveIntegerField(default=0)
    clicks = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.sponsor}: {self.title}"

    def is_live(self) -> bool:
        now = timezone.now()
        if not self.is_active:
            return False
        if self.starts_at and self.starts_at > now:
            return False
        if self.ends_at and self.ends_at < now:
            return False
        if self.max_impressions is not None and self.impressions >= self.max_impressions:
            return False
        return True

    def record(self, kind: str) -> None:
        if kind == AdEvent.Kind.IMPRESSION:
            Ad.objects.filter(pk=self.pk).update(impressions=F("impressions") + 1)
        elif kind == AdEvent.Kind.CLICK:
            Ad.objects.filter(pk=self.pk).update(clicks=F("clicks") + 1)
        AdEvent.objects.create(ad=self, kind=kind)


class AdEvent(models.Model):
    class Kind(models.TextChoices):
        IMPRESSION = "imp", "Impression"
        CLICK = "click", "Click"
        DISMISS = "dismiss", "Dismiss"

    ad = models.ForeignKey(Ad, on_delete=models.CASCADE, related_name="events")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    # Deliberately no IP / user-agent / session fingerprint columns (anonymity).
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
