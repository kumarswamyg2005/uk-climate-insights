"""Production (Render) and the docker-compose stack. Everything sensitive is required from env."""

from .base import *  # noqa: F403
from .base import ALLOWED_HOSTS, env

DEBUG = False
SECRET_KEY = env("SECRET_KEY")

# The container healthcheck calls http://127.0.0.1:8000/healthz from inside the container.
ALLOWED_HOSTS = [*ALLOWED_HOSTS, "localhost", "127.0.0.1"]

DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["CONN_MAX_AGE"] = env.int("CONN_MAX_AGE", default=60)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True

# Render terminates TLS at its proxy and forwards the original scheme in this header.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# One switch for everything that assumes HTTPS; docker-compose sets HTTPS_ONLY=False for localhost.
HTTPS_ONLY = env.bool("HTTPS_ONLY", default=True)
SECURE_SSL_REDIRECT = HTTPS_ONLY
SECURE_REDIRECT_EXEMPT = [r"^healthz$"]
SESSION_COOKIE_SECURE = HTTPS_ONLY
CSRF_COOKIE_SECURE = HTTPS_ONLY
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=3600) if HTTPS_ONLY else 0

# includeSubDomains / preload would bind every *.onrender.com subdomain; not ours to set.
SILENCED_SYSTEM_CHECKS = ["security.W005", "security.W021"]
