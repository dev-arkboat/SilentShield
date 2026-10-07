from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from marketplace.forms import ContactRequestForm
from marketplace.models import HackerProfile


def hacker_list(request):
    hackers = HackerProfile.objects.filter(is_verified=True, is_listed=True).prefetch_related("ratings")
    return render(request, "marketplace/list.html", {"hackers": hackers})


def hacker_detail(request, nickname):
    hacker = get_object_or_404(HackerProfile, nickname=nickname, is_verified=True, is_listed=True)
    ratings = hacker.ratings.select_related("created_by")[:10]
    if request.method == "POST":
        form = ContactRequestForm(request.POST)
        if form.is_valid():
            req = form.save(commit=False)
            req.hacker = hacker  # blind relay: no hacker PII involved
            req.save()
            messages.success(
                request,
                f"Sent via blind relay to {hacker.nickname}. The team will connect you without exposing anyone.",
            )
            return redirect(hacker.get_absolute_url())
    else:
        form = ContactRequestForm()
    return render(request, "marketplace/detail.html", {"hacker": hacker, "ratings": ratings, "form": form})
