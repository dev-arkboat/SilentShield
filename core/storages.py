"""Evidence storage backends.

EVIDENCE_STORAGE=local (default) -> FileSystemStorage under MEDIA_ROOT.
EVIDENCE_STORAGE=github (demo)   -> commit-on-upload to a GitHub repo,
                                    served via raw.githubusercontent.com.

The github backend exists so demos run without disk/S3; production must
switch to S3-compatible storage. Demo limits, enforced or stated here:
- GitHub caps blobs at 100 MB -> backend refuses anything over 90 MB up
  front (use S3 for real video).
- raw.githubusercontent.com has no range-request support -> seeking in
  <video>/<audio> is poor. Demo only.
- Git history is append-only -> delete() removes the working-tree file
  but the blob persists in history. Documented, not hidden.

Backend choice is lazy (ConfiguredEvidenceStorage resolves on first use)
so no repo/token secret ever lands in a migration file.
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, SuspiciousFileOperation
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage, Storage


class GitHubRepoStorage(Storage):
    """Minimal Storage over the GitHub Contents API. Stdlib only, no new deps."""

    API = "https://api.github.com"
    RAW = "https://raw.githubusercontent.com"
    MAX_BYTES = 90 * 1024 * 1024

    def __init__(self, repo: str = "", token: str = "", branch: str = "main"):
        self.repo = (repo or "").strip().strip("/")
        self.token = (token or "").strip()
        self.branch = (branch or "main").strip() or "main"
        if "/" not in self.repo or not self.token:
            raise ImproperlyConfigured(
                "GitHub evidence storage needs "
                "GITHUB_EVIDENCE_REPO='owner/repo' and GITHUB_EVIDENCE_TOKEN."
            )

    # -- HTTP ------------------------------------------------------------
    def _request(self, method: str, path: str, payload: dict | None = None, query: str = ""):
        url = f"{self.API}/repos/{self.repo}/contents/{urllib.parse.quote(path)}"
        if query:
            url += "?" + query
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode() if payload is not None else None,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/json",
                "User-Agent": "silent-shield-demo",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as res:
                return json.loads(res.read().decode() or "{}"), res.status
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")[:300]
            raise SuspiciousFileOperation(f"GitHub API {method} failed ({e.code}): {body}") from e

    # -- Storage API -----------------------------------------------------
    def _save(self, name: str, content) -> str:
        content.seek(0)
        raw = content.read()
        if len(raw) > self.MAX_BYTES:
            raise SuspiciousFileOperation(
                f"Refusing {len(raw)}-byte upload: demo GitHub backend caps at 90 MB (use S3 for video)."
            )
        payload = {"message": f"evidence upload {name} (automated demo)",
                   "content": base64.b64encode(raw).decode(),
                   "branch": self.branch}
        try:
            self._request("PUT", name, payload)
        except SuspiciousFileOperation as e:
            if "422" not in str(e):  # path exists (e.g. re-PUT) -> overwrite needs its sha
                raise
            data, _ = self._request("GET", name, query=f"ref={urllib.parse.quote(self.branch)}")
            if not data.get("sha"):
                raise
            payload["sha"] = data["sha"]
            self._request("PUT", name, payload)
        return name

    def _open(self, name: str, mode: str = "rb"):
        # Reads go over the public CDN (no token in HTML); needed so model
        # save() cycles and admin downloads work on remote files.
        req = urllib.request.Request(self.url(name), headers={"User-Agent": "silent-shield-demo"})
        try:
            with urllib.request.urlopen(req, timeout=30) as res:
                return ContentFile(res.read(), name=urllib.parse.unquote(name.rsplit("/", 1)[-1]))
        except urllib.error.HTTPError as e:
            raise FileNotFoundError(f"GitHub raw fetch failed ({e.code}): {name}") from e

    def exists(self, name: str) -> bool:
        return False  # names are uuid-randomised upstream; skip the existence round-trip

    def delete(self, name: str) -> None:
        try:
            data, _ = self._request("GET", name, query=f"ref={urllib.parse.quote(self.branch)}")
            if data.get("sha"):
                self._request("DELETE", name, {
                    "message": f"remove {name} (automated demo)",
                    "sha": data["sha"], "branch": self.branch})
        except SuspiciousFileOperation:
            pass  # best-effort; history retains the blob regardless (demo caveat)

    def url(self, name: str) -> str:
        return f"{self.RAW}/{self.repo}/{urllib.parse.quote(self.branch)}/{urllib.parse.quote(name)}"

    def size(self, name: str) -> int:
        data, _ = self._request("GET", name, query=f"ref={urllib.parse.quote(self.branch)}")
        return int(data.get("size", 0))

    def listdir(self, path: str):
        raise NotImplementedError("Demo backend: directory listing not supported.")


def get_evidence_storage() -> Storage:
    if getattr(settings, "EVIDENCE_STORAGE", "local") == "github":
        return GitHubRepoStorage(
            repo=getattr(settings, "GITHUB_EVIDENCE_REPO", ""),
            token=getattr(settings, "GITHUB_EVIDENCE_TOKEN", ""),
            branch=getattr(settings, "GITHUB_EVIDENCE_BRANCH", "main"),
        )
    return FileSystemStorage()


class ConfiguredEvidenceStorage(Storage):
    """Migration-safe proxy: resolves local-vs-github on first use (no secrets in migrations)."""

    def __init__(self):
        self._real: Storage | None = None

    def deconstruct(self):
        # No args, no secrets — safe to freeze into migrations.
        return ("core.storages.ConfiguredEvidenceStorage", [], {})

    @property
    def _backend(self) -> Storage:
        if self._real is None:
            self._real = get_evidence_storage()
        return self._real

    def _open(self, name, mode="rb"):
        return self._backend._open(name, mode)

    def _save(self, name, content):
        return self._backend._save(name, content)

    def exists(self, name):
        return self._backend.exists(name)

    def delete(self, name):
        return self._backend.delete(name)

    def url(self, name):
        return self._backend.url(name)

    def size(self, name):
        return self._backend.size(name)

    def listdir(self, path):
        return self._backend.listdir(path)

    def get_available_name(self, name, max_length=None):
        return self._backend.get_available_name(name, max_length=max_length)
