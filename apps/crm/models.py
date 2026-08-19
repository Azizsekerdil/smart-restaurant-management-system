"""Müşteri, sadakat, kampanya ve yorum modelleri.

KVKK notu
---------
Kişisel veriler (ad, telefon, e-posta, adres) açık rıza ile işlenir.
`ConsentRecord` her izin türü için zaman damgalı kayıt tutar.
`anonymize()` metodu, silme talebinde kişisel verileri geri döndürülemez
biçimde temizlerken sipariş geçmişinin istatistiksel bütünlüğünü korur.
"""

from __future__ import annotations

import hashlib
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import SoftDeleteModel, TimeStampedModel
from apps.core.utils import generate_code, money, safe_divide


class CustomerSegment(models.TextChoices):
    NEW = "new", _("Yeni müşteri")
    REGULAR = "regular", _("Düzenli")
    VIP = "vip", _("VIP")
    AT_RISK = "at_risk", _("Kayıp riski")
    LOST = "lost", _("Kayıp")
    CORPORATE = "corporate", _("Kurumsal")


class Customer(SoftDeleteModel):
    """Müşteri profili."""

    class Tier(models.TextChoices):
        BRONZE = "bronze", _("Bronz")
        SILVER = "silver", _("Gümüş")
        GOLD = "gold", _("Altın")
        PLATINUM = "platinum", _("Platin")

    code = models.CharField(_("müşteri kodu"), max_length=12, unique=True, db_index=True)
    first_name = models.CharField(_("ad"), max_length=80)
    last_name = models.CharField(_("soyad"), max_length=80, blank=True)
    phone = models.CharField(_("telefon"), max_length=20, blank=True, db_index=True)
    email = models.EmailField(_("e-posta"), blank=True)
    birth_date = models.DateField(_("doğum tarihi"), null=True, blank=True)
    address = models.TextField(_("adres"), blank=True)
    company_name = models.CharField(_("firma"), max_length=200, blank=True)
    tax_number = models.CharField(_("vergi no"), max_length=20, blank=True)

    segment = models.CharField(
        _("segment"),
        max_length=12,
        choices=CustomerSegment.choices,
        default=CustomerSegment.NEW,
        db_index=True,
    )
    tier = models.CharField(_("seviye"), max_length=10, choices=Tier.choices, default=Tier.BRONZE)

    preferences = models.TextField(_("tercihler"), blank=True)
    allergy_notes = models.CharField(
        _("alerji notları"),
        max_length=400,
        blank=True,
        help_text=_("Servis sırasında uyarı olarak gösterilir."),
    )
    internal_notes = models.TextField(_("dahili notlar"), blank=True)

    loyalty_points = models.IntegerField(_("sadakat puanı"), default=0)
    lifetime_value = models.DecimalField(
        _("toplam harcama"), max_digits=14, decimal_places=2, default=Decimal("0.00")
    )
    visit_count = models.PositiveIntegerField(_("ziyaret sayısı"), default=0)
    last_visit_at = models.DateTimeField(_("son ziyaret"), null=True, blank=True, db_index=True)
    no_show_count = models.PositiveIntegerField(_("gelmediği rezervasyon"), default=0)

    is_anonymized = models.BooleanField(_("anonimleştirildi"), default=False)
    anonymized_at = models.DateTimeField(_("anonimleştirme zamanı"), null=True, blank=True)
    is_active = models.BooleanField(_("aktif"), default=True)

    class Meta:
        verbose_name = _("Müşteri")
        verbose_name_plural = _("Müşteriler")
        ordering = ["-last_visit_at", "first_name"]
        indexes = [
            models.Index(fields=["segment", "-lifetime_value"]),
            models.Index(fields=["phone"]),
        ]

    def __str__(self) -> str:
        return f"{self.full_name} ({self.code})"

    def save(self, *args, **kwargs):
        if not self.code:
            code = generate_code("M", 7)
            while Customer.all_objects.filter(code=code).exists():
                code = generate_code("M", 7)
            self.code = code
        super().save(*args, **kwargs)

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def masked_phone(self) -> str:
        """Yetkisiz kullanıcılara gösterilecek maskeli telefon."""
        if not self.phone or len(self.phone) < 6:
            return "***"
        return f"{self.phone[:4]}***{self.phone[-2:]}"

    @property
    def masked_email(self) -> str:
        if not self.email or "@" not in self.email:
            return "***"
        local, domain = self.email.split("@", 1)
        return f"{local[:1]}***@{domain}"

    @property
    def average_spend(self) -> Decimal:
        return money(safe_divide(self.lifetime_value, max(self.visit_count, 1)))

    @property
    def days_since_last_visit(self) -> int | None:
        if not self.last_visit_at:
            return None
        return (timezone.now() - self.last_visit_at).days

    @property
    def churn_risk(self) -> str:
        """Basit kural tabanlı kayıp riski göstergesi."""
        days = self.days_since_last_visit
        if days is None:
            return "unknown"
        if self.visit_count < 2:
            return "low_data"
        if days > 120:
            return "high"
        if days > 60:
            return "medium"
        return "low"

    def has_consent(self, kind: str) -> bool:
        record = self.consents.filter(kind=kind).order_by("-created_at").first()
        return bool(record and record.granted)

    def anonymize(self, *, user=None, reason: str = "") -> None:
        """KVKK silme talebi: kişisel verileri geri döndürülemez şekilde temizler.

        Sipariş geçmişi silinmez; müşteri ilişkisi anonim bir kayda bağlanır.
        Böylece mali kayıtların bütünlüğü korunur.
        """
        from apps.core.models import AuditLog
        from apps.core.services import record_audit

        digest = hashlib.sha256(
            f"{self.pk}:{self.phone}:{self.email}:{settings.SECRET_KEY}".encode()
        ).hexdigest()[:12]

        self.first_name = "Anonim"
        self.last_name = f"Müşteri-{digest}"
        self.phone = ""
        self.email = ""
        self.address = ""
        self.birth_date = None
        self.company_name = ""
        self.tax_number = ""
        self.preferences = ""
        self.allergy_notes = ""
        self.internal_notes = ""
        self.is_anonymized = True
        self.anonymized_at = timezone.now()
        self.is_active = False
        self.save()
        self.consents.all().delete()

        record_audit(
            AuditLog.Action.DATA_ERASURE,
            user=user,
            obj=self,
            description=f"Müşteri {self.code} KVKK kapsamında anonimleştirildi. Gerekçe: {reason}",
            severity=AuditLog.Severity.CRITICAL,
        )


