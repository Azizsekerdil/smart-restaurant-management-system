"""Django ayarları - Akıllı Restaurant Yönetim Sistemi.

12-factor yaklaşımı: tüm ortama bağlı değerler `.env` üzerinden gelir.
`DJANGO_ENV` değişkeni (development | production | test) davranışı belirler.
"""

from __future__ import annotations

# ============================================================
#  ORTAM
# ============================================================
import sys  # noqa: E402
from pathlib import Path

from django.core.management.utils import get_random_secret_key

from config.env import (
    BASE_DIR,
    DATA_DIR,
    IS_FROZEN,
    env_bool,
    env_decimal,
    env_int,
    env_list,
    env_str,
    has_secret,
)

DJANGO_ENV = env_str("DJANGO_ENV", "development").lower()
IS_PRODUCTION = DJANGO_ENV == "production"

# Test çalıştırıcısı altında olup olmadığımızı güvenilir biçimde tespit et.
# Bu bayrak, testlerin yanlışlıkla gerçek AI sağlayıcılarına ağ isteği
# göndermesini engeller (hermetik test ortamı).
_UNDER_TEST = "pytest" in sys.modules or "test" in sys.argv
IS_TEST = DJANGO_ENV == "test" or _UNDER_TEST

DEBUG = env_bool("DJANGO_DEBUG", not IS_PRODUCTION)

_secret = env_str("DJANGO_SECRET_KEY", "")
if not _secret or _secret.startswith("degistir"):
    if IS_PRODUCTION:
        raise RuntimeError(
            "Üretim ortamında DJANGO_SECRET_KEY tanımlanmalıdır. "
            'Üretmek için: python -c "from django.core.management.utils import '
            'get_random_secret_key as k; print(k())"'
        )
    # Geliştirme/test: her başlatmada geçici anahtar üret.
    _secret = get_random_secret_key()
SECRET_KEY = _secret

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]")
CSRF_TRUSTED_ORIGINS = env_list(
    "DJANGO_CSRF_TRUSTED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000"
)

# ============================================================
#  UYGULAMALAR
# ============================================================
DJANGO_APPS = [
    "daphne",  # ASGI runserver desteği (channels)
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    # Döndürülen refresh token'ların kara listeye alınması: çalınan bir
    # refresh token, kullanıcı yeni token aldığı anda geçersizleşir.
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "corsheaders",
    "channels",
    "axes",
]

LOCAL_APPS = [
    "apps.core",
    "apps.accounts",
    "apps.catalog",
    "apps.inventory",
    "apps.floor",
    "apps.orders",
    "apps.kitchen",
    "apps.crm",
    "apps.hr",
    "apps.reports",
    "apps.backups",
    "apps.training",
    "apps.ai",
    "apps.devcenter",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ============================================================
#  ARA KATMANLAR
# ============================================================
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "axes.middleware.AxesMiddleware",
    # AuthenticationMiddleware'den sonra gelmelidir: kullanıcının profil
    # dilini uygular ve LocaleMiddleware'in seçimini geçersiz kılar.
    "apps.core.middleware.UserLanguageMiddleware",
    # Geçici/ilk parola ile açılmış oturumu, parola değiştirilene kadar
    # korumalı alanların TAMAMINDAN uzak tutar (MessageMiddleware'den
    # sonra olmalıdır: uyarı mesajı yazar).
    "apps.core.middleware.PasswordChangeRequiredMiddleware",
    "apps.core.middleware.RequestContextMiddleware",
    "apps.core.middleware.SecurityHeadersMiddleware",
    "apps.core.middleware.RateLimitMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.template.context_processors.i18n",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.restaurant_context",
                "apps.core.context_processors.navigation_context",
            ],
        },
    },
]

# ============================================================
#  VERİTABANI
# ============================================================
_db_engine = env_str("DB_ENGINE", "sqlite").lower()

