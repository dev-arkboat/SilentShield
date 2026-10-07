# Silent Shield — Production Setup Guide

From zero to a live, hardened server. Read top to bottom the first time;
after that, each section stands alone.

Contents: [Token](#1-github-token--demo-evidence-backend) ·
[Server](#2-server-prep) · [Install](#3-install) · [Env](#4-environment-file)
· [Database](#5-database) · [First boot](#6-first-boot) ·
[HTTPS](#7-gunicorn--nginx--https) · [Cron & backups](#8-cron--backups) ·
[Checklist](#9-go-live-checklist) · [S3](#10-s3-later) · [Ops](#11-day-to-day-ops)
· [Troubleshooting](#12-troubleshooting)

---

## 1. GitHub token — demo evidence backend

Only needed if `EVIDENCE_STORAGE=github` (demo mode; production uses S3 —
see §10). Give the token the **smallest possible** permissions:

1. GitHub → Settings → Developer settings → **Personal access tokens →
   Fine-grained tokens** → Generate new token.
2. **Resource owner:** your account (or org).
3. **Repository access:** *Only select repositories* → pick **exactly one**:
   your evidence repo (e.g. `you/shield-evidence-demo`).
4. **Repository permissions:** set **Contents → Read and write**.
   Leave *everything else* (Actions, Issues, Pull requests, Workflows,
   Administration…) at *No access*. No Account permissions at all.
5. Expiry: 90 days or less; rotate with a calendar reminder.

Why these: the backend only calls the **Contents API** — `PUT` to commit a
file, `GET` (for the blob SHA) and `DELETE` to remove one. Reads in templates
use unauthenticated `raw.githubusercontent.com` links, so the token is only
ever used server-side on upload/delete.

Rules for the demo repo itself:

- **Public.** Raw links work without credentials only on public repos.
  (Private repos would need signed URLs — one more reason this is demo-only.)
- **Initialize it** with any commit (a README). The Contents API cannot
  create the very first commit on a truly empty repo's `main` branch.
- Name the branch to match `GITHUB_EVIDENCE_BRANCH` (default `main`).
- Never reuse a repo that holds other code — evidence commits share its
  history. Never commit the token anywhere; it lives only in the server `.env`.

Do **not** use a *classic* token if you can avoid it: its `repo` scope grants
full control over **all** your repositories. If you must (old GitHub
Enterprise), scope it to `repo` and rotate it immediately after demoing.

---

## 2. Server prep

Ubuntu 24.04 LTS, 2 GB RAM minimum, domain pointed at the server (A record).

```bash
sudo apt update && sudo apt install -y git nginx certbot python-certbot-nginx postgresql postgresql-contrib
curl -LsSf https://astral.sh/uv/install.sh | sh   # restart shell afterwards
```

Postgres (skip if you accept sqlite — see §5, not recommended for prod):

```bash
sudo -u postgres psql -c "CREATE USER shield WITH PASSWORD 'REPLACE-WITH-STRONG-PASSWORD';"
sudo -u postgres psql -c "CREATE DATABASE shield OWNER shield;"
```

---

## 3. Install

```bash
sudo useradd -m -s /bin/bash shield
sudo -i -u shield
git clone <your-repo-url> /home/shield/app && cd /home/shield/app
uv sync
cp .env.example .env
```

---

## 4. Environment file

Edit `/home/shield/app/.env`. Full reference:

```ini
# Random 50+ chars. Generate:  uv run python -c "import secrets; print(secrets.token_urlsafe(64))"
DJANGO_SECRET_KEY=PASTE-GENERATED-VALUE
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=shield.example.org
DJANGO_CSRF_TRUSTED_ORIGINS=https://shield.example.org

# Postgres when set, local sqlite when absent (verified fallback):
DATABASE_URL=postgres://shield:STRONG-PASSWORD@localhost:5432/shield

CLAIM_TTL_DAYS=300
MAX_IMAGE_MB=10
MAX_VIDEO_MB=100
MAX_AUDIO_MB=20
EVIDENCE_STORAGE=local
```

Notes:

- `DJANGO_DEBUG` can later be flipped from the admin panel
  (`/admin/server-settings/`, superusers only) — it rewrites this file and
  asks for a restart. It is deliberately **not** a live toggle: Django bakes
  DEBUG in at startup, and flipping it per-request would be unsafe.
- `DJANGO_CSRF_TRUSTED_ORIGINS` must list your exact `https://` origin or
  admin/officer logins will fail CSRF checks behind HTTPS.

---

## 5. Database

- `DATABASE_URL` **present** → Postgres (or any `dj-database-url` scheme).
  Verify parsing any time with:
  `uv run python manage.py check` (fails fast on a bad URL at startup).
- `DATABASE_URL` **absent** → local `db.sqlite3` fallback (verified:
  engine resolves to `django.db.backends.sqlite3` with no variable set).
  Fine for demos; do not run a public site on it — concurrent writes lock it.

---

## 6. First boot

```bash
cd /home/shield/app
uv run python manage.py migrate
uv run python manage.py collectstatic --noinput
uv run python manage.py createsuperuser        # your admin login
# Do NOT run seed_demo in prod — it creates sample reports and house ads.
```

Then open `/admin/` and, as superuser:

1. **Users → add officers.** Fill username/password, tick *Staff status* (NOT
   superuser), save, then fill the inline *Officer profile* (badge ID,
   department, rank). Hand credentials to the officer in person.
2. **Site notices → the seeded headline is absent in prod** (seed is
   demo-only), so add one if you want the bar under the nav — or leave it
   empty and no bar renders.
3. **Sponsorships → ad slots/campaigns** as needed (all optional; missing
   slots render nothing).

---

## 7. Gunicorn + nginx + HTTPS

Systemd unit `/etc/systemd/system/shield.service`:

```ini
[Unit]
Description=Silent Shield (gunicorn)
After=network.target postgresql.service

[Service]
User=shield
WorkingDirectory=/home/shield/app
EnvironmentFile=/home/shield/app/.env
ExecStart=/home/shield/.local/bin/uv run gunicorn AntiCorruption.wsgi:application \
  --bind 127.0.0.1:8000 --workers 3 --timeout 120
Restart=always

[Install]
WantedBy=multi-user.target
```

nginx site `/etc/nginx/sites-available/shield` (symlink to `sites-enabled`):

```nginx
server {
    listen 80;
    server_name shield.example.org;
    client_max_body_size 110m;  # above MAX_VIDEO_MB

    location /static/ { alias /home/shield/app/staticfiles/; expires 30d; }
    location /media/  { alias /home/shield/app/media/; expires 7d; }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Then:

```bash
sudo systemctl enable --now shield
sudo certbot --nginx -d shield.example.org   # HTTPS; HSTS + secure cookies auto-apply (DEBUG=False)
```

Static files are fingerprinted (`CompressedManifestStaticFilesStorage`) and
served by WhiteNoise/nginx; templates use `{% static %}` so hashes resolve.

---

## 8. Cron & backups

Stale-claim release (10-month rule), daily at 03:00 as user `shield`:

```bash
crontab -e
# 0 3 * * * cd /home/shield/app && /home/shield/.local/bin/uv run python manage.py release_stale_claims >> /home/shield/cron.log 2>&1
```

Backups (daily — database **and** `media/`; a DB dump without evidence files
is a room full of empty frames):

```bash
pg_dump "postgres://shield:PASSWORD@localhost:5432/shield" | gzip > /home/shield/backups/db-$(date +%F).sql.gz
rsync -a /home/shield/app/media/ /home/shield/backups/media/
```

Keep 14 days, copy one weekly off-site. Test a restore quarterly.

---

## 9. Go-live checklist

- [ ] `DJANGO_DEBUG=False` effective (check `/admin/server-settings/`).
- [ ] `DJANGO_SECRET_KEY` generated, unique, never committed.
- [ ] `ALLOWED_HOSTS` + `CSRF_TRUSTED_ORIGINS` list the real domain.
- [ ] HTTPS works; admin login succeeds (proves CSRF origins right).
- [ ] `collectstatic` ran; CSS/JS load with hashed filenames.
- [ ] At least one superuser; officers provisioned as **staff, not superuser**.
- [ ] Cron installed; a trial `release_stale_claims` run logged.
- [ ] Backup + restore rehearsed once.
- [ ] No `.env`, `db.sqlite3`, or `media/` in git (`git status` clean of secrets).
- [ ] Server access logs rotated aggressively (they can see IPs even though
      the app stores none — restrict who can read them).

---

## 10. S3 later

1. `uv add "django-storages[s3]"` (+ `boto3` comes along).
2. In `core/storages.py`, extend `get_evidence_storage()` with an `s3` branch
   returning `S3Storage` (bucket, region, credentials from env).
3. Copy existing `media/evidence/**` to the bucket preserving paths
   (filenames are already uuid-based, so nothing else changes).
4. Set `EVIDENCE_STORAGE=s3`, restart. No model/form/template changes needed.

EXIF scrubbing already happens in memory pre-upload, so S3 never receives
metadata bytes either.

---

## 11. Day-to-day ops

- **Reports:** none needed — they publish themselves. Officers claim from
  `/dashboard/`; stale claims free up automatically (lazy check + cron).
- **Notices:** `/admin/` → Site notices (message, level, schedule, order).
- **Debug:** `/admin/server-settings/` (superuser), then
  `sudo systemctl restart shield`.
- **Guardians:** add `HackerProfile` with `is_verified` OFF; flip it ON only
  after identity checks. Ratings are staff-authored. `private_identity_ref`
  is superuser-visible only — never rendered publicly.
- **Ads:** Sponsorships → slots/campaigns; delivery, caps, and aggregate
  counts are automatic.
- **Health:** `systemctl is-active shield` + one HTTP check on `/` (any
  uptime monitor). Logs: `journalctl -u shield -f`.

---

## 12. Troubleshooting

| Symptom | Cause → Fix |
|---|---|
| `DisallowedHost` 400 | Domain missing from `DJANGO_ALLOWED_HOSTS` → add, restart. |
| Admin login “CSRF verification failed” | Origin missing → set `DJANGO_CSRF_TRUSTED_ORIGINS=https://…`, restart. |
| CSS/JS 404 in prod | `collectstatic` not run, or nginx `/static/` path wrong → rerun, check alias. |
| `Missing staticfiles manifest entry` | Dev/test without collected files → normal; prod always runs `collectstatic`. |
| Uploads fail to GitHub backend | Token scopes (§1), repo public + initialized, file ≤90 MB. |
| DB connection refused | `DATABASE_URL` typo / Postgres down → `pg_isready`, check `check` output. |
| Counts look stale after `.env` edit | Every `.env` change needs `systemctl restart shield`. |
