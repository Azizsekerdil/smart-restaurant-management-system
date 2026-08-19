"""Sağlayıcı arayüzü ve ortak veri tipleri."""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


class ProviderError(Exception):
    """Sağlayıcı kaynaklı genel hata."""


class ProviderNotConfigured(ProviderError):
    """Sağlayıcı kapalı veya API anahtarı tanımlı değil."""


class ProviderUnavailable(ProviderError):
    """Sağlayıcıya ulaşılamıyor (ağ hatası, sunucu kapalı)."""


class ProviderTimeout(ProviderError):
    """İstek zaman aşımına uğradı."""


class ProviderRateLimited(ProviderError):
    """Kota veya hız limiti aşıldı."""


@dataclass
class AIMessage:
    """Sohbet mesajı."""

    role: str  # system | user | assistant
    content: str
    images: list[str] = field(default_factory=list)  # base64 data URI listesi

    def to_openai(self) -> dict[str, Any]:
        if not self.images:
            return {"role": self.role, "content": self.content}
        parts: list[dict[str, Any]] = [{"type": "text", "text": self.content}]
        for image in self.images:
            parts.append({"type": "image_url", "image_url": {"url": image}})
        return {"role": self.role, "content": parts}


@dataclass
class AIResponse:
    """Sağlayıcıdan dönen yanıt."""

    text: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    finish_reason: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class BaseProvider:
    """Tüm sağlayıcıların uygulaması gereken arayüz."""

    #: settings.AI_PROVIDERS içindeki anahtar
    key: str = ""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.label: str = config.get("label", self.key)
        self.base_url: str = config.get("base_url", "").rstrip("/")
        self.is_local: bool = bool(config.get("is_local", False))
        self.models: dict[str, str] = config.get("models", {})

    # -------------------------------------------------- yapılandırma
    @property
    def api_key(self) -> str:
        """API anahtarını ortam değişkeninden okur.

        Anahtar hiçbir zaman veritabanına yazılmaz veya loglanmaz.
        """
        env_name = self.config.get("api_key_env", "")
        return os.environ.get(env_name, "").strip() if env_name else ""

    @property
    def is_enabled(self) -> bool:
        return bool(self.config.get("enabled"))

    @property
    def is_configured(self) -> bool:
        """Yerel sağlayıcılar anahtar gerektirmez."""
        if not self.is_enabled:
            return False
        if self.is_local:
            return True
        return bool(self.api_key)

    def model_for(self, task: str) -> str:
        """Göreve uygun model kimliğini döndürür; yoksa genel modele düşer."""
        return self.models.get(task) or self.models.get("general") or ""

    @property
    def price_input(self) -> Decimal:
        return Decimal(str(self.config.get("price_per_1m_input", 0)))

    @property
    def price_output(self) -> Decimal:
        return Decimal(str(self.config.get("price_per_1m_output", 0)))

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> Decimal:
        cost = (
            Decimal(input_tokens) * self.price_input + Decimal(output_tokens) * self.price_output
        ) / Decimal("1000000")
        return cost.quantize(Decimal("0.000001"))

    # -------------------------------------------------- arayüz
    def chat(
        self,
        messages: list[AIMessage],
        *,
        model: str = "",
        temperature: float = 0.3,
        max_tokens: int = 1500,
        timeout: int = 120,
        json_mode: bool = False,
    ) -> AIResponse:
        raise NotImplementedError

    def stream(
        self,
        messages: list[AIMessage],
        *,
        model: str = "",
        temperature: float = 0.3,
        max_tokens: int = 1500,
        timeout: int = 120,
    ) -> Iterator[str]:
        raise NotImplementedError

    def list_models(self, *, timeout: int = 15) -> list[str]:
        """Sağlayıcıdaki kullanılabilir modelleri döndürür."""
        raise NotImplementedError

    def health_check(self, *, timeout: int = 15) -> tuple[bool, str, int]:
        """(başarılı_mı, mesaj, gecikme_ms) döndürür. Anahtarı asla göstermez."""
        raise NotImplementedError
