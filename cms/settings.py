import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DJANGO_ENV = os.environ.get("DJANGO_ENV", "development")
DEBUG = os.environ.get("DJANGO_DEBUG", "0" if DJANGO_ENV == "production" else "1") == "1"
if DJANGO_ENV == "production" and DEBUG:
    raise RuntimeError("Production refuses DEBUG=True. Set DJANGO_ENV=production and DJANGO_DEBUG=0.")

_INSECURE_KEY = "django-insecure-alrashid-contracts-dev-only"
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", _INSECURE_KEY)
if not DEBUG:
    if not os.environ.get("DJANGO_SECRET_KEY") or SECRET_KEY.startswith("django-insecure"):
        raise RuntimeError("DJANGO_SECRET_KEY must be set when DEBUG is False.")
ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")
    if host.strip()
]
if DEBUG:
    ALLOWED_HOSTS = list({*ALLOWED_HOSTS, "testserver"})

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "accounts",
    "contracts",
    "dashboard",
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

ROOT_URLCONF = "cms.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "dashboard.context_processors.nav_counts",
            ],
        },
    },
]

WSGI_APPLICATION = "cms.wsgi.application"


def _parse_database_url(url):
    from urllib.parse import unquote

    scheme, rest = url.split("://", 1)
    creds, hostpart = rest.rsplit("@", 1)
    user, password = creds.split(":", 1)
    hostport, name = hostpart.split("/", 1)
    name = name.split("?")[0]
    if ":" in hostport:
        host, port = hostport.rsplit(":", 1)
    else:
        host, port = hostport, ""
    engine = "django.db.backends.mysql" if scheme.startswith("mysql") else "django.db.backends.postgresql"
    return {
        "ENGINE": engine,
        "NAME": unquote(name),
        "USER": unquote(user),
        "PASSWORD": unquote(password),
        "HOST": host,
        "PORT": port or ("3306" if engine.endswith("mysql") else "5432"),
        "CONN_MAX_AGE": 60,
    }


_database_url = os.environ.get("DATABASE_URL", "").strip()
if os.environ.get("MYSQL_DATABASE") or os.environ.get("MYSQL_HOST"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": os.environ.get("MYSQL_DATABASE", ""),
            "USER": os.environ.get("MYSQL_USER", ""),
            "PASSWORD": os.environ.get("MYSQL_PASSWORD", ""),
            "HOST": os.environ.get("MYSQL_HOST", "127.0.0.1"),
            "PORT": os.environ.get("MYSQL_PORT", "3306"),
            "CONN_MAX_AGE": 60,
            "OPTIONS": {
                "charset": "utf8mb4",
                "init_command": "SET sql_mode='STRICT_TRANS_TABLES', time_zone='+03:00'",
            },
        }
    }
elif _database_url:
    DATABASES = {"default": _parse_database_url(_database_url)}
    if DATABASES["default"]["ENGINE"].endswith("mysql"):
        DATABASES["default"]["OPTIONS"] = {
            "charset": "utf8mb4",
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES', time_zone='+03:00'",
        }
    else:
        DATABASES["default"]["OPTIONS"] = {"options": "-c timezone=Asia/Riyadh"}
elif os.environ.get("POSTGRES_DB"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ["POSTGRES_DB"],
            "USER": os.environ.get("POSTGRES_USER", "postgres"),
            "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
            "HOST": os.environ.get("POSTGRES_HOST", "127.0.0.1"),
            "PORT": os.environ.get("POSTGRES_PORT", "5432"),
            "CONN_MAX_AGE": 60,
            "OPTIONS": {"options": "-c timezone=Asia/Riyadh"},
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 6}},
]

LANGUAGE_CODE = "ar"
TIME_ZONE = "Asia/Riyadh"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [path for path in [BASE_DIR / "static"] if path.exists()]
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard:home"
LOGOUT_REDIRECT_URL = "login"

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "cms-cache",
    }
}

FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 12 * 1024 * 1024
FILE_UPLOAD_PERMISSIONS = 0o640

SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 8 * 60 * 60
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

HIGH_VALUE_THRESHOLD = "15000"

ORGANIZATION = {
    "name": "أسواق الرشيد",
    "legal_name": "أسواق الرشيد",
    "country": "المملكة العربية السعودية",
    "unit": "إدارة العقود والمشتريات",
    "city": "المملكة العربية السعودية",
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}

if not DEBUG:
    SECURE_SSL_REDIRECT = os.environ.get("DJANGO_SSL_REDIRECT", "0") == "1"
    _secure_cookies = os.environ.get(
        "DJANGO_COOKIE_SECURE",
        "1" if SECURE_SSL_REDIRECT else "0",
    ) == "1"
    SESSION_COOKIE_SECURE = _secure_cookies
    CSRF_COOKIE_SECURE = _secure_cookies
    if SECURE_SSL_REDIRECT:
        SECURE_HSTS_SECONDS = 31536000
        SECURE_HSTS_INCLUDE_SUBDOMAINS = True
        SECURE_HSTS_PRELOAD = True
    AUTH_PASSWORD_VALIDATORS = [
        {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
        {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
        {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
        {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
    ]
