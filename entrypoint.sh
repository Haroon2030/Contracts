#!/bin/sh
set -e

python manage.py migrate --noinput
python manage.py collectstatic --noinput

if [ -n "${DJANGO_ADMIN_USERNAME:-}" ] && [ -n "${DJANGO_ADMIN_PASSWORD:-}" ]; then
  python manage.py ensure_admin
fi

exec gunicorn cms.wsgi:application \
  --bind "0.0.0.0:${PORT:-8000}" \
  --workers "${WEB_CONCURRENCY:-2}" \
  --timeout "${GUNICORN_TIMEOUT:-60}" \
  --access-logfile - \
  --error-logfile -
