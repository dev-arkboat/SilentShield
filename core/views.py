"""Core views: public feed, anonymous intake, officer casework, static pages."""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, F, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.forms import MultiEvidenceField, ReportEvidenceForm, ReportForm, ResolutionForm, _classify
from core.models import Report, ReportEvidence
from marketplace.models import HackerProfile


# ------------------------------------------------------------------ helpers

ANON_REMINDER = (
    "Saved. Your case code is {pid} — write it down. "
    "We store no name, no account, no IP with this report."
)


def _release_stale():
    Report.objects.release_stale_claims()


def _limits():
    return {"image": settings.MAX_IMAGE_MB, "video": settings.MAX_VIDEO_MB, "audio": settings.MAX_AUDIO_MB}


def _store_files(report: Report, files, *, is_resolution: bool):
    for f in files:
        kind = _classify(f.name)
        ReportEvidence.objects.create(report=report, kind=kind, file=f, is_resolution=is_resolution)


# ------------------------------------------------------------------ public

def home(request):
    _release_stale()
    stats = {
        "total": Report.objects.live().count(),
        "pending": Report.objects.live().filter(status=Report.Status.PENDING).count(),
        "investigating": Report.objects.live().filter(status=Report.Status.INVESTIGATING).count(),
        "resolved": Report.objects.live().filter(status=Report.Status.RESOLVED).count(),
        "guardians": HackerProfile.objects.filter(is_verified=True, is_listed=True).count(),
    }
    recent = Report.objects.live().prefetch_related("evidence")[:6]
    resolved = Report.objects.live().filter(status=Report.Status.RESOLVED).order_by("-resolved_at")[:3]
    guardians = HackerProfile.objects.filter(is_verified=True, is_listed=True).order_by("-rating")[:3]
    return render(request, "core/home.html", {"stats": stats, "recent": recent, "resolved": resolved, "guardians": guardians})


def report_list(request):
    _release_stale()
    qs = Report.objects.live().prefetch_related("evidence").order_by("-created_at")
    status = request.GET.get("status", "")
    category = request.GET.get("category", "")
    q = request.GET.get("q", "").strip()
    if status in dict(Report.Status.choices):
        qs = qs.filter(status=status)
    if category in dict(Report.Category.choices):
        qs = qs.filter(category=category)
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q) | Q(location_text__icontains=q) | Q(public_id__iexact=q))
    paginator = Paginator(qs, 9)
    page = paginator.get_page(request.GET.get("page"))
    return render(
        request,
        "core/report_list.html",
        {"page_obj": page, "status": status, "category": category, "q": q,
         "status_choices": Report.Status.choices, "category_choices": Report.Category.choices},
    )


def report_detail(request, public_id):
    _release_stale()
    report = get_object_or_404(Report.objects.live().prefetch_related("evidence"), public_id=public_id)
    report.release_if_stale()
    # Anonymous view counter: F() increment, no reader identity stored.
    Report.objects.filter(pk=report.pk).update(view_count=F("view_count") + 1)
    report.refresh_from_db(fields=["view_count"])
    proof = report.evidence.filter(is_resolution=True)
    initial = report.evidence.filter(is_resolution=False)
    resolution_form = ResolutionForm() if request.user.is_authenticated else None
    ttl_days = settings.CLAIM_TTL_DAYS
    return render(
        request,
        "core/report_detail.html",
        {"report": report, "initial": initial, "proof": proof,
         "resolution_form": resolution_form, "ttl_days": ttl_days, "limits": _limits()},
    )


def report_create(request):
    """Fully anonymous intake: no login, no IP/user-agent capture, randomised filenames."""
    if request.method == "POST":
        form = ReportForm(request.POST)
        ev_form = ReportEvidenceForm(request.POST, request.FILES)
        if form.is_valid() and ev_form.is_valid():
            report = form.save(commit=False)
            report.is_published = True  # goes straight live
            report.save()
            _store_files(report, ev_form.cleaned_data["files"], is_resolution=False)
            messages.success(request, ANON_REMINDER.format(pid=report.public_id))
            return redirect(report.get_absolute_url())
    else:
        form = ReportForm()
        ev_form = ReportEvidenceForm()
    return render(request, "core/report_form.html", {"form": form, "ev_form": ev_form, "limits": _limits()})


