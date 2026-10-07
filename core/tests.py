"""Contract tests: anonymity, exclusivity, 10-month release, proof-gated resolution."""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.exceptions import ImproperlyConfigured, SuspiciousFileOperation
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from core.models import Report

GIF = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!"
    b"\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)
WAV = b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00D\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00"


def gif(name="shot.gif"):
    return SimpleUploadedFile(name, GIF, content_type="image/gif")


def wav(name="note.wav"):
    return SimpleUploadedFile(name, WAV, content_type="audio/wav")


def submit(client, files):
    data = {
        "title": "Bribe at ward office",
        "description": "Clerk demanded cash to move a file.",
        "category": "bribery",
        "location_text": "Ward 4 counter",
        "files": files,
    }
    return client.post("/file-report/", data)


class AnonIntakeTests(TestCase):
    def test_goes_live_pending_with_image(self):
        r = self.client.post("/file-report/", {
            "title": "T", "description": "D", "category": "bribery",
            "location_text": "L", "files": [gif()],
        })
        self.assertEqual(r.status_code, 302)
        rep = Report.objects.get()
        self.assertEqual(rep.status, "pending")
        self.assertTrue(rep.is_published)
        # anonymity: model exposes no reporter/ip columns
        field_names = {f.name for f in Report._meta.get_fields()}
        self.assertTrue({"reporter", "reporter_ip", "ip_address", "user_agent"} & field_names == set())
        self.assertEqual(rep.evidence.count(), 1)

    def test_audio_alone_rejected(self):
        r = submit(self.client, [wav()])
        self.assertEqual(r.status_code, 200)  # re-rendered with errors
        self.assertEqual(Report.objects.count(), 0)

    def test_many_files_all_arrive(self):
        files = [gif(f"shot{i}.gif") for i in range(5)] + [wav()]
        r = submit(self.client, files)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Report.objects.get().evidence.count(), 6)

    def test_image_dims_recorded(self):
        submit(self.client, [gif()])
        ev = Report.objects.get().evidence.get()
        self.assertEqual((ev.width, ev.height), (1, 1))


class ClaimTests(TestCase):
    def setUp(self):
        self.o1 = User.objects.create_user("officer1", password="x" * 12)
        self.o2 = User.objects.create_user("officer2", password="x" * 12)
        self.rep = Report.objects.create(title="T", description="D", category="fraud", location_text="L")
        from core.models import ReportEvidence
        ev = ReportEvidence(report=self.rep, kind="image")
        ev.file.save("e.gif", gif(), save=True)

    def test_exclusive_first_claim_wins(self):
        self.client.force_login(self.o1)
        r1 = self.client.post(f"/reports/{self.rep.public_id}/claim/")
        self.assertEqual(r1.status_code, 302)
        self.rep.refresh_from_db()
        self.assertEqual(self.rep.claimed_by, self.o1)
        self.client.force_login(self.o2)
        r2 = self.client.post(f"/reports/{self.rep.public_id}/claim/")
        self.rep.refresh_from_db()
        self.assertEqual(self.rep.claimed_by, self.o1)  # unchanged

    def test_stale_claim_releases_after_ttl(self):
        from django.conf import settings

        self.rep.status = "investigating"
        self.rep.claimed_by = self.o1
        self.rep.claimed_at = timezone.now() - timedelta(days=settings.CLAIM_TTL_DAYS + 1)
        self.rep.save()
        self.assertTrue(self.rep.release_if_stale())
        self.rep.refresh_from_db()
        self.assertEqual(self.rep.status, "pending")
        self.assertIsNone(self.rep.claimed_by)

    def test_resolution_needs_proof_and_message(self):
        self.rep.status = "investigating"
        self.rep.claimed_by = self.o1
        self.rep.claimed_at = timezone.now()
        self.rep.save()
        self.client.force_login(self.o1)
        no_proof = self.client.post(f"/reports/{self.rep.public_id}/resolve/", {"message": "Done"})
        self.assertEqual(no_proof.status_code, 302)
        self.rep.refresh_from_db()
        self.assertNotEqual(self.rep.status, "resolved")
        ok = self.client.post(
            f"/reports/{self.rep.public_id}/resolve/",
            {"message": "Arrest made, file ref 12.", "files": [gif("proof.gif")]},
        )
        self.assertEqual(ok.status_code, 302)
        self.rep.refresh_from_db()
        self.assertEqual(self.rep.status, "resolved")
        self.assertTrue(self.rep.evidence.filter(is_resolution=True).exists())