if _db_engine in {"postgres", "postgresql", "psql"}:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env_str("DB_NAME", "restaurant"),
            "USER": env_str("DB_USER", "restaurant"),
            "PASSWORD": env_str("DB_PASSWORD", ""),
            "HOST": env_str("DB_HOST", "127.0.0.1"),
            "PORT": env_str("DB_PORT", "5432"),
            "CONN_MAX_AGE": 60,
            "OPTIONS": {"connect_timeout": 10},
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": DATA_DIR / f"{env_str('DB_NAME', 'restaurant')}.sqlite3",
            "OPTIONS": {
                # Eşzamanlı POS + mutfak ekranı erişimi için gerekli.
                "timeout": 30,
                "init_command": (
                    "PRAGMA journal_mode=WAL;"
                    "PRAGMA synchronous=NORMAL;"
                    "PRAGMA foreign_keys=ON;"
                ),
            },
        }
    }

# Testlerde SQLite varsayılan olarak bellekte çalışır. Yedekleme kodu
# veritabanı dosyasına ayrı bir bağlantı açtığı için, bellek içi bir
# veritabanı gerçek kod yolunu sınamaz. Testlerde de dosya kullanılır.
if IS_TEST and "sqlite" in DATABASES["default"]["ENGINE"]:
    DATABASES["default"]["TEST"] = {"NAME": str(DATA_DIR / "test_restaurant.sqlite3")}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ============================================================
#  KİMLİK DOĞRULAMA VE YETKİLENDİRME
# ============================================================
AUTH_USER_MODEL = "accounts.User"

AUTHENTICATION_BACKENDS = [
    # django-axes önce gelmelidir (brute-force kilidi).
    "axes.backends.AxesStandaloneBackend",
    "apps.accounts.backends.EmailOrUsernameBackend",
    "django.contrib.auth.backends.ModelBackend",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
    {"NAME": "apps.accounts.validators.ComplexityValidator"},
]

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "core:home"
LOGOUT_REDIRECT_URL = "accounts:login"

# --- Brute force koruması (django-axes) ---
AXES_FAILURE_LIMIT = env_int("AXES_FAILURE_LIMIT", 5)
AXES_COOLOFF_TIME = env_int("AXES_COOLOFF_HOURS", 1)
AXES_LOCKOUT_PARAMETERS = ["username", "ip_address"]
AXES_RESET_ON_SUCCESS = True
AXES_ENABLED = not IS_TEST
AXES_LOCKOUT_TEMPLATE = "accounts/lockout.html"
AXES_VERBOSE = False

# --- Oturum ---
SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_AGE = env_int("SESSION_TIMEOUT_MINUTES", 480) * 60
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
SESSION_SAVE_EVERY_REQUEST = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", IS_PRODUCTION)

# --- CSRF ---
CSRF_COOKIE_HTTPONLY = False  # HTMX/Alpine JS token okuyabilmeli
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = env_bool("CSRF_COOKIE_SECURE", IS_PRODUCTION)

# ============================================================
#  GÜVENLİK BAŞLIKLARI
# ============================================================
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", False)
if IS_PRODUCTION:
    SECURE_HSTS_SECONDS = 31_536_000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# CORS: varsayılan olarak kapalı; yalnızca açıkça izin verilen kaynaklar.
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS", "http://localhost:8000")
CORS_ALLOW_CREDENTIALS = True

# Basit istek hızı sınırlaması (apps.core.middleware.RateLimitMiddleware)
RATELIMIT_RULES = {
    "/accounts/login/": (10, 300),  # 5 dakikada 10 deneme
    # PIN kısa bir sırdır: yol bazlı sınır, apps.accounts.pin_security
    # kilidinin üstüne ikinci bir katman koyar.
    "/accounts/pin/": (10, 300),
    "/api/": (300, 60),  # dakikada 300 API isteği
    "/ai/": (30, 60),  # dakikada 30 AI isteği
    "/devcenter/": (60, 60),
}
RATELIMIT_ENABLED = not IS_TEST

# ============================================================
#  ULUSLARARASILAŞTIRMA
# ============================================================
LANGUAGE_CODE = env_str("DJANGO_LANGUAGE_CODE", "tr")
TIME_ZONE = env_str("DJANGO_TIME_ZONE", "Europe/Istanbul")
USE_I18N = True
USE_TZ = True
USE_THOUSAND_SEPARATOR = True

