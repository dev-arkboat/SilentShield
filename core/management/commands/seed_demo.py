"""Seed demo slots, house ads, guardians and sample live reports.

Usage:  uv run python manage.py seed_demo
Idempotent: uses get_or_create / update_or_create throughout.
Creates no reporter PII (samples carry no identity either).
"""

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.utils import timezone

MIN_GIF = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!"
    b"\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)


class Command(BaseCommand):
    help = "Seed ad slots, house sponsors, guardians, and sample reports."

    def handle(self, *args, **options):
        from ads.models import Ad, AdSlot
        from core.models import Report, ReportEvidence
        from marketplace.models import HackerProfile, HackerRating

        slots = {
            "header-leaderboard": ("Top leaderboard", "Site-wide banner under the header.", 970, 250),
            "feed-inline": ("In-feed native", "Native card inside report feeds.", 728, 90),
            "sidebar-box": ("Sidebar box", "Sticky rail unit on wide screens.", 300, 600),
            "marketplace-sidebar": ("Guardian sidebar", "Marketplace rail unit.", 300, 250),
        }
        for key, (name, desc, w, h) in slots.items():
            AdSlot.objects.get_or_create(key=key, defaults={"name": name, "description": desc, "width": w, "height": h})

        house = [
            ("header-leaderboard", "Civic VPN Shield", "Browse safely on any network.", "https://example.com/vpn", 3),
            ("feed-inline", "SecureDrop Storage", "Encrypted vaults for journalists.", "https://example.com/vault", 2),
            ("sidebar-box", "Legal Aid Network", "Free counsel for whistleblowers.", "https://example.com/legalaid", 2),
            ("marketplace-sidebar", "Forensics Lab", "Verify leaks before you publish.", "https://example.com/lab", 1),
        ]
        for slot_key, title, tagline, url, weight in house:
            slot = AdSlot.objects.get(key=slot_key)
            ad, created = Ad.objects.get_or_create(
                slot=slot, title=title,
                defaults={"sponsor": title.split()[0] + " Org", "tagline": tagline, "target_url": url, "weight": weight},
            )
            if created:
                ad.image.save(f"{slot_key}.gif", ContentFile(MIN_GIF), save=True)

        guardians = [
            ("ghostledger", "Blockchain & fund-trail forensics", "forensics, fund tracing, data recovery",
             "Follow-the-money analysis, leak authentication, device triage.", "NPR 5,000–25,000 / case", "relay-7f3a"),
            ("quietpacket", "Network logs & CCTV recovery", "network forensics, cctv recovery, malware analysis",
             "Log reconstruction, tamper checks, safe disclosure packaging.", "NPR 8,000–30,000 / case", "relay-91bc"),
            ("paperlantern", "Document verification desk", "document forensics, osint, source protection",
             "Contract & paper-trail verification with chain-of-custody notes.", "NPR 4,000–18,000 / case", "relay-44d1"),
        ]
        officer, _ = User.objects.get_or_create(username="team", defaults={"is_staff": True})
        for nick, tag, skills, services, price, relay in guardians:
            h, _ = HackerProfile.objects.update_or_create(
                nickname=nick,
                defaults={"tagline": tag, "bio": tag + ".", "skills": skills, "services": services,
                          "price_range": price, "relay_handle": relay, "is_verified": True, "is_listed": True,
                          "affiliated_org": "Civic Tech Collective", "verified_by": officer,
                          "verified_at": timezone.now()},
            )
            if not h.ratings.exists():
                HackerRating.objects.create(hacker=h, score=5, comment="Verified methodology, clean handoffs.", created_by=officer)
                HackerRating.objects.create(hacker=h, score=4, comment="Fast triage on fund trails.", created_by=officer)

        samples = [
            ("Bribe demanded for land mutation papers", "bribery", "Ward office counter, Tuesday morning",
             "A clerk asked for NPR 15,000 to move a mutation file that had waited 4 months. Video covers the demand; faces of bystanders trimmed."),
            ("School repair fund never reached the school", "embezzlement", "Shree Secondary School gate",
             "Budget board shows NPR 900,000 for roof repair in FY 2081/82; roof still leaks. Photos of board + damage, plus audio of caretaker account."),
            ("Tender awarded before bids closed", "procurement", "Municipality notice board",
             "Contractor began work 3 days before the published deadline. Dated photos of site activity + notice copy."),
        ]
        for title, cat, loc, desc in samples:
            rep, created = Report.objects.get_or_create(
                title=title, defaults={"description": desc, "category": cat, "location_text": loc}
            )
            if created and not rep.evidence.exists():
                # Single scrubbed upload via create() — never fieldfile.save(save=True),
                # which would upload raw bytes first and re-enter instance.save().
                ReportEvidence.objects.create(
                    report=rep, kind="image", caption="Sample evidence still",
                    file=ContentFile(MIN_GIF, name=f"{rep.public_id}.gif"),
                )

        from core.models import SiteNotice

        SiteNotice.objects.update_or_create(
            key="headline",
            defaults={
                "message": "No name. No account. Nothing that leads back to you — a photo or video is required.",
                "level": SiteNotice.Level.INFO,
                "is_active": True,
                "order": 0,
            },
        )

        self.stdout.write(self.style.SUCCESS("Seeded slots, house ads, guardians, sample reports."))