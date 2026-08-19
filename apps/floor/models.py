"""Salon, masa ve rezervasyon modelleri."""

from __future__ import annotations

import uuid
from datetime import timedelta

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel
from apps.core.utils import slugify_tr


class Area(TimeStampedModel):
    """Salon / bölüm (iç salon, teras, bahçe, VIP)."""

    name = models.CharField(_("ad"), max_length=100, unique=True)
    code = models.SlugField(_("kod"), max_length=40, unique=True, blank=True)
    description = models.CharField(_("açıklama"), max_length=200, blank=True)
    is_outdoor = models.BooleanField(_("açık alan"), default=False)
    is_smoking = models.BooleanField(_("sigara içilebilir"), default=False)
    service_charge_rate = models.DecimalField(
        _("servis bedeli (%)"),
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text=_("Bu bölümdeki siparişlere eklenecek servis oranı."),
    )
    sort_order = models.PositiveIntegerField(_("sıra"), default=100)
    is_active = models.BooleanField(_("aktif"), default=True)

    class Meta:
        verbose_name = _("Salon / Bölüm")
        verbose_name_plural = _("Salonlar / Bölümler")
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = slugify_tr(self.name)[:40]
        super().save(*args, **kwargs)

    @property
    def table_count(self) -> int:
        return self.tables.filter(is_active=True).count()

    @property
    def occupied_count(self) -> int:
        return self.tables.filter(is_active=True, status=Table.Status.OCCUPIED).count()


