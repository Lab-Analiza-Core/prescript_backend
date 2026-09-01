from datetime import timedelta
from pathlib import Path

import environ


BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(DEBUG=(bool, False))
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY", default="prescript-local-dev-key")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

DEFAULT_CLIENT_ORIGINS = [
    "https://prescript-frontend-murex.vercel.app",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
    "http://localhost:5175",
    "http://127.0.0.1:5175",
]

DEFAULT_CLIENT_ORIGIN_REGEXES = [
    r"^https://prescript-frontend-[a-z0-9-]+-analiza\.vercel\.app$",
]

CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_PRIVATE_NETWORK = env.bool("CORS_ALLOW_PRIVATE_NETWORK", default=True)
CORS_ALLOWED_ORIGINS = list(
    dict.fromkeys(DEFAULT_CLIENT_ORIGINS + env.list("CORS_ALLOWED_ORIGINS", default=[]))
)
CORS_ALLOWED_ORIGIN_REGEXES = list(
    dict.fromkeys(DEFAULT_CLIENT_ORIGIN_REGEXES + env.list("CORS_ALLOWED_ORIGIN_REGEXES", default=[]))
)
CSRF_TRUSTED_ORIGINS = list(
    dict.fromkeys(DEFAULT_CLIENT_ORIGINS + env.list("CSRF_TRUSTED_ORIGINS", default=[]))
)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "api.apps.ApiConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "Prescript.urls"

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

WSGI_APPLICATION = "Prescript.wsgi.application"


def postgres_config(prefix, default_name):
    url = env(f"{prefix}_DATABASE_URL", default="")
    if url:
        return env.db(f"{prefix}_DATABASE_URL")
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env(f"{prefix}_DB", default=default_name),
        "USER": env(f"{prefix}_USER", default="postgres"),
        "PASSWORD": env(f"{prefix}_PASSWORD", default="postgres"),
        "HOST": env(f"{prefix}_HOST", default="localhost"),
        "PORT": env(f"{prefix}_PORT", default="5432"),
    }


DATABASES = {
    "default": postgres_config("PRESCRIPT", "prescript_db"),
    "interactive_core": postgres_config("INTERACTIVE_CORE", "interactivecore_db"),
}

# El modulo de administracion de usuarios valida el rol ADMIN contra esta BD
# en cada request; si InteractiveCore esta lento o caido, la consulta debe
# fallar rapido en vez de colgar el request.
DATABASES["interactive_core"].setdefault("OPTIONS", {})
DATABASES["interactive_core"]["OPTIONS"]["options"] = "-c statement_timeout=3000"

legacy_database_url = env("DATABASE_URL", default="")
if legacy_database_url:
    DATABASES["default"] = env.db("DATABASE_URL")

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
}

LANGUAGE_CODE = "es-hn"
TIME_ZONE = "America/Tegucigalpa"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

INTERACTIVE_CORE_API_BASE_URL = env("INTERACTIVE_CORE_API_BASE_URL", default="")
INTERACTIVE_CORE_API_TOKEN = env("INTERACTIVE_CORE_API_TOKEN", default="")
PRESCRIPT_TOP_DOCTOR_MIN_SCORE = env.float("PRESCRIPT_TOP_DOCTOR_MIN_SCORE", default=80.0)
PRESCRIPT_INTERACTIVE_CORE_DOCTOR_ROLES = env.list(
    "PRESCRIPT_INTERACTIVE_CORE_DOCTOR_ROLES",
    default=["DOCTOR"],
)
PRESCRIPT_INTERACTIVE_CORE_PORTAL_ROLES = env.list(
    "PRESCRIPT_INTERACTIVE_CORE_PORTAL_ROLES",
    default=["DOCTOR", "SECRETARY", "NURSE", "ADMIN", "COUNTRY_MANAGER"],
)
