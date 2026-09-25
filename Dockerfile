# syntax=docker/dockerfile:1

# --- build: install dependencies into a virtualenv ------------------------------------------
FROM python:3.12-slim AS builder
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
COPY requirements.txt .
# psycopg[binary] ships its own libpq, so no compiler or system packages are needed.
RUN pip install -r requirements.txt

# --- runtime: slim image, non-root user, static files baked in ------------------------------
FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH \
    DJANGO_SETTINGS_MODULE=config.settings.prod \
    PORT=8000
RUN useradd --create-home --uid 10001 app
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --chown=app:app . .
# Hashed, compressed static files are part of the image: immutable and nothing to do at boot.
# The settings need these two values to import; neither is used by collectstatic.
RUN SECRET_KEY=build-only DATABASE_URL=sqlite:////tmp/unused.db \
    python manage.py collectstatic --noinput --verbosity 0
USER app
EXPOSE 8000
# Liveness plus a database round-trip. The start period covers the first-boot ingest.
HEALTHCHECK --interval=30s --timeout=5s --start-period=240s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/healthz' % os.environ.get('PORT', '8000'), timeout=4)"
ENTRYPOINT ["/app/docker/entrypoint.sh"]
