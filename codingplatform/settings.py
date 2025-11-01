import os
from pathlib import Path
import dj_database_url
from dotenv import load_dotenv # Add this

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv() # And this
SECRET_KEY = os.environ.get('SECRET_KEY', 'your-default-secret-key')
DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'
JUDGE0_API_KEY = os.environ.get('JUDGE0_API_KEY')
#DEBUG = True
#PISTON_API_URL = "https://emkc.org/api/v2/piston/execute"
#PISTON_API_URL = "http://localhost:2000/api/v2/execute"
PISTON_API_URL = os.environ.get('PISTON_API_URL', 'https://emkc.org/api/v2/piston/execute')
SUPPORTED_LANGUAGES = ["python", "c", "cpp", "java", "javascript"]


#ALLOWED_HOSTS = ['localhost', '127.0.0.1','192.168.72.169']
ALLOWED_HOSTS = ['localhost', '127.0.0.1']

RENDER_EXTERNAL_HOSTNAME = os.environ.get('RENDER_EXTERNAL_HOSTNAME')
if RENDER_EXTERNAL_HOSTNAME:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'codingapp',
    "widget_tweaks",
]

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'


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
                'codingapp.context_processors.unread_notice_count',  # ✅ Add custom context processor
            ],
        },
    },
]

WSGI_APPLICATION = 'codingplatform.wsgi.application'

#DATABASES = {
 #   'default': {
  #      'ENGINE': 'django.db.backends.sqlite3',
   #     'NAME': BASE_DIR / "db.sqlite3",
    #}
#}
#DATABASES = {
   # 'default': dj_database_url.config(
  #      default='sqlite:///db.sqlite3',
 #       conn_max_age=600
#    )
#}

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

SESSION_ENGINE = 'django.contrib.sessions.backends.db'  # ✅ Use database-backed session storage

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

STATIC_URL = '/static/'

STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
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

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_URL = 'static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

# ⭐ FIX: Add this setting to tell Django where to find your app's static files
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'codingapp/static'),
]

# ----------------
# CELERY CONFIGURATION
# ----------------



# ... inside CELERY CONFIGURATION ...
CELERY_BROKER_URL = os.environ.get('REDIS_URL', 'redis://127.0.0.1:6380/0')
CELERY_RESULT_BACKEND = os.environ.get('REDIS_URL', 'redis://127.0.0.1:6380/0')
# ... rest of celery settings
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TASK_TIME_LIMIT = 300 # Max task execution time (5 minutes)
CELERY_TASK_SOFT_TIME_LIMIT = 240 # Soft time limit (4 minutes)