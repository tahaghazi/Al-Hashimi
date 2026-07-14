#!/usr/bin/env bash
# Render build step for the Django backend.
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate

# Create an admin user on first deploy if you set these env vars in Render
# (DJANGO_SUPERUSER_USERNAME / _PASSWORD / _EMAIL). Safe to leave unset.
if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
  python manage.py createsuperuser --no-input || true
fi
