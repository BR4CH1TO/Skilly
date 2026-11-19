import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from django.core.management.utils import get_random_secret_key
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BASE_DIR.parent
load_dotenv(BASE_DIR / ".env")

DEBUG = os.getenv("DJANGO_DEBUG", "true").lower() == "true"
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured("Configura DJANGO_SECRET_KEY antes de desactivar DEBUG.")
    SECRET_KEY = get_random_secret_key()
ALLOWED_HOSTS = [host.strip() for host in os.getenv(
    "DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]"
).split(",") if host.strip()]

INSTALLED_APPS = ["core", "django.contrib.staticfiles"]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django_mongodb_backend",
        "HOST": os.getenv("MONGODB_URI", "mongodb://127.0.0.1:27017/"),
        "NAME": os.getenv("MONGODB_DB_NAME", "skilly"),
        "OPTIONS": {"serverSelectionTimeoutMS": 3000},
    }
}
DEFAULT_AUTO_FIELD = "django_mongodb_backend.fields.ObjectIdAutoField"
LANGUAGE_CODE = "es-cl"
TIME_ZONE = "America/Santiago"
USE_I18N = True
USE_TZ = True
STATIC_URL = "/static/"
STATICFILES_DIRS = [
    ("assets", PROJECT_DIR / "assets"),
    ("js", PROJECT_DIR / "js"),
    ("css", PROJECT_DIR / "css"),
]
STATIC_ROOT = BASE_DIR / "staticfiles"
PRIVATE_DOCUMENT_ROOT = Path(os.getenv("SKILLY_DOCUMENT_ROOT", str(BASE_DIR / "private_documents")))
CSRF_COOKIE_SECURE = not DEBUG

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
# Sesiones opacas revocables en MongoDB; contraseñas con los hashers de Django.

STORAGES = {"default":{"BACKEND":"django.core.files.storage.FileSystemStorage"}, "staticfiles":{"BACKEND":"whitenoise.storage.CompressedManifestStaticFilesStorage"}}
SECURE_SSL_REDIRECT = not DEBUG
SECURE_HSTS_SECONDS = 3600 if not DEBUG else 0
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
DATA_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024
