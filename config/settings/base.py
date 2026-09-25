"""Settings shared by every environment. Values that differ per environment come from env vars."""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
if (BASE_DIR / ".env").exists():
    # Real environment variables always win over .env (overwrite=False).
    environ.Env.read_env(BASE_DIR / ".env")

DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "django_filters",
    "drf_spectacular",
    "climate",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-gb"
TIME_ZONE = "Europe/London"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    # Public, anonymous, read-only API: no sessions or tokens to authenticate against.
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "COERCE_DECIMAL_TO_STRING": False,  # values are JSON numbers
    # Invariant 12. Counted per client IP in the default (in-process) cache: exact with one
    # gunicorn worker; move to a shared cache (Redis/DB) before running several workers.
    "DEFAULT_THROTTLE_RATES": {"chat": env("CHAT_RATE_LIMIT", default="10/min")},
    # Behind Render's proxy the client IP is the last X-Forwarded-For hop; 0 locally.
    "NUM_PROXIES": env.int("NUM_PROXIES", default=0),
}

# LLM chat (Groq). Without a key the chat endpoint answers 503 and everything else works.
GROQ_API_KEY = env.str("GROQ_API_KEY", default="").strip()
LLM_MODEL = env.str("LLM_MODEL", default="openai/gpt-oss-120b")
LLM_FALLBACK_MODEL = env.str("LLM_FALLBACK_MODEL", default="openai/gpt-oss-20b")
LLM_TIMEOUT = env.float("LLM_TIMEOUT", default=15.0)

SPECTACULAR_SETTINGS = {
    "TITLE": "UK Climate Insights API",
    "DESCRIPTION": (
        "Read-only access to the Met Office UK and regional climate series (monthly, seasonal "
        "and annual values per region). Contains Met Office data © Crown copyright, "
        "Open Government Licence v3.0."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

# Seconds between Met Office requests during an ingest (invariant 14).
METOFFICE_REQUEST_DELAY = env.float("METOFFICE_REQUEST_DELAY", default=0.5)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": "WARNING"},
    "loggers": {"climate": {"level": env("CLIMATE_LOG_LEVEL", default="INFO")}},
}
