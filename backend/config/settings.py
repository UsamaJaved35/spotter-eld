"""Django settings for the Spotter ELD trip planner."""

from __future__ import annotations

import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Local development reads backend/.env; on Vercel the values are real env vars.
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR / ".env.local", override=False)


def env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-insecure-key-change-in-production")
DEBUG = env_bool("DEBUG", default=False)

# Vercel serves the app from a *.vercel.app host that is not known until deploy,
# so allow it by suffix rather than pinning an exact hostname.
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1,.vercel.app")

CSRF_TRUSTED_ORIGINS = [
    origin if origin.startswith("http") else f"https://{origin}"
    for origin in env_list("CSRF_TRUSTED_ORIGINS", "https://*.vercel.app")
]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "trips",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# There is deliberately no CsrfViewMiddleware. CSRF defends cookie-authenticated
# requests; this API has no authentication, no sessions and sets no cookies, so
# there is no ambient authority for a forged request to ride on. Adding the
# middleware here would only make the frontend fetch and forward a token to
# protect nothing. Revisit the moment any per-user state is introduced.

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": []},
    }
]

# dj_database_url.config() honours DATABASE_URL even when it is set to an empty
# string, returning {} and leaving Django without an ENGINE. Treat blank as
# absent so a placeholder line in .env (or an empty Vercel variable) still falls
# back to SQLite instead of failing at the first query.
_database_url = os.environ.get("DATABASE_URL", "").strip()

DATABASES = {
    "default": (
        dj_database_url.parse(_database_url, conn_max_age=600, conn_health_checks=True)
        if _database_url
        else {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    )
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = False
# Log sheets are kept in the driver's home-terminal time, so datetimes are
# handled as naive local wall-clock time rather than being shifted to UTC.
USE_TZ = False

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# --- Transport security ----------------------------------------------
# Vercel terminates TLS and forwards over HTTP, so Django must be told to trust
# the forwarded protocol header. Without this, SECURE_SSL_REDIRECT would see
# every request as insecure and redirect forever.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

# Gate on Vercel's own marker rather than `not DEBUG`. DEBUG defaults to false,
# so keying off it would make `manage.py runserver` redirect every local http
# request to https and refuse to serve anything.
ON_VERCEL = bool(os.environ.get("VERCEL"))

if ON_VERCEL:
    SECURE_SSL_REDIRECT = True
    # One year. No includeSubDomains or preload: this deploys onto a shared
    # *.vercel.app parent that is not ours to make claims about.
    SECURE_HSTS_SECONDS = 31_536_000

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "UNAUTHENTICATED_USER": None,
}

# In production the React app proxies /api through its own domain, so requests
# are same-origin. CORS is only needed for the Vite dev server.
CORS_ALLOWED_ORIGINS = env_list(
    "CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
)
CORS_ALLOWED_ORIGIN_REGEXES = [r"^https://.*\.vercel\.app$"]

# --- Trip planner -----------------------------------------------------

#: Optional. With a key the app uses OpenRouteService; without one it falls
#: back to OSRM plus Nominatim, which need no signup.
ORS_API_KEY = os.environ.get("ORS_API_KEY", "").strip()

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": os.environ.get("LOG_LEVEL", "INFO")},
}
