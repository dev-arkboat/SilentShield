"""Server runtime config edited from the admin panel.

Why a file write + restart instead of a live toggle: Django reads DEBUG
at startup in dozens of places (template caching, error pages, static
handling, host checks). Flipping it per-request at runtime is thread-unsafe
and lies about what is actually active. So this module persists the desired
value to the .env file and the UI tells the operator to restart — same
contract as a router admin page ("saved, reboot to apply").
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from dotenv import dotenv_values, set_key


def env_file() -> Path:
    return Path(getattr(settings, "ENV_FILE", Path(settings.BASE_DIR) / ".env"))


def current_state() -> dict:
    """Effective runtime values + what is persisted on disk."""
    stored = dotenv_values(env_file()).get("DJANGO_DEBUG")
    db_url = __import__("os").getenv("DATABASE_URL", "")
    engine = "postgresql" if db_url else "sqlite (fallback — no DATABASE_URL)"
    return {
        "debug_effective": bool(settings.DEBUG),
        "debug_stored": stored,  # None => file has no entry (env/default wins)
        "debug_checked": (stored.lower() in ("1", "true", "yes")) if stored is not None else bool(settings.DEBUG),
        "env_file": str(env_file()),
        "env_exists": env_file().exists(),
        "database": engine,
        "allowed_hosts": list(getattr(settings, "ALLOWED_HOSTS", [])),
    }


def write_debug_value(on: bool) -> Path:
    path = env_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.touch()
    set_key(str(path), "DJANGO_DEBUG", "True" if on else "False")
    return path
