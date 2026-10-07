"""
Django settings for GCOEK MIS project.

Government College of Engineering, Kolhapur (Autonomous)
College Student Management & Administrative Data System
"""
import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env file explicitly
load_dotenv(BASE_DIR / '.env')
load_dotenv(BASE_DIR.parent / '.env')
load_dotenv()

# SECURITY WARNING: keep the secret key used in production secret!
# Fail closed if SECRET_KEY is missing. Insecure django-insecure- prefix is
# only tolerated for local DEBUG development, never for production.
SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    from django.core.exceptions import ImproperlyConfigured
    raise ImproperlyConfigured('SECRET_KEY environment variable is required. Set it in .env (see .env.example).')
DEBUG = os.getenv('DEBUG', 'False').lower() in ('true', '1', 'yes')
if not DEBUG and SECRET_KEY.startswith('django-insecure-'):
    from django.core.exceptions import ImproperlyConfigured
    raise ImproperlyConfigured('Insecure SECRET_KEY cannot be used when DEBUG=False. Generate a strong key.')

# Field-level encryption key for PII (Aadhaar/bank). Fernet key from env.
# Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
FIELD_ENCRYPTION_KEY = os.getenv('FIELD_ENCRYPTION_KEY', '')
if not FIELD_ENCRYPTION_KEY and not DEBUG:
    from django.core.exceptions import ImproperlyConfigured
    raise ImproperlyConfigured('FIELD_ENCRYPTION_KEY environment variable is required in production.')

ALLOWED_HOSTS = [
    h.strip()
    for h in os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1,testserver').split(',')
    if h.strip()
]

# ---------------------------------------------------------------------------
# Application definition
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Third-party
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    # Project apps
    'apps.common',
    'apps.audit',
    'apps.authentication',
    'apps.academic_structure',
    'apps.curriculum',
    'apps.students',
    'apps.admissions',
    'apps.results',
    'apps.faculty',
    'apps.finance',
    'apps.reporting',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'gceok_core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'gceok_core.wsgi.application'

# ---------------------------------------------------------------------------
# Database — PostgreSQL (SECURITY.md: credentials from environment only)
# ---------------------------------------------------------------------------
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DB_NAME', 'gceok_mis'),
        'USER': os.getenv('DB_USER', 'gceok_app'),
        'PASSWORD': os.getenv('DB_PASSWORD', ''),
        'HOST': os.getenv('DB_HOST', 'localhost'),
        'PORT': os.getenv('DB_PORT', '5432'),
        'CONN_MAX_AGE': int(os.getenv('DB_CONN_MAX_AGE', '60')),
        'OPTIONS': {
            'connect_timeout': 5,
        },
    }
}

# ---------------------------------------------------------------------------
# Custom User Model (must be set before first migration)
# ---------------------------------------------------------------------------
AUTH_USER_MODEL = 'authentication.User'

# ---------------------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
     'OPTIONS': {'min_length': 12}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ---------------------------------------------------------------------------
# Password hashing — Argon2 preferred (SECURITY.md)
# ---------------------------------------------------------------------------
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.Argon2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher',
    'django.contrib.auth.hashers.BCryptSHA256PasswordHasher',
    'django.contrib.auth.hashers.ScryptPasswordHasher',
]

# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static files (CSS, JavaScript, Images)
# ---------------------------------------------------------------------------
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Media files (uploaded documents)
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

# ---------------------------------------------------------------------------
# Default primary key field type
# ---------------------------------------------------------------------------
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ---------------------------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 25,
    'DEFAULT_RENDERER_CLASSES': (
        'rest_framework.renderers.JSONRenderer',
    ),
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
        'rest_framework.throttling.ScopedRateThrottle',
    ],
    # SECURITY.md Sec 10 targets: login 5/min (scoped), import 10/hr
    # (scoped), general authenticated use 1000/hr.
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/minute',
        'user': '1000/hour',
        'login': '5/minute',
        'import_upload': '10/hour',
        'payment_initiate': '10/minute',
        'payment_verify': '20/minute',
        'payment_status': '60/minute',
        'payment_callback': '60/minute',
    },
    'EXCEPTION_HANDLER': 'rest_framework.views.exception_handler',
}

# ---------------------------------------------------------------------------
# Simple JWT Configuration (SECURITY.md)
# ---------------------------------------------------------------------------
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(
        seconds=int(os.getenv('JWT_ACCESS_TOKEN_LIFETIME', '900'))
    ),
    'REFRESH_TOKEN_LIFETIME': timedelta(
        seconds=int(os.getenv('JWT_REFRESH_TOKEN_LIFETIME', '604800'))
    ),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
}

