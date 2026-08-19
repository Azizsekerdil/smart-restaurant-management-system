"""POS PIN doğrulaması için deneme sınırlaması ve PIN gücü politikası.

Neden ayrı bir modül?
---------------------
PIN, parolanın yerine geçen kısa (4-8 haneli) bir sırdır. Anahtar uzayı
küçük olduğu için tek savunma **deneme sayısını sınırlamaktır**. Bu modül
iki bağımsız yerde kullanılır:

* ``apps.accounts.views.pin_switch`` — POS terminalinde hızlı kullanıcı
  değişimi,
* ``apps.accounts.decorators.manager_approval_required`` — iptal/iade/
  indirim gibi işlemlerde yetkili onayı.

Sayaç hem **hedef kullanıcı adına** hem de **istemci IP'sine** göre
tutulur; böylece tek bir hesaba yönelik saldırı da, tek bir makineden
farklı hesaplara yayılan saldırı da durur.

Sınır: sayaçlar Django önbelleğinde tutulur. Varsayılan kurulum tek
süreçlidir (LocMemCache) ve bu yeterlidir. Çok süreçli/çok sunuculu bir
dağıtımda paylaşımlı bir önbellek (Redis/Memcached) yapılandırılmalıdır;
bkz. ``docs/known-limitations.md``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from django.conf import settings
from django.core.cache import cache

#: Kilitlenmeden önce izin verilen başarısız deneme sayısı.
MAX_FAILURES = 5
#: Başarısız denemelerin sayıldığı ve kilidin sürdüğü süre (saniye).
LOCKOUT_SECONDS = 900
#: Artan gecikmenin üst sınırı (saniye). Testlerde gecikme uygulanmaz.
MAX_DELAY_SECONDS = 2.0

_PREFIX = "pin-attempt"


@dataclass(frozen=True)
class LockState:
    locked: bool
    failures: int
    retry_after: int


def client_ip(request) -> str:
    """İstemci IP'si. Ters vekil arkasında X-Forwarded-For'un ilk değeri."""
    forwarded = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip()
    return forwarded or request.META.get("REMOTE_ADDR") or "unknown"


def _keys(request, username: str) -> tuple[str, str]:
    user_key = f"{_PREFIX}:user:{(username or '').strip().lower()[:150]}"
    ip_key = f"{_PREFIX}:ip:{client_ip(request)}"
    return user_key, ip_key


def _failures(key: str) -> int:
    return int(cache.get(key) or 0)


def state(request, username: str) -> LockState:
    """Bu istek için kilit durumunu döndürür (sayacı artırmaz)."""
    user_key, ip_key = _keys(request, username)
    failures = max(_failures(user_key), _failures(ip_key))
    locked = failures >= MAX_FAILURES
    retry_after = LOCKOUT_SECONDS if locked else 0
    return LockState(locked=locked, failures=failures, retry_after=retry_after)


def record_failure(request, username: str) -> LockState:
    """Başarısız denemeyi her iki sayaca da işler ve yeni durumu döndürür."""
    user_key, ip_key = _keys(request, username)
    failures = 0
    for key in (user_key, ip_key):
        current = _failures(key) + 1
        # Pencere her başarısız denemede yenilenir: saldırgan bekleyerek
        # sayacı sıfırlayamaz.
        cache.set(key, current, LOCKOUT_SECONDS)
        failures = max(failures, current)
    locked = failures >= MAX_FAILURES
    return LockState(locked=locked, failures=failures, retry_after=LOCKOUT_SECONDS if locked else 0)


def reset(request, username: str) -> None:
    """Başarılı doğrulamadan sonra sayaçları temizler."""
    for key in _keys(request, username):
        cache.delete(key)


def failure_count(*, username: str | None = None, ip: str | None = None) -> int:
    """Bir kullanıcı adı ya da IP için işlenmiş başarısız deneme sayısı.

    Sayaçları dışarıdan (testlerden ve işletim izlemesinden) okunabilir
    kılar; ``state`` bir ``request`` nesnesi ister, bu ise istemeden
    kullanılabilir.
    """
    total = 0
    if username is not None:
        total = max(total, _failures(f"{_PREFIX}:user:{username.strip().lower()[:150]}"))
    if ip is not None:
        total = max(total, _failures(f"{_PREFIX}:ip:{ip}"))
    return total


def apply_backoff(failures: int) -> None:
    """Artan gecikme: her başarısız denemeden sonra yanıt yavaşlar.

    Otomatik deneme hızını düşürür, insan kullanıcıyı rahatsız etmez.
    Test ortamında (``settings.IS_TEST``) uygulanmaz.
    """
    if getattr(settings, "IS_TEST", False) or failures <= 0:
        return
    time.sleep(min(0.25 * (2 ** (failures - 1)), MAX_DELAY_SECONDS))


# ------------------------------------------------------------------
#  PIN gücü politikası
# ------------------------------------------------------------------
#: Sık kullanılan / tahmin edilmesi kolay PIN'ler.
WEAK_PINS = frozenset(
    {
        "0000",
        "1111",
        "1212",
        "1234",
        "1004",
        "2000",
        "2222",
        "2580",
        "3333",
        "4321",
        "4444",
        "5555",
        "6666",
        "6969",
        "7777",
        "8888",
        "9999",
        "123456",
        "654321",
        "112233",
        "121212",
        "000000",
        "111111",
    }
)

MIN_PIN_LENGTH = 4
MAX_PIN_LENGTH = 8


class WeakPinError(ValueError):
    """PIN politikayı karşılamıyor."""


def _is_sequential(pin: str) -> bool:
    pairs = list(zip(pin, pin[1:], strict=False))
    ascending = all(int(b) - int(a) == 1 for a, b in pairs)
    descending = all(int(a) - int(b) == 1 for a, b in pairs)
    return ascending or descending


def validate_pin(pin: str) -> None:
    """PIN politikasını uygular; ihlalde ``WeakPinError`` yükseltir.

    Kural: 4-8 hane, tek rakamın tekrarı değil, ardışık dizi değil,
    bilinen zayıf PIN listesinde değil.
    """
    if not pin or not pin.isdigit():
        raise WeakPinError("PIN yalnızca rakamlardan oluşmalıdır.")
    if not (MIN_PIN_LENGTH <= len(pin) <= MAX_PIN_LENGTH):
        raise WeakPinError(f"PIN {MIN_PIN_LENGTH}-{MAX_PIN_LENGTH} haneli rakamlardan oluşmalıdır.")
    if len(set(pin)) == 1:
        raise WeakPinError("PIN aynı rakamın tekrarı olamaz (ör. 1111).")
    if _is_sequential(pin):
        raise WeakPinError("PIN ardışık bir dizi olamaz (ör. 1234, 4321).")
    if pin in WEAK_PINS:
        raise WeakPinError("Bu PIN çok yaygın kullanılıyor; başka bir PIN seçin.")
