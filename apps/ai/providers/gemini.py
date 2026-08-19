"""Google Gemini adapteri (generateContent API)."""

from __future__ import annotations

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


class GeminiProvider(BaseProvider):
    """Google Generative Language API.

    Roller `user` / `model` olarak adlandırılır; sistem istemi ayrı bir
    `system_instruction` alanında gönderilir.
    """

    @staticmethod
    def _convert(messages: list[AIMessage]) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        system_parts = [m.content for m in messages if m.role == "system"]
        system = {"parts": [{"text": "\n\n".join(system_parts)}]} if system_parts else None
        contents = []
        for message in messages:
            if message.role == "system":
                continue
            parts: list[dict[str, Any]] = [{"text": message.content}]
            for image in message.images:
                if image.startswith("data:") and ";base64," in image:
                    media_type, b64 = image.split(";base64,", 1)
                    parts.append(
                        {
                            "inline_data": {
                                "mime_type": media_type.replace("data:", ""),
                                "data": b64,
                            }
                        }
                    )
            contents.append(
                {"role": "model" if message.role == "assistant" else "user", "parts": parts}
            )
        return system, contents

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
                f"{self.label} yapılandırılmamış. .env içinde GEMINI_API_KEY tanımlayın."
            )
        model = model or self.model_for("general")
        system, contents = self._convert(messages)

        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        if system:
            payload["system_instruction"] = system
        if json_mode:
            payload["generationConfig"]["response_mime_type"] = "application/json"

        url = f"{self.base_url}/models/{model}:generateContent"
        started = time.perf_counter()
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.post(
                    url,
                    json=payload,
                    headers={"Content-Type": "application/json", "x-goog-api-key": self.api_key},
                )
        except httpx.TimeoutException as exc:
            raise ProviderTimeout(f"{self.label} zaman aşımı.") from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(f"{self.label} bağlantı hatası.") from exc

        self._raise_for_status(response)
        latency = int((time.perf_counter() - started) * 1000)
        data = response.json()
        try:
            candidate = data["candidates"][0]
            text = "".join(p.get("text", "") for p in candidate["content"]["parts"])
        except (KeyError, IndexError) as exc:
            raise ProviderError(
                f"{self.label}: yanıt boş veya güvenlik filtresine takıldı."
            ) from exc

        usage = data.get("usageMetadata", {})
        return AIResponse(
            text=text.strip(),
            provider=self.key,
            model=model,
            input_tokens=int(usage.get("promptTokenCount", 0)),
            output_tokens=int(usage.get("candidatesTokenCount", 0)),
            latency_ms=latency,
            finish_reason=candidate.get("finishReason", ""),
        )

    def stream(
        self, messages, *, model="", temperature=0.3, max_tokens=1500, timeout=120
    ) -> Iterator[str]:
        # Basitlik için akış desteği tek parça yanıtla taklit edilir.
        yield self.chat(
            messages, model=model, temperature=temperature, max_tokens=max_tokens, timeout=timeout
        ).text

    def list_models(self, *, timeout: int = 15) -> list[str]:
        if not self.is_configured:
            raise ProviderNotConfigured(f"{self.label} yapılandırılmamış.")
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.get(
                    f"{self.base_url}/models", headers={"x-goog-api-key": self.api_key}
                )
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(f"{self.label} model listesi alınamadı.") from exc
        self._raise_for_status(response)
        return [
            m.get("name", "").replace("models/", "")
            for m in response.json().get("models", [])
            if "generateContent" in m.get("supportedGenerationMethods", [])
        ]

    def health_check(self, *, timeout: int = 15) -> tuple[bool, str, int]:
        started = time.perf_counter()
        try:
            models = self.list_models(timeout=timeout)
        except ProviderError as exc:
            return False, str(exc), int((time.perf_counter() - started) * 1000)
        latency = int((time.perf_counter() - started) * 1000)
        return True, f"{self.label} erişilebilir ({len(models)} model).", latency
