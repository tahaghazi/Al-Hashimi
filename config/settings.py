"""
Django settings for chat bot project.

Generated by 'django-admin startproject' using Django 5.1.4.

For more information on this file, see
https://docs.djangoproject.com/en/5.1/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/5.1/ref/settings/
"""
import asyncio
import datetime
from pathlib import Path
from uuid import uuid4

import django
from django.utils.encoding import force_str, smart_str
from django.utils.translation import gettext, gettext_lazy

django.utils.encoding.smart_text = smart_str
django.utils.encoding.force_text = force_str
django.utils.translation.ugettext = gettext
django.utils.translation.ugettext_lazy = gettext_lazy


# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.1/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-r14_0+r^tq2t_9&n!jqpknrj!855ceo0++$cg==ka2il%*#r@u'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ["*"]


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',

    'django.contrib.staticfiles',
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    'rest_framework',
    'rest_framework.authtoken',
    'rest_framework_simplejwt',
    'django_filters',
    'dj_rest_auth',
    'dj_rest_auth.registration',
    'corsheaders',
    "apps.users",
    "apps.products",
    "apps.orders",
    "apps.wallets",

]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    # "allauth.account.middleware.AccountMiddleware",

]

ROOT_URLCONF = 'config.urls'

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
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# Database
# https://docs.djangoproject.com/en/5.1/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}


# Password validation
# https://docs.djangoproject.com/en/5.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.1/topics/i18n/

LANGUAGE_CODE = 'ar-eg'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True

# ==============================================================================
# STATIC & MEDIA FILES SETTINGS
# ==============================================================================

STATICFILES_DIRS = [BASE_DIR / "static"]

STATIC_URL = "/static/"

STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"

MEDIA_ROOT = BASE_DIR / "media"

# Default primary key field type
# https://docs.djangoproject.com/en/5.1/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

REST_FRAMEWORK = {

    "COERCE_DECIMAL_TO_STRING": False,
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_AUTHENTICATION_CLASSES": [
        # "rest_framework.authentication.BasicAuthentication",
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    "DEFAULT_PARSER_CLASSES": (
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
    ),
}
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": datetime.timedelta(days=7),
    "REFRESH_TOKEN_LIFETIME": datetime.timedelta(days=7),
    "AUTH_HEADER_TYPES": ("Bearer", "JWT", "Token"),
    "ROTATE_REFRESH_TOKENS": True,
}

REST_USE_JWT = True

REST_AUTH_REGISTER_SERIALIZERS = {
    # "REGISTER_SERIALIZER": "core.serializers.RegisterSerializer",
}

REST_AUTH_SERIALIZERS = {
    # "USER_DETAILS_SERIALIZER": "src.apps.authentication.custom_account.api.serializers.UserDetailsSerializer",
    # "LOGIN_SERIALIZER": "apps.users.api.serializers.CustomLoginSerializer",
    # "PASSWORD_RESET_SERIALIZER": "src.apps.authentication.custom_account.api.serializers.CustomPasswordResetSerializer",  # noqa
}

REST_USE_JWT = True
SITE_ID = 1

# ==============================================================================
# DJANGO ALLAUTH SETTINGS
# ==============================================================================

ACCOUNT_EMAIL_REQUIRED = True

ACCOUNT_EMAIL_VERIFICATION = "optional"

ACCOUNT_AUTHENTICATION_METHOD = "username"

ACCOUNT_USER_DISPLAY = lambda user: user.get_full_name()  # noqa

ACCOUNT_SIGNUP_PASSWORD_ENTER_TWICE = False

ACCOUNT_UNIQUE_EMAIL = False

ACCOUNT_USERNAME_REQUIRED = False

# =========================================================
# EMAIL SETTINGS
# =========================================================

EMAIL_BACKEND = "django.core.mail.backends.filebased.EmailBackend"
EMAIL_FILE_PATH = "tmp/app-messages"  # change this to a proper location

AUTHENTICATION_BACKENDS = [
    # Needed to login by username in Django admin, regardless of `allauth`
    'django.contrib.auth.backends.ModelBackend',

    # `allauth` specific authentication methods, such as login by email
    'allauth.account.auth_backends.AuthenticationBackend',
]

CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    'https://7b1c-154-177-231-215.ngrok-free.app',

]
CSRF_TRUSTED_ORIGINS = [
    'http://localhost:3000',
    'http://127.0.0.1:3000',
    'https://7b1c-154-177-231-215.ngrok-free.app',
]
# In settings.py
CORS_ALLOW_METHODS = [
    'DELETE',
    'GET',
    'OPTIONS',
    'PATCH',
    'POST',
    'PUT',
]
# ==============================================================================
# CHANNELS SETTINGS
# ==============================================================================

CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

AUTH_USER_MODEL = "users.CustomUser"

