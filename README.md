# Silent Shield — anonymous anti-corruption reporting

> **Going live? Read [GUIDE.md](GUIDE.md)** — token scopes, server setup,
> HTTPS, backups, and the go-live checklist live there.

File corruption and crime reports **fully anonymously** with photo / video / audio
evidence. Reports go **live instantly** as *Awaiting Justice*. Corps officers
(logins only, no public registration) claim cases exclusively, and close them with
proof. Claims auto-release after 10 months. A vetted guardian (ethical-hacker)
marketplace and a privacy-safe sponsorship system fund the operation.

## Stack

Django 6 · vanilla JS · pure CSS · SQLite (dev) · UV package manager.

## Quickstart (UV best practices)

```powershell
uv sync
Copy-Item .env.example .env
uv run python manage.py migrate
uv run python manage.py seed_demo
uv run python manage.py createsuperuser   # admin provisions corps logins
uv run python manage.py runserver
```

Open http://127.0.0.1:8000.

## Evidence storage (local default, GitHub demo, S3 later)

`ReportEvidence.file` uses `core.storages.ConfiguredEvidenceStorage`, which
resolves the backend lazily from `EVIDENCE_STORAGE`:

| Mode | Env | Behaviour |
|---|---|---|
| `local` (default) | — | `MEDIA_ROOT/evidence/YYYY/MM/<uuid>.<ext>` |
| `github` (demo only) | `GITHUB_EVIDENCE_REPO=owner/repo`, `GITHUB_EVIDENCE_TOKEN=ghp_…`, `GITHUB_EVIDENCE_BRANCH=main` | commit-on-upload via Contents API, served from `raw.githubusercontent.com` |

Demo limits (enforced in code): 90 MB cap, no video seeking on raw links,
git history retains "deleted" blobs. EXIF/GPS scrubbing happens in memory
*before* persist, so no backend ever receives metadata bytes.

**Going to S3 later:** add `django-storages[s3]`, point a new backend at the
same `upload_to` layout in `get_evidence_storage()`, migrate existing files —
no model, form, or template changes needed (filenames are already uuid-based).

## Corps accounts (no public register)

Officers never self-register. An admin creates the `User` in
`/admin/` (a blank `OfficerProfile` with badge ID is attached inline —
fill badge/department/rank), then hands over the credentials.
Officers log in at `/corps/login/` and land on `/dashboard/` (case desk).

## Case lifecycle

1. **File anonymously** at `/file-report/` — photo or video required
   (audio alone rejected), up to 12 files. EXIF stripped, filenames randomised,
   no name / account / IP stored.
2. **Live immediately** as *Awaiting Justice* (`pending`).
3. **Claim** — first logged-in officer wins; the row is locked
   (`select_for_update`) so a second claim fails.
4. **Resolve** — the holder posts a note + ≥1 proof file (video/audio/image).
5. **Auto-release** — claims older than `CLAIM_TTL_DAYS` (default 300 ≈ 10
   months) revert to pending, via lazy checks on every view plus
   `uv run python manage.py release_stale_claims` (run daily via cron).

## Guardian marketplace (`/guardians/`)

- Only `is_verified + is_listed` profiles render publicly.
- Public fields: nickname, tagline, bio, skills, services, price, relay handle.
- `private_identity_ref` exists on the model but is **superuser-only in admin**
  and never rendered in templates.
- Contact is a blind relay (`ContactRequest`): visitors leave subject/message
  (+ optional throwaway callback); the team connects both sides.
- Ratings are authored by staff (`HackerRating.created_by`), averaged onto the profile.

## Ads (`/advertise/`, slots via `{% render_ad_slot %}`)

Self-hosted, contextual-only sponsorships modelled on famous publishers:

| Slot key | Placement | Size |
|---|---|---|
| `header-leaderboard` | under header | 970×250 |
| `feed-inline` | inside feeds | 728×90 |
| `sidebar-box` | rail | 300×600 |
| `marketplace-sidebar` | guardian rail | 300×250 |

- Weighted-random rotation among *live* campaigns (schedule + caps respected).
- Viewability beacons (`IntersectionObserver` → `POST /ads/imp/<id>/`),
  click redirect (`/ads/click/<id>/`), dismiss (`/ads/dismiss/<id>/`).
- Frequency capping in `localStorage` (client-side); server stores aggregate
  counts only — no IP / UA / fingerprint, preserving reporter anonymity.
- Every unit is labelled “Advertisement” and dismissible. Optional per-campaign
  `embed_html` supports AdSense-style snippets; seeded default is first-party
  creatives only (zero third-party requests).

## Custom pages & nav

Public: home, live reports, file-a-report, guardians, protection guide,
advertise, about. Authed officers additionally get **Case desk** in the nav,
plus claim / release / resolve actions on case pages. No register links anywhere.

## Anonymity notes (read before operating)

- Do not add analytics, fonts, or captcha providers — any third-party request
  can de-anonymise reporters. The frontend ships zero external requests.
- Media: cap sizes in `.env` (`MAX_IMAGE_MB` etc.); files land in
  `media/evidence/YYYY/MM/<uuid>.<ext>`.
- Backups and server access logs are the remaining identification risk —
  rotate them aggressively and restrict access (see `core/logging.py` filter).
- For production set `DJANGO_DEBUG=False`, a strong `DJANGO_SECRET_KEY`,
  `DATABASE_URL` (Postgres), and serve `staticfiles/` + `media/` via hardened storage.

## Tests

```powershell
uv run python manage.py test
```
