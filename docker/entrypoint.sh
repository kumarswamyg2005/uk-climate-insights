#!/bin/sh
# migrate -> (first boot only) ingest -> gunicorn. Static files were collected at build time.
set -eu

python manage.py migrate --noinput

if [ -n "${DJANGO_SUPERUSER_USERNAME:-}" ]; then
  # Uses DJANGO_SUPERUSER_USERNAME / _EMAIL / _PASSWORD; harmless if the user already exists.
  python manage.py createsuperuser --noinput 2>/dev/null || echo "Superuser already exists."
fi

# Fetch the Met Office data only when the database is empty (about 2 minutes). If the Met Office
# is unreachable the app still starts; an admin can re-run the ingest from /admin/.
python manage.py ingest_metoffice --if-empty || echo "Initial ingest failed; starting anyway."

# One process, four threads: the chat throttle's in-memory counters are then exact, and a slow
# LLM call doesn't block other requests. Timeout > chat deadline (30 s) + one LLM call (15 s).
exec gunicorn config.wsgi \
  --bind "0.0.0.0:${PORT:-8000}" \
  --workers 1 --threads 4 --timeout 60 \
  --access-logfile - --error-logfile -
