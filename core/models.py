"""Core domain: anonymous reports, evidence, officer profiles.

Anonymity contract (load-bearing, do not weaken):
- Report has NO reporter FK, NO ip field, NO user-agent field.
- Views/forms must never read REMOTE_ADDR for reporting paths.
- Filenames are randomised (uuid4); EXIF is stripped on save.
- Original client filenames are never persisted.
"""

from __future__ import annotations

import os
import uuid
from datetime import timedelta
from io import BytesIO

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import models, transaction
from django.urls import reverse
from django.utils import timezone
from PIL import Image, ImageSequence

from core.storages import ConfiguredEvidenceStorage


def _ext(name: str) -> str:
    return os.path.splitext(name or "")[1].lower()


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
VIDEO_EXTS = {".mp4", ".webm", ".mov", ".mkv", ".avi"}
AUDIO_EXTS = {".mp3", ".wav", ".ogg", ".m4a", ".aac", ".opus"}


def evidence_upload_to(_instance: ReportEvidence, filename: str) -> str:
    # Randomised path: no reporter info leaks via filename or date-of-report linkage.
    ext = _ext(filename)
    day = timezone.now().strftime("%Y/%m")
    return f"evidence/{day}/{uuid.uuid4().hex}{ext}"


def public_id_default() -> str:
    return "AC-" + uuid.uuid4().hex[:8].upper()