LANGUAGES = [
    ("tr", "Türkçe"),
    ("en", "English"),
]
LOCALE_PATHS = [BASE_DIR / "locale"]

# ============================================================
#  STATİK VE MEDYA DOSYALARI
# ============================================================
STATIC_URL = "/static/"
# Kaynak dosyalar pakete gömülür; kullanıcı yüklemeleri yazılabilir dizine.
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"] if (BASE_DIR / "static").is_dir() else []

MEDIA_URL = "/media/"
MEDIA_ROOT = DATA_DIR / "media"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        )
    },
}

# Güvenli dosya yükleme sınırları
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10 MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = 2000
ALLOWED_UPLOAD_EXTENSIONS = [".jpg", ".jpeg", ".png", ".webp", ".gif", ".pdf", ".csv", ".xlsx"]
ALLOWED_UPLOAD_MIME_TYPES = [
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
    "application/pdf",
    "text/csv",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
]

# ============================================================
#  DJANGO REST FRAMEWORK
# ============================================================
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "apps.core.api.StandardPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.AnonRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {"user": "1000/hour", "anon": "60/hour"},
    "EXCEPTION_HANDLER": "apps.core.api.friendly_exception_handler",
}

from datetime import timedelta  # noqa: E402

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=2),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# ============================================================
#  GERÇEK ZAMANLI KATMAN (Channels)
# ============================================================
if env_str("CHANNEL_LAYER", "inmemory").lower() == "redis":
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {"hosts": [env_str("REDIS_URL", "redis://127.0.0.1:6379/0")]},
        }
    }
else:
    CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

# ============================================================
#  ARKA PLAN GÖREVLERİ (isteğe bağlı Celery)
# ============================================================
CELERY_ENABLED = env_bool("CELERY_ENABLED", False)
CELERY_BROKER_URL = env_str("CELERY_BROKER_URL", "redis://127.0.0.1:6379/1")
CELERY_RESULT_BACKEND = env_str("CELERY_RESULT_BACKEND", "redis://127.0.0.1:6379/2")
CELERY_TASK_ALWAYS_EAGER = not CELERY_ENABLED
CELERY_TIMEZONE = TIME_ZONE

# ============================================================
#  İŞLETME AYARLARI
# ============================================================
RESTAURANT = {
    "NAME": env_str("RESTAURANT_NAME", "Akıllı Restaurant"),
    "CURRENCY": env_str("RESTAURANT_CURRENCY", "TRY"),
    "CURRENCY_SYMBOL": env_str("RESTAURANT_CURRENCY_SYMBOL", "₺"),
    "DEFAULT_TAX_RATE": env_decimal("RESTAURANT_DEFAULT_TAX_RATE", "10.00"),
    "SERVICE_CHARGE_RATE": env_decimal("RESTAURANT_SERVICE_CHARGE_RATE", "0.00"),
}

# ============================================================
#  YAPAY ZEKÂ AYARLARI
# ============================================================
AI = {
    "ROUTING_POLICY": env_str("AI_ROUTING_POLICY", "local_first"),
    "MASK_PII": env_bool("AI_MASK_PII", True),
    "SENSITIVE_LOCAL_ONLY": env_bool("AI_SENSITIVE_LOCAL_ONLY", True),
    "TIMEOUT_SECONDS": env_int("AI_TIMEOUT_SECONDS", 120),
    # Muhakeme (reasoning) modelleri yanıttan önce token harcadığı için
    # varsayılan sınır cömert tutulur; düşük değerler boş yanıta yol açar.
    "MAX_TOKENS": env_int("AI_MAX_TOKENS", 2500),
    "MAX_RETRIES": env_int("AI_MAX_RETRIES", 2),
    "DAILY_BUDGET_USD": env_decimal("AI_DAILY_BUDGET_USD", "1.00"),
    "MONTHLY_BUDGET_USD": env_decimal("AI_MONTHLY_BUDGET_USD", "20.00"),
    # Devre kesici: art arda bu kadar hata sonrası sağlayıcı geçici kapanır.
    "CIRCUIT_BREAKER_THRESHOLD": 3,
    "CIRCUIT_BREAKER_COOLDOWN_SECONDS": 120,
}