# ---------------------------------------------------------------------------
# CORS Configuration
# ---------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv(
        'CORS_ALLOWED_ORIGINS',
        'http://localhost:5173,http://localhost:5174,http://localhost:5175,http://127.0.0.1:5173,http://127.0.0.1:5174,http://127.0.0.1:5175'
    ).split(',')
    if o.strip()
]
CORS_ALLOW_CREDENTIALS = True

if DEBUG:
    CORS_ALLOWED_ORIGIN_REGEXES = [
        r"^http://localhost:(517[0-9]|3000)$",
        r"^http://127\.0\.0\.1:(517[0-9]|3000)$",
    ]

# ---------------------------------------------------------------------------
# Security Headers (production-ready defaults)
# ---------------------------------------------------------------------------
if not DEBUG:
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = True
    X_FRAME_OPTIONS = 'DENY'

# ---------------------------------------------------------------------------
# Login attempt security
# ---------------------------------------------------------------------------
MAX_FAILED_LOGIN_ATTEMPTS = 5
LOGIN_LOCKOUT_DURATION_MINUTES = 15
PASSWORD_HISTORY_COUNT = 5

# ---------------------------------------------------------------------------
# File upload limits
# ---------------------------------------------------------------------------
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10 MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10 MB

# ---------------------------------------------------------------------------
# Easebuzz Payment Gateway Configuration (Production Ready)
# ---------------------------------------------------------------------------
EASEBUZZ_ENABLED = os.getenv('EASEBUZZ_ENABLED', 'True').lower() in ('true', '1', 'yes')
EASEBUZZ_ENV = os.getenv('EASEBUZZ_ENV', 'sandbox').lower()  # 'sandbox' or 'production'
EASEBUZZ_KEY = os.getenv('EASEBUZZ_KEY', '')
EASEBUZZ_SALT = os.getenv('EASEBUZZ_SALT', '')
EASEBUZZ_SUB_MERCHANT_ID = os.getenv('EASEBUZZ_SUB_MERCHANT_ID', '')
EASEBUZZ_TIMEOUT = int(os.getenv('EASEBUZZ_TIMEOUT', '5'))  # seconds
# Mock checkout works ONLY when this is True (kept False in prod even with DEBUG on).
EASEBUZZ_MOCK_MODE = os.getenv('EASEBUZZ_MOCK_MODE', 'False').lower() in ('true', '1', 'yes')
# Comma-separated Easebuzz server IPs allowed to hit callback/webhook. Empty = allow all (dev).
EASEBUZZ_WEBHOOK_ALLOWED_IPS = [
    ip.strip() for ip in os.getenv('EASEBUZZ_WEBHOOK_ALLOWED_IPS', '').split(',') if ip.strip()
]
FRONTEND_BASE_URL = os.getenv('FRONTEND_BASE_URL', 'http://localhost:5173').rstrip('/')

# ---------------------------------------------------------------------------
# Notification / Email Configuration
# ---------------------------------------------------------------------------
EMAIL_ENABLED = os.getenv('EMAIL_ENABLED', 'True').lower() in ('true', '1', 'yes')
EMAIL_PROVIDER = os.getenv('EMAIL_PROVIDER', 'console')  # 'console' or 'smtp'
EMAIL_FROM_ADDRESS = os.getenv('EMAIL_FROM_ADDRESS', 'accounts@gceok.ac.in')
EMAIL_FROM_NAME = os.getenv('EMAIL_FROM_NAME', 'GCOEK Accounts Desk')

# ---------------------------------------------------------------------------
# Production application logging (SECURITY.md Sec 13)
# Console + rotating files under <BASE_DIR>/logs. No secrets, passwords,
# tokens, Aadhaar or bank numbers are ever written here by convention —
# callers must pass redacted values (audit service enforces redaction).
# ---------------------------------------------------------------------------
LOG_DIR = BASE_DIR / 'logs'
try:
    LOG_DIR.mkdir(exist_ok=True)
except Exception:
    pass

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{asctime} {levelname} {name} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {name}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose' if not DEBUG else 'simple',
        },
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(LOG_DIR / 'django.log'),
            'maxBytes': 5 * 1024 * 1024,
            'backupCount': 5,
            'formatter': 'verbose',
        },
        'audit_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(LOG_DIR / 'audit.log'),
            'maxBytes': 5 * 1024 * 1024,
            'backupCount': 5,
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console', 'file'],
        'level': 'DEBUG' if DEBUG else 'INFO',
    },
    'loggers': {
        'django.request': {
            'handlers': ['console', 'file'],
            'level': 'WARNING',
            'propagate': False,
        },
        'apps.audit': {
            'handlers': ['console', 'audit_file', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'apps.finance': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

