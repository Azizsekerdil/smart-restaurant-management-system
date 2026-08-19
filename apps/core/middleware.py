"""Ara katmanlar: istek bağlamı, güvenlik başlıkları, hız sınırlama."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import translation
from django.utils.deprecation import MiddlewareMixin

_local = threading.local()


def get_current_request():
    """Aktif isteği döndürür (denetim kaydı için).

    Thread-local kullanır; istek dışında (yönetim komutu, Celery) None döner.
    """
    return getattr(_local, "request", None)


class RequestContextMiddleware:
    """Aktif isteği thread-local'e koyar ve istek sonunda temizler."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _local.request = request
        try:
            return self.get_response(request)
        finally:
            _local.request = None


class UserLanguageMiddleware:
    """Giriş yapmış kullanıcının dil tercihini uygular.

    Django'nun ``LocaleMiddleware``'i dili oturumdan, çerezden ve
    ``Accept-Language`` başlığından çıkarır; kullanıcı profilindeki
    tercihten haberi yoktur. Bu ara katman olmadan, kullanıcının
    ayarlarda seçtiği dil hiçbir işe yaramaz.

    Giriş yapmış kullanıcı için **profil tek doğruluk kaynağıdır**. Üst
    çubuktaki dil değiştirici de seçimi profile yazar (bkz.
    ``apps.accounts.views.switch_language``), böylece çerez ile profil
    arasında "hangisi kazanır" sorusu hiç doğmaz.

    Anonim kullanıcılarda (giriş ekranı) karar ``LocaleMiddleware``'e
    bırakılır; o dili çerezden ve ``Accept-Language`` başlığından çıkarır.

    ``AuthenticationMiddleware``'den **sonra** çalışmalıdır (kullanıcıya
    erişebilmek için) ve ``LocaleMiddleware``'in seçimini bilinçli olarak
    geçersiz kılar.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.supported = dict(settings.LANGUAGES)

    def __call__(self, request):
        user = getattr(request, "user", None)
        activated = False

        if user is not None and getattr(user, "is_authenticated", False):
            preferred = getattr(user, "language_preference", "") or ""
            if preferred in self.supported:
                translation.activate(preferred)
                request.LANGUAGE_CODE = translation.get_language()
                activated = True

        try:
            return self.get_response(request)
        finally:
            if activated:
                # Sunucu iş parçacıklarını yeniden kullanır; bir sonraki
                # isteğe dil sızmamalı.
                translation.deactivate()


class PasswordChangeRequiredMiddleware:
    """``must_change_password`` işaretli hesabı parola değiştirmeye kilitler.

    Neden ara katman?
    -----------------
    Bayrağı yalnızca giriş görünümünde denetlemek yeterli DEĞİLDİR:
    kullanıcı giriş sonrası yönlendirmeyi yok sayıp herhangi bir adrese
    (panel, müşteri listesi, mali rapor, yedek indirme, AI ayarları)
    doğrudan gidebilir. Bu ara katman her istekte çalışır; böylece geçici
    parolayla açılmış bir oturum, parola değiştirilene kadar hiçbir
    korumalı alana erişemez.

    Serbest bırakılanlar: parola değiştirme ekranının kendisi, çıkış, giriş
    ve dil değiştirme ile statik/medya dosyaları. API istekleri
    yönlendirilmez; makine istemcisi anlayabilsin diye 403 + kod döner.
    """

    #: URL adı bazlı muafiyetler (yol değişse de geçerli kalır).
    EXEMPT_URL_NAMES = frozenset(
        {
            "accounts:password_change",
            "accounts:logout",
            "accounts:login",
            "accounts:switch_language",
        }
    )
    #: Önek bazlı muafiyetler.
    EXEMPT_PREFIXES = ("/static/", "/media/", "/i18n/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if (
            user is not None
            and getattr(user, "is_authenticated", False)
            and getattr(user, "must_change_password", False)
            and not self._is_exempt(request)
        ):
            return self._block(request)
        return self.get_response(request)

    def _is_exempt(self, request) -> bool:
        if request.path.startswith(self.EXEMPT_PREFIXES):
            return True
        from django.urls import Resolver404, resolve

        try:
            match = resolve(request.path_info)
        except Resolver404:
            return False
        return match.view_name in self.EXEMPT_URL_NAMES

    @staticmethod
    def _block(request):
        from django.contrib import messages as django_messages
        from django.shortcuts import redirect

        message = (
            "Geçici parolanızı değiştirmeden sisteme erişemezsiniz. "
            "Lütfen yeni bir parola belirleyin."
        )
        if request.path.startswith("/api/") or request.headers.get("Accept") == "application/json":
            return JsonResponse({"detail": message, "code": "password_change_required"}, status=403)
        django_messages.warning(request, message)
        return redirect("accounts:password_change")


class SecurityHeadersMiddleware(MiddlewareMixin):
    """Ek güvenlik başlıkları ve içerik güvenlik politikası.

    Django'nun SecurityMiddleware'ini tamamlar: CSP, Permissions-Policy.
    Statik varlıklar yerelde sunulduğu için CSP 'self' ile sıkı tutulabilir.
    """

    CSP = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; "
        "font-src 'self' data:; "
        "connect-src 'self' ws: wss:; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )

    def process_response(self, request, response):
        response.setdefault("Content-Security-Policy", self.CSP)
        response.setdefault(
            "Permissions-Policy",
            "geolocation=(), microphone=(), camera=(), payment=(), usb=()",
        )
        response.setdefault("X-Content-Type-Options", "nosniff")
        response.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        return response


class RateLimitMiddleware:
    """Basit, bağımlılık gerektirmeyen istek hızı sınırlayıcı.

    `settings.RATELIMIT_RULES` içindeki yol öneklerine göre çalışır.
    Tek süreçli kurulum için yeterlidir; çok sunuculu dağıtımda Redis
    tabanlı bir çözüme (django-ratelimit + Redis cache) geçirilmelidir.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.rules: dict[str, tuple[int, int]] = getattr(settings, "RATELIMIT_RULES", {})
        self.enabled: bool = getattr(settings, "RATELIMIT_ENABLED", True)
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def __call__(self, request):
        if self.enabled and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            rule = self._match(request.path)
            if rule is not None:
                limit, window = rule
                key = f"{self._identity(request)}::{request.path[:80]}"
                if not self._allow(key, limit, window):
                    return self._too_many(request, window)
        return self.get_response(request)

    def _match(self, path: str) -> tuple[int, int] | None:
        for prefix, rule in self.rules.items():
            if path.startswith(prefix):
                return rule
        return None

    @staticmethod
    def _identity(request) -> str:
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            return f"u{user.pk}"
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        ip = forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR", "?")
        return f"ip{ip}"

    def _allow(self, key: str, limit: int, window: int) -> bool:
        now = time.monotonic()
        with self._lock:
            bucket = self._hits[key]
            while bucket and now - bucket[0] > window:
                bucket.popleft()
            if len(bucket) >= limit:
                return False
            bucket.append(now)
            # Bellek sızıntısını önle: nadiren kullanılan anahtarları temizle.
            if len(self._hits) > 5000:
                stale = [k for k, v in self._hits.items() if not v or now - v[-1] > 3600]
                for k in stale:
                    self._hits.pop(k, None)
            return True

    @staticmethod
    def _too_many(request, window: int):
        message = f"Çok fazla istek gönderildi. Lütfen {window} saniye içinde tekrar deneyin."
        if request.path.startswith("/api/") or request.headers.get("Accept") == "application/json":
            return JsonResponse({"detail": message, "code": "rate_limited"}, status=429)
        return render(request, "core/429.html", {"message": message}, status=429)
