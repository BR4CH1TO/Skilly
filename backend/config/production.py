"""Configuración para un servidor HTTPS; usa collectstatic antes de iniciarlo."""
from .settings import *

DEBUG = False
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', '')
if not SECRET_KEY:
    raise ImproperlyConfigured('Producción requiere DJANGO_SECRET_KEY propia en el entorno.')
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = int(os.getenv('DJANGO_HSTS_SECONDS','3600'))
SECURE_HSTS_INCLUDE_SUBDOMAINS = os.getenv('DJANGO_HSTS_SUBDOMAINS','false').lower() == 'true'