class ConsentRecord(models.Model):
    """KVKK açık rıza kaydı."""

    class Kind(models.TextChoices):
        MARKETING_SMS = "marketing_sms", _("SMS ile pazarlama")
        MARKETING_EMAIL = "marketing_email", _("E-posta ile pazarlama")
        DATA_PROCESSING = "data_processing", _("Kişisel veri işleme")
        PROFILING = "profiling", _("Profilleme ve öneri")

    customer = models.ForeignKey(
        Customer, verbose_name=_("müşteri"), on_delete=models.CASCADE, related_name="consents"
    )
    kind = models.CharField(_("izin türü"), max_length=20, choices=Kind.choices)
    granted = models.BooleanField(_("verildi"), default=False)
    source = models.CharField(_("alınma kanalı"), max_length=60, blank=True)
    created_at = models.DateTimeField(_("zaman"), auto_now_add=True, db_index=True)
    ip_address = models.GenericIPAddressField(_("IP"), null=True, blank=True)

    class Meta:
        verbose_name = _("Rıza kaydı")
        verbose_name_plural = _("Rıza kayıtları")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        state = "verildi" if self.granted else "reddedildi"
        return f"{self.customer.code} · {self.get_kind_display()}: {state}"


class LoyaltyTransaction(TimeStampedModel):
    """Sadakat puanı hareketi."""

    class Kind(models.TextChoices):
        EARN = "earn", _("Kazanım")
        REDEEM = "redeem", _("Harcama")
        EXPIRE = "expire", _("Süre dolumu")
        ADJUST = "adjust", _("Düzeltme")
        BONUS = "bonus", _("Bonus / kampanya")

    customer = models.ForeignKey(
        Customer,
        verbose_name=_("müşteri"),
        on_delete=models.CASCADE,
        related_name="loyalty_transactions",
    )
    order = models.ForeignKey(
        "orders.Order",
        verbose_name=_("sipariş"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="loyalty_transactions",
    )
    kind = models.CharField(_("tür"), max_length=10, choices=Kind.choices)
    points = models.IntegerField(_("puan"), help_text=_("Harcamalar negatiftir."))
    balance_after = models.IntegerField(_("işlem sonrası bakiye"), default=0)
    description = models.CharField(_("açıklama"), max_length=200, blank=True)
    expires_at = models.DateField(_("son kullanma"), null=True, blank=True)

    class Meta:
        verbose_name = _("Sadakat hareketi")
        verbose_name_plural = _("Sadakat hareketleri")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.customer.code}: {self.points:+d} puan"