# ------------------------------------------------------------------ officers

@login_required
def dashboard(request):
    _release_stale()
    mine = Report.objects.filter(claimed_by=request.user, status=Report.Status.INVESTIGATING).order_by("-claimed_at")
    available = Report.objects.pending().order_by("-created_at")[:12]
    done = Report.objects.filter(claimed_by=request.user, status=Report.Status.RESOLVED).order_by("-resolved_at")[:12]
    soon = timezone.now() - timedelta(days=settings.CLAIM_TTL_DAYS - 30)
    ageing = mine.filter(claimed_at__lt=soon)
    stats = {
        "mine": mine.count(),
        "available": Report.objects.pending().count(),
        "resolved_by_me": Report.objects.filter(claimed_by=request.user, status=Report.Status.RESOLVED).count(),
        "resolved_all": Report.objects.live().filter(status=Report.Status.RESOLVED).count(),
    }
    return render(request, "core/dashboard.html",
                  {"mine": mine, "available": available, "done": done, "ageing": ageing, "stats": stats,
                   "ttl_days": settings.CLAIM_TTL_DAYS})


@login_required
@require_POST
def claim_report(request, public_id):
    report = get_object_or_404(Report.objects.live(), public_id=public_id)
    try:
        with transaction.atomic():
            report.claim(request.user)
    except ValidationError as e:
        messages.error(request, "; ".join(e.messages))
    else:
        messages.success(request, f"{report.public_id} is now yours. It is locked for others for 10 months.")
    return redirect(report.get_absolute_url())


@login_required
@require_POST
def release_report(request, public_id):
    report = get_object_or_404(Report.objects.live(), claimed_by=request.user, public_id=public_id)
    report.status = Report.Status.PENDING
    report.claimed_by = None
    report.claimed_at = None
    report.save(update_fields=["status", "claimed_by", "claimed_at", "updated_at"])
    messages.info(request, f"{report.public_id} released back to the live queue.")
    return redirect(report.get_absolute_url())


@login_required
@require_POST
def resolve_report(request, public_id):
    report = get_object_or_404(Report.objects.live(), claimed_by=request.user, public_id=public_id)
    if report.status == Report.Status.RESOLVED:
        messages.info(request, "Already resolved.")
        return redirect(report.get_absolute_url())
    form = ResolutionForm(request.POST, request.FILES)
    if not form.is_valid():
        for field, errs in form.errors.items():
            for e in errs:
                messages.error(request, f"{field}: {e}")
        return redirect(report.get_absolute_url())
    with transaction.atomic():
        locked = Report.objects.select_for_update().get(pk=report.pk)
        if locked.claimed_by_id != request.user.id:
            messages.error(request, "You no longer hold this case.")
            return redirect(locked.get_absolute_url())
        _store_files(locked, form.cleaned_data["files"], is_resolution=True)
        locked.status = Report.Status.RESOLVED
        locked.resolution_message = form.cleaned_data["message"]
        locked.resolved_at = timezone.now()
        locked.save(update_fields=["status", "resolution_message", "resolved_at", "updated_at"])
    messages.success(request, f"{locked.public_id} marked Resolved & Verified with proof attached.")
    return redirect(locked.get_absolute_url())


class CorpsLoginView(LoginView):
    template_name = "core/login.html"
    redirect_authenticated_user = True


class CorpsLogoutView(LogoutView):
    pass


# ------------------------------------------------------------------ static

def safety(request):
    return render(request, "core/safety.html", {"ttl_days": settings.CLAIM_TTL_DAYS})


def about(request):
    counts = {
        "reports": Report.objects.live().count(),
        "resolved": Report.objects.live().filter(status=Report.Status.RESOLVED).count(),
    }
    return render(request, "core/about.html", counts)


def advertise(request):
    from ads.models import AdSlot

    slots = AdSlot.objects.filter(is_active=True).prefetch_related("campaigns")
    return render(request, "core/advertise.html", {"slots": slots})
