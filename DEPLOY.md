# Deploying the backend to Render (free)

This repo is ready to deploy as a free Render web service with automatic HTTPS.

## Steps

1. Push this branch and merge it (or deploy the branch directly).
2. Go to <https://dashboard.render.com> → **New** → **Blueprint** → connect your
   GitHub and pick the `Al-Hashimi` repo. Render reads `render.yaml`.
3. Click **Apply**. Render runs `build.sh` (installs deps, collects static,
   migrates the SQLite DB) and starts gunicorn. First build takes a few minutes.
4. Your API is live at `https://al-hashimi-api.onrender.com` (the exact name is
   shown in the dashboard). Check `https://<that-host>/admin/` loads.

## Create an admin login

In the service's **Environment** tab add (then "Manual Deploy" once):
`DJANGO_SUPERUSER_USERNAME`, `DJANGO_SUPERUSER_PASSWORD`, `DJANGO_SUPERUSER_EMAIL`.
`build.sh` creates the superuser on the next deploy.

## After the frontend is deployed

Set these on the API service (Environment tab) to the frontend's URL, then
redeploy:
- `CORS_ALLOW_ALL_ORIGINS` → `false`
- `CORS_ALLOWED_ORIGINS` → `https://<your-frontend>.onrender.com`
- `CSRF_TRUSTED_ORIGINS` → `https://<your-frontend>.onrender.com`

## Known free-tier limits (fine for testing)

- The service **sleeps after ~15 min idle**; the next request wakes it (~50s).
- **SQLite resets on every deploy** (ephemeral disk). For durable data later,
  switch to Render PostgreSQL (free for 30 days) — the settings already read a
  `DATABASE_URL`-style config easily; ask and I'll wire it.
- **Uploaded product images** (media/) are also lost on redeploy. Use an object
  store (e.g. Cloudinary free tier) for durable media later.
