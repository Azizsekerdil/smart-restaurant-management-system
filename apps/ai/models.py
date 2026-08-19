"""Yapay zekâ kullanım kayıtları, sohbet geçmişi ve üretilen içgörüler."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class AITask(models.TextChoices):
    """AI görev türleri. Yönlendirici, göreve göre model seçer."""

    GENERAL = "general", _("Genel asistan")
    REASONING = "reasoning", _("Muhakeme ve raporlama")
    CODE = "code", _("Kod yardımcısı")
    MATH = "math", _("Maliyet / sayısal analiz")
    VISION = "vision", _("Görsel analiz")
    DOMAIN = "domain", _("Alan bilgisi (alerjen vb.)")
    EMBEDDING = "embedding", _("Vektör gömme")


class AIUsageLog(TimeStampedModel):
    """Her AI çağrısının kaydı: model, token, maliyet, gecikme, sonuç.

    İstem ve yanıt metinleri **maskelenmiş** olarak saklanır; müşteri
    kişisel verileri veya API anahtarları buraya yazılmaz.
    """

    class Outcome(models.TextChoices):
        SUCCESS = "success", _("Başarılı")
        FAILED = "failed", _("Başarısız")
        TIMEOUT = "timeout", _("Zaman aşımı")
        BLOCKED_BUDGET = "blocked_budget", _("Bütçe limiti")
        BLOCKED_POLICY = "blocked_policy", _("Politika engeli")
        FALLBACK = "fallback", _("Yedek sağlayıcıya düşüldü")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("kullanıcı"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ai_usages",
    )
    task = models.CharField(
        _("görev"), max_length=16, choices=AITask.choices, default=AITask.GENERAL, db_index=True
    )
    feature = models.CharField(
        _("özellik"),
        max_length=60,
        blank=True,
        db_index=True,
        help_text=_("Hangi ekran/işlev çağırdı (ör. 'menu_description')."),
    )
    provider = models.CharField(_("sağlayıcı"), max_length=32, db_index=True)
    model = models.CharField(_("model"), max_length=120)
    is_local = models.BooleanField(_("yerel model"), default=True)

    input_tokens = models.PositiveIntegerField(_("girdi token"), default=0)
    output_tokens = models.PositiveIntegerField(_("çıktı token"), default=0)
    estimated_cost_usd = models.DecimalField(
        _("tahminî maliyet (USD)"), max_digits=12, decimal_places=6, default=Decimal("0.000000")
    )
    latency_ms = models.PositiveIntegerField(_("gecikme (ms)"), default=0)

    outcome = models.CharField(
        _("sonuç"), max_length=16, choices=Outcome.choices, default=Outcome.SUCCESS, db_index=True
    )
    error_message = models.CharField(_("hata"), max_length=500, blank=True)

    prompt_preview = models.TextField(
        _("istem önizleme"), blank=True, help_text=_("Maskelenmiş, kısaltılmış istem.")
    )
    response_preview = models.TextField(_("yanıt önizleme"), blank=True)

    class Meta:
        verbose_name = _("AI kullanım kaydı")
        verbose_name_plural = _("AI kullanım kayıtları")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["-created_at", "provider"]),
            models.Index(fields=["feature", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.provider}/{self.model} · {self.get_outcome_display()}"

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    # ------------------------------------------------------ bütçe
    @classmethod
    def spent_today(cls) -> Decimal:
        start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        total = cls.objects.filter(created_at__gte=start).aggregate(t=Sum("estimated_cost_usd"))[
            "t"
        ]
        return Decimal(total or 0)

    @classmethod
    def spent_this_month(cls) -> Decimal:
        start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        total = cls.objects.filter(created_at__gte=start).aggregate(t=Sum("estimated_cost_usd"))[
            "t"
        ]
        return Decimal(total or 0)

    @classmethod
    def statistics(cls, days: int = 30) -> dict:
        since = timezone.now() - timedelta(days=days)
        qs = cls.objects.filter(created_at__gte=since)
        return {
            "period_days": days,
            "total_calls": qs.count(),
            "successful": qs.filter(outcome=cls.Outcome.SUCCESS).count(),
            "failed": qs.exclude(outcome=cls.Outcome.SUCCESS).count(),
            "local_calls": qs.filter(is_local=True).count(),
            "cloud_calls": qs.filter(is_local=False).count(),
            "total_tokens": (qs.aggregate(t=Sum("input_tokens"))["t"] or 0)
            + (qs.aggregate(t=Sum("output_tokens"))["t"] or 0),
            "total_cost_usd": Decimal(qs.aggregate(t=Sum("estimated_cost_usd"))["t"] or 0),
            "spent_today": cls.spent_today(),
            "spent_month": cls.spent_this_month(),
        }


class AIConversation(TimeStampedModel):
    """Asistan sohbet oturumu."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("kullanıcı"),
        on_delete=models.CASCADE,
        related_name="ai_conversations",
    )
    title = models.CharField(_("başlık"), max_length=200, default="Yeni sohbet")
    task = models.CharField(
        _("görev"), max_length=16, choices=AITask.choices, default=AITask.GENERAL
    )
    provider_preference = models.CharField(_("tercih edilen sağlayıcı"), max_length=32, blank=True)
    model_preference = models.CharField(_("tercih edilen model"), max_length=120, blank=True)
    is_archived = models.BooleanField(_("arşivlendi"), default=False)

    class Meta:
        verbose_name = _("AI sohbeti")
        verbose_name_plural = _("AI sohbetleri")
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return self.title


