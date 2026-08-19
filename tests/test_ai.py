"""Yapay zekâ katmanı testleri.

Bu testler ağa çıkmaz. Sağlayıcı davranışı sahte (fake) nesnelerle
taklit edilir; asıl doğrulanan yönlendirme, yedekleme, bütçe kontrolü,
devre kesici ve maskeleme mantığıdır.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.test import override_settings

from apps.ai import gateway
from apps.ai.models import AIUsageLog
from apps.ai.providers import AIResponse, BaseProvider
from apps.ai.providers.base import (
    ProviderNotConfigured,
    ProviderTimeout,
    ProviderUnavailable,
)

pytestmark = pytest.mark.django_db


class FakeProvider(BaseProvider):
    """Testlerde kullanılan sahte sağlayıcı."""

    def __init__(self, key, *, is_local=True, fail_with=None, text="merhaba"):
        super().__init__(
            {
                "label": f"Fake {key}",
                "is_local": is_local,
                "enabled": True,
                "base_url": "http://fake",
                "api_key_env": "FAKE_KEY",
                "models": {"general": "fake-model", "reasoning": "fake-model"},
                "price_per_1m_input": 1.0,
                "price_per_1m_output": 2.0,
            }
        )
        self.key = key
        self.fail_with = fail_with
        self.text = text
        self.calls = 0

    @property
    def is_configured(self):
        return True

    def chat(self, messages, **kwargs):
        self.calls += 1
        if self.fail_with:
            raise self.fail_with
        return AIResponse(
            text=self.text,
            provider=self.key,
            model="fake-model",
            input_tokens=100,
            output_tokens=50,
            latency_ms=42,
        )


@pytest.fixture(autouse=True)
def clear_ai_cache():
    cache.clear()
    yield
    cache.clear()


# ------------------------------------------------------------------ maskeleme
def test_mask_pii_hides_email_and_phone():
    text = "Müşteri ahmet.yilmaz@ornek.com, telefon 0532 123 45 67"
    masked = gateway.mask_pii(text)
    assert "ahmet.yilmaz@ornek.com" not in masked
    assert "[E-POSTA]" in masked
    assert "[TELEFON]" in masked


def test_mask_pii_hides_identity_and_card_numbers():
    masked = gateway.mask_pii("TC 12345678901 kart 4111 1111 1111 1111")
    assert "12345678901" not in masked
    assert "[TC-KIMLIK]" in masked
    assert "[KART-NO]" in masked


def test_mask_secrets_hides_api_keys():
    from apps.core.logging_filters import mask_secrets

    # Aşağıdaki değer SAHTEDİR; maskelemenin çalıştığını doğrulamak için
    # gerçekçi biçimde yazılmıştır.  secret-scan: allow
    fake_key = "nvapi-" + "abcdefghijklmnopqrstuvwxyz123456"
    masked = mask_secrets(f"NVIDIA_API_KEY={fake_key}")
    assert fake_key not in masked
    assert "MASKELENDI" in masked


def test_mask_secrets_hides_bearer_tokens():
    from apps.core.logging_filters import mask_secrets

    # SAHTE anahtar.  secret-scan: allow
    fake_key = "sk-proj-" + "abcdef1234567890abcdef"
    masked = mask_secrets(f"Authorization: Bearer {fake_key}")
    assert fake_key not in masked


# ------------------------------------------------------------------ yönlendirme
def test_ask_uses_local_provider_first():
    local = FakeProvider("local", is_local=True, text="yerel yanıt")
    cloud = FakeProvider("cloud", is_local=False, text="bulut yanıt")
    with patch("apps.ai.gateway.available_providers", return_value=[local, cloud]):
        response = gateway.ask("Merhaba", feature="test")
    assert response.text == "yerel yanıt"
    assert local.calls == 1
    assert cloud.calls == 0


def test_falls_back_to_next_provider_on_failure():
    broken = FakeProvider("broken", fail_with=ProviderUnavailable("bağlanamadı"))
    backup = FakeProvider("backup", is_local=False, text="yedek yanıt")
    with patch("apps.ai.gateway.available_providers", return_value=[broken, backup]):
        response = gateway.ask("Merhaba", feature="test")
    assert response.text == "yedek yanıt"
    assert backup.calls == 1


def test_raises_when_no_provider_available():
    with patch("apps.ai.gateway.available_providers", return_value=[]):
        with pytest.raises(gateway.AIUnavailable) as exc:
            gateway.ask("Merhaba", feature="test")
    assert "LM Studio" in str(exc.value)


def test_ask_safe_returns_message_instead_of_raising():
    with patch("apps.ai.gateway.available_providers", return_value=[]):
        ok, message = gateway.ask_safe("Merhaba", feature="test")
    assert ok is False
    assert "LM Studio" in message


def test_timeout_is_retried_then_fails():
    slow = FakeProvider("slow", fail_with=ProviderTimeout("zaman aşımı"))
    with override_settings(AI={**gateway.settings.AI, "MAX_RETRIES": 1}):
        with patch("apps.ai.gateway.available_providers", return_value=[slow]):
            with pytest.raises(gateway.AIUnavailable):
                gateway.ask("Merhaba", feature="test")
    assert slow.calls == 2  # ilk deneme + 1 yeniden deneme


@override_settings(AI_ROUTING_POLICY="local_first")
def test_sensitive_task_stays_local():
    local = FakeProvider("local", is_local=True)
    cloud = FakeProvider("cloud", is_local=False)
    with patch("apps.ai.gateway.available_providers", return_value=[local, cloud]):
        chain = gateway.build_chain("general", sensitive=True)
    assert all(decision.provider.is_local for decision in chain)


# ------------------------------------------------------------------ devre kesici
def test_circuit_breaker_opens_after_threshold():
    key = "flaky"
    threshold = gateway.settings.AI["CIRCUIT_BREAKER_THRESHOLD"]
    for _ in range(threshold):
        gateway.record_failure(key)
    assert gateway.is_circuit_open(key)


def test_circuit_breaker_resets_on_success():
    key = "flaky2"
    for _ in range(gateway.settings.AI["CIRCUIT_BREAKER_THRESHOLD"]):
        gateway.record_failure(key)
    gateway.record_success(key)
    assert not gateway.is_circuit_open(key)


def test_open_circuit_excluded_from_chain():
    local = FakeProvider("local", is_local=True)
    for _ in range(gateway.settings.AI["CIRCUIT_BREAKER_THRESHOLD"]):
        gateway.record_failure("local")
    with patch("apps.ai.gateway.available_providers", return_value=[local]):
        assert gateway.build_chain("general") == []


# ------------------------------------------------------------------ bütçe
def test_budget_blocks_cloud_when_exceeded():
    AIUsageLog.objects.create(
        provider="cloud",
        model="x",
        is_local=False,
        estimated_cost_usd=Decimal("999"),
        outcome=AIUsageLog.Outcome.SUCCESS,
    )
    allowed, reason = gateway.can_use_cloud()
    assert not allowed
    assert "bütçe" in reason.lower()


def test_budget_exceeded_forces_local_chain():
    AIUsageLog.objects.create(
        provider="cloud",
        model="x",
        is_local=False,
        estimated_cost_usd=Decimal("999"),
        outcome=AIUsageLog.Outcome.SUCCESS,
    )
    local = FakeProvider("local", is_local=True)
    cloud = FakeProvider("cloud", is_local=False)
    with patch("apps.ai.gateway.available_providers", return_value=[local, cloud]):
        chain = gateway.build_chain("general")
    assert len(chain) == 1
    assert chain[0].provider.key == "local"


def test_local_provider_costs_nothing():
    from apps.ai.providers.registry import get_provider

    provider = get_provider("lmstudio")
    assert provider.estimate_cost(1000, 1000) == Decimal("0.000000")


# ------------------------------------------------------------------ kayıt
def test_usage_is_logged_with_masked_prompt():
    local = FakeProvider("local")
    with patch("apps.ai.gateway.available_providers", return_value=[local]):
        gateway.ask("Müşteri e-postası test@ornek.com", feature="unit-test")
    log = AIUsageLog.objects.latest("created_at")
    assert log.provider == "local"
    assert log.outcome == AIUsageLog.Outcome.SUCCESS
    assert "test@ornek.com" not in log.prompt_preview


def test_failed_call_is_logged():
    broken = FakeProvider("broken", fail_with=ProviderNotConfigured("anahtar yok"))
    with patch("apps.ai.gateway.available_providers", return_value=[broken]):
        with pytest.raises(gateway.AIUnavailable):
            gateway.ask("Merhaba", feature="unit-test")
    assert AIUsageLog.objects.filter(outcome=AIUsageLog.Outcome.FAILED).exists()


# ------------------------------------------------------------------ sağlayıcı testi
def test_test_provider_never_leaks_api_key():
    result = gateway.test_provider("nvidia")
    assert "api_key" not in result
    assert "nvapi-" not in str(result)


def test_provider_status_masks_keys():
    from apps.ai.providers import provider_status

    for row in provider_status():
        assert "•" in row["api_key_masked"] or "tanımlı değil" in row["api_key_masked"]


def test_unknown_provider_raises():
    from apps.ai.providers.registry import get_provider

    with pytest.raises(ProviderNotConfigured):
        get_provider("olmayan-saglayici")


# ------------------------------------------------------------------ analizler AI'sız
def test_analytics_work_without_ai(db):
    """AI erişilemese bile sayısal analizler çalışmalı."""
    from apps.ai.analytics import stock_forecast, waste_analysis

    with patch("apps.ai.gateway.available_providers", return_value=[]):
        waste = waste_analysis(days=30, narrate=True)
        stock = stock_forecast(narrate=False)

    assert waste["ok"] is True
    assert waste["ai_available"] is False
    assert stock["ok"] is True
