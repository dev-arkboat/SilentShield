"""Guardian marketplace: vetted ethical hackers with masked identities.

Privacy contract:
- `private_identity_ref` is operational only: visible in Django admin to
  superusers, NEVER rendered in any public template or API.
- Public contact happens through ContactRequest (blind relay). No email,
  phone, or external handle of the hacker is ever exposed.
- Ratings are authored by the site team (staff users), not the public.
"""

from __future__ import annotations

from django.contrib.auth.models import User
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse


class HackerProfile(models.Model):
    nickname = models.CharField(max_length=60, unique=True, help_text="Public alias only.")
    tagline = models.CharField(max_length=140, blank=True)
    bio = models.TextField(max_length=2000, blank=True)
    skills = models.CharField(max_length=255, blank=True, help_text="Comma-separated, e.g. forensics, malware analysis")
    services = models.TextField(max_length=2000, blank=True)
    price_range = models.CharField(max_length=80, blank=True, help_text="e.g. NPR 5,000–25,000 / case")
    avatar = models.ImageField(upload_to="guardians/%Y/", blank=True, null=True)
    relay_handle = models.CharField(
        max_length=80, blank=True, help_text="Masked relay ID shown publicly, e.g. relay-7f3a. Never a personal handle."
    )
    affiliated_org = models.CharField(max_length=160, blank=True)

    rating = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    ratings_count = models.PositiveIntegerField(default=0)

    is_verified = models.BooleanField(default=False, help_text="Set only after cops / affiliated org verify identity.")
    is_listed = models.BooleanField(default=True)
    verified_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="verified_hackers")
    verified_at = models.DateTimeField(null=True, blank=True)

    # NEVER expose in templates. Admin superuser-only.
    private_identity_ref = models.TextField(
        blank=True, help_text="Real identity dossier reference. Staff-only. Never rendered publicly."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-rating", "nickname"]

    def __str__(self) -> str:  # pragma: no cover
        return self.nickname

    def get_absolute_url(self):
        return reverse("hacker_detail", kwargs={"nickname": self.nickname})

    @property
    def skill_list(self) -> list[str]:
        return [s.strip() for s in (self.skills or "").split(",") if s.strip()]

    def refresh_rating(self):
        agg = self.ratings.aggregate(avg=models.Avg("score"), n=models.Count("id"))
        self.rating = round(agg["avg"] or 0, 2)
        self.ratings_count = agg["n"] or 0
        self.save(update_fields=["rating", "ratings_count"])


class HackerRating(models.Model):
    hacker = models.ForeignKey(HackerProfile, on_delete=models.CASCADE, related_name="ratings")
    score = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.CharField(max_length=280, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, help_text="Team member authoring the rating.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.hacker.nickname} ★{self.score}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.hacker.refresh_rating()

    def delete(self, *args, **kwargs):
        hacker = self.hacker
        super().delete(*args, **kwargs)
        hacker.refresh_rating()


class ContactRequest(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "New"
        REVIEWED = "reviewed", "Reviewed by team"
        CONNECTED = "connected", "Connected via relay"

    hacker = models.ForeignKey(HackerProfile, on_delete=models.CASCADE, related_name="contact_requests")
    subject = models.CharField(max_length=140)
    message = models.TextField(max_length=2000, help_text="Describe the help you need. Do NOT include your real name.")
    # Optional anonymous callback: a throwaway relay the requester monitors.
    callback = models.CharField(max_length=140, blank=True, help_text="Optional throwaway relay where the team can reach you.")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.NEW)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:  # pragma: no cover
        return f"→ {self.hacker.nickname}: {self.subject[:50]}"
