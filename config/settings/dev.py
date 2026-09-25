"""Local development and the test run. Safe defaults so a fresh clone works without a .env."""

from .base import *  # noqa: F403
from .base import STORAGES, env

DEBUG = env.bool("DEBUG", default=True)
SECRET_KEY = env("SECRET_KEY", default="django-insecure-dev-only-never-use-in-prod")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1", "0.0.0.0"])  # noqa: S104

# Matches the `db` service in docker-compose.yml (published on localhost:5432).
DATABASES = {
    "default": env.db("DATABASE_URL", default="postgres://climate:climate@localhost:5432/climate")
}

# No manifest in dev/tests, so templates render without running collectstatic first.
STORAGES = {
    **STORAGES,
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

# Serve static from source dirs. Set explicitly: pytest forces DEBUG=False.
WHITENOISE_AUTOREFRESH = True
WHITENOISE_USE_FINDERS = True
