"""Sağlayıcı kayıt defteri."""

from __future__ import annotations

from django.conf import settings

from apps.ai.providers.anthropic import AnthropicProvider
from apps.ai.providers.base import BaseProvider, ProviderNotConfigured
from apps.ai.providers.gemini import GeminiProvider
from apps.ai.providers.openai_compatible import OpenAICompatibleProvider

PROVIDER_CLASSES: dict[str, type[BaseProvider]] = {
    "openai_compatible": OpenAICompatibleProvider,
    "anthropic": AnthropicProvider,
    "gemini": GeminiProvider,
}

_cache: dict[str, BaseProvider] = {}


def get_provider(key: str) -> BaseProvider:
    """Anahtarına göre sağlayıcı örneği döndürür."""
    if key in _cache:
        return _cache[key]

    config = settings.AI_PROVIDERS.get(key)
    if config is None:
        raise ProviderNotConfigured(f"Bilinmeyen sağlayıcı: '{key}'")

    provider_class = PROVIDER_CLASSES.get(config.get("kind", "openai_compatible"))
    if provider_class is None:
        raise ProviderNotConfigured(f"'{key}' için adapter bulunamadı.")

    provider = provider_class(config)
    provider.key = key
    _cache[key] = provider
    return provider


def clear_cache() -> None:
    """Ayar değişikliğinden sonra önbelleği temizler (testler için)."""
    _cache.clear()


def all_providers() -> list[BaseProvider]:
    return [get_provider(key) for key in settings.AI_PROVIDERS]


def available_providers(*, local_only: bool = False) -> list[BaseProvider]:
    """Kullanıma hazır (etkin ve yapılandırılmış) sağlayıcılar."""
    providers = [p for p in all_providers() if p.is_configured]
    if local_only:
        providers = [p for p in providers if p.is_local]
    # Yerel sağlayıcılar önce gelsin (gizlilik ve maliyet avantajı).
    return sorted(providers, key=lambda p: (not p.is_local, p.key))


def provider_status() -> list[dict]:
    """Arayüzde gösterilecek durum listesi. API anahtarı asla dönmez."""
    rows = []
    for provider in all_providers():
        rows.append(
            {
                "key": provider.key,
                "label": provider.label,
                "is_local": provider.is_local,
                "enabled": provider.is_enabled,
                "configured": provider.is_configured,
                "base_url": provider.base_url,
                "api_key_env": provider.config.get("api_key_env", ""),
                "api_key_masked": _mask(provider.api_key),
                "models": provider.models,
                "price_input": float(provider.price_input),
                "price_output": float(provider.price_output),
                # Governance: bölge/saklama/eğitim kullanımı. Bulut
                # sağlayıcılarda doğrulanmamış değerler REVIEW_REQUIRED
                # gelir; işletme resmî belgeden doğrulayıp .env ile doldurur.
                "governance": provider.config.get("governance", {}),
            }
        )
    return rows


def _mask(value: str) -> str:
    """API anahtarını maskeler: yalnızca ilk 4 ve son 2 karakter görünür."""
    if not value:
        return "— tanımlı değil —"
    if len(value) <= 8:
        return "•" * len(value)
    return f"{value[:4]}{'•' * 12}{value[-2:]}"
