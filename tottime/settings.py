import os
import logging
from pathlib import Path
import stripe

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = "django-insecure-e84gb%3c5fb5(s0!imu3b&n_=&@)c4j-+i%h1y!tt$e9l!+k=*"
# Allows Django to still read sessions/cookies signed with the old key after key rotation
SECRET_KEY_FALLBACKS = [
    "django-insecure-e84gb%3c5fb5(s0!imu3b&n_=&@)c4j-+i%h1y!tt$e9l!+k=*",
]
DEBUG = True
ALLOWED_HOSTS = ['44.209.83.215', 'localhost', '127.0.0.1', 'tot-time.com', 'www.tot-time.com']

# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    'django_user_agents',
    'django_q',
    "tottimeapp",
    

]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "tottimeapp.middleware.TemporaryAccessMiddleware", 
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    
]

ROOT_URLCONF = "tottime.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [
            os.path.join(BASE_DIR, 'tottimeapp', 'templates', 'tottimeapp'),
            os.path.join(BASE_DIR, 'templates'),
        ],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'tottimeapp.context_processors.unread_messages_count',
                'tottimeapp.context_processors.is_app_context',
                'tottimeapp.context_processors.show_back_button',
                'tottimeapp.context_processors.account_switcher_context',
                'tottimeapp.context_processors.template_type',
                'tottimeapp.context_processors.template_base',
            ],
        },
    },
]

WSGI_APPLICATION = "tottime.wsgi.application"

# Database settings
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'NAME': 'postgres',
        'USER': 'aficklin12',
        'PASSWORD': 'Uiyqdi1994!',
        'HOST': 'tottime.cbeiq0qm4vjk.us-east-1.rds.amazonaws.com',
        'PORT': '5432',
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "America/New_York"
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'tottimeapp', 'static'),
]
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'tottimeapp.auth.TemporaryAccessBackend', 
]

# Logging configuration
logging.basicConfig(level=logging.DEBUG)

LOGIN_URL = '/login/'

# Email settings
# For development:
# EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# For production (SMTP configuration):
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'tottimeapp@gmail.com'
EMAIL_HOST_PASSWORD = 'cfks wtbl kdxr zqqs' 
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER

AUTH_USER_MODEL = 'tottimeapp.MainUser'


AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
AWS_STORAGE_BUCKET_NAME = 'tot-time-media'
AWS_S3_REGION_NAME = 'us-east-1'  # or your region
AWS_S3_CUSTOM_DOMAIN = f'{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com'
DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/'
# MEDIA_ROOT = BASE_DIR / 'media'
SECURE_SSL_REDIRECT = False


MESSAGE_STORAGE = 'django.contrib.messages.storage.session.SessionStorage'


# CSRF settings for Cordova app compatibility
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = False  # Allow JavaScript access for Cordova
CSRF_COOKIE_SAMESITE = 'Lax'
CSRF_TRUSTED_ORIGINS = ['https://tot-time.com', 'https://www.tot-time.com']


# Static files for PWA
PWA_APP_NAME = 'Tot-Time'
PWA_APP_DESCRIPTION = 'Childcare management software.'
PWA_APP_THEME_COLOR = '#333741'
PWA_APP_BACKGROUND_COLOR = '#ffffff'
PWA_APP_DISPLAY = 'standalone'
PWA_APP_SCOPE = '/'
PWA_APP_START_URL = '/'
PWA_APP_ORIENTATION = 'portrait'
PWA_APP_LANG = 'en'

# Service Worker and Manifest Paths
PWA_SERVICE_WORKER_PATH = os.path.join(BASE_DIR, 'tottimeapp', 'static', 'pwa', 'service-worker.js')
PWA_MANIFEST_PATH = os.path.join(BASE_DIR, 'tottimeapp', 'static', 'pwa', 'manifest.json')


STRIPE_PUBLIC_KEY = os.getenv("STRIPE_PUBLIC_KEY", "")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_CLIENT_ID = os.getenv("STRIPE_CLIENT_ID", "")
STRIPE_REDIRECT_URI = os.getenv("STRIPE_REDIRECT_URI", "https://tot-time.com/stripe/callback/")

# Square OAuth Credentials (Sandbox)
SQUARE_APPLICATION_ID = os.getenv("SQUARE_APPLICATION_ID", "")
SQUARE_CLIENT_SECRET = os.getenv("SQUARE_CLIENT_SECRET", "")
SQUARE_ACCESS_TOKEN = os.getenv("SQUARE_ACCESS_TOKEN", "")
SQUARE_LOCATION_ID = os.getenv("SQUARE_LOCATION_ID", "")
SQUARE_SUBSCRIPTION_PLAN_ID = os.getenv("SQUARE_SUBSCRIPTION_PLAN_ID", "")
SQUARE_SUBSCRIPTION_PLAN_VARIATION_ID = os.getenv("SQUARE_SUBSCRIPTION_PLAN_VARIATION_ID", "")
SQUARE_WEBHOOK_SIGNATURE_KEY = os.getenv("SQUARE_WEBHOOK_SIGNATURE_KEY", "")

# Square OAuth Auth URL for sandbox
SQUARE_AUTH_URL = "https://sandbox.connect.squareup.com/oauth2/authorize"

Q_CLUSTER = {
    'name': 'tottime',
    'workers': 4,
    'recycle': 500,
    'timeout': 60,
    'retry': 120,
    'queue_limit': 50,
    'bulk': 10,
    'catch_up': False,
    'scheduler': True,
    'orm': 'default',  # This avoids Redis
}