class AIConversationMessage(models.Model):
    conversation = models.ForeignKey(
        AIConversation, verbose_name=_("sohbet"), on_delete=models.CASCADE, related_name="messages"
    )
    role = models.CharField(
        _("rol"),
        max_length=12,
        choices=[("user", _("Kullanıcı")), ("assistant", _("Asistan")), ("system", _("Sistem"))],
    )
    content = models.TextField(_("içerik"))
    provider = models.CharField(_("sağlayıcı"), max_length=32, blank=True)
    model = models.CharField(_("model"), max_length=120, blank=True)
    created_at = models.DateTimeField(_("zaman"), auto_now_add=True)

    class Meta:
        verbose_name = _("AI mesajı")
        verbose_name_plural = _("AI mesajları")
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.role}: {self.content[:50]}"


class AIInsight(TimeStampedModel):
    """Yapay zekânın ürettiği içgörü / öneri kaydı.

    Tahminler kesin gerçek olarak sunulmaz: `confidence`, `data_points`
    ve `limitations` alanları güven düzeyini açıkça belirtir.
    """

    class Kind(models.TextChoices):
        DAILY_SUMMARY = "daily_summary", _("Günlük yönetici özeti")
        DEMAND_FORECAST = "demand_forecast", _("Talep tahmini")
        MENU_ENGINEERING = "menu_engineering", _("Menü mühendisliği")
        WASTE_ANALYSIS = "waste_analysis", _("İsraf analizi")
        STAFF_SUGGESTION = "staff_suggestion", _("Personel önerisi")
        PRICE_SIMULATION = "price_simulation", _("Fiyat simülasyonu")
        ANOMALY = "anomaly", _("Anormallik tespiti")
        CHURN = "churn", _("Müşteri kaybı riski")
        SENTIMENT = "sentiment", _("Yorum duygu analizi")
        CAMPAIGN = "campaign", _("Kampanya önerisi")
        STOCK_FORECAST = "stock_forecast", _("Stok tükenme tahmini")

    class Confidence(models.TextChoices):
        LOW = "low", _("Düşük")
        MEDIUM = "medium", _("Orta")
        HIGH = "high", _("Yüksek")

    kind = models.CharField(_("tür"), max_length=20, choices=Kind.choices, db_index=True)
    title = models.CharField(_("başlık"), max_length=200)
    summary = models.TextField(_("özet"))
    details = models.JSONField(_("detaylar"), default=dict, blank=True)

    confidence = models.CharField(
        _("güven düzeyi"), max_length=8, choices=Confidence.choices, default=Confidence.MEDIUM
    )
    data_points = models.PositiveIntegerField(
        _("veri noktası sayısı"),
        default=0,
        help_text=_("Analizin dayandığı kayıt sayısı. Az veri = düşük güven."),
    )
    limitations = models.TextField(
        _("sınırlamalar"),
        blank=True,
        help_text=_("Bu tahminin neden kesin olmadığını açıklar."),
    )

    period_start = models.DateField(_("dönem başı"), null=True, blank=True)
    period_end = models.DateField(_("dönem sonu"), null=True, blank=True)

    generated_by_ai = models.BooleanField(_("AI tarafından üretildi"), default=True)
    provider = models.CharField(_("sağlayıcı"), max_length=32, blank=True)
    model = models.CharField(_("model"), max_length=120, blank=True)

    is_acknowledged = models.BooleanField(_("okundu / işlendi"), default=False)
    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("işleyen"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="acknowledged_insights",
    )

    class Meta:
        verbose_name = _("AI içgörüsü")
        verbose_name_plural = _("AI içgörüleri")
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["kind", "-created_at"])]

    def __str__(self) -> str:
        return f"[{self.get_kind_display()}] {self.title}"

    @property
    def confidence_color(self) -> str:
        return {"low": "danger", "medium": "warning", "high": "success"}.get(
            self.confidence, "secondary"
        )

    @property
    def disclaimer(self) -> str:
        """Kullanıcıya gösterilecek standart uyarı metni."""
        return (
            f"Bu analiz {self.data_points} veri noktasına dayanmaktadır ve güven düzeyi "
            f"'{self.get_confidence_display().lower()}'dir. Tahminler kesin sonuç değildir; "
            "karar almadan önce kendi değerlendirmenizi yapın."
        )

    # İçgörü türü -> üretimde kullanılan sistem istemi (prompt) adı.
    # PROMPT_REGISTRY (apps/ai/prompts.py) ile birlikte gerekçe-makbuzunu
    # besler. Eşleşmesi olmayan türler istem kullanmadan (kural tabanlı)
    # üretilir.
    _KIND_TO_PROMPT = {
        "daily_summary": "DAILY_SUMMARY",
        "demand_forecast": "DEMAND_FORECAST",
        "menu_engineering": "MENU_ENGINEERING",
        "waste_analysis": "WASTE_ANALYSIS",
        "staff_suggestion": "STAFF_SUGGESTION",
        "anomaly": "ANOMALY",
        "sentiment": "SENTIMENT",
        "campaign": "CAMPAIGN_SUGGESTION",
    }

    @property
    def receipt(self) -> dict:
        """Gerekçe-makbuzu: bu öneri neyle ve neye dayanarak üretildi?

        Kullanıcının "kim, ne zaman, hangi model, hangi veriyle?" sorusuna
        cevap verir. İstem sürümü, kayıt defterinin GÜNCEL sürümüdür; istem
        sonradan değiştiyse sürüm numarası artmış olacağından fark görünür.
        """
        from apps.ai.prompts import PROMPT_REGISTRY

        prompt_name = self._KIND_TO_PROMPT.get(self.kind)
        prompt_meta = PROMPT_REGISTRY.get(prompt_name, {}) if prompt_name else {}
        return {
            "uretim_zamani": self.created_at,
            "uretici": "AI" if self.generated_by_ai else "kural tabanlı",
            "saglayici": self.provider or "-",
            "model": self.model or "-",
            "istem": prompt_name or "-",
            "istem_surumu": prompt_meta.get("version", "-"),
            "veri_noktasi": self.data_points,
            "guven": self.get_confidence_display(),
            "donem": (
                f"{self.period_start} – {self.period_end}"
                if self.period_start and self.period_end
                else "-"
            ),
        }
