import os
from pathlib import Path
import dj_database_url
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.environ.get('SECRET_KEY', 'your-default-secret-key')
#DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'
# In codingplatform/settings.py (for debugging only)
DEBUG = True
JUDGE0_API_KEY = os.environ.get('JUDGE0_API_KEY')
PISTON_API_URL = os.environ.get('PISTON_API_URL', 'https://emkc.org/api/v2/piston/execute')
SUPPORTED_LANGUAGES = ["python", "c", "cpp", "java", "javascript"]


ALLOWED_HOSTS = ['localhost', '127.0.0.1','nonfiguratively-unconfected-lora.ngrok-free.dev','www.acecodeloop.me','acecodeloop.me','https://www.acecodeloop.me',
'*']
CSRF_TRUSTED_ORIGINS = [
    'https://*.ngrok-free.app',
    'https://*.ngrok-free.dev',
    'https://*.cloudflare-tunnel.dev',
    'https://*.eu.org',
    'https://www.acecodeloop.me',
    'https://acecodeloop.me',
    'https://*.devtunnels.ms',
    'https://*.inc1.devtunnels.ms',
    'https://*.trycloudflare.com',
    'https://acecodeloop.me',
    'https://acecodeloop.me',
    'https://www.acecodeloop.me',

]

RENDER_EXTERNAL_HOSTNAME = os.environ.get('RENDER_EXTERNAL_HOSTNAME')
if RENDER_EXTERNAL_HOSTNAME:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'whitenoise.runserver_nostatic', 
    'django.contrib.staticfiles',
    'codingapp',
    "widget_tweaks",
]


MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware', 
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]
MIDDLEWARE += ["codingapp.middleware.permission_middleware.RoleAccessMiddleware"]

ROOT_URLCONF = 'codingplatform.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'codingapp.context_processors.unread_notice_count',
                'codingapp.context_processors.user_permissions_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'codingplatform.wsgi.application'


DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DB_NAME'),
        'USER': os.environ.get('DB_USER'),
        'PASSWORD': os.environ.get('DB_PASSWORD'),
        'HOST': os.environ.get('DB_HOST'),
        'PORT': os.environ.get('DB_PORT'),
    }
}

SESSION_ENGINE = 'django.contrib.sessions.backends.db' 

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True

# --- ⭐ CORRECTED STATIC AND MEDIA CONFIGURATION ---
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
# We only list the static directory inside codingapp, for collectstatic to find.
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'codingapp/static')] 

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
# --- END CORRECTION ---

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_REDIRECT_URL = 'login'
PISTON_API_TIMEOUT = 10

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
}

# ----------------
# CELERY CONFIGURATION
# ----------------
CELERY_BROKER_URL = os.environ.get('REDIS_URL', 'redis://127.0.0.1:6380/0')
CELERY_RESULT_BACKEND = os.environ.get('REDIS_URL', 'redis://127.0.0.1:6380/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TASK_TIME_LIMIT = 300 
CELERY_TASK_SOFT_TIME_LIMIT = 240
CELERY_TASK_IGNORE_RESULT = False
CELERY_TASK_STORE_ERRORS_EVEN_IF_IGNORED = True
CELERY_RESULT_EXTENDED = True
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# ================= EMAIL CONFIG (GMAIL) =================

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = "smtp.gmail.com"
EMAIL_PORT = 587
EMAIL_USE_TLS = True

EMAIL_HOST_USER = "vsrgunturi@gmail.com"
EMAIL_HOST_PASSWORD = "mksm kshu rzgz eyjz"

DEFAULT_FROM_EMAIL = EMAIL_HOST_USER
