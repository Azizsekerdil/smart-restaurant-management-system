"""Anthropic Claude adapteri (Messages API)."""

from __future__ import annotations

import json
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

ANTHROPIC_VERSION = "2023-06-01"


class AnthropicProvider(BaseProvider):
    """Anthropic Messages API sözleşmesi.

    OpenAI'den iki farkı vardır: sistem istemi ayrı bir alandır ve
    kimlik doğrulama `x-api-key` başlığıyla yapılır.
    """

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": ANTHROPIC_VERSION,
        }

    @staticmethod
    def _split(messages: list[AIMessage]) -> tuple[str, list[dict[str, Any]]]:
        system_parts = [m.content for m in messages if m.role == "system"]
        turns = []
        for message in messages:
            if message.role == "system":
                continue
            if message.images:
                content: list[dict[str, Any]] = [{"type": "text", "text": message.content}]
                for image in message.images:
                    if image.startswith("data:") and ";base64," in image:
                        media_type, b64 = image.split(";base64,", 1)
                        content.append(
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type.replace("data:", ""),
                                    "data": b64,
                                },
                            }
                        )
                turns.append({"role": message.role, "content": content})
            else:
                turns.append({"role": message.role, "content": message.content})
        return "\n\n".join(system_parts), turns

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code < 400:
            return
        detail = ""
        try:
            detail = response.json().get("error", {}).get("message", "")
        except Exception:
            detail = response.text[:300]
        if response.status_code in (401, 403):
            raise ProviderNotConfigured(f"{self.label}: API anahtarı geçersiz.")
        if response.status_code == 429:
            raise ProviderRateLimited(f"{self.label}: kota aşıldı. {detail}")
        raise ProviderError(f"{self.label}: HTTP {response.status_code}. {detail}")

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
        if not self.is_configured:
            raise ProviderNotConfigured(
                f"{self.label} yapılandırılmamış. .env içinde ANTHROPIC_API_KEY tanımlayın."
            )
        model = model or self.model_for("general")
        system, turns = self._split(messages)
        if json_mode:
            system = (system + "\n\nYanıtı yalnızca geçerli JSON olarak ver.").strip()

        payload = {
            "model": model,
            "system": system,
            "messages": turns,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        started = time.perf_counter()
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.post(
                    f"{self.base_url}/messages", json=payload, headers=self._headers()
                )
        except httpx.TimeoutException as exc:
            raise ProviderTimeout(f"{self.label} zaman aşımı.") from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(f"{self.label} bağlantı hatası.") from exc

        self._raise_for_status(response)
        latency = int((time.perf_counter() - started) * 1000)
        data = response.json()
        text = "".join(
            block.get("text", "")
            for block in data.get("content", [])
            if block.get("type") == "text"
        )
        usage = data.get("usage", {})
        return AIResponse(
            text=text.strip(),
            provider=self.key,
            model=data.get("model", model),
            input_tokens=int(usage.get("input_tokens", 0)),
            output_tokens=int(usage.get("output_tokens", 0)),
            latency_ms=latency,
            finish_reason=data.get("stop_reason", ""),
        )

    def stream(
        self,
        messages: list[AIMessage],
        *,
        model: str = "",
        temperature: float = 0.3,
        max_tokens: int = 1500,
        timeout: int = 120,
    ) -> Iterator[str]:
        if not self.is_configured:
            raise ProviderNotConfigured(f"{self.label} yapılandırılmamış.")
        model = model or self.model_for("general")
        system, turns = self._split(messages)
        payload = {
            "model": model,
            "system": system,
            "messages": turns,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }
        try:
            with httpx.Client(timeout=timeout) as client:
                with client.stream(
                    "POST", f"{self.base_url}/messages", json=payload, headers=self._headers()
                ) as response:
                    if response.status_code >= 400:
                        response.read()
                        self._raise_for_status(response)
                    for line in response.iter_lines():
                        if not line.startswith("data:"):
                            continue
                        try:
                            event = json.loads(line[5:].strip())
                        except ValueError:
                            continue
                        if event.get("type") == "content_block_delta":
                            piece = event.get("delta", {}).get("text")
                            if piece:
                                yield piece
        except httpx.TimeoutException as exc:
            raise ProviderTimeout(f"{self.label} akış zaman aşımı.") from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(f"{self.label} akışı kesildi.") from exc

    def list_models(self, *, timeout: int = 15) -> list[str]:
        # Anthropic model listesi uç noktası her hesapta açık olmayabilir;
        # yapılandırılmış model döndürülür.
        return [m for m in self.models.values() if m]

    def health_check(self, *, timeout: int = 15) -> tuple[bool, str, int]:
        started = time.perf_counter()
        try:
            response = self.chat(
                [AIMessage(role="user", content="Yalnızca 'OK' yaz.")],
                max_tokens=8,
                temperature=0,
                timeout=timeout,
            )
        except ProviderError as exc:
            return False, str(exc), int((time.perf_counter() - started) * 1000)
        return True, f"{self.label} erişilebilir (model: {response.model}).", response.latency_ms