class Campaign(TimeStampedModel):
    """Pazarlama kampanyası."""

    class Status(models.TextChoices):
        DRAFT = "draft", _("Taslak")
        ACTIVE = "active", _("Aktif")
        PAUSED = "paused", _("Duraklatıldı")
        FINISHED = "finished", _("Bitti")

    name = models.CharField(_("ad"), max_length=200)
    description = models.TextField(_("açıklama"), blank=True)
    status = models.CharField(
        _("durum"), max_length=10, choices=Status.choices, default=Status.DRAFT
    )
    target_segments = models.JSONField(_("hedef segmentler"), default=list, blank=True)
    coupon = models.ForeignKey(
        "orders.Coupon",
        verbose_name=_("kupon"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="campaigns",
    )
    starts_at = models.DateTimeField(_("başlangıç"), default=timezone.now)
    ends_at = models.DateTimeField(_("bitiş"), null=True, blank=True)
    budget = models.DecimalField(
        _("bütçe"), max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    is_ai_suggested = models.BooleanField(
        _("AI önerisi"),
        default=False,
        help_text=_("Yapay zekâ tarafından önerilen kampanya."),
    )
    ai_rationale = models.TextField(_("AI gerekçesi"), blank=True)

    class Meta:
        verbose_name = _("Kampanya")
        verbose_name_plural = _("Kampanyalar")
        ordering = ["-starts_at"]

    def __str__(self) -> str:
        return self.name

    @property
    def is_running(self) -> bool:
        now = timezone.now()
        return (
            self.status == self.Status.ACTIVE
            and self.starts_at <= now
            and (self.ends_at is None or self.ends_at >= now)
        )


class Review(TimeStampedModel):
    """Müşteri yorumu / geri bildirimi."""

    class Sentiment(models.TextChoices):
        POSITIVE = "positive", _("Olumlu")
        NEUTRAL = "neutral", _("Nötr")
        NEGATIVE = "negative", _("Olumsuz")
        UNKNOWN = "unknown", _("Analiz edilmedi")

    class Source(models.TextChoices):
        IN_HOUSE = "in_house", _("Restoran içi")
        QR = "qr", _("QR anket")
        GOOGLE = "google", _("Google")
        SOCIAL = "social", _("Sosyal medya")
        DELIVERY = "delivery", _("Teslimat platformu")

    customer = models.ForeignKey(
        Customer,
        verbose_name=_("müşteri"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviews",
    )
    order = models.ForeignKey(
        "orders.Order",
        verbose_name=_("sipariş"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviews",
    )
    rating = models.PositiveSmallIntegerField(_("puan"), default=5, help_text=_("1-5"))
    comment = models.TextField(_("yorum"), blank=True)
    source = models.CharField(
        _("kaynak"), max_length=10, choices=Source.choices, default=Source.IN_HOUSE
    )

    sentiment = models.CharField(
        _("duygu"),
        max_length=10,
        choices=Sentiment.choices,
        default=Sentiment.UNKNOWN,
        db_index=True,
    )
    sentiment_score = models.DecimalField(
        _("duygu skoru"),
        max_digits=4,
        decimal_places=3,
        null=True,
        blank=True,
        help_text=_("-1 (çok olumsuz) ile +1 (çok olumlu) arası."),
    )
    topics = models.JSONField(
        _("konular"),
        default=list,
        blank=True,
        help_text=_("AI tarafından çıkarılan konu etiketleri (servis, lezzet, fiyat...)."),
    )
    ai_summary = models.CharField(_("AI özeti"), max_length=300, blank=True)
    analyzed_at = models.DateTimeField(_("analiz zamanı"), null=True, blank=True)

    is_resolved = models.BooleanField(_("çözüldü"), default=False)
    resolution_note = models.TextField(_("çözüm notu"), blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("çözen"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="resolved_reviews",
    )

    class Meta:
        verbose_name = _("Müşteri yorumu")
        verbose_name_plural = _("Müşteri yorumları")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["sentiment", "-created_at"]),
            models.Index(fields=["rating"]),
        ]

    def __str__(self) -> str:
        return f"{self.rating}★ · {self.comment[:40]}"

    @property
    def needs_attention(self) -> bool:
        return self.rating <= 2 and not self.is_resolved

    @property
    def age_days(self) -> int:
        return (timezone.now() - self.created_at).days


class GiftCard(TimeStampedModel):
    """Hediye çeki / ön ödemeli kart."""

    code = models.CharField(_("kod"), max_length=20, unique=True, db_index=True)
    initial_balance = models.DecimalField(_("yüklenen tutar"), max_digits=12, decimal_places=2)
    balance = models.DecimalField(_("kalan bakiye"), max_digits=12, decimal_places=2)
    customer = models.ForeignKey(
        Customer,
        verbose_name=_("müşteri"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="gift_cards",
    )
    expires_at = models.DateField(_("son kullanma"), null=True, blank=True)
    is_active = models.BooleanField(_("aktif"), default=True)

    class Meta:
        verbose_name = _("Hediye çeki")
        verbose_name_plural = _("Hediye çekleri")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.code} ({self.balance} ₺)"

    def save(self, *args, **kwargs):
        if not self.code:
            code = generate_code("HC", 8)
            while GiftCard.objects.filter(code=code).exists():
                code = generate_code("HC", 8)
            self.code = code
        super().save(*args, **kwargs)

    @property
    def is_usable(self) -> bool:
        if not self.is_active or self.balance <= 0:
            return False
        if self.expires_at and self.expires_at < timezone.localdate():
            return False
        return True


def recent_customers(days: int = 30):
    since = timezone.now() - timedelta(days=days)
    return Customer.objects.filter(last_visit_at__gte=since)
