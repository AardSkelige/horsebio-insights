import os
from pathlib import Path
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# SECRET_KEY must be set via environment variable
SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    raise ValueError("SECRET_KEY environment variable is required")

DEBUG = os.getenv('DEBUG', 'False') == 'True'

ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1,insight.horse-bio.ru').split(',')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Third party apps
    'rest_framework',
    'corsheaders',
    
    # Local apps
    'core',
    'api',
    'sync.apps.SyncConfig',  # Explicit config to ensure label='parser' is used
    'forecasting',

    # OZON
    'ozon',

    # Мониторинг инвентаризации
    'inventory_tracking',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',  # CORS must be before CommonMiddleware
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'api.middleware.APIAuthenticationMiddleware',  # API authentication check
    'api.middleware.APIErrorHandlerMiddleware',  # Centralized error handling
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            BASE_DIR / 'templates'  
        ],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# Database Configuration
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

if os.getenv('POSTGRES_DB'):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.getenv('POSTGRES_DB'),
            'USER': os.getenv('POSTGRES_USER'),
            'PASSWORD': os.getenv('POSTGRES_PASSWORD'),
            'HOST': os.getenv('POSTGRES_HOST', 'db'),
            'PORT': os.getenv('POSTGRES_PORT', '5432'),
            'CONN_MAX_AGE': 600,  # Переиспользование соединений (10 минут)
            'OPTIONS': {
                'keepalives': 1,
                'keepalives_idle': 30,
                'keepalives_interval': 10,
                'keepalives_count': 5,
            }
        }
    }
    
LANGUAGE_CODE = 'ru-ru'
TIME_ZONE = 'Europe/Moscow'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# MoySklad settings
MOYSKLAD_TOKEN = os.getenv('MOYSKLAD_TOKEN')

# Scripts monitor settings
SCRIPTS_LOGS_DIR = os.getenv('SCRIPTS_LOGS_DIR', '/app/scripts_logs')
CRON_SECRET = os.getenv('CRON_SECRET', '')

# Обновленные CORS настройки
_BASE_CORS_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost:8001",
    "http://frontend:3001",
    "http://insight.horse-bio.ru",
]
_extra_cors = os.getenv('CORS_ALLOWED_ORIGINS', '')
CORS_ALLOWED_ORIGINS = _BASE_CORS_ORIGINS + [o.strip() for o in _extra_cors.split(',') if o.strip()]

# Добавляем CSRF доверенные источники
_BASE_CSRF_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost:8001",
    "http://frontend:3001",
    "http://insight.horse-bio.ru",
    "http://insight.horse-bio.ru:8001",
]
_extra_csrf = os.getenv('CSRF_TRUSTED_ORIGINS', '')
CSRF_TRUSTED_ORIGINS = _BASE_CSRF_ORIGINS + [o.strip() for o in _extra_csrf.split(',') if o.strip()]

# Расширенные настройки CORS
CORS_ALLOW_CREDENTIALS = True
# CSRF_USE_SESSIONS = False (default) - store CSRF token in cookie, not session
CORS_ALLOW_METHODS = [
    'DELETE',
    'GET',
    'OPTIONS',
    'PATCH',
    'POST',
    'PUT',
]

# Дополнительные CORS настройки для разработки
if DEBUG:
    CORS_EXPOSE_HEADERS = ['Content-Type', 'X-CSRFToken']
    CORS_ALLOW_CREDENTIALS = True
    # NOTE: CORS_ALLOW_ALL_ORIGINS removed for security - use CORS_ALLOWED_ORIGINS instead

# REST Framework settings
# Authentication is handled by APIAuthenticationMiddleware in api/middleware.py
# which protects all /api/* and /parser/* endpoints except /api/auth/*
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.AllowAny',  # Middleware handles auth
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 100,
}

# Настройки статических файлов
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'  
STATICFILES_DIRS = [
    BASE_DIR / 'static',  
]

# Cache settings with reasonable timeouts
# Cache keys prefixes for different data types (used for invalidation)
CACHE_KEY_PREFIXES = {
    'stats': 'stats_',
    'shipments': 'shipments_',
    'supplies': 'supplies_',
    'products': 'products_',
    'materials': 'materials_',
    'counterparties': 'counterparties_',
    'sync': 'sync_',
}

# Cache timeouts in seconds
CACHE_TIMEOUTS = {
    'stats': 300,           # 5 minutes for statistics
    'list_data': 600,       # 10 minutes for list data
    'detail_data': 900,     # 15 minutes for detail views
    'analysis': 1800,       # 30 minutes for analysis results
    'sync_status': 60,      # 1 minute for sync status
}

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache',
        'LOCATION': BASE_DIR / 'cache',
        'TIMEOUT': 600,  # Default: 10 minutes
        'OPTIONS': {
            'MAX_ENTRIES': 1000,
        },
        'KEY_PREFIX': 'horsebio_',
        'VERSION': 1,
    }
}

# Session lifetime: 7 days, rolling (each request resets the clock)
SESSION_COOKIE_AGE = 604800
SESSION_SAVE_EVERY_REQUEST = True

# Security settings - environment-aware
# In production (DEBUG=False), enforce secure cookies and HTTPS
CSRF_COOKIE_HTTPONLY = False  # Required for JavaScript CSRF token access
CSRF_COOKIE_NAME = 'csrftoken'
CSRF_HEADER_NAME = 'HTTP_X_CSRFTOKEN'

if DEBUG:
    # Development settings - allow HTTP
    CSRF_COOKIE_SECURE = False
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SAMESITE = 'Lax'
    CSRF_COOKIE_DOMAIN = None
    SESSION_COOKIE_DOMAIN = None
else:
    # Production settings - enforce HTTPS and security
    # Allow override via environment for local Docker testing (HTTP without SSL)
    CSRF_COOKIE_SECURE = os.getenv('CSRF_COOKIE_SECURE', 'True') == 'True'
    SESSION_COOKIE_SECURE = os.getenv('SESSION_COOKIE_SECURE', 'True') == 'True'
    CSRF_COOKIE_SAMESITE = os.getenv('CSRF_COOKIE_SAMESITE', 'Lax')
    SESSION_COOKIE_SAMESITE = os.getenv('SESSION_COOKIE_SAMESITE', 'Lax')
    CSRF_COOKIE_DOMAIN = None
    SESSION_COOKIE_DOMAIN = None

    # HTTPS enforcement - can be disabled for local Docker without SSL
    SECURE_SSL_REDIRECT = os.getenv('SECURE_SSL_REDIRECT', 'True') == 'True'
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

    # Security headers
    SECURE_HSTS_SECONDS = 31536000  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_BROWSER_XSS_FILTER = True
    X_FRAME_OPTIONS = 'DENY'

# Настройки логирования - убираем спам от stream-progress запросов
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'filters': {
        'ignore_stream_progress': {
            '()': 'django.utils.log.CallbackFilter',
            'callback': lambda record: 'stream-progress' not in getattr(record, 'getMessage', lambda: '')()
        },
    },
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
            'filters': ['ignore_stream_progress'],
        },
    },
    'root': {
        'handlers': ['console'],
    },
    'loggers': {
        'django.server': {
            'handlers': ['console'],
            'level': 'INFO',
            'filters': ['ignore_stream_progress'],
            'propagate': False,
        },
    },
}