def _provider_enabled(env_key: str, default: bool) -> bool:
    """Sağlayıcı etkin mi? Test ortamında tüm sağlayıcılar zorla kapatılır.

    Böylece test paketi hiçbir koşulda gerçek bir AI sunucusuna bağlanmaz;
    AI davranışı testlerde sahte (fake) sağlayıcılarla doğrulanır.
    """
    if IS_TEST:
        return False
    return env_bool(env_key, default)


# Sağlayıcı governance metadata'sı (bölge/saklama/eğitim kullanımı).
# İLKE: Resmî kaynak doğrulanmadan sağlayıcı şartı UYDURULMAZ. Bulut
# sağlayıcılarda değerler REVIEW_REQUIRED başlar; işletme/DPO resmî
# belgeden doğrulayıp .env üzerinden geçersiz kılabilir (örn.
# OPENAI_GOV_REGION). "reviewed" alanı yalnızca yapısal olarak kesin olan
# yerel sağlayıcılarda True'dur.
def _local_governance() -> dict:
    return {
        "region": "Yerel makine — veri bilgisayardan çıkmaz",
        "training_use": "YOK (yerel süreç, dışarı veri gitmez)",
        "retention": "YOK (istek bellekte işlenir)",
        "terms_url": "",
        "reviewed": True,
    }


def _safe_terms_url(url: str) -> str:
    """Şartlar bağlantısı şablonda ``href`` içine basılır.

    Değer koddaki sabitten gelir, ama yanlışlıkla ``javascript:`` benzeri
    bir şema girilirse tıklanabilir bir betiğe dönüşür. Yalnızca https'e
    izin verilir.
    """
    return url if url.startswith("https://") else ""


def _cloud_governance(prefix: str, terms_url: str) -> dict:
    terms_url = _safe_terms_url(terms_url)
    return {
        "region": env_str(f"{prefix}_GOV_REGION", "UNKNOWN — REVIEW_REQUIRED"),
        "training_use": env_str(f"{prefix}_GOV_TRAINING", "UNKNOWN — REVIEW_REQUIRED"),
        "retention": env_str(f"{prefix}_GOV_RETENTION", "UNKNOWN — REVIEW_REQUIRED"),
        "terms_url": terms_url,
        "reviewed": env_bool(f"{prefix}_GOV_REVIEWED", False),
    }


