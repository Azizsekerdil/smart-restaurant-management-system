"""Mutfak istasyonları ve KOT (kitchen order ticket) modelleri."""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel
from apps.core.utils import daily_sequence_number, slugify_tr


class Station(TimeStampedModel):
    """Hazırlık istasyonu (sıcak mutfak, soğuk mutfak, ızgara, bar, tatlı)."""

    class Kind(models.TextChoices):
        KITCHEN = "kitchen", _("Mutfak")
        GRILL = "grill", _("Izgara")
        COLD = "cold", _("Soğuk mutfak")
        BAR = "bar", _("Bar")
        DESSERT = "dessert", _("Tatlı")
        PASTRY = "pastry", _("Pastane")

    name = models.CharField(_("ad"), max_length=80, unique=True)
    code = models.SlugField(_("kod"), max_length=40, unique=True, blank=True)
    kind = models.CharField(_("tür"), max_length=10, choices=Kind.choices, default=Kind.KITCHEN)
    color = models.CharField(_("renk"), max_length=7, default="#fd7e14")
    printer_name = models.CharField(
        _("yazıcı adı"),
        max_length=100,
        blank=True,
        help_text=_("KOT çıktısının gönderileceği yazıcı (isteğe bağlı)."),
    )
    warning_minutes = models.PositiveIntegerField(
        _("uyarı süresi (dk)"),
        default=10,
        help_text=_("Bu süreyi aşan siparişler sarı renkte gösterilir."),
    )
    critical_minutes = models.PositiveIntegerField(
        _("kritik süre (dk)"),
        default=20,
        help_text=_("Bu süreyi aşan siparişler kırmızı renkte ve sesli uyarıyla gösterilir."),
    )
    sort_order = models.PositiveIntegerField(_("sıra"), default=100)
    is_active = models.BooleanField(_("aktif"), default=True)

    class Meta:
        verbose_name = _("İstasyon")
        verbose_name_plural = _("İstasyonlar")
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = slugify_tr(self.name)[:40]
        super().save(*args, **kwargs)

    @property
    def is_bar(self) -> bool:
        return self.kind == self.Kind.BAR

    @property
    def active_ticket_count(self) -> int:
        return self.tickets.exclude(
            status__in=[KitchenTicket.Status.COMPLETED, KitchenTicket.Status.CANCELLED]
        ).count()


