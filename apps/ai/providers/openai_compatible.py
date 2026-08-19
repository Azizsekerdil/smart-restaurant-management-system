"""OpenAI uyumlu sağlayıcı adapteri.

LM Studio, Ollama, NVIDIA NIM, OpenRouter ve OpenAI'nin kendisi aynı
`/v1/chat/completions` sözleşmesini kullanır; hepsi bu tek adapterle
desteklenir.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator
from typing import Any

import httpx

from apps.ai.providers.base import (
    AIMessage,
    AIResponse,
    BaseProvider,
    ProviderError,
    ProviderNotConfigured,
    ProviderRateLimited,
    ProviderTimeout,
    ProviderUnavailable,
)

logger = logging.getLogger("apps.ai")


class OpenAICompatibleProvider(BaseProvider):
    """`/v1/chat/completions` sözleşmesini uygulayan sağlayıcılar."""

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        key = self.api_key
        if key:
            headers["Authorization"] = f"Bearer {key}"
        elif self.is_local:
            # LM Studio anahtar doğrulaması yapmaz ama başlık bekleyebilir.
            headers["Authorization"] = "Bearer lm-studio"
        if self.key == "openrouter":
            headers["HTTP-Referer"] = "http://localhost:8000"
            headers["X-Title"] = "Akilli Restaurant Yonetim Sistemi"
        return headers

    def _post(self, path: str, payload: dict[str, Any], timeout: int) -> httpx.Response:
        if not self.is_configured:
            raise ProviderNotConfigured(
                f"{self.label} yapılandırılmamış. "
                f".env dosyasında {self.config.get('api_key_env')} tanımlayın "
                f"ve sağlayıcıyı etkinleştirin."
            )
        url = f"{self.base_url}{path}"
        try:
            with httpx.Client(timeout=timeout) as client:
                return client.post(url, json=payload, headers=self._headers())
        except httpx.TimeoutException as exc:
            raise ProviderTimeout(f"{self.label} {timeout} saniye içinde yanıt vermedi.") from exc
        except httpx.ConnectError as exc:
            hint = (
                " LM Studio açık mı ve 'Local Server' başlatıldı mı?"
                if self.key == "lmstudio"
                else ""
            )
            raise ProviderUnavailable(
                f"{self.label} adresine bağlanılamadı ({url}).{hint}"
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(f"{self.label} ile iletişim hatası.") from exc

    @staticmethod
    def _raise_for_status(response: httpx.Response, label: str) -> None:
        if response.status_code < 400:
            return
        detail = ""
        try:
            body = response.json()
            detail = body.get("error", {}).get("message") or body.get("detail") or ""
        except Exception:
            detail = response.text[:300]
        if response.status_code in (401, 403):
            raise ProviderNotConfigured(
                f"{label}: kimlik doğrulama başarısız (HTTP {response.status_code}). "
                "API anahtarını kontrol edin."
            )
        if response.status_code == 429:
            raise ProviderRateLimited(f"{label}: kota veya hız limiti aşıldı. {detail}")
        if response.status_code == 404:
            raise ProviderError(f"{label}: model veya uç nokta bulunamadı (HTTP 404). {detail}")
        raise ProviderError(f"{label}: HTTP {response.status_code}. {detail}")

    # ------------------------------------------------------------ chat
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
        model = model or self.model_for("general")
        if not model:
            raise ProviderNotConfigured(f"{self.label} için model tanımlı değil.")

        payload: dict[str, Any] = {
            "model": model,
            "messages": [m.to_openai() for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        started = time.perf_counter()
        response = self._post("/chat/completions", payload, timeout)
        self._raise_for_status(response, self.label)
        latency = int((time.perf_counter() - started) * 1000)

        try:
            data = response.json()
            choice = data["choices"][0]
            message = choice["message"]
        except (KeyError, IndexError, ValueError) as exc:
            raise ProviderError(f"{self.label}: beklenmeyen yanıt biçimi.") from exc

        text = (message.get("content") or "").strip()
        # Muhakeme (reasoning) modelleri düşünme adımlarını ayrı bir alanda
        # döndürür ve nihai yanıt gelene kadar `content` boş kalır.
        reasoning = (message.get("reasoning_content") or message.get("reasoning") or "").strip()
        finish_reason = choice.get("finish_reason", "")

        if not text and reasoning:
            if finish_reason == "length":
                raise ProviderError(
                    f"{self.label}: '{model}' bir muhakeme (reasoning) modeli ve token "
                    f"sınırına düşünme aşamasındayken ulaştı, bu yüzden yanıt üretemedi. "
                    f"Çözüm: daha yüksek bir token sınırı verin ya da muhakeme yapmayan "
                    f"bir modeli (ör. qwen/qwen3-vl-8b) tercih edin."
                )
            # Bazı sunucular nihai yanıtı da bu alanda döndürür.
            text = reasoning

        if not text:
            raise ProviderError(
                f"{self.label}: '{model}' boş yanıt döndürdü "
                f"(bitiş nedeni: {finish_reason or 'bilinmiyor'})."
            )

        usage = data.get("usage") or {}
        return AIResponse(
            text=text,
            provider=self.key,
            model=data.get("model", model),
            input_tokens=int(usage.get("prompt_tokens", 0)),
            output_tokens=int(usage.get("completion_tokens", 0)),
            latency_ms=latency,
            finish_reason=finish_reason,
            raw={
                "id": data.get("id", ""),
                "reasoning_tokens": (usage.get("completion_tokens_details") or {}).get(
                    "reasoning_tokens", 0
                ),
            },
        )

    # ---------------------------------------------------------- stream
    def stream(
        self,
        messages: list[AIMessage],
        *,
        model: str = "",
        temperature: float = 0.3,
        max_tokens: int = 1500,
        timeout: int = 120,
    ) -> Iterator[str]:
        model = model or self.model_for("general")
        if not self.is_configured:
            raise ProviderNotConfigured(f"{self.label} yapılandırılmamış.")

        payload = {
            "model": model,
            "messages": [m.to_openai() for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        url = f"{self.base_url}/chat/completions"
        try:
            with httpx.Client(timeout=timeout) as client:
                with client.stream("POST", url, json=payload, headers=self._headers()) as response:
                    if response.status_code >= 400:
                        response.read()
                        self._raise_for_status(response, self.label)
                    for line in response.iter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        chunk = line[5:].strip()
                        if chunk == "[DONE]":
                            break
                        try:
                            delta = json.loads(chunk)["choices"][0].get("delta", {})
                        except (ValueError, KeyError, IndexError):
                            continue
                        piece = delta.get("content")
                        if piece:
                            yield piece
        except httpx.TimeoutException as exc:
            raise ProviderTimeout(f"{self.label} akış zaman aşımına uğradı.") from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(f"{self.label} akışı kesildi.") from exc

    # ---------------------------------------------------------- models
    def list_models(self, *, timeout: int = 15) -> list[str]:
        if not self.is_configured:
            raise ProviderNotConfigured(f"{self.label} yapılandırılmamış.")
        url = f"{self.base_url}/models"
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.get(url, headers=self._headers())
        except httpx.TimeoutException as exc:
            raise ProviderTimeout(f"{self.label} model listesi zaman aşımı.") from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(f"{self.label} model listesi alınamadı.") from exc

        self._raise_for_status(response, self.label)
        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderError(f"{self.label}: model listesi okunamadı.") from exc
        return [m.get("id", "") for m in data.get("data", []) if m.get("id")]

    # ---------------------------------------------------------- health
    def health_check(self, *, timeout: int = 15) -> tuple[bool, str, int]:
        started = time.perf_counter()
        try:
            models = self.list_models(timeout=timeout)
        except ProviderError as exc:
            return False, str(exc), int((time.perf_counter() - started) * 1000)

        latency = int((time.perf_counter() - started) * 1000)
        if not models:
            return False, f"{self.label}: hiç model bulunamadı.", latency

        configured = self.model_for("general")
        if configured and configured not in models:
            return (
                True,
                (
                    f"{self.label} erişilebilir ({len(models)} model). "
                    f"UYARI: yapılandırılan '{configured}' modeli listede yok. "
                    f"Mevcut ilk model: {models[0]}"
                ),
                latency,
            )
        return True, f"{self.label} erişilebilir ({len(models)} model).", latency