class Table(TimeStampedModel):
    """Masa. Konum bilgisi görsel masa planı için tutulur."""

    class Status(models.TextChoices):
        FREE = "free", _("Boş")
        OCCUPIED = "occupied", _("Dolu")
        RESERVED = "reserved", _("Rezerve")
        CLEANING = "cleaning", _("Temizlikte")
        DISABLED = "disabled", _("Kullanım dışı")

    class Shape(models.TextChoices):
        SQUARE = "square", _("Kare")
        ROUND = "round", _("Yuvarlak")
        RECT = "rect", _("Dikdörtgen")

    area = models.ForeignKey(
        Area, verbose_name=_("bölüm"), on_delete=models.PROTECT, related_name="tables"
    )
    name = models.CharField(_("masa adı"), max_length=40)
    capacity = models.PositiveSmallIntegerField(
        _("kapasite"), default=4, validators=[MinValueValidator(1), MaxValueValidator(50)]
    )
    status = models.CharField(
        _("durum"), max_length=10, choices=Status.choices, default=Status.FREE, db_index=True
    )
    shape = models.CharField(_("şekil"), max_length=10, choices=Shape.choices, default=Shape.SQUARE)

    # Masa planındaki konum (yüzde cinsinden, responsive yerleşim için)
    pos_x = models.DecimalField(_("X konumu (%)"), max_digits=5, decimal_places=2, default=10)
    pos_y = models.DecimalField(_("Y konumu (%)"), max_digits=5, decimal_places=2, default=10)

    assigned_waiter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("atanan garson"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_tables",
    )
    merged_into = models.ForeignKey(
        "self",
        verbose_name=_("birleştirildiği masa"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="merged_tables",
        help_text=_("Masa birleştirildiğinde ana masayı gösterir."),
    )
    qr_token = models.UUIDField(_("QR anahtarı"), default=uuid.uuid4, unique=True, editable=False)
    notes = models.CharField(_("not"), max_length=200, blank=True)
    is_active = models.BooleanField(_("aktif"), default=True, db_index=True)
    occupied_since = models.DateTimeField(_("doluluk başlangıcı"), null=True, blank=True)

    class Meta:
        verbose_name = _("Masa")
        verbose_name_plural = _("Masalar")
        ordering = ["area__sort_order", "name"]
        constraints = [
            models.UniqueConstraint(fields=["area", "name"], name="uniq_table_name_per_area")
        ]
        indexes = [models.Index(fields=["status", "is_active"])]

    def __str__(self) -> str:
        return f"{self.area.name} · {self.name}"

    @property
    def is_merged_child(self) -> bool:
        return self.merged_into_id is not None

    @property
    def effective_capacity(self) -> int:
        """Birleştirilmiş masalar dahil toplam kapasite."""
        extra = sum(t.capacity for t in self.merged_tables.all())
        return self.capacity + extra

    @property
    def active_order(self):
        """Masadaki açık sipariş (varsa)."""
        from apps.orders.models import Order

        return (
            Order.objects.filter(table=self)
            .exclude(status__in=[Order.Status.PAID, Order.Status.CANCELLED])
            .order_by("-created_at")
            .first()
        )

    @property
    def occupied_minutes(self) -> int:
        if not self.occupied_since:
            return 0
        return int((timezone.now() - self.occupied_since).total_seconds() // 60)

    @property
    def status_color(self) -> str:
        return {
            self.Status.FREE: "success",
            self.Status.OCCUPIED: "danger",
            self.Status.RESERVED: "warning",
            self.Status.CLEANING: "info",
            self.Status.DISABLED: "secondary",
        }.get(self.status, "secondary")

    def mark_occupied(self) -> None:
        self.status = self.Status.OCCUPIED
        if not self.occupied_since:
            self.occupied_since = timezone.now()
        self.save(update_fields=["status", "occupied_since", "updated_at"])

    def mark_free(self, *, cleaning: bool = True) -> None:
        self.status = self.Status.CLEANING if cleaning else self.Status.FREE
        self.occupied_since = None
        self.save(update_fields=["status", "occupied_since", "updated_at"])

    @property
    def qr_menu_path(self) -> str:
        return f"/menu/qr/{self.qr_token}/"


class Reservation(TimeStampedModel):
    """Masa rezervasyonu."""

    class Status(models.TextChoices):
        PENDING = "pending", _("Onay bekliyor")
        CONFIRMED = "confirmed", _("Onaylandı")
        SEATED = "seated", _("Misafir oturdu")
        COMPLETED = "completed", _("Tamamlandı")
        CANCELLED = "cancelled", _("İptal edildi")
        NO_SHOW = "no_show", _("Gelmedi")

    class Source(models.TextChoices):
        PHONE = "phone", _("Telefon")
        WALK_IN = "walk_in", _("Kapıdan")
        ONLINE = "online", _("Online")
        PARTNER = "partner", _("Anlaşmalı platform")

    code = models.CharField(_("rezervasyon kodu"), max_length=12, unique=True, db_index=True)
    customer = models.ForeignKey(
        "crm.Customer",
        verbose_name=_("müşteri"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reservations",
    )
    guest_name = models.CharField(_("misafir adı"), max_length=120)
    guest_phone = models.CharField(_("telefon"), max_length=20, blank=True)
    guest_email = models.EmailField(_("e-posta"), blank=True)

    party_size = models.PositiveSmallIntegerField(
        _("kişi sayısı"), default=2, validators=[MinValueValidator(1), MaxValueValidator(200)]
    )
    reserved_at = models.DateTimeField(_("rezervasyon zamanı"), db_index=True)
    duration_minutes = models.PositiveIntegerField(_("süre (dk)"), default=90)

    tables = models.ManyToManyField(
        Table, verbose_name=_("masalar"), blank=True, related_name="reservations"
    )
    area = models.ForeignKey(
        Area,
        verbose_name=_("tercih edilen bölüm"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reservations",
    )

    status = models.CharField(
        _("durum"), max_length=10, choices=Status.choices, default=Status.CONFIRMED, db_index=True
    )
    source = models.CharField(
        _("kaynak"), max_length=10, choices=Source.choices, default=Source.PHONE
    )
    special_requests = models.TextField(_("özel istekler"), blank=True)
    allergy_notes = models.CharField(_("alerji notu"), max_length=300, blank=True)
    occasion = models.CharField(
        _("özel gün"), max_length=60, blank=True, help_text=_("Doğum günü, yıldönümü vb.")
    )

    seated_at = models.DateTimeField(_("oturma zamanı"), null=True, blank=True)
    completed_at = models.DateTimeField(_("bitiş zamanı"), null=True, blank=True)
    reminder_sent_at = models.DateTimeField(_("hatırlatma gönderildi"), null=True, blank=True)
    cancellation_reason = models.CharField(_("iptal nedeni"), max_length=300, blank=True)

    class Meta:
        verbose_name = _("Rezervasyon")
        verbose_name_plural = _("Rezervasyonlar")
        ordering = ["reserved_at"]
        indexes = [
            models.Index(fields=["reserved_at", "status"]),
            models.Index(fields=["guest_phone"]),
        ]

    def __str__(self) -> str:
        return f"{self.code} · {self.guest_name} ({self.party_size} kişi)"

    def save(self, *args, **kwargs):
        if not self.code:
            from apps.core.utils import generate_code

            code = generate_code("R", 6)
            while Reservation.objects.filter(code=code).exists():
                code = generate_code("R", 6)
            self.code = code
        super().save(*args, **kwargs)

    @property
    def masked_guest_phone(self) -> str:
        """`customer.pii` izni olmayan kullanıcıya gösterilecek telefon.

        ``crm.Customer.masked_phone`` ile aynı biçimi kullanır; iki ekranda
        farklı maske görmek kullanıcıyı yanıltıyordu.
        """
        if not self.guest_phone:
            return ""
        if len(self.guest_phone) < 6:
            return "***"
        return f"{self.guest_phone[:4]}***{self.guest_phone[-2:]}"

    @property
    def ends_at(self):
        return self.reserved_at + timedelta(minutes=self.duration_minutes)

    @property
    def is_upcoming(self) -> bool:
        return self.status in {self.Status.PENDING, self.Status.CONFIRMED} and (
            self.reserved_at >= timezone.now()
        )

    @property
    def is_late(self) -> bool:
        """15 dakikadan fazla gecikti mi? (no-show adayı)"""
        if self.status != self.Status.CONFIRMED:
            return False
        return timezone.now() > self.reserved_at + timedelta(minutes=15)

    @property
    def minutes_until(self) -> int:
        return int((self.reserved_at - timezone.now()).total_seconds() // 60)

    def conflicts_with(self, table: Table) -> bool:
        """Bu masa için zaman çakışması var mı?"""
        return (
            Reservation.objects.filter(
                tables=table,
                status__in=[self.Status.PENDING, self.Status.CONFIRMED, self.Status.SEATED],
                reserved_at__lt=self.ends_at,
            )
            .exclude(pk=self.pk)
            .filter(reserved_at__gt=self.reserved_at - timedelta(minutes=self.duration_minutes))
            .exists()
        )


class WaitlistEntry(TimeStampedModel):
    """Bekleme listesi (masa boşalınca çağrılacak misafirler)."""

    class Status(models.TextChoices):
        WAITING = "waiting", _("Bekliyor")
        NOTIFIED = "notified", _("Çağrıldı")
        SEATED = "seated", _("Oturdu")
        LEFT = "left", _("Ayrıldı")

    guest_name = models.CharField(_("misafir adı"), max_length=120)
    guest_phone = models.CharField(_("telefon"), max_length=20, blank=True)
    party_size = models.PositiveSmallIntegerField(_("kişi sayısı"), default=2)
    area = models.ForeignKey(
        Area, verbose_name=_("tercih"), null=True, blank=True, on_delete=models.SET_NULL
    )
    status = models.CharField(
        _("durum"), max_length=10, choices=Status.choices, default=Status.WAITING, db_index=True
    )
    estimated_wait_minutes = models.PositiveIntegerField(_("tahminî bekleme (dk)"), default=15)
    notified_at = models.DateTimeField(_("çağrılma zamanı"), null=True, blank=True)
    seated_at = models.DateTimeField(_("oturma zamanı"), null=True, blank=True)
    note = models.CharField(_("not"), max_length=200, blank=True)

    class Meta:
        verbose_name = _("Bekleme listesi kaydı")
        verbose_name_plural = _("Bekleme listesi")
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.guest_name} ({self.party_size} kişi)"

    @property
    def waiting_minutes(self) -> int:
        return int((timezone.now() - self.created_at).total_seconds() // 60)