AI_PROVIDERS = {
    "lmstudio": {
        "label": "LM Studio (yerel)",
        "kind": "openai_compatible",
        "is_local": True,
        "enabled": _provider_enabled("LMSTUDIO_ENABLED", True),
        "base_url": env_str("LMSTUDIO_BASE_URL", "http://127.0.0.1:1234/v1"),
        "api_key_env": "LMSTUDIO_API_KEY",
        "has_key": True,  # yerel sunucu anahtar gerektirmez
        "models": {
            "general": env_str("LMSTUDIO_MODEL_GENERAL", "google/gemma-4-12b-qat"),
            "reasoning": env_str("LMSTUDIO_MODEL_REASONING", "qwen/qwen3-vl-8b"),
            "code": env_str("LMSTUDIO_MODEL_CODE", "qwen/qwen3-vl-8b"),
            "math": env_str("LMSTUDIO_MODEL_MATH", "qwen2.5-math-7b-instruct"),
            "vision": env_str("LMSTUDIO_MODEL_VISION", "moondream-2b-2025-04-14"),
            "domain": env_str("LMSTUDIO_MODEL_DOMAIN", "biomistral-7b"),
            "embedding": env_str(
                "LMSTUDIO_MODEL_EMBEDDING", "text-embedding-nomic-embed-text-v1.5"
            ),
        },
        # Yerel model ücretsizdir.
        "price_per_1m_input": 0.0,
        "price_per_1m_output": 0.0,
        "governance": _local_governance(),
    },
    "ollama": {
        "label": "Ollama (yerel)",
        "kind": "openai_compatible",
        "is_local": True,
        "enabled": _provider_enabled("OLLAMA_ENABLED", False),
        "base_url": env_str("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1"),
        "api_key_env": "OLLAMA_API_KEY",
        "has_key": True,
        "models": {"general": env_str("OLLAMA_MODEL_GENERAL", "llama3.1:8b")},
        "price_per_1m_input": 0.0,
        "price_per_1m_output": 0.0,
        "governance": _local_governance(),
    },
    "nvidia": {
        "label": "NVIDIA NIM",
        "kind": "openai_compatible",
        "is_local": False,
        "enabled": _provider_enabled("NVIDIA_ENABLED", False),
        "base_url": env_str("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
        "api_key_env": "NVIDIA_API_KEY",
        "has_key": has_secret("NVIDIA_API_KEY"),
        # Model kimlikleri build.nvidia.com kataloğundan doğrulanmıştır
        # (Ağustos 2026). Katalog değişebilir; "Test et" düğmesi
        # /v1/models çıktısıyla karşılaştırma yapar.
        "models": {
            "general": env_str("NVIDIA_MODEL_GENERAL", "nvidia/nemotron-3.5-lightning-30b-a3b"),
            "reasoning": env_str("NVIDIA_MODEL_REASONING", "nvidia/nemotron-3-ultra-550b-a55b"),
            "code": env_str("NVIDIA_MODEL_CODE", "zai/glm-5.2"),
            "math": env_str("NVIDIA_MODEL_REASONING", "nvidia/nemotron-3-ultra-550b-a55b"),
            "vision": env_str(
                "NVIDIA_MODEL_VISION", "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"
            ),
            "domain": env_str("NVIDIA_MODEL_GENERAL", "nvidia/nemotron-3.5-lightning-30b-a3b"),
            "embedding": env_str("NVIDIA_MODEL_EMBEDDING", "nvidia/nemotron-3-embed-1b"),
        },
        # Ücretsiz uç nokta (free endpoint) kullanımı için maliyet 0 kabul
        # edilir; ücretli/partner uç noktaya geçerseniz burayı güncelleyin.
        "price_per_1m_input": 0.0,
        "price_per_1m_output": 0.0,
        "governance": _cloud_governance("NVIDIA", "https://www.nvidia.com/en-us/agreements/"),
    },
    "openai": {
        "label": "OpenAI uyumlu",
        "kind": "openai_compatible",
        "is_local": False,
        "enabled": _provider_enabled("OPENAI_ENABLED", False),
        "base_url": env_str("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        "api_key_env": "OPENAI_API_KEY",
        "has_key": has_secret("OPENAI_API_KEY"),
        "models": {"general": env_str("OPENAI_MODEL_GENERAL", "gpt-4o-mini")},
        "price_per_1m_input": 0.15,
        "price_per_1m_output": 0.60,
        "governance": _cloud_governance("OPENAI", "https://openai.com/policies/"),
    },
    "anthropic": {
        "label": "Anthropic Claude",
        "kind": "anthropic",
        "is_local": False,
        "enabled": _provider_enabled("ANTHROPIC_ENABLED", False),
        "base_url": env_str("ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1"),
        "api_key_env": "ANTHROPIC_API_KEY",
        "has_key": has_secret("ANTHROPIC_API_KEY"),
        "models": {"general": env_str("ANTHROPIC_MODEL_GENERAL", "claude-sonnet-4-5")},
        "price_per_1m_input": 3.00,
        "price_per_1m_output": 15.00,
        "governance": _cloud_governance(
            "ANTHROPIC", "https://www.anthropic.com/legal/commercial-terms"
        ),
    },
    "gemini": {
        "label": "Google Gemini",
        "kind": "gemini",
        "is_local": False,
        "enabled": _provider_enabled("GEMINI_ENABLED", False),
        "base_url": env_str("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta"),
        "api_key_env": "GEMINI_API_KEY",
        "has_key": has_secret("GEMINI_API_KEY"),
        "models": {"general": env_str("GEMINI_MODEL_GENERAL", "gemini-2.0-flash")},
        "price_per_1m_input": 0.10,
        "price_per_1m_output": 0.40,
        "governance": _cloud_governance("GEMINI", "https://ai.google.dev/gemini-api/terms"),
    },
    "openrouter": {
        "label": "OpenRouter",
        "kind": "openai_compatible",
        "is_local": False,
        "enabled": _provider_enabled("OPENROUTER_ENABLED", False),
        "base_url": env_str("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        "api_key_env": "OPENROUTER_API_KEY",
        "has_key": has_secret("OPENROUTER_API_KEY"),
        "models": {
            "general": env_str("OPENROUTER_MODEL_GENERAL", "meta-llama/llama-3.3-70b-instruct")
        },
        "price_per_1m_input": 0.30,
        "price_per_1m_output": 0.60,
        "governance": _cloud_governance("OPENROUTER", "https://openrouter.ai/terms"),
    },
}

# ============================================================
#  AI GELİŞTİRME MERKEZİ / GÜVENLİ TERMİNAL
# ============================================================
# Paketlenmiş uygulamada kaynak kodu yoktur; geliştirme merkezi anlamsız
# ve risklidir, bu yüzden zorla kapatılır.
#  GÜVENLİ VARSAYILAN: Geliştirme Merkezi ve terminali VARSAYILAN OLARAK
#  KAPALIDIR ve yalnızca açıkça `DEVCENTER_ENABLED=True` yazılırsa açılır.
#  Önceki varsayılan "üretim değilse açık" idi; bu, .env dosyası olmayan
#  her kurulumda kod çalıştırma yüzeyini sessizce açıyordu.
DEVCENTER = {
    "ENABLED": env_bool("DEVCENTER_ENABLED", False) and not IS_FROZEN,
    "TERMINAL_ENABLED": (env_bool("DEVCENTER_TERMINAL_ENABLED", False) and not IS_FROZEN),
    "ROOT": Path(env_str("DEVCENTER_ROOT", str(BASE_DIR))).resolve(),
    "COMMAND_TIMEOUT": env_int("DEVCENTER_COMMAND_TIMEOUT", 180),
    "SNAPSHOT_DIR": DATA_DIR / ".devcenter" / "snapshots",
}

# Güvenlik gereği: üretim ortamında bu özellikler varsayılan olarak kapalıdır.
if IS_PRODUCTION and not env_bool("DEVCENTER_ENABLED", False):
    DEVCENTER["ENABLED"] = False
    DEVCENTER["TERMINAL_ENABLED"] = False

FIELD_ENCRYPTION_KEY = env_str("FIELD_ENCRYPTION_KEY", "")

# ============================================================
#  YEDEKLEME
# ============================================================
#  Yedekler yazılabilir veri dizininde tutulur; paketlenmiş uygulamada bu
#  exe'nin yanıdır. Yedek arşivi müşteri kişisel verisi içerir, bu yüzden
#  klasör depoya girmez (bkz. .gitignore) ve indirme ayrı bir izne bağlıdır.
BACKUP_DIR = Path(env_str("BACKUP_DIR", str(DATA_DIR / "backups"))).resolve()
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

BACKUP = {
    # Kaç yedek saklanacak (elle + otomatik ayrı sayılır). 0 = sınırsız.
    "KEEP_LAST": env_int("BACKUP_KEEP_LAST", 20),
    # Otomatik yedekleme
    "SCHEDULE_ENABLED": env_bool("BACKUP_SCHEDULE_ENABLED", False),
    "SCHEDULE_HOURS": env_int("BACKUP_SCHEDULE_HOURS", 24),
    # .env dosyası (API anahtarları) yedeğe VARSAYILAN OLARAK GİRMEZ.
    # Yedek paylaşıldığında anahtarların sızmaması için bilinçli tercihtir;
    # arayüzden açıkça istenirse eklenir.
    "ALLOW_SECRETS": env_bool("BACKUP_ALLOW_SECRETS", False),
    # Medya klasörü büyükse yedek çok şişebilir; üst sınır (MB).
    "MEDIA_LIMIT_MB": env_int("BACKUP_MEDIA_LIMIT_MB", 512),
}

# ============================================================
#  VERİ SAKLAMA (KVKK/GDPR storage limitation)
# ============================================================
#  Süreler GÜN cinsindendir; 0 = o kategori için otomatik temizleme KAPALI.
#  Varsayılanlar bilinçli olarak 0'dır: saklama süresi işletmenin ve veri
#  sorumlusunun (DPO) vereceği bir karardır, kod bir süre dayatmaz.
#  Temizleme `manage.py purge_expired_logs` ile yapılır (önizleme varsayılan,
#  uygulama --apply ister) ve her çalıştırma denetim kaydı bırakır.
RETENTION = {
    # AuditLog.ip_address / user_agent redaksiyonu (kayıt silinmez).
    "AUDIT_IP_DAYS": env_int("RETENTION_AUDIT_IP_DAYS", 0),
    # ConsentRecord.ip_address redaksiyonu (rıza kanıtının kendisi kalır).
    "CONSENT_IP_DAYS": env_int("RETENTION_CONSENT_IP_DAYS", 0),
    # Sonuçlanmış rezervasyonlarda misafir kimlik bilgisi redaksiyonu.
    "RESERVATION_GUEST_DAYS": env_int("RETENTION_RESERVATION_GUEST_DAYS", 0),
    # Kapanmış bekleme listesi kayıtlarında misafir bilgisi redaksiyonu.
    "WAITLIST_GUEST_DAYS": env_int("RETENTION_WAITLIST_GUEST_DAYS", 0),
}

# ============================================================
#  E-POSTA
# ============================================================
EMAIL_BACKEND = env_str("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env_str("EMAIL_HOST", "")
EMAIL_PORT = env_int("EMAIL_PORT", 587)
EMAIL_HOST_USER = env_str("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env_str("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
DEFAULT_FROM_EMAIL = env_str("DEFAULT_FROM_EMAIL", "noreply@restaurant.local")

# ============================================================
#  ÖNBELLEK
# ============================================================
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "restaurant-default",
        "TIMEOUT": 300,
    }
}

# ============================================================
#  GÜNLÜKLEME
#  Not: Hassas veriler (API anahtarları, parolalar) SensitiveDataFilter
#  tarafından maskelenir.
# ============================================================
LOG_DIR = DATA_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "mask_secrets": {"()": "apps.core.logging_filters.SensitiveDataFilter"},
    },
    "formatters": {
        "verbose": {
            "format": "{asctime} [{levelname}] {name}: {message}",
            "style": "{",
        },
        "simple": {"format": "[{levelname}] {message}", "style": "{"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
            "filters": ["mask_secrets"],
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOG_DIR / "restaurant.log",
            "maxBytes": 5 * 1024 * 1024,
            "backupCount": 5,
            "encoding": "utf-8",
            "formatter": "verbose",
            "filters": ["mask_secrets"],
        },
        "security_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOG_DIR / "security.log",
            "maxBytes": 5 * 1024 * 1024,
            "backupCount": 10,
            "encoding": "utf-8",
            "formatter": "verbose",
            "filters": ["mask_secrets"],
        },
    },
    "root": {"handlers": ["console", "file"], "level": "INFO"},
    "loggers": {
        "django": {"handlers": ["console", "file"], "level": "INFO", "propagate": False},
        "django.security": {
            "handlers": ["security_file", "console"],
            "level": "INFO",
            "propagate": False,
        },
        "axes": {"handlers": ["security_file"], "level": "WARNING", "propagate": False},
        "apps": {"handlers": ["console", "file"], "level": "DEBUG" if DEBUG else "INFO"},
        "apps.security": {
            "handlers": ["security_file", "console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

MESSAGE_STORAGE = "django.contrib.messages.storage.session.SessionStorage"

# Test ortamında hızlandırma
if IS_TEST:
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # nosec B303
    EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