class FakeResp:
    def __init__(self, payload=None, status=201):
        import json as _json

        self._body = _json.dumps(payload or {}).encode() if isinstance(payload, dict) else payload
        self.status = status

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class GitHubStorageTests(SimpleTestCase):
    """Demo backend, fully mocked — no network touched."""

    def _storage(self):
        from core.storages import GitHubRepoStorage

        return GitHubRepoStorage(repo="demo-owner/evidence-demo", token="demo-token")

    def test_missing_config_raises(self):
        from core.storages import GitHubRepoStorage

        with self.assertRaises(ImproperlyConfigured):
            GitHubRepoStorage(repo="", token="")

    def test_url_points_at_raw_cdn(self):
        self.assertEqual(
            self._storage().url("evidence/2026/10/abc.gif"),
            "https://raw.githubusercontent.com/demo-owner/evidence-demo/main/evidence/2026/10/abc.gif",
        )

    def test_save_puts_base64_to_contents_api(self):
        seen = {}

        def fake_urlopen(req, timeout=30):
            seen["url"] = req.full_url
            seen["method"] = req.get_method()
            import json as _json

            seen["payload"] = _json.loads(req.data.decode())
            return FakeResp({"content": {"sha": "abc"}}, 201)

        with patch("urllib.request.urlopen", fake_urlopen):
            name = self._storage()._save("evidence/x.gif", SimpleUploadedFile("x.gif", GIF))
        self.assertEqual(name, "evidence/x.gif")
        self.assertEqual(seen["method"], "PUT")
        self.assertIn("/repos/demo-owner/evidence-demo/contents/evidence/x.gif", seen["url"])
        self.assertEqual(seen["payload"]["branch"], "main")
        self.assertTrue(seen["payload"]["content"])  # base64 body present

    def test_oversize_rejected_before_network(self):
        big = SimpleUploadedFile("v.mp4", b"\0" * (91 * 1024 * 1024), content_type="video/mp4")
        with patch("urllib.request.urlopen") as m:
            with self.assertRaises(SuspiciousFileOperation):
                self._storage()._save("evidence/v.mp4", big)
            m.assert_not_called()

    def test_open_downloads_via_cdn(self):
        def fake_urlopen(req, timeout=30):
            self.assertIn("raw.githubusercontent.com", req.full_url)
            return FakeResp(GIF, 200)

        with patch("urllib.request.urlopen", fake_urlopen):
            f = self._storage()._open("evidence/x.gif")
        self.assertEqual(f.read(), GIF)

    def test_save_overwrite_retries_with_sha(self):
        import io
        import json as _json
        import urllib.error

        calls = []

        def fake_urlopen(req, timeout=30):
            calls.append((_json.loads(req.data.decode()) if req.data else {}, req.get_method()))
            if req.get_method() == "PUT" and "sha" not in (calls[-1][0]):
                raise urllib.error.HTTPError(
                    req.full_url, 422, "Unprocessable", {}, io.BytesIO(b'{"message":"sha required"}'))
            if req.get_method() == "GET":
                return FakeResp({"sha": "oldsha", "size": 10}, 200)
            return FakeResp({"content": {"sha": "new"}}, 201)

        with patch("urllib.request.urlopen", fake_urlopen):
            name = self._storage()._save("evidence/x.gif", SimpleUploadedFile("x.gif", GIF))
        self.assertEqual(name, "evidence/x.gif")
        puts = [c for c in calls if c[1] == "PUT"]
        self.assertEqual(len(puts), 2)
        self.assertEqual(puts[1][0]["sha"], "oldsha")

