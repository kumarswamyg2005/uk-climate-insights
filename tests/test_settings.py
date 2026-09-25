"""Invariant 13: no secrets in the repo, and production configuration comes only from the env."""

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROBE = "from django.conf import settings; print(settings.DEBUG, settings.SECRET_KEY == 'from-env')"


def load_prod_settings(**env):
    clean = {k: v for k, v in os.environ.items() if k not in {"SECRET_KEY", "DEBUG"}}
    clean.update(
        DJANGO_SETTINGS_MODULE="config.settings.prod",
        DATABASE_URL="postgres://u:p@localhost:5432/db",
        **env,
    )
    return subprocess.run(
        [sys.executable, "-c", PROBE], cwd=ROOT, env=clean, capture_output=True, text=True
    )


def test_production_refuses_to_start_without_a_secret_key():
    result = load_prod_settings()
    assert result.returncode != 0
    assert "SECRET_KEY" in result.stderr


def test_production_forces_debug_off_and_reads_the_key_from_env():
    result = load_prod_settings(SECRET_KEY="from-env", DEBUG="True")
    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == ["False", "True"]


def test_render_hostname_is_allowed_and_trusted_for_csrf():
    probe = (
        "from django.conf import settings; "
        "print('app.onrender.com' in settings.ALLOWED_HOSTS, settings.CSRF_TRUSTED_ORIGINS)"
    )
    clean = {k: v for k, v in os.environ.items() if k != "DEBUG"}
    clean.update(
        DJANGO_SETTINGS_MODULE="config.settings.prod",
        DATABASE_URL="postgres://u:p@localhost:5432/db",
        SECRET_KEY="x",
        RENDER_EXTERNAL_HOSTNAME="app.onrender.com",
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], cwd=ROOT, env=clean, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "True ['https://app.onrender.com']"


def test_no_credentials_in_tracked_files():
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.split()
    assert ".env" not in tracked
    secret = re.compile(
        r"gsk_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{32,}|-----BEGIN [A-Z ]*PRIVATE KEY-----"
    )
    leaks = [
        name
        for name in tracked
        if (ROOT / name).is_file() and secret.search((ROOT / name).read_text(errors="ignore"))
    ]
    assert leaks == []
