"""AI Gateway / Yönlendirici.

Sorumlulukları
--------------
* **Yönlendirme**: göreve ve gizlilik politikasına göre sağlayıcı seçer.
* **Yedekleme**: bir sağlayıcı başarısız olursa sıradakine geçer.
* **Devre kesici**: art arda hata veren sağlayıcıyı geçici olarak devre dışı bırakır.
* **Bütçe**: günlük/aylık USD limiti aşılırsa bulut çağrılarını engeller.
* **Gizlilik**: istem içindeki kişisel verileri maskeler; hassas görevleri
  yalnızca yerel modele yönlendirir.
* **Kayıt**: her çağrıyı token ve maliyetle birlikte kaydeder.

Tüm uygulama AI'ya yalnızca bu modül üzerinden erişir.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Iterator
from dataclasses import dataclass
from decimal import Decimal

from django.conf import settings
from django.core.cache import cache

from apps.ai.models import AITask, AIUsageLog
from apps.ai.providers import (
    AIMessage,
    AIResponse,
    BaseProvider,
    ProviderError,
    ProviderNotConfigured,
    ProviderTimeout,
    available_providers,
    get_provider,
)
from apps.ai.providers.base import ProviderRateLimited, ProviderUnavailable
from apps.core.logging_filters import mask_secrets

logger = logging.getLogger("apps.ai")


class AIUnavailable(Exception):
    """Hiçbir sağlayıcı kullanılamıyor. Kullanıcıya anlaşılır mesaj taşır."""


class BudgetExceeded(Exception):
    """Bütçe limiti aşıldı."""


@dataclass
class RouteDecision:
    provider: BaseProvider
    model: str
    reason: str


# ------------------------------------------------------------------
#  Kişisel veri maskeleme (KVKK)
# ------------------------------------------------------------------
_PII_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b[\w.%+-]+@[\w.-]+\.[A-Za-z]{2,}\b"), "[E-POSTA]"),
    (
        re.compile(r"(?<!\d)(?:\+?90[\s\-]?)?0?5\d{2}[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}(?!\d)"),
        "[TELEFON]",
    ),
    (re.compile(r"(?<!\d)\d{11}(?!\d)"), "[TC-KIMLIK]"),
    (re.compile(r"(?<!\d)(?:\d{4}[\s\-]?){3}\d{4}(?!\d)"), "[KART-NO]"),
    (re.compile(r"\bTR\d{2}[\s]?(?:\d{4}[\s]?){5}\d{2}\b", re.IGNORECASE), "[IBAN]"),
]


def mask_pii(text: str) -> str:
    """İstemdeki kişisel verileri maskeler."""
    if not text:
        return text
    masked = text
    for pattern, replacement in _PII_RULES:
        masked = pattern.sub(replacement, masked)
    return masked


# ------------------------------------------------------------------
#  Devre kesici
# ------------------------------------------------------------------
def _breaker_key(provider_key: str) -> str:
    return f"ai:breaker:{provider_key}"


def _failure_key(provider_key: str) -> str:
    return f"ai:failures:{provider_key}"


def is_circuit_open(provider_key: str) -> bool:
    return bool(cache.get(_breaker_key(provider_key)))


def record_failure(provider_key: str) -> None:
    threshold = settings.AI["CIRCUIT_BREAKER_THRESHOLD"]
    cooldown = settings.AI["CIRCUIT_BREAKER_COOLDOWN_SECONDS"]
    count = (cache.get(_failure_key(provider_key)) or 0) + 1
    cache.set(_failure_key(provider_key), count, timeout=cooldown * 2)
    if count >= threshold:
        cache.set(_breaker_key(provider_key), True, timeout=cooldown)
        logger.warning(
            "AI devre kesici açıldı: %s (%d hata). %d saniye devre dışı.",
            provider_key,
            count,
            cooldown,
        )


def record_success(provider_key: str) -> None:
    cache.delete(_failure_key(provider_key))
    cache.delete(_breaker_key(provider_key))


def reset_all_breakers() -> None:
    for key in settings.AI_PROVIDERS:
        record_success(key)


# ------------------------------------------------------------------
#  Bütçe
# ------------------------------------------------------------------
def budget_status() -> dict:
    daily_limit = Decimal(settings.AI["DAILY_BUDGET_USD"])
    monthly_limit = Decimal(settings.AI["MONTHLY_BUDGET_USD"])
    spent_today = AIUsageLog.spent_today()
    spent_month = AIUsageLog.spent_this_month()
    return {
        "daily_limit": daily_limit,
        "monthly_limit": monthly_limit,
        "spent_today": spent_today,
        "spent_month": spent_month,
        "daily_remaining": max(daily_limit - spent_today, Decimal("0")) if daily_limit else None,
        "monthly_remaining": (
            max(monthly_limit - spent_month, Decimal("0")) if monthly_limit else None
        ),
        "daily_exceeded": bool(daily_limit) and spent_today >= daily_limit,
        "monthly_exceeded": bool(monthly_limit) and spent_month >= monthly_limit,
        "daily_percent": (min(int(spent_today / daily_limit * 100), 100) if daily_limit else 0),
        "monthly_percent": (
            min(int(spent_month / monthly_limit * 100), 100) if monthly_limit else 0
        ),
    }


def can_use_cloud() -> tuple[bool, str]:
    status = budget_status()
    if status["daily_exceeded"]:
        return False, (
            f"Günlük yapay zekâ bütçesi ({status['daily_limit']} USD) doldu. "
            "Yerel model kullanılıyor. Limiti .env içindeki AI_DAILY_BUDGET_USD "
            "ile değiştirebilirsiniz."
        )
    if status["monthly_exceeded"]:
        return False, (
            f"Aylık yapay zekâ bütçesi ({status['monthly_limit']} USD) doldu. "
            "Yerel model kullanılıyor."
        )
    return True, ""


# ------------------------------------------------------------------
#  Yönlendirme
# ------------------------------------------------------------------
def build_chain(
    task: str,
    *,
    preferred_provider: str = "",
    sensitive: bool = False,
    require_vision: bool = False,
) -> list[RouteDecision]:
    """Denenecek sağlayıcı sırasını oluşturur."""
    policy = settings.AI["ROUTING_POLICY"]
    sensitive_local_only = settings.AI["SENSITIVE_LOCAL_ONLY"]

    candidates = available_providers()
    if not candidates:
        return []

    cloud_ok, _reason = can_use_cloud()
    force_local = policy == "local_only" or (sensitive and sensitive_local_only) or not cloud_ok

    local = [p for p in candidates if p.is_local]
    cloud = [p for p in candidates if not p.is_local]

    if force_local:
        ordered = local
    elif policy == "cloud_only":
        ordered = cloud
    elif policy == "cloud_first":
        ordered = cloud + local
    else:  # local_first (varsayılan)
        ordered = local + cloud

    # Açıkça istenen sağlayıcı öne alınır.
    if preferred_provider:
        ordered = sorted(ordered, key=lambda p: p.key != preferred_provider)

    chain: list[RouteDecision] = []
    for provider in ordered:
        if is_circuit_open(provider.key):
            continue
        model = provider.model_for("vision" if require_vision else task)
        if not model:
            continue
        if require_vision and "vision" not in provider.models:
            continue
        reason = "yerel model (gizlilik/maliyet önceliği)" if provider.is_local else "bulut modeli"
        if sensitive and provider.is_local:
            reason = "hassas veri -> yerel model zorunlu"
        chain.append(RouteDecision(provider=provider, model=model, reason=reason))
    return chain


# ------------------------------------------------------------------
#  Ana giriş noktası
# ------------------------------------------------------------------
def ask(
    prompt: str,
    *,
    system: str = "",
    task: str = AITask.GENERAL,
    feature: str = "",
    user=None,
    history: list[AIMessage] | None = None,
    images: list[str] | None = None,
    temperature: float = 0.3,
    max_tokens: int = 0,
    json_mode: bool = False,
    sensitive: bool = False,
    preferred_provider: str = "",
    preferred_model: str = "",
    timeout: int | None = None,
) -> AIResponse:
    """Yapay zekâya soru sorar ve yanıtı döndürür.

    Hiçbir sağlayıcı kullanılamıyorsa `AIUnavailable` yükseltir; çağıran
    taraf bunu kullanıcıya anlaşılır bir uyarı olarak göstermelidir.
    """
    timeout = timeout or settings.AI["TIMEOUT_SECONDS"]
    max_tokens = max_tokens or settings.AI["MAX_TOKENS"]
    max_retries = settings.AI["MAX_RETRIES"]

    safe_prompt = mask_pii(prompt) if settings.AI["MASK_PII"] else prompt
    safe_system = mask_pii(system) if settings.AI["MASK_PII"] else system

    messages: list[AIMessage] = []
    if safe_system:
        messages.append(AIMessage(role="system", content=safe_system))
    for item in history or []:
        messages.append(item)
    messages.append(AIMessage(role="user", content=safe_prompt, images=images or []))

    chain = build_chain(
        task,
        preferred_provider=preferred_provider,
        sensitive=sensitive,
        require_vision=bool(images),
    )
    if not chain:
        message = _no_provider_message(sensitive=sensitive)
        _log(
            user=user,
            task=task,
            feature=feature,
            provider="-",
            model="-",
            is_local=True,
            outcome=AIUsageLog.Outcome.BLOCKED_POLICY,
            error=message,
            prompt=safe_prompt,
        )
        raise AIUnavailable(message)

    errors: list[str] = []
    for index, decision in enumerate(chain):
        provider = decision.provider
        model = preferred_model if (preferred_model and index == 0) else decision.model

        for attempt in range(max_retries + 1):
            try:
                response = provider.chat(
                    messages,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=timeout,
                    json_mode=json_mode,
                )
                record_success(provider.key)
                _log(
                    user=user,
                    task=task,
                    feature=feature,
                    provider=provider.key,
                    model=response.model,
                    is_local=provider.is_local,
                    outcome=(
                        AIUsageLog.Outcome.FALLBACK if index > 0 else AIUsageLog.Outcome.SUCCESS
                    ),
                    input_tokens=response.input_tokens,
                    output_tokens=response.output_tokens,
                    cost=provider.estimate_cost(response.input_tokens, response.output_tokens),
                    latency=response.latency_ms,
                    prompt=safe_prompt,
                    response=response.text,
                )
                return response

            except (ProviderTimeout, ProviderUnavailable, ProviderRateLimited) as exc:
                errors.append(f"{provider.label}: {exc}")
                record_failure(provider.key)
                if attempt < max_retries:
                    time.sleep(0.5 * (attempt + 1))  # kısa geri çekilme
                    continue
                break
            except ProviderNotConfigured as exc:
                errors.append(f"{provider.label}: {exc}")
                break
            except ProviderError as exc:
                errors.append(f"{provider.label}: {exc}")
                record_failure(provider.key)
                break

    detail = " | ".join(errors[:3])
    message = (
        "Yapay zekâ şu anda yanıt veremiyor. Denenen sağlayıcılar başarısız oldu.\n"
        f"Ayrıntı: {detail}\n\n"
        "Yerel model için LM Studio'yu açıp bir model yükleyin ve "
        "'Developer > Start Server' ile sunucuyu başlatın (varsayılan adres "
        "http://127.0.0.1:1234). Sistem, yapay zekâ olmadan da tam olarak çalışır."
    )
    _log(
        user=user,
        task=task,
        feature=feature,
        provider=chain[0].provider.key,
        model=chain[0].model,
        is_local=chain[0].provider.is_local,
        outcome=AIUsageLog.Outcome.FAILED,
        error=detail,
        prompt=safe_prompt,
    )
    raise AIUnavailable(message)


def ask_safe(prompt: str, **kwargs) -> tuple[bool, str]:
    """`ask` fonksiyonunun hata yükseltmeyen sarmalayıcısı.

    Arayüz kodunu basitleştirir: (başarılı_mı, metin) döndürür.
    """
    try:
        response = ask(prompt, **kwargs)
        return True, response.text
    except AIUnavailable as exc:
        return False, str(exc)
    except Exception as exc:  # pragma: no cover
        logger.exception("Beklenmeyen AI hatası")
        return False, f"Beklenmeyen bir yapay zekâ hatası oluştu: {exc}"


def stream(
    prompt: str,
    *,
    system: str = "",
    task: str = AITask.GENERAL,
    feature: str = "",
    user=None,
    history: list[AIMessage] | None = None,
    temperature: float = 0.3,
    max_tokens: int = 0,
    sensitive: bool = False,
    preferred_provider: str = "",
    preferred_model: str = "",
) -> Iterator[str]:
    """Akış (streaming) yanıt üretir."""
    timeout = settings.AI["TIMEOUT_SECONDS"]
    max_tokens = max_tokens or settings.AI["MAX_TOKENS"]
    safe_prompt = mask_pii(prompt) if settings.AI["MASK_PII"] else prompt
    safe_system = mask_pii(system) if settings.AI["MASK_PII"] else system

    messages: list[AIMessage] = []
    if safe_system:
        messages.append(AIMessage(role="system", content=safe_system))
    messages.extend(history or [])
    messages.append(AIMessage(role="user", content=safe_prompt))

    chain = build_chain(task, preferred_provider=preferred_provider, sensitive=sensitive)
    if not chain:
        yield _no_provider_message(sensitive=sensitive)
        return

    decision = chain[0]
    provider = decision.provider
    model = preferred_model or decision.model
    started = time.perf_counter()
    collected: list[str] = []
    try:
        for piece in provider.stream(
            messages, model=model, temperature=temperature, max_tokens=max_tokens, timeout=timeout
        ):
            collected.append(piece)
            yield piece
        record_success(provider.key)
        outcome = AIUsageLog.Outcome.SUCCESS
        error = ""
    except ProviderError as exc:
        record_failure(provider.key)
        outcome = AIUsageLog.Outcome.FAILED
        error = str(exc)
        yield f"\n\n[Yapay zekâ hatası: {exc}]"

    text = "".join(collected)
    # Akışta token sayısı gelmez; kaba tahmin: ~4 karakter = 1 token
    approx_out = max(len(text) // 4, 0)
    approx_in = max(len(safe_prompt + safe_system) // 4, 0)
    _log(
        user=user,
        task=task,
        feature=feature,
        provider=provider.key,
        model=model,
        is_local=provider.is_local,
        outcome=outcome,
        error=error,
        input_tokens=approx_in,
        output_tokens=approx_out,
        cost=provider.estimate_cost(approx_in, approx_out),
        latency=int((time.perf_counter() - started) * 1000),
        prompt=safe_prompt,
        response=text,
    )


def _no_provider_message(*, sensitive: bool) -> str:
    cloud_ok, budget_reason = can_use_cloud()
    parts = ["Kullanılabilir bir yapay zekâ sağlayıcısı bulunamadı."]
    if not cloud_ok:
        parts.append(budget_reason)
    if sensitive and settings.AI["SENSITIVE_LOCAL_ONLY"]:
        parts.append(
            "Bu görev hassas veri içerdiği için yalnızca yerel modele "
            "yönlendirilebilir (AI_SENSITIVE_LOCAL_ONLY=True)."
        )
    parts.append(
        "Çözüm: LM Studio'yu açın, bir model yükleyin ve "
        "'Developer > Start Server' ile yerel sunucuyu başlatın "
        "(http://127.0.0.1:1234). Alternatif olarak .env dosyasında bir bulut "
        "sağlayıcısını etkinleştirip API anahtarı tanımlayın."
    )
    return " ".join(parts)


def _log(
    *,
    user,
    task: str,
    feature: str,
    provider: str,
    model: str,
    is_local: bool,
    outcome: str,
    error: str = "",
    input_tokens: int = 0,
    output_tokens: int = 0,
    cost: Decimal = Decimal("0"),
    latency: int = 0,
    prompt: str = "",
    response: str = "",
) -> None:
    """Kullanım kaydı yazar. İstem/yanıt maskelenir ve kısaltılır."""
    try:
        AIUsageLog.objects.create(
            user=user if (user is not None and getattr(user, "pk", None)) else None,
            task=task,
            feature=feature[:60],
            provider=provider[:32],
            model=str(model)[:120],
            is_local=is_local,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=cost,
            latency_ms=latency,
            outcome=outcome,
            error_message=mask_secrets(error)[:500],
            prompt_preview=mask_secrets(mask_pii(prompt))[:1500],
            response_preview=mask_secrets(mask_pii(response))[:1500],
        )
    except Exception:  # pragma: no cover - kayıt hatası akışı durdurmamalı
        logger.debug("AI kullanım kaydı yazılamadı", exc_info=True)


# ------------------------------------------------------------------
#  Bağlantı testi
# ------------------------------------------------------------------
def test_provider(provider_key: str, *, timeout: int = 20) -> dict:
    """Tek bir sağlayıcıyı test eder. API anahtarını asla döndürmez."""
    try:
        provider = get_provider(provider_key)
    except ProviderNotConfigured as exc:
        return {"key": provider_key, "ok": False, "message": str(exc), "latency_ms": 0}

    if not provider.is_enabled:
        return {
            "key": provider_key,
            "label": provider.label,
            "ok": False,
            "message": f"{provider.label} .env dosyasında etkin değil.",
            "latency_ms": 0,
            "models": [],
        }
    if not provider.is_configured:
        return {
            "key": provider_key,
            "label": provider.label,
            "ok": False,
            "message": (
                f"{provider.label} için API anahtarı tanımlı değil "
                f"({provider.config.get('api_key_env')})."
            ),
            "latency_ms": 0,
            "models": [],
        }

    ok, message, latency = provider.health_check(timeout=timeout)
    models: list[str] = []
    if ok:
        try:
            models = provider.list_models(timeout=timeout)
        except ProviderError:
            models = []
    return {
        "key": provider_key,
        "label": provider.label,
        "ok": ok,
        "message": message,
        "latency_ms": latency,
        "is_local": provider.is_local,
        "models": models[:50],
        "configured_models": provider.models,
        "circuit_open": is_circuit_open(provider_key),
    }


def test_all_providers(*, timeout: int = 20) -> list[dict]:
    return [test_provider(key, timeout=timeout) for key in settings.AI_PROVIDERS]
