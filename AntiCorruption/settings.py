"""
Django settings for AntiCorruption project (Silent Shield).
Best practices: env-driven config, no reporter PII stored by design,
system-font frontend (no third-party trackers), file validation limits.
"""

import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "django-insecure-dev-only-change-me")
DEBUG = os.getenv("DJANGO_DEBUG", "True").lower() in ("1", "true", "yes")
ALLOWED_HOSTS = [h.strip() for h in os.getenv("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",") if h.strip()]
CSRF_TRUSTED_ORIGINS = [o.strip() for o in os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()]
# Optional override for tooling/tests: path of the .env file the admin editor writes.
ENV_FILE = os.getenv("ENV_FILE", str(BASE_DIR / ".env"))

INSTALLED_APPS = [
    "jazzmin",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "core",
    "marketplace",
    "ads",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "AntiCorruption.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.site_notice",
                "ads.context_processors.ad_slots",
            ],
        },
    },
]

WSGI_APPLICATION = "AntiCorruption.wsgi.application"

DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# Evidence storage: "local" (default, MEDIA_ROOT) or "github" (demo only —
# commits uploads to a repo and serves raw links; production must use S3).
EVIDENCE_STORAGE = os.getenv("EVIDENCE_STORAGE", "local").lower()
GITHUB_EVIDENCE_REPO = os.getenv("GITHUB_EVIDENCE_REPO", "")
GITHUB_EVIDENCE_TOKEN = os.getenv("GITHUB_EVIDENCE_TOKEN", "")
GITHUB_EVIDENCE_BRANCH = os.getenv("GITHUB_EVIDENCE_BRANCH", "main")

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    # Hashed filenames in prod (collectstatic); plain files in dev/test.
    "staticfiles": {
        "BACKEND": (
            "whitenoise.storage.CompressedManifestStaticFilesStorage"
            if not DEBUG
            else "django.contrib.staticfiles.storage.StaticFilesStorage"
        )
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "home"

# --- Domain constants -----------------------------------------------------
# 10 months ≈ 300 days. A claimed case auto-releases after this TTL if unresolved.
CLAIM_TTL_DAYS = int(os.getenv("CLAIM_TTL_DAYS", "300"))

# Per-file upload caps (bytes). Enforced in forms + model clean.
MAX_IMAGE_MB = int(os.getenv("MAX_IMAGE_MB", "10"))
MAX_VIDEO_MB = int(os.getenv("MAX_VIDEO_MB", "100"))
MAX_AUDIO_MB = int(os.getenv("MAX_AUDIO_MB", "20"))

DATA_UPLOAD_MAX_NUMBER_OF_FIELDS = 2000
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10 MB in-memory, rest to disk

# Anonymity: never store reporter IP / user-agent. Views must NOT read
# request.META["REMOTE_ADDR"] for reports. Counts only, no fingerprinting.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"no_ip": {"()": "core.logging.NoIPFilter"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "filters": ["no_ip"]}},
    "root": {"handlers": ["console"], "level": "INFO"},
}

if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "no-referrer"

JAZZMIN_SETTINGS = {
    "site_title": "Silent Shield Ops",
    "site_header": "Silent Shield Ops",
    "site_brand": "Silent Shield",
    "welcome_sign": "Corps sign-in — officer accounts are provisioned by admins only.",
}
