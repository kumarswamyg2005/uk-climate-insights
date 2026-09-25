#!/bin/sh
# migrate -> (until one completes) ingest in the background -> gunicorn.
# Static files were collected at build time.
set -eu

python manage.py migrate --noinput

if [ -n "${DJANGO_SUPERUSER_USERNAME:-}" ]; then
  # Uses DJANGO_SUPERUSER_USERNAME / _EMAIL / _PASSWORD; harmless if the user already exists.
  python manage.py createsuperuser --noinput 2>/dev/null || echo "Superuser already exists."
fi

# Load the Met Office data until one ingest has completed (about 2 minutes). It runs in the
# background so gunicorn binds its port straight away: hosts like Render fail a deploy that
# doesn't open its port in time. Pages show whatever has loaded so far; if the container stops
# mid-ingest, the next boot runs it again (upserts make that safe).
python manage.py ingest_metoffice --if-needed &

# One process, four threads: the chat throttle's in-memory counters are then exact, and a slow
# LLM call doesn't block other requests. Timeout > chat deadline (30 s) + one LLM call (15 s).
exec gunicorn config.wsgi \
  --bind "0.0.0.0:${PORT:-8000}" \
  --workers 1 --threads 4 --timeout 60 \
  --access-logfile - --error-logfile -
