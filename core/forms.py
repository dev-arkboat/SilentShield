"""Anonymous report + officer resolution forms.

Best practices: explicit per-kind validation, friendly errors next to fields,
no placeholder-as-label (templates carry real <label>s).
"""

from __future__ import annotations

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError

from core.models import AUDIO_EXTS, IMAGE_EXTS, VIDEO_EXTS, Report


def _classify(filename: str) -> str | None:
    from core.models import _ext

    ext = _ext(filename)
    if ext in IMAGE_EXTS:
        return "image"
    if ext in VIDEO_EXTS:
        return "video"
    if ext in AUDIO_EXTS:
        return "audio"
    return None


def validate_upload(f) -> str:
    kind = _classify(getattr(f, "name", ""))
    if kind is None:
        raise ValidationError(f"“{f.name}” is not a supported image, video or audio file.")
    cap_mb = {"image": settings.MAX_IMAGE_MB, "video": settings.MAX_VIDEO_MB, "audio": settings.MAX_AUDIO_MB}[kind]
    if f.size and f.size > cap_mb * 1024 * 1024:
        raise ValidationError(f"“{f.name}” exceeds the {cap_mb} MB {kind} limit.")
    return kind


class ReportForm(forms.ModelForm):
    class Meta:
        model = Report
        fields = ["title", "description", "category", "location_text", "district", "happened_at"]
        widgets = {
            "title": forms.TextInput(attrs={"maxlength": 160, "autocomplete": "off"}),
            "description": forms.Textarea(attrs={"rows": 6, "maxlength": 8000}),
            "location_text": forms.TextInput(attrs={"maxlength": 200, "autocomplete": "off"}),
            "district": forms.TextInput(attrs={"maxlength": 120, "autocomplete": "off"}),
            "happened_at": forms.DateInput(attrs={"type": "date"}),
        }
        help_texts = {
            "description": "Facts only — what happened, when, who was involved by role (not your name).",
            "location_text": "Area or landmark. Never include your name, address, or phone.",
        }


class MultipleUploadWidget(forms.ClearableFileInput):
    """File widget that returns the full getlist() for <input multiple>.

    Django >= 6 resolves bound values via the widget (see
    BoundField.data -> Form._widget_data_value), so a plain Field-level
    override is not enough — the widget must pull from FILES.
    """

    allow_multiple_selected = True

    def value_from_datadict(self, data, files, name):
        if hasattr(files, "getlist"):
            lst = files.getlist(name)
            if lst:
                return lst
        return None


class MultiEvidenceField(forms.Field):
    """Accepts <input type=file multiple> as a list of files (read from FILES)."""

    widget = MultipleUploadWidget(attrs={"multiple": True})

    def value_from_datadict(self, data, files, name):
        return self.widget.value_from_datadict(data, files, name)

    def to_python(self, value):
        if not value:
            return []
        if isinstance(value, (list, tuple)):
            return list(value)
        return [value]

    def validate(self, value):
        super().validate(value)


class ReportEvidenceForm(forms.Form):
    files = MultiEvidenceField(
        required=True,
        help_text="Attach images, audio or video. At least one image or video is required.",
    )

    def clean_files(self):
        files = self.cleaned_data.get("files") or []
        if not files:
            raise ValidationError("Attach at least one file. A video or an image is required.")
        kinds = set()
        for f in files:
            kinds.add(validate_upload(f))
        if "image" not in kinds and "video" not in kinds:
            raise ValidationError("A video or an image is required (audio alone is not enough).")
        if len(files) > 20:
            raise ValidationError("Maximum 20 files per report — split the rest across a second report.")
        return files


class ResolutionForm(forms.Form):
    message = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 4, "maxlength": 4000}),
        max_length=4000,
        help_text="What was done, verified outcome, reference numbers (no reporter data is stored).",
    )
    files = MultiEvidenceField(
        required=True, help_text="Attach proof: video, audio or image (at least one file)."
    )

    def clean_files(self):
        files = self.cleaned_data.get("files") or []
        if not files:
            raise ValidationError("Attach at least one proof file (video, audio or image).")
        for f in files:
            validate_upload(f)
        if len(files) > 8:
            raise ValidationError("Maximum 8 proof files.")
        return files