class GitHubSaveCycleTests(TestCase):
    """End-to-end regression for the reported traceback: ev.file.save(...,
    save=True) re-enters instance.save() with no cached file object, against
    the remote backend. Fully mocked — no network."""

    def test_fieldfile_save_cycle_with_remote_backend(self):
        from core.models import Report, ReportEvidence

        def fake_urlopen(req, timeout=30):
            url = req.full_url
            if "api.github.com" in url:
                if req.get_method() == "GET":
                    return FakeResp({"sha": "s", "size": len(GIF)}, 200)
                return FakeResp({"content": {"sha": "n"}}, 201)
            return FakeResp(GIF, 200)  # raw CDN download

        field_storage = ReportEvidence._meta.get_field("file").storage
        field_storage._real = None
        self.addCleanup(setattr, field_storage, "_real", None)
        with self.settings(EVIDENCE_STORAGE="github",
                           GITHUB_EVIDENCE_REPO="o/r",
                           GITHUB_EVIDENCE_TOKEN="t"):
            with patch("urllib.request.urlopen", fake_urlopen):
                rep = Report.objects.create(
                    title="T", description="D", category="bribery", location_text="L")
                ev = ReportEvidence(report=rep, kind="image")
                ev.file.save("x.gif", SimpleUploadedFile("x.gif", GIF), save=True)
        ev.refresh_from_db()
        self.assertTrue(ev.file.name.startswith("evidence/"))
        self.assertEqual((ev.width, ev.height), (1, 1))


class SiteNoticeTests(TestCase):
    def test_active_notice_shows(self):
        from core.models import SiteNotice

        SiteNotice.objects.create(key="headline", message="Courts resume Monday.", is_active=True)
        r = self.client.get("/")
        self.assertContains(r, "Courts resume Monday.")
        self.assertContains(r, "safety-strip")

    def test_inactive_notice_hidden(self):
        from core.models import SiteNotice

        SiteNotice.objects.create(key="headline", message="You should not see this.", is_active=False)
        r = self.client.get("/")
        self.assertNotContains(r, "You should not see this.")
        self.assertNotContains(r, "safety-strip")

    def test_window_respected(self):
        from core.models import SiteNotice

        SiteNotice.objects.create(
            key="future", message="Not yet.", is_active=True,
            starts_at=timezone.now() + timedelta(days=1),
        )
        SiteNotice.objects.create(
            key="past", message="Gone.", is_active=True,
            ends_at=timezone.now() - timedelta(days=1),
        )
        r = self.client.get("/")
        self.assertNotContains(r, "Not yet.")
        self.assertNotContains(r, "Gone.")

    def test_lowest_order_wins(self):
        from core.models import SiteNotice

        SiteNotice.objects.create(key="b", message="Second.", is_active=True, order=5)
        SiteNotice.objects.create(key="a", message="First.", is_active=True, order=1)
        r = self.client.get("/")
        self.assertContains(r, "First.")
        self.assertNotContains(r, "Second.")


class NavTests(TestCase):
    def test_anonymous_nav(self):
        r = self.client.get("/")
        self.assertContains(r, "Corps Login")
        self.assertContains(r, "More")
        self.assertNotContains(r, "Your Desk")

    def test_officer_nav_single_row(self):
        officer = User.objects.create_user("officer9", password="x" * 12)
        self.client.force_login(officer)
        r = self.client.get("/")
        html = r.content.decode()
        self.assertContains(r, "Your Desk")
        self.assertContains(r, "Log Out")
        self.assertContains(r, "officer9")
        # auth-specific items ride in dropdowns, not loose top-level links
        self.assertNotContains(r, "officer-chip")
        self.assertIn("nav-drop nav-user", html)


class ServerSettingsTests(TestCase):
    def setUp(self):
        import os
        import tempfile

        fd, self.env_path = tempfile.mkstemp(suffix=".env")
        with os.fdopen(fd, "w") as f:
            f.write("DJANGO_DEBUG=True\n")
        self.override = self.settings(ENV_FILE=self.env_path)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.addCleanup(os.unlink, self.env_path)
        self.admin = User.objects.create_superuser("root", password="x" * 12)
        self.staff = User.objects.create_user("clerk", password="x" * 12, is_staff=True)

    def test_helper_roundtrip(self):
        from core.server_config import current_state, write_debug_value

        self.assertEqual(current_state()["debug_stored"], "True")
        write_debug_value(False)
        self.assertEqual(current_state()["debug_stored"], "False")

    def test_superuser_can_toggle(self):
        self.client.force_login(self.admin)
        r = self.client.get("/admin/server-settings/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Debug Mode")
        self.client.post("/admin/server-settings/", {"debug": "off"})
        with open(self.env_path) as f:
            self.assertIn("DJANGO_DEBUG='False'", f.read().replace('"', "'"))

    def test_staff_and_anonymous_blocked(self):
        self.assertEqual(self.client.get("/admin/server-settings/").status_code, 302)  # login
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get("/admin/server-settings/").status_code, 403)
