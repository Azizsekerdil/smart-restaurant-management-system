"""Muhasebe ve rapor modelleri: gelir/gider, günlük kapanış özeti."""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel
from apps.core.utils import money, safe_divide


class ExpenseCategory(models.Model):
    name = models.CharField(_("ad"), max_length=100, unique=True)
    is_fixed = models.BooleanField(
        _("sabit gider"), default=False, help_text=_("Kira, maaş gibi düzenli giderler.")
    )
    sort_order = models.PositiveIntegerField(_("sıra"), default=100)

    class Meta:
        verbose_name = _("Gider kategorisi")
        verbose_name_plural = _("Gider kategorileri")
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        return self.name


class Expense(TimeStampedModel):
    """Gider kaydı."""

    class PaymentMethod(models.TextChoices):
        CASH = "cash", _("Nakit")
        BANK = "bank", _("Banka")
        CARD = "card", _("Kart")
        CREDIT = "credit", _("Vadeli")

    category = models.ForeignKey(
        ExpenseCategory,
        verbose_name=_("kategori"),
        on_delete=models.PROTECT,
        related_name="expenses",
    )
    description = models.CharField(_("açıklama"), max_length=300)
    amount = models.DecimalField(_("tutar"), max_digits=12, decimal_places=2)
    tax_amount = models.DecimalField(
        _("KDV"), max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    expense_date = models.DateField(_("tarih"), default=timezone.localdate, db_index=True)
    payment_method = models.CharField(
        _("ödeme yöntemi"), max_length=10, choices=PaymentMethod.choices, default=PaymentMethod.CASH
    )
    supplier = models.ForeignKey(
        "inventory.Supplier",
        verbose_name=_("tedarikçi"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="expenses",
    )
    invoice_number = models.CharField(_("belge no"), max_length=60, blank=True)
    receipt_image = models.ImageField(
        _("fiş görseli"), upload_to="receipts/", blank=True, null=True
    )
    ai_extracted_data = models.JSONField(
        _("AI çıkarımı"),
        default=dict,
        blank=True,
        help_text=_("Fiş görselinden yapay zekâ ile okunan alanlar."),
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("kaydeden"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="expenses",
    )

    class Meta:
        verbose_name = _("Gider")
        verbose_name_plural = _("Giderler")
        ordering = ["-expense_date", "-created_at"]
        indexes = [models.Index(fields=["-expense_date", "category"])]

    def __str__(self) -> str:
        return f"{self.description} · {self.amount} ₺"

    @property
    def net_amount(self) -> Decimal:
        return money(self.amount - self.tax_amount)


class DailyClosing(TimeStampedModel):
    """Gün sonu kapanış özeti (Z raporu benzeri).

    UYARI: Bu belge **mali değeri olmayan** bir işletme içi özettir.
    Yasal Z raporu, onaylı ödeme kaydedici cihaz (ÖKC/yeni nesil yazarkasa)
    tarafından üretilir. Bu kayıt onun yerine geçmez.
    """

    closing_date = models.DateField(_("tarih"), unique=True, db_index=True)
    cash_session = models.ForeignKey(
        "orders.CashSession",
        verbose_name=_("kasa oturumu"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="closings",
    )

    order_count = models.PositiveIntegerField(_("sipariş sayısı"), default=0)
    guest_count = models.PositiveIntegerField(_("misafir sayısı"), default=0)
    gross_sales = models.DecimalField(
        _("brüt satış"), max_digits=14, decimal_places=2, default=Decimal("0.00")
    )
    discount_total = models.DecimalField(
        _("indirim"), max_digits=14, decimal_places=2, default=Decimal("0.00")
    )
    refund_total = models.DecimalField(
        _("iade"), max_digits=14, decimal_places=2, default=Decimal("0.00")
    )
    service_charge_total = models.DecimalField(
        _("servis bedeli"), max_digits=14, decimal_places=2, default=Decimal("0.00")
    )
    tax_total = models.DecimalField(
        _("KDV"), max_digits=14, decimal_places=2, default=Decimal("0.00")
    )
    net_sales = models.DecimalField(
        _("net satış"), max_digits=14, decimal_places=2, default=Decimal("0.00")
    )
    tip_total = models.DecimalField(
        _("bahşiş"), max_digits=14, decimal_places=2, default=Decimal("0.00")
    )

    payment_breakdown = models.JSONField(_("ödeme dağılımı"), default=dict, blank=True)
    category_breakdown = models.JSONField(_("kategori dağılımı"), default=dict, blank=True)

    cash_expected = models.DecimalField(
        _("beklenen nakit"), max_digits=14, decimal_places=2, default=Decimal("0.00")
    )
    cash_counted = models.DecimalField(
        _("sayılan nakit"), max_digits=14, decimal_places=2, default=Decimal("0.00")
    )
    void_count = models.PositiveIntegerField(_("iptal sayısı"), default=0)
    void_total = models.DecimalField(
        _("iptal tutarı"), max_digits=14, decimal_places=2, default=Decimal("0.00")
    )

    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("kapatan"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="daily_closings",
    )
    notes = models.TextField(_("notlar"), blank=True)
    ai_summary = models.TextField(_("AI günlük özeti"), blank=True)

    class Meta:
        verbose_name = _("Gün sonu kapanışı")
        verbose_name_plural = _("Gün sonu kapanışları")
        ordering = ["-closing_date"]

    def __str__(self) -> str:
        return f"{self.closing_date} kapanışı · {self.net_sales} ₺"

    @property
    def average_ticket(self) -> Decimal:
        return money(safe_divide(self.net_sales, max(self.order_count, 1)))

    @property
    def average_per_guest(self) -> Decimal:
        return money(safe_divide(self.net_sales, max(self.guest_count, 1)))

    @property
    def cash_variance(self) -> Decimal:
        return money(self.cash_counted - self.cash_expected)

    @property
    def legal_notice(self) -> str:
        return (
            "Bu belge işletme içi bir özet raporudur ve yasal mali belge "
            "(Z raporu / e-fatura / e-arşiv) yerine geçmez. Yasal belgeler "
            "onaylı ÖKC cihazı veya yetkili e-fatura entegratörü üzerinden üretilmelidir."
        )


class SavedReport(TimeStampedModel):
    """Kullanıcının kaydettiği rapor filtresi."""

    name = models.CharField(_("ad"), max_length=160)
    report_type = models.CharField(_("rapor türü"), max_length=60)
    filters = models.JSONField(_("filtreler"), default=dict, blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("sahip"),
        on_delete=models.CASCADE,
        related_name="saved_reports",
    )
    is_shared = models.BooleanField(_("paylaşılan"), default=False)

    class Meta:
        verbose_name = _("Kayıtlı rapor")
        verbose_name_plural = _("Kayıtlı raporlar")
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name
