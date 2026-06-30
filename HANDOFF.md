# Al-Hashimi (الهاشمي / Black Rock) — Backend Handoff

> Continue on any device after `git clone`. **Secrets are NOT in this file** — the
> repo is public. Recreate `.env` from the values your assistant gave you (or your
> password manager). Session: `eab2bfbf-d91e-405c-b750-c7d568376aa6`.
> Last updated: 2026-06-30.

## What this is
Battery warehouse system. One warehouse + four stores; each store is a **customer**
who withdraws batteries (**orders/bills**), returns scrap (**supplement**, adds to
what they owe), and makes **payments** (reduce it). Arabic / RTL. App name **Black Rock**.

## Repos & branches
| Part | Repo | Branch |
|---|---|---|
| Backend | `github.com/tahaghazi/Al-Hashimi` (PUBLIC) | `improvement/backend-modernization` |
| Frontend | `github.com/Mo7ammedAzzam/Al-Hashimi-frontend` (private) | `improvement/frontend-modernization` |

Frontend also has a fuller `SESSION_NOTES.md` at its root.

## Live servers
| | Primary | Old |
|---|---|---|
| IP | 64.226.96.164 | 134.209.212.2 |
| URL | https://64-226-96-164.sslip.io | https://134-209-212-2.sslip.io |
| Stack | gunicorn (systemd `al-hashimi-api`) + pm2 (`al-hashimi-web`, SPA) + nginx + Let's Encrypt | same family |
| DB | fresh SQLite | live data |

Backend at `/opt/al-hashimi/backend` (venv, gunicorn 127.0.0.1:8000, EnvironmentFile=.env).
Frontend static SPA at `/opt/al-hashimi/frontend/public` served by `pm2 serve --spa` on :3000.
nginx: `/`→3000, `/api`,`/admin`→8000, `/static`,`/media`→alias dirs.

## Stack
Django 5.2 + DRF + SQLite + JWT (simplejwt + dj-rest-auth + allauth). Apps: `users`
(CustomUser/roles/audit/backups), `products`, `orders` (Order/OrderItem/UserBalance/
revisions/exports). Python 3.13 venv. Tests: `manage.py test` (25 passing).

## Start on a new device
```bash
git clone https://github.com/tahaghazi/Al-Hashimi
cd Al-Hashimi && git checkout improvement/backend-modernization
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt
# create .env (see "Secrets to recreate" below)
.venv/Scripts/python manage.py migrate
.venv/Scripts/python manage.py test
```
Frontend: clone the frontend repo, `git checkout improvement/frontend-modernization`,
`npm install`, `npx nuxt generate` → `.output/public`.

## Deploy (from dev machine, paramiko; set PYTHONIOENCODING=utf-8)
- Backend: `cd /opt/al-hashimi/backend && git reset --hard origin/improvement/backend-modernization && venv/bin/pip install -r requirements.txt && venv/bin/python manage.py migrate && systemctl restart al-hashimi-api`
- Frontend: `npx nuxt generate` → `tar -czf spa.tar.gz -C .output/public .` → upload → extract into `/opt/al-hashimi/frontend/public` → `pm2 restart al-hashimi-web`
- **Do NOT reset the admin password on deploy** (use a deploy script with no `set_password`).
- **Windows build gotcha:** never `cd` into `.output/public` in a persistent shell (locks the dir → `EBUSY`); tar with `-C` from the repo root.
- `db.sqlite3` is gitignored on the server, so `git reset --hard` preserves live data.

## Secrets to recreate in `.env` (values NOT in this repo)
```
DJANGO_DEBUG, DJANGO_SECRET_KEY, DJANGO_ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS,
CORS_ALLOW_ALL_ORIGINS,
R2_ENDPOINT, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET
```
Plus (not Django settings, keep in your password manager): server root passwords,
Cloudflare Account ID + API token, app super-admin logins.

## Features delivered (all live)
RBAC (super_admin/manager/staff) + staff management; append-only audit log; invoice
revisions (in-place edit, unlimited, history + rollback); **invoices editable to any
value incl. net credit — difference flows to the customer balance (can go negative)**;
offline-first (outbox + read-through cache + drafts); Excel financial export; daily
backups (cron 02:30) + **Cloudflare R2 off-site (active)**; biometric app-lock; barcode
scanning (shows a clear "not supported" notice where unavailable); PWA install/auto-update/
pull-to-refresh/immersive chrome; self-service password change (old+new, live validation,
popup modal); `discount_note` on invoices; **print invoice shows previous-invoices total,
all-invoices total, amount paid, and remaining due — matching the customer page**.

## Edit gating (where the ✏️ lives)
Edit button only on the per-customer bills (`/users/[id]` → الفواتير). The global
`/orders` list is view/print only. Offline-pending bills can't be edited until synced.

## Pending / ideas
- Push notifications deferred (py-vapid needs cryptography>=46 but app pins 44 for
  allauth/JWT; needs a device + auth regression). Workbox importScripts is the safe path.
- Optional: edit button on the global `/orders` list; "in-tab vs installed" install nudge;
  discount_note column in the Excel export.

## Open question
Scrap/`supplement` currently ADDS to what a customer owes (`amount_to_pay = total +
supplement - discount`). Confirm this is the intended direction.