class KitchenTicket(TimeStampedModel):
    """Bir siparişin belirli bir istasyona giden bölümü (KOT)."""

    class Status(models.TextChoices):
        QUEUED = "queued", _("Sırada")
        PREPARING = "preparing", _("Hazırlanıyor")
        READY = "ready", _("Hazır")
        COMPLETED = "completed", _("Teslim edildi")
        CANCELLED = "cancelled", _("İptal")

    class Priority(models.IntegerChoices):
        LOW = 1, _("Düşük")
        NORMAL = 2, _("Normal")
        HIGH = 3, _("Yüksek")
        RUSH = 4, _("Acil")

    number = models.CharField(_("KOT no"), max_length=32, unique=True, db_index=True)
    order = models.ForeignKey(
        "orders.Order", verbose_name=_("sipariş"), on_delete=models.CASCADE, related_name="tickets"
    )
    station = models.ForeignKey(
        Station, verbose_name=_("istasyon"), on_delete=models.PROTECT, related_name="tickets"
    )
    status = models.CharField(
        _("durum"), max_length=10, choices=Status.choices, default=Status.QUEUED, db_index=True
    )
    priority = models.PositiveSmallIntegerField(
        _("öncelik"), choices=Priority.choices, default=Priority.NORMAL
    )
    course = models.PositiveSmallIntegerField(_("servis sırası"), default=1)
    note = models.CharField(_("not"), max_length=300, blank=True)

    queued_at = models.DateTimeField(_("sıraya girme"), default=timezone.now, db_index=True)
    started_at = models.DateTimeField(_("başlama"), null=True, blank=True)
    ready_at = models.DateTimeField(_("hazır olma"), null=True, blank=True)
    completed_at = models.DateTimeField(_("teslim"), null=True, blank=True)

    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("başlatan"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="started_tickets",
    )
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("tamamlayan"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="completed_tickets",
    )
    printed_at = models.DateTimeField(_("yazdırma zamanı"), null=True, blank=True)

    class Meta:
        verbose_name = _("Mutfak fişi (KOT)")
        verbose_name_plural = _("Mutfak fişleri (KOT)")
        ordering = ["-priority", "queued_at"]
        indexes = [
            models.Index(fields=["station", "status", "queued_at"]),
            models.Index(fields=["status", "-priority"]),
        ]

    def __str__(self) -> str:
        return f"{self.number} · {self.station.name}"

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = daily_sequence_number(KitchenTicket, "number", "KOT-")
        super().save(*args, **kwargs)

    # ------------------------------------------------------- süreler
    @property
    def elapsed_minutes(self) -> int:
        end = self.ready_at or timezone.now()
        return int((end - self.queued_at).total_seconds() // 60)

    @property
    def preparation_minutes(self) -> int | None:
        if self.started_at and self.ready_at:
            return int((self.ready_at - self.started_at).total_seconds() // 60)
        return None

    @property
    def target_minutes(self) -> int:
        """Satırlardaki en uzun hazırlık süresi."""
        values = [
            line.order_item.product.preparation_minutes
            for line in self.lines.select_related("order_item__product")
        ]
        return max(values) if values else 10

    @property
    def urgency(self) -> str:
        """Ekranda renk kodu: normal | warning | critical."""
        if self.status in {self.Status.COMPLETED, self.Status.CANCELLED}:
            return "normal"
        elapsed = self.elapsed_minutes
        if elapsed >= self.station.critical_minutes:
            return "critical"
        if elapsed >= self.station.warning_minutes:
            return "warning"
        return "normal"

    @property
    def is_delayed(self) -> bool:
        return self.urgency == "critical"

    @property
    def table_label(self) -> str:
        if self.order.table_id:
            return self.order.table.name
        return self.order.get_order_type_display()

    def to_stream_dict(self) -> dict:
        """WebSocket üzerinden gönderilecek özet."""
        return {
            "id": self.pk,
            "number": self.number,
            "order_number": self.order.number,
            "station": self.station.code,
            "status": self.status,
            "status_label": self.get_status_display(),
            "priority": self.priority,
            "course": self.course,
            "table": self.table_label,
            "note": self.note,
            "elapsed_minutes": self.elapsed_minutes,
            "urgency": self.urgency,
            "queued_at": self.queued_at.isoformat(),
            "items": [
                {
                    "id": line.pk,
                    "name": line.order_item.product_name,
                    "quantity": str(line.order_item.quantity),
                    "note": line.order_item.note,
                    "modifiers": line.order_item.modifier_summary,
                    "status": line.status,
                }
                for line in self.lines.select_related("order_item").prefetch_related(
                    "order_item__modifiers"
                )
            ],
        }


class TicketLine(models.Model):
    """KOT satırı - bir sipariş satırının istasyondaki karşılığı."""

    class Status(models.TextChoices):
        PENDING = "pending", _("Bekliyor")
        PREPARING = "preparing", _("Hazırlanıyor")
        READY = "ready", _("Hazır")
        CANCELLED = "cancelled", _("İptal")

    ticket = models.ForeignKey(
        KitchenTicket, verbose_name=_("KOT"), on_delete=models.CASCADE, related_name="lines"
    )
    order_item = models.ForeignKey(
        "orders.OrderItem",
        verbose_name=_("sipariş satırı"),
        on_delete=models.CASCADE,
        related_name="ticket_lines",
    )
    status = models.CharField(
        _("durum"), max_length=10, choices=Status.choices, default=Status.PENDING
    )
    completed_at = models.DateTimeField(_("tamamlanma"), null=True, blank=True)

    class Meta:
        verbose_name = _("KOT satırı")
        verbose_name_plural = _("KOT satırları")
        constraints = [
            models.UniqueConstraint(
                fields=["ticket", "order_item"], name="uniq_order_item_per_ticket"
            )
        ]

    def __str__(self) -> str:
        return f"{self.ticket.number} · {self.order_item.product_name}"