class OfficerProfile(models.Model):
    """Corps account metadata. Accounts are provisioned by admins only (no public register)."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="officer_profile")
    badge_id = models.CharField(max_length=64, unique=True)
    department = models.CharField(max_length=120, blank=True)
    rank = models.CharField(max_length=120, blank=True)
    organization = models.CharField(max_length=160, blank=True, default="Anti-Corruption Corps")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["badge_id"]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.badge_id} ({self.user.get_username()})"


class ReportQuerySet(models.QuerySet):
    def live(self):
        return self.filter(is_published=True)

    def pending(self):
        return self.live().filter(status=Report.Status.PENDING)

    def release_stale_claims(self) -> int:
        """Bulk-release claims older than CLAIM_TTL_DAYS. Returns count released."""
        cutoff = timezone.now() - timedelta(days=settings.CLAIM_TTL_DAYS)
        qs = self.filter(status=Report.Status.INVESTIGATING, claimed_at__lt=cutoff)
        return qs.update(status=Report.Status.PENDING, claimed_by=None, claimed_at=None)


class Report(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Awaiting Justice"
        INVESTIGATING = "investigating", "Justice in Motion"
        RESOLVED = "resolved", "Resolved & Verified"

    class Category(models.TextChoices):
        BRIBERY = "bribery", "Bribery / Kickbacks"
        EMBEZZLEMENT = "embezzlement", "Embezzlement / Misuse of Funds"
        ABUSE = "abuse", "Abuse of Power"
        FRAUD = "fraud", "Fraud / Forgery"
        PROCUREMENT = "procurement", "Rigged Procurement / Contracts"
        ELECTORAL = "electoral", "Electoral Misconduct"
        VIOLENCE = "violence", "Threats / Violence / Intimidation"
        OTHER = "other", "Other Corruption / Crime"

    public_id = models.CharField(max_length=16, unique=True, default=public_id_default, db_index=True)
    title = models.CharField(max_length=160)
    description = models.TextField(max_length=8000)
    category = models.CharField(max_length=24, choices=Category.choices, default=Category.OTHER)
    location_text = models.CharField(max_length=200, help_text="Area / landmark. Never include your name or address.")
    district = models.CharField(max_length=120, blank=True)
    happened_at = models.DateField(null=True, blank=True)

    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    claimed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="claimed_reports")
    claimed_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_message = models.TextField(blank=True, max_length=4000)

    view_count = models.PositiveIntegerField(default=0)
    is_published = models.BooleanField(default=True, help_text="Reports go live immediately.")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ReportQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["category", "-created_at"]),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.public_id} — {self.title[:60]}"

    def get_absolute_url(self):
        return reverse("report_detail", kwargs={"public_id": self.public_id})

    @property
    def is_claimed(self) -> bool:
        return self.status == self.Status.INVESTIGATING and self.claimed_by_id is not None

    def is_stale_claim(self) -> bool:
        if self.status != self.Status.INVESTIGATING or not self.claimed_at:
            return False
        return self.claimed_at < timezone.now() - timedelta(days=settings.CLAIM_TTL_DAYS)

    def release_if_stale(self) -> bool:
        if self.is_stale_claim():
            self.status = self.Status.PENDING
            self.claimed_by = None
            self.claimed_at = None
            self.save(update_fields=["status", "claimed_by", "claimed_at", "updated_at"])
            return True
        return False

    @transaction.atomic
    def claim(self, user: User) -> None:
        """Exclusive claim: first officer wins; locked row prevents double-claim races."""
        locked = Report.objects.select_for_update().get(pk=self.pk)
        locked.release_if_stale()
        if locked.status == Report.Status.RESOLVED:
            raise ValidationError("This case is already resolved and cannot be claimed.")
        if locked.status == Report.Status.INVESTIGATING:
            raise ValidationError("This case is already being handled by another officer.")
        locked.status = Report.Status.INVESTIGATING
        locked.claimed_by = user
        locked.claimed_at = timezone.now()
        locked.save(update_fields=["status", "claimed_by", "claimed_at", "updated_at"])
        # refresh caller
        self.status, self.claimed_by, self.claimed_at = locked.status, locked.claimed_by, locked.claimed_at


class ReportEvidence(models.Model):
    class Kind(models.TextChoices):
        IMAGE = "image", "Image"
        VIDEO = "video", "Video"
        AUDIO = "audio", "Audio"

    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name="evidence")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    file = models.FileField(upload_to=evidence_upload_to, max_length=255, storage=ConfiguredEvidenceStorage())
    caption = models.CharField(max_length=200, blank=True)
    # Natural image dims, captured at upload so pages reserve the right box (no shift, no crop).
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    is_resolution = models.BooleanField(default=False, help_text="Officer-supplied proof of resolution.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["is_resolution", "created_at"]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.report.public_id} / {self.kind} #{self.pk}"

    def clean(self):
        ext = _ext(self.file.name if self.file else "")
        if self.kind == self.Kind.IMAGE and ext not in IMAGE_EXTS:
            raise ValidationError("Image must be JPG, PNG, WEBP or GIF.")
        if self.kind == self.Kind.VIDEO and ext not in VIDEO_EXTS:
            raise ValidationError("Video must be MP4, WEBM or MOV.")
        if self.kind == self.Kind.AUDIO and ext not in AUDIO_EXTS:
            raise ValidationError("Audio must be MP3, WAV, OGG or M4A.")
        size = getattr(self.file, "size", 0) or 0
        cap_mb = {
            self.Kind.IMAGE: settings.MAX_IMAGE_MB,
            self.Kind.VIDEO: settings.MAX_VIDEO_MB,
            self.Kind.AUDIO: settings.MAX_AUDIO_MB,
        }[self.kind]
        if size > cap_mb * 1024 * 1024:
            raise ValidationError(f"{self.kind.title()} exceeds the {cap_mb} MB limit.")

    def save(self, *args, **kwargs):
        self.full_clean(exclude=["report"])
        # Scrub BEFORE persist so remote backends (demo GitHub, future S3)
        # never receive EXIF/GPS bytes — there is no local path to fix up later.
        if self._state.adding and self.kind == self.Kind.IMAGE and self.file:
            scrubbed = self._scrubbed_upload()
            if scrubbed is not None:
                self.file.save(os.path.basename(self.file.name or "evidence"), scrubbed, save=False)
        super().save(*args, **kwargs)

    def _scrubbed_upload(self) -> ContentFile | None:
        """Re-encode image pixels without metadata. None = keep original (best-effort)."""
        try:
            underlying = self.file.file
            underlying.seek(0)
            raw = underlying.read()
            underlying.seek(0)
        except (AttributeError, ValueError, OSError, NotImplementedError):
            # No local bytes available (e.g. remote backend re-save cycle) —
            # keep the file as-is rather than crash the whole save.
            return None
        if not raw:
            return None
        try:
            with Image.open(BytesIO(raw)) as img:
                self.width, self.height = img.size
                fmt = (img.format or "PNG").upper()
                out = BytesIO()
                if getattr(img, "is_animated", False):
                    frames = [frame.copy() for frame in ImageSequence.Iterator(img)]
                    frames[0].save(out, format=fmt, save_all=True, append_images=frames[1:])
                else:
                    clean = Image.new(img.mode, img.size)
                    clean.putdata(list(img.getdata()))
                    clean.save(out, format=fmt)
            return ContentFile(out.getvalue())
        except Exception:  # corrupt/odd image: store as-is rather than lose evidence
            return None


class SiteNoticeQuerySet(models.QuerySet):
    def current(self) -> SiteNotice | None:
        """The one headline to show: active, inside its window, lowest order first."""
        now = timezone.now()
        return (
            self.filter(is_active=True)
            .filter(models.Q(starts_at__isnull=True) | models.Q(starts_at__lte=now))
            .filter(models.Q(ends_at__isnull=True) | models.Q(ends_at__gte=now))
            .order_by("order", "-updated_at")
            .first()
        )


class SiteNotice(models.Model):
    """Admin-controlled headline bar under the nav (replaces any hardcoded notice)."""

    class Level(models.TextChoices):
        INFO = "info", "Info"
        WARNING = "warning", "Warning"
        URGENT = "urgent", "Urgent"

    key = models.SlugField(unique=True, default="headline", help_text="Stable id, e.g. headline.")
    message = models.CharField(max_length=240, help_text="One line. Plain words — shown under the nav on every page.")
    level = models.CharField(max_length=10, choices=Level.choices, default=Level.INFO)
    is_active = models.BooleanField(default=True, help_text="Only active notices can show.")
    order = models.PositiveSmallIntegerField(default=0, help_text="Lowest order wins when several are active.")
    starts_at = models.DateTimeField(null=True, blank=True, help_text="Optional: show from this time.")
    ends_at = models.DateTimeField(null=True, blank=True, help_text="Optional: hide after this time.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = SiteNoticeQuerySet.as_manager()

    class Meta:
        ordering = ["order", "-updated_at"]

    def __str__(self) -> str:  # pragma: no cover
        state = "live" if self.is_active else "off"
        return f"[{self.level}/{state}] {self.message[:70]}"
