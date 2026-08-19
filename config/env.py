"""Ortam değişkeni okuma yardımcıları.

`.env` dosyasını yükler ve tip güvenli okuyucular sunar. Ayarların
tamamı ortam değişkeninden gelir; hiçbir gizli değer kaynak kodunda
sabitlenmez.
"""

from __future__ import annotations

import os
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

from dotenv import load_dotenv

#: Uygulama kaynaklarının (şablon, statik dosya, kod) bulunduğu dizin.
#: PyInstaller ile paketlendiğinde bu, geçici açılma dizinidir (salt okunur
#: kabul edilmelidir).
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    BASE_DIR = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    IS_FROZEN = True
else:
    BASE_DIR = Path(__file__).resolve().parent.parent
    IS_FROZEN = False

#: Yazılabilir verinin (veritabanı, medya, günlük, yedek) bulunduğu dizin.
#: Normal kurulumda proje köküyle aynıdır. Paketlenmiş uygulamada ise
#: exe'nin yanındaki klasördür — geçici açılma dizinine yazmak, program
#: kapandığında tüm verinin silinmesi anlamına gelirdi.
_data_override = os.environ.get("RESTAURANT_DATA_DIR", "").strip()
if _data_override:
    DATA_DIR = Path(_data_override).resolve()
elif IS_FROZEN:
    DATA_DIR = Path(sys.executable).resolve().parent
else:
    DATA_DIR = BASE_DIR
DATA_DIR.mkdir(parents=True, exist_ok=True)

# .env önce yazılabilir dizinde aranır (paketlenmiş uygulamada kullanıcı
# bunu exe'nin yanına koyar), yoksa kaynak dizininde.
for _candidate in (DATA_DIR / ".env", BASE_DIR / ".env"):
    if _candidate.is_file():
        load_dotenv(_candidate, override=False)
        break

_TRUE = {"1", "true", "yes", "on", "evet", "acik", "açık"}
_FALSE = {"0", "false", "no", "off", "hayir", "hayır", "kapali", "kapalı"}


class ImproperlyConfigured(Exception):
    """Zorunlu bir ortam değişkeni eksik veya hatalı."""


def env_str(key: str, default: str | None = None, *, required: bool = False) -> str:
    value = os.environ.get(key)
    if value is None or value == "":
        if required and default is None:
            raise ImproperlyConfigured(
                f"Zorunlu ortam değişkeni tanımlı değil: {key}. "
                f".env.example dosyasını .env olarak kopyalayıp doldurun."
            )
        return default if default is not None else ""
    return value.strip()


def env_bool(key: str, default: bool = False) -> bool:
    raw = os.environ.get(key)
    if raw is None or raw.strip() == "":
        return default
    normalized = raw.strip().lower()
    if normalized in _TRUE:
        return True
    if normalized in _FALSE:
        return False
    return default


def env_int(key: str, default: int = 0) -> int:
    raw = os.environ.get(key)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw.strip())
    except ValueError:
        return default


def env_decimal(key: str, default: str = "0") -> Decimal:
    raw = os.environ.get(key, default)
    try:
        return Decimal(str(raw).strip() or default)
    except (InvalidOperation, ValueError):
        return Decimal(default)


def env_list(key: str, default: str = "") -> list[str]:
    raw = os.environ.get(key, default) or default
    return [part.strip() for part in raw.split(",") if part.strip()]


def has_secret(key: str) -> bool:
    """Bir API anahtarının gerçekten tanımlı olup olmadığını söyler.

    Değerin kendisini asla döndürmez; yalnızca varlık bilgisini verir.
    """
    value = os.environ.get(key, "").strip()
    if not value:
        return False
    lowered = value.lower()
    # Yer tutucu değerler "tanımlı" sayılmaz. Aksi hâlde uygulama, örnek
    # dosyadan kopyalanmış bir metinle gerçek sağlayıcıya istek atmayı
    # dener ve kullanıcıya anlamsız bir kimlik doğrulama hatası gösterir.
    placeholders = (
        "degistir",
        "değiştir",
        "your-",
        "your_",
        "yourprovider",
        "xxx",
        "changeme",
        "<",
    )
    if lowered.startswith(placeholders):
        return False
    return "api_key_here" not in lowered and "apikeyhere" not in lowered
