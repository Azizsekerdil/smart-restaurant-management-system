"""Sipariş ve ödeme modelleri.

Tutar hesabı
------------
Ürün fiyatları KDV **dahil** girildiği için akış şöyledir:

    brüt satır toplamı  = (birim fiyat + seçenekler) * adet
    satır indirimi      = brüt * indirim oranı
    ara toplam          = Σ (brüt - satır indirimi)
    sipariş indirimi    = ara toplam üzerinden (kupon vb.)
    servis bedeli       = (ara toplam - sipariş indirimi) * servis oranı
    genel toplam        = ara toplam - sipariş indirimi + servis bedeli
    KDV (bilgi amaçlı)  = satırlardan geriye doğru hesaplanır

Tutarlar `recalculate()` içinde hesaplanıp modele yazılır; böylece
raporlar geçmiş fiyat değişikliklerinden etkilenmez.
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import SoftDeleteModel, TimeStampedModel
from apps.core.utils import daily_sequence_number, money, safe_divide


class Coupon(TimeStampedModel):
    """İndirim kuponu / kampanya kodu."""

    class Kind(models.TextChoices):
        PERCENT = "percent", _("Yüzde indirim")
        AMOUNT = "amount", _("Tutar indirimi")
        FREE_ITEM = "free_item", _("Ücretsiz ürün")

    code = models.CharField(_("kod"), max_length=32, unique=True, db_index=True)
    name = models.CharField(_("ad"), max_length=160)
    kind = models.CharField(_("tür"), max_length=10, choices=Kind.choices, default=Kind.PERCENT)
    value = models.DecimalField(
        _("değer"),
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text=_("Yüzde indirimde oran, tutar indiriminde tutar."),
    )
    max_discount = models.DecimalField(
        _("azami indirim"),
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text=_("0 = sınırsız. Yüzde indirimlerde üst sınır."),
    )
    minimum_order_total = models.DecimalField(
        _("asgari sipariş tutarı"), max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    free_product = models.ForeignKey(
        "catalog.Product",
        verbose_name=_("ücretsiz ürün"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="coupons",
    )
    valid_from = models.DateTimeField(_("başlangıç"), default=timezone.now)
    valid_until = models.DateTimeField(_("bitiş"), null=True, blank=True)
    usage_limit = models.PositiveIntegerField(_("toplam kullanım limiti"), default=0)
    usage_limit_per_customer = models.PositiveIntegerField(_("müşteri başına limit"), default=0)
    used_count = models.PositiveIntegerField(_("kullanım sayısı"), default=0, editable=False)
    is_active = models.BooleanField(_("aktif"), default=True, db_index=True)

    class Meta:
        verbose_name = _("Kupon")
        verbose_name_plural = _("Kuponlar")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.code} · {self.name}"

    def is_valid(self, order: Order | None = None) -> tuple[bool, str]:
        """Kuponun kullanılabilirliğini ve nedenini döndürür."""
        now = timezone.now()
        if not self.is_active:
            return False, "Kupon aktif değil."
        if self.valid_from > now:
            return False, "Kupon henüz başlamadı."
        if self.valid_until and self.valid_until < now:
            return False, "Kuponun süresi dolmuş."
        if self.usage_limit and self.used_count >= self.usage_limit:
            return False, "Kupon kullanım limiti dolmuş."
        if order is not None:
            if order.subtotal < self.minimum_order_total:
                return False, (f"Bu kupon için asgari sipariş tutarı {self.minimum_order_total} ₺.")
            if self.usage_limit_per_customer and order.customer_id:
                used = OrderDiscount.objects.filter(
                    coupon=self, order__customer_id=order.customer_id
                ).count()
                if used >= self.usage_limit_per_customer:
                    return False, "Bu müşteri kuponu kullanım hakkını doldurmuş."
        return True, ""

    def compute_discount(self, base_amount: Decimal) -> Decimal:
        if self.kind == self.Kind.PERCENT:
            amount = money(base_amount * self.value / Decimal("100"))
        elif self.kind == self.Kind.AMOUNT:
            amount = money(self.value)
        else:
            amount = money(self.free_product.price) if self.free_product else Decimal("0.00")
        if self.max_discount and amount > self.max_discount:
            amount = money(self.max_discount)
        return min(amount, money(base_amount))


class Order(SoftDeleteModel):
    """Sipariş / adisyon."""

    class Type(models.TextChoices):
        DINE_IN = "dine_in", _("Masada servis")
        TAKEAWAY = "takeaway", _("Paket")
        PICKUP = "pickup", _("Gel-al")
        DELIVERY = "delivery", _("Kurye")

    class Status(models.TextChoices):
        DRAFT = "draft", _("Taslak")
        OPEN = "open", _("Açık")
        SENT = "sent", _("Mutfağa gönderildi")
        PREPARING = "preparing", _("Hazırlanıyor")
        READY = "ready", _("Hazır")
        SERVED = "served", _("Servis edildi")
        PAID = "paid", _("Ödendi")
        CANCELLED = "cancelled", _("İptal edildi")

    number = models.CharField(_("adisyon no"), max_length=32, unique=True, db_index=True)
    order_type = models.CharField(
        _("sipariş türü"), max_length=10, choices=Type.choices, default=Type.DINE_IN, db_index=True
    )
    status = models.CharField(
        _("durum"), max_length=10, choices=Status.choices, default=Status.OPEN, db_index=True
    )

    table = models.ForeignKey(
        "floor.Table",
        verbose_name=_("masa"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="orders",
    )
    area = models.ForeignKey(
        "floor.Area",
        verbose_name=_("bölüm"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="orders",
    )
    customer = models.ForeignKey(
        "crm.Customer",
        verbose_name=_("müşteri"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="orders",
    )
    waiter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("garson"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="waiter_orders",
    )
    cashier = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("kasiyer"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="cashier_orders",
    )
    courier = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("kurye"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="courier_orders",
    )

    guest_count = models.PositiveSmallIntegerField(_("kişi sayısı"), default=1)
    parent_order = models.ForeignKey(
        "self",
        verbose_name=_("ana adisyon"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="split_orders",
        help_text=_("Hesap bölündüğünde kaynak adisyonu gösterir."),
    )

    # Teslimat bilgileri
    delivery_address = models.TextField(_("teslimat adresi"), blank=True)
    delivery_phone = models.CharField(_("teslimat telefonu"), max_length=20, blank=True)
    delivery_fee = models.DecimalField(
        _("teslimat ücreti"), max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    delivered_at = models.DateTimeField(_("teslim zamanı"), null=True, blank=True)

    # Tutarlar (recalculate ile hesaplanır)
    subtotal = models.DecimalField(
        _("ara toplam"), max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    item_discount_total = models.DecimalField(
        _("satır indirimleri"), max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    order_discount_total = models.DecimalField(
        _("sipariş indirimi"), max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    service_charge = models.DecimalField(
        _("servis bedeli"), max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    service_charge_rate = models.DecimalField(
        _("servis oranı (%)"), max_digits=5, decimal_places=2, default=Decimal("0.00")
    )
    tax_total = models.DecimalField(
        _("KDV toplamı"), max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    grand_total = models.DecimalField(
        _("genel toplam"), max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    paid_total = models.DecimalField(
        _("ödenen"), max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    tip_total = models.DecimalField(
        _("bahşiş"), max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    refunded_total = models.DecimalField(
        _("iade edilen"), max_digits=12, decimal_places=2, default=Decimal("0.00")
    )

    note = models.TextField(_("sipariş notu"), blank=True)
    kitchen_note = models.CharField(_("mutfak notu"), max_length=300, blank=True)

    opened_at = models.DateTimeField(_("açılış"), default=timezone.now, db_index=True)
    sent_at = models.DateTimeField(_("mutfağa gönderim"), null=True, blank=True)
    ready_at = models.DateTimeField(_("hazır olma"), null=True, blank=True)
    closed_at = models.DateTimeField(_("kapanış"), null=True, blank=True, db_index=True)

    cancelled_at = models.DateTimeField(_("iptal zamanı"), null=True, blank=True)
    cancel_reason = models.CharField(_("iptal nedeni"), max_length=300, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("iptal eden"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="cancelled_orders",
    )

    cash_session = models.ForeignKey(
        "orders.CashSession",
        verbose_name=_("kasa oturumu"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="orders",
    )

    class Meta:
        verbose_name = _("Sipariş")
        verbose_name_plural = _("Siparişler")
        ordering = ["-opened_at"]
        indexes = [
            models.Index(fields=["status", "-opened_at"]),
            models.Index(fields=["order_type", "status"]),
            models.Index(fields=["-closed_at"]),
        ]

    def __str__(self) -> str:
        where = self.table.name if self.table_id else self.get_order_type_display()
        return f"{self.number} · {where}"

    def save(self, *args, **kwargs):
        if not self.number:
            prefix = {
                self.Type.DINE_IN: "A-",
                self.Type.TAKEAWAY: "P-",
                self.Type.PICKUP: "G-",
                self.Type.DELIVERY: "K-",
            }.get(self.order_type, "A-")
            self.number = daily_sequence_number(Order, "number", prefix)
        if self.table_id and not self.area_id:
            self.area_id = self.table.area_id
        super().save(*args, **kwargs)

    # ------------------------------------------------------ durumlar
    @property
    def is_open(self) -> bool:
        return self.status not in {self.Status.PAID, self.Status.CANCELLED}

    @property
    def is_paid(self) -> bool:
        return self.status == self.Status.PAID

    @property
    def balance_due(self) -> Decimal:
        return money(self.grand_total - self.paid_total)

    @property
    def is_fully_paid(self) -> bool:
        return self.balance_due <= Decimal("0.00")

    @property
    def active_items(self):
        return self.items.exclude(status=OrderItem.Status.CANCELLED)

    @property
    def item_count(self) -> int:
        return sum(i.quantity for i in self.active_items)

    @property
    def duration_minutes(self) -> int:
        end = self.closed_at or timezone.now()
        return int((end - self.opened_at).total_seconds() // 60)

    @property
    def average_per_guest(self) -> Decimal:
        return money(safe_divide(self.grand_total, max(self.guest_count, 1)))

    @property
    def status_color(self) -> str:
        return {
            self.Status.DRAFT: "secondary",
            self.Status.OPEN: "primary",
            self.Status.SENT: "info",
            self.Status.PREPARING: "warning",
            self.Status.READY: "success",
            self.Status.SERVED: "success",
            self.Status.PAID: "dark",
            self.Status.CANCELLED: "danger",
        }.get(self.status, "secondary")

    # ------------------------------------------------------ hesaplama
    def recalculate(self, *, save: bool = True) -> Order:
        """Tüm tutarları satırlardan yeniden hesaplar."""
        items = list(
            self.active_items.select_related("product", "variant").prefetch_related("modifiers")
        )

        gross = Decimal("0.00")
        item_discounts = Decimal("0.00")
        for item in items:
            gross += item.gross_total
            item_discounts += item.discount_amount

        self.subtotal = money(gross - item_discounts)
        self.item_discount_total = money(item_discounts)

        order_discounts = self.discounts.aggregate(t=models.Sum("amount"))["t"] or Decimal("0.00")
        # Sipariş indirimi ara toplamı aşamaz.
        self.order_discount_total = min(money(order_discounts), self.subtotal)

        taxable_base = money(self.subtotal - self.order_discount_total)

        rate = self.service_charge_rate
        if rate == 0 and self.area_id:
            rate = self.area.service_charge_rate
        if rate == 0 and self.order_type == self.Type.DINE_IN:
            rate = settings.RESTAURANT["SERVICE_CHARGE_RATE"]
        self.service_charge_rate = rate
        self.service_charge = money(taxable_base * rate / Decimal("100"))

        self.grand_total = money(taxable_base + self.service_charge + self.delivery_fee)

        # KDV: satır bazında, indirim oranı satırlara dağıtılarak hesaplanır.
        discount_ratio = (
            safe_divide(self.order_discount_total, self.subtotal) if self.subtotal else Decimal("0")
        )
        tax = Decimal("0.00")
        for item in items:
            net_line = item.net_total * (Decimal("1") - discount_ratio)
            item_rate = Decimal(item.tax_rate or 0)
            if item_rate:
                tax += net_line * item_rate / (Decimal("100") + item_rate)
        self.tax_total = money(tax)

        payments = self.payments.filter(status=Payment.Status.COMPLETED)
        self.paid_total = money(
            payments.exclude(method=Payment.Method.TIP).aggregate(t=models.Sum("amount"))["t"]
            or Decimal("0.00")
        )
        self.tip_total = money(
            payments.filter(method=Payment.Method.TIP).aggregate(t=models.Sum("amount"))["t"]
            or Decimal("0.00")
        )
        self.refunded_total = money(
            self.refunds.aggregate(t=models.Sum("amount"))["t"] or Decimal("0.00")
        )

        if save:
            self.save(
                update_fields=[
                    "subtotal",
                    "item_discount_total",
                    "order_discount_total",
                    "service_charge",
                    "service_charge_rate",
                    "tax_total",
                    "grand_total",
                    "paid_total",
                    "tip_total",
                    "refunded_total",
                    "updated_at",
                ]
            )
        return self


class OrderItem(TimeStampedModel):
    """Adisyon satırı."""

    class Status(models.TextChoices):
        NEW = "new", _("Yeni")
        SENT = "sent", _("Mutfağa gönderildi")
        PREPARING = "preparing", _("Hazırlanıyor")
        READY = "ready", _("Hazır")
        SERVED = "served", _("Servis edildi")
        CANCELLED = "cancelled", _("İptal")

    order = models.ForeignKey(
        Order, verbose_name=_("sipariş"), on_delete=models.CASCADE, related_name="items"
    )
    product = models.ForeignKey(
        "catalog.Product",
        verbose_name=_("ürün"),
        on_delete=models.PROTECT,
        related_name="order_items",
    )
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        verbose_name=_("porsiyon"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="order_items",
    )

    # Ürün adı ve fiyatı satırda dondurulur: sonradan menü değişse bile
    # geçmiş adisyon ve raporlar bozulmaz.
    product_name = models.CharField(_("ürün adı"), max_length=200)
    unit_price = models.DecimalField(_("birim fiyat"), max_digits=10, decimal_places=2)
    original_price = models.DecimalField(
        _("liste fiyatı"), max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    tax_rate = models.DecimalField(
        _("KDV oranı (%)"), max_digits=5, decimal_places=2, default=Decimal("10.00")
    )
    quantity = models.DecimalField(
        _("adet"),
        max_digits=8,
        decimal_places=2,
        default=Decimal("1.00"),
        validators=[MinValueValidator(Decimal("0.01"))],
    )

    discount_percent = models.DecimalField(
        _("indirim (%)"), max_digits=5, decimal_places=2, default=Decimal("0.00")
    )
    discount_amount_manual = models.DecimalField(
        _("indirim tutarı"), max_digits=10, decimal_places=2, default=Decimal("0.00")
    )

    status = models.CharField(
        _("durum"), max_length=10, choices=Status.choices, default=Status.NEW, db_index=True
    )
    seat_number = models.PositiveSmallIntegerField(
        _("koltuk no"),
        null=True,
        blank=True,
        help_text=_("Hesabı kişilere göre bölmek için."),
    )
    course = models.PositiveSmallIntegerField(
        _("servis sırası"), default=1, help_text=_("1: başlangıç, 2: ana yemek, 3: tatlı")
    )
    note = models.CharField(_("not"), max_length=300, blank=True)

    station = models.ForeignKey(
        "kitchen.Station",
        verbose_name=_("istasyon"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="order_items",
    )
    sent_at = models.DateTimeField(_("gönderim zamanı"), null=True, blank=True)
    started_at = models.DateTimeField(_("hazırlığa başlama"), null=True, blank=True)
    ready_at = models.DateTimeField(_("hazır olma"), null=True, blank=True)
    served_at = models.DateTimeField(_("servis zamanı"), null=True, blank=True)

    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("iptal eden"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="cancelled_order_items",
    )
    cancel_reason = models.CharField(_("iptal nedeni"), max_length=300, blank=True)
    stock_deducted = models.BooleanField(_("stok düşüldü"), default=False)

    class Meta:
        verbose_name = _("Sipariş satırı")
        verbose_name_plural = _("Sipariş satırları")
        ordering = ["course", "created_at"]
        indexes = [
            models.Index(fields=["order", "status"]),
            models.Index(fields=["status", "station"]),
        ]

    def __str__(self) -> str:
        return f"{self.quantity} x {self.product_name}"

    def save(self, *args, **kwargs):
        if not self.product_name:
            name = self.product.name
            if self.variant_id:
                name = f"{name} ({self.variant.name})"
            self.product_name = name
        if not self.original_price:
            self.original_price = self.unit_price
        if not self.station_id and self.product_id:
            self.station_id = self.product.station_id
        super().save(*args, **kwargs)

    # ------------------------------------------------------ tutarlar
    @property
    def modifier_total(self) -> Decimal:
        return money(sum((m.price_delta for m in self.modifiers.all()), Decimal("0.00")))

    @property
    def effective_unit_price(self) -> Decimal:
        return money(self.unit_price + self.modifier_total)

    @property
    def gross_total(self) -> Decimal:
        return money(self.effective_unit_price * self.quantity)

    @property
    def discount_amount(self) -> Decimal:
        amount = money(self.gross_total * self.discount_percent / Decimal("100"))
        amount += money(self.discount_amount_manual)
        return min(amount, self.gross_total)

    @property
    def net_total(self) -> Decimal:
        return money(self.gross_total - self.discount_amount)

    @property
    def tax_amount(self) -> Decimal:
        rate = Decimal(self.tax_rate or 0)
        if not rate:
            return Decimal("0.00")
        return money(self.net_total * rate / (Decimal("100") + rate))

    @property
    def is_price_overridden(self) -> bool:
        return self.original_price != self.unit_price

    @property
    def preparation_minutes(self) -> int | None:
        if self.sent_at and self.ready_at:
            return int((self.ready_at - self.sent_at).total_seconds() // 60)
        return None

    @property
    def waiting_minutes(self) -> int:
        if not self.sent_at or self.status in {self.Status.SERVED, self.Status.CANCELLED}:
            return 0
        end = self.ready_at or timezone.now()
        return int((end - self.sent_at).total_seconds() // 60)

    @property
    def is_delayed(self) -> bool:
        """Hedef hazırlık süresini %50 aşan siparişler gecikmiş sayılır."""
        target = self.product.preparation_minutes or 10
        return self.waiting_minutes > target * 1.5

    @property
    def modifier_summary(self) -> str:
        return ", ".join(m.modifier_name for m in self.modifiers.all())


class OrderItemModifier(models.Model):
    """Sipariş satırında seçilen ekstra/seçenek."""

    order_item = models.ForeignKey(
        OrderItem, verbose_name=_("satır"), on_delete=models.CASCADE, related_name="modifiers"
    )
    modifier = models.ForeignKey(
        "catalog.Modifier",
        verbose_name=_("seçenek"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="order_item_modifiers",
    )
    modifier_name = models.CharField(_("seçenek adı"), max_length=160)
    price_delta = models.DecimalField(
        _("fiyat farkı"), max_digits=10, decimal_places=2, default=Decimal("0.00")
    )

    class Meta:
        verbose_name = _("Satır seçeneği")
        verbose_name_plural = _("Satır seçenekleri")

    def __str__(self) -> str:
        return self.modifier_name

    def save(self, *args, **kwargs):
        if not self.modifier_name and self.modifier_id:
            self.modifier_name = self.modifier.name
        super().save(*args, **kwargs)


class OrderDiscount(TimeStampedModel):
    """Sipariş geneline uygulanan indirim."""

    class Kind(models.TextChoices):
        COUPON = "coupon", _("Kupon")
        MANUAL = "manual", _("Elle indirim")
        LOYALTY = "loyalty", _("Sadakat puanı")
        CAMPAIGN = "campaign", _("Kampanya")
        STAFF = "staff", _("Personel indirimi")

    order = models.ForeignKey(
        Order, verbose_name=_("sipariş"), on_delete=models.CASCADE, related_name="discounts"
    )
    kind = models.CharField(_("tür"), max_length=10, choices=Kind.choices, default=Kind.MANUAL)
    coupon = models.ForeignKey(
        Coupon,
        verbose_name=_("kupon"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="usages",
    )
    label = models.CharField(_("açıklama"), max_length=160)
    percent = models.DecimalField(
        _("oran (%)"), max_digits=5, decimal_places=2, default=Decimal("0.00")
    )
    amount = models.DecimalField(_("tutar"), max_digits=12, decimal_places=2)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("onaylayan"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_discounts",
    )
    reason = models.CharField(_("gerekçe"), max_length=300, blank=True)

    class Meta:
        verbose_name = _("Sipariş indirimi")
        verbose_name_plural = _("Sipariş indirimleri")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.label}: {self.amount}"


class CashSession(TimeStampedModel):
    """Kasa açılış/kapanış oturumu (Z raporu kaynağı)."""

    class Status(models.TextChoices):
        OPEN = "open", _("Açık")
        CLOSED = "closed", _("Kapalı")

    number = models.CharField(_("oturum no"), max_length=32, unique=True)
    terminal_name = models.CharField(_("terminal"), max_length=60, default="Kasa-1")
    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("açan"),
        on_delete=models.PROTECT,
        related_name="opened_cash_sessions",
    )
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("kapatan"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="closed_cash_sessions",
    )
    status = models.CharField(_("durum"), max_length=8, choices=Status.choices, default=Status.OPEN)
    opening_float = models.DecimalField(
        _("açılış kasası"), max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    counted_cash = models.DecimalField(
        _("sayılan nakit"), max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    opened_at = models.DateTimeField(_("açılış"), default=timezone.now, db_index=True)
    closed_at = models.DateTimeField(_("kapanış"), null=True, blank=True)
    notes = models.TextField(_("notlar"), blank=True)

    class Meta:
        verbose_name = _("Kasa oturumu")
        verbose_name_plural = _("Kasa oturumları")
        ordering = ["-opened_at"]

    def __str__(self) -> str:
        return f"{self.number} ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = daily_sequence_number(CashSession, "number", "KASA-")
        super().save(*args, **kwargs)

    @property
    def expected_cash(self) -> Decimal:
        """Kasada olması gereken nakit."""
        cash_in = self.payments.filter(
            method=Payment.Method.CASH, status=Payment.Status.COMPLETED
        ).aggregate(t=models.Sum("amount"))["t"] or Decimal("0.00")
        cash_refunds = Refund.objects.filter(
            order__cash_session=self, method=Payment.Method.CASH
        ).aggregate(t=models.Sum("amount"))["t"] or Decimal("0.00")
        movements = self.movements.aggregate(t=models.Sum("amount"))["t"] or Decimal("0.00")
        return money(self.opening_float + cash_in - cash_refunds + movements)

    @property
    def cash_variance(self) -> Decimal:
        return money(self.counted_cash - self.expected_cash)


class CashMovement(TimeStampedModel):
    """Kasadan para giriş/çıkışı (gider ödemesi, para çekme)."""

    class Kind(models.TextChoices):
        PAID_IN = "paid_in", _("Kasaya giriş")
        PAID_OUT = "paid_out", _("Kasadan çıkış")
        DROP = "drop", _("Kasadan kasaya aktarım")

    session = models.ForeignKey(
        CashSession, verbose_name=_("oturum"), on_delete=models.CASCADE, related_name="movements"
    )
    kind = models.CharField(_("tür"), max_length=10, choices=Kind.choices)
    amount = models.DecimalField(
        _("tutar"),
        max_digits=12,
        decimal_places=2,
        help_text=_("Çıkışlar negatif kaydedilir."),
    )
    reason = models.CharField(_("gerekçe"), max_length=300)

    class Meta:
        verbose_name = _("Kasa hareketi")
        verbose_name_plural = _("Kasa hareketleri")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.get_kind_display()}: {self.amount}"


class Payment(TimeStampedModel):
    """Ödeme kaydı. Bir siparişte birden fazla ödeme olabilir (çoklu ödeme)."""

    class Method(models.TextChoices):
        CASH = "cash", _("Nakit")
        CARD = "card", _("Kredi / banka kartı")
        MEAL_CARD = "meal_card", _("Yemek kartı")
        TRANSFER = "transfer", _("Havale / EFT")
        ONLINE = "online", _("Online ödeme")
        LOYALTY = "loyalty", _("Sadakat puanı")
        GIFT = "gift", _("Hediye çeki")
        ON_ACCOUNT = "on_account", _("Cari hesaba")
        TIP = "tip", _("Bahşiş")

    class Status(models.TextChoices):
        PENDING = "pending", _("Bekliyor")
        COMPLETED = "completed", _("Tamamlandı")
        FAILED = "failed", _("Başarısız")
        VOIDED = "voided", _("İptal")

    order = models.ForeignKey(
        Order, verbose_name=_("sipariş"), on_delete=models.PROTECT, related_name="payments"
    )
    method = models.CharField(_("yöntem"), max_length=12, choices=Method.choices, db_index=True)
    amount = models.DecimalField(_("tutar"), max_digits=12, decimal_places=2)
    received_amount = models.DecimalField(
        _("alınan"),
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text=_("Nakit ödemede müşteriden alınan tutar."),
    )
    change_amount = models.DecimalField(
        _("para üstü"), max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    status = models.CharField(
        _("durum"), max_length=10, choices=Status.choices, default=Status.COMPLETED, db_index=True
    )
    reference = models.CharField(
        _("referans"),
        max_length=100,
        blank=True,
        help_text=_("POS terminal işlem numarası, son 4 hane vb."),
    )
    cashier = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("kasiyer"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="payments_taken",
    )
    cash_session = models.ForeignKey(
        CashSession,
        verbose_name=_("kasa oturumu"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="payments",
    )
    paid_at = models.DateTimeField(_("ödeme zamanı"), default=timezone.now, db_index=True)
    note = models.CharField(_("not"), max_length=200, blank=True)

    class Meta:
        verbose_name = _("Ödeme")
        verbose_name_plural = _("Ödemeler")
        ordering = ["-paid_at"]
        indexes = [models.Index(fields=["method", "-paid_at"])]

    def __str__(self) -> str:
        return f"{self.get_method_display()}: {self.amount}"


class Refund(TimeStampedModel):
    """İade kaydı."""

    class Reason(models.TextChoices):
        CUSTOMER_COMPLAINT = "complaint", _("Müşteri şikâyeti")
        WRONG_ORDER = "wrong_order", _("Yanlış sipariş")
        QUALITY = "quality", _("Ürün kalitesi")
        LONG_WAIT = "long_wait", _("Uzun bekleme")
        CASHIER_ERROR = "cashier_error", _("Kasa hatası")
        OTHER = "other", _("Diğer")

    order = models.ForeignKey(
        Order, verbose_name=_("sipariş"), on_delete=models.PROTECT, related_name="refunds"
    )
    order_item = models.ForeignKey(
        OrderItem,
        verbose_name=_("satır"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="refunds",
    )
    amount = models.DecimalField(_("tutar"), max_digits=12, decimal_places=2)
    method = models.CharField(
        _("iade yöntemi"),
        max_length=12,
        choices=Payment.Method.choices,
        default=Payment.Method.CASH,
    )
    reason = models.CharField(_("neden"), max_length=20, choices=Reason.choices)
    description = models.CharField(_("açıklama"), max_length=300, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("onaylayan"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_refunds",
    )
    restock = models.BooleanField(
        _("stoğa geri ekle"),
        default=False,
        help_text=_("Ürün kullanılmadıysa malzemeler stoğa geri yüklenir."),
    )

    class Meta:
        verbose_name = _("İade")
        verbose_name_plural = _("İadeler")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.order.number} iade: {self.amount}"
