"""Stok modelleri: birim, malzeme, depo, parti (lot), hareket, satın alma.

Stok yaklaşımı
--------------
* Her malzemenin bir **temel birimi** vardır (ör. gram). Diğer birimler
  (kg, adet, litre) katsayıyla temel birime çevrilir. Böylece "1 kg un
  aldım, 250 g kullandım" doğru hesaplanır.
* Miktarlar **parti (batch)** bazında tutulur; her partinin kendi birim
  maliyeti ve son kullanma tarihi vardır. Bu, FIFO/FEFO tüketimini ve
  gerçek maliyet takibini mümkün kılar.
* `StockItem` özet tablodur (hızlı sorgu için); gerçek kaynak partiler ve
  hareketlerdir.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import SoftDeleteModel, TimeStampedModel
from apps.core.utils import money, safe_divide
from apps.core.utils import quantity as q3


class UnitOfMeasure(models.Model):
    """Ölçü birimi ve temel birime dönüşüm katsayısı."""

    class Dimension(models.TextChoices):
        MASS = "mass", _("Ağırlık")
        VOLUME = "volume", _("Hacim")
        COUNT = "count", _("Adet")

    code = models.CharField(_("kod"), max_length=12, unique=True)
    name = models.CharField(_("ad"), max_length=60)
    dimension = models.CharField(
        _("boyut"), max_length=10, choices=Dimension.choices, default=Dimension.MASS
    )
    factor_to_base = models.DecimalField(
        _("temel birime katsayı"),
        max_digits=16,
        decimal_places=6,
        default=Decimal("1.000000"),
        help_text=_("1 bu birim = kaç temel birim? (ör. kg -> 1000 g)"),
    )
    is_base = models.BooleanField(_("temel birim"), default=False)

    class Meta:
        verbose_name = _("Ölçü birimi")
        verbose_name_plural = _("Ölçü birimleri")
        ordering = ["dimension", "-is_base", "code"]

    def __str__(self) -> str:
        return self.code

    def to_base(self, value: Decimal) -> Decimal:
        return q3(Decimal(str(value)) * self.factor_to_base)

    def from_base(self, value: Decimal) -> Decimal:
        return q3(safe_divide(Decimal(str(value)), self.factor_to_base))


class IngredientCategory(models.Model):
    name = models.CharField(_("ad"), max_length=100, unique=True)
    sort_order = models.PositiveIntegerField(_("sıra"), default=100)

    class Meta:
        verbose_name = _("Malzeme kategorisi")
        verbose_name_plural = _("Malzeme kategorileri")
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        return self.name


class Warehouse(TimeStampedModel):
    """Depo / stok noktası (ana depo, mutfak, bar, soğuk oda)."""

    name = models.CharField(_("ad"), max_length=100, unique=True)
    code = models.SlugField(_("kod"), max_length=30, unique=True)
    location = models.CharField(_("konum"), max_length=200, blank=True)
    is_default = models.BooleanField(_("varsayılan"), default=False)
    is_cold_storage = models.BooleanField(_("soğuk depo"), default=False)
    is_active = models.BooleanField(_("aktif"), default=True)

    class Meta:
        verbose_name = _("Depo")
        verbose_name_plural = _("Depolar")
        ordering = ["-is_default", "name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_default:
            Warehouse.objects.exclude(pk=self.pk).update(is_default=False)

    @classmethod
    def get_default(cls) -> Warehouse:
        return cls.objects.filter(is_active=True).order_by("-is_default", "pk").first()


class Ingredient(SoftDeleteModel):
    """Stok takibi yapılan malzeme."""

    class Rotation(models.TextChoices):
        FIFO = "fifo", _("FIFO - İlk giren ilk çıkar")
        FEFO = "fefo", _("FEFO - Önce son kullanma tarihi yakın olan")

    name = models.CharField(_("ad"), max_length=160, db_index=True)
    sku = models.CharField(_("stok kodu"), max_length=40, unique=True, blank=True, null=True)
    category = models.ForeignKey(
        IngredientCategory,
        verbose_name=_("kategori"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ingredients",
    )
    base_unit = models.ForeignKey(
        UnitOfMeasure,
        verbose_name=_("temel birim"),
        on_delete=models.PROTECT,
        related_name="ingredients",
        help_text=_("Stok bu birimde tutulur (ör. gram, ml, adet)."),
    )
    purchase_unit = models.ForeignKey(
        UnitOfMeasure,
        verbose_name=_("satın alma birimi"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="purchased_ingredients",
        help_text=_("Tedarikçiden alınan birim (ör. kg, koli)."),
    )

    critical_level = models.DecimalField(
        _("kritik seviye"),
        max_digits=14,
        decimal_places=3,
        default=Decimal("0.000"),
        help_text=_("Bu seviyenin altına düşünce uyarı üretilir (temel birimde)."),
    )
    reorder_quantity = models.DecimalField(
        _("sipariş miktarı"), max_digits=14, decimal_places=3, default=Decimal("0.000")
    )
    is_perishable = models.BooleanField(_("bozulabilir"), default=False)
    shelf_life_days = models.PositiveIntegerField(_("raf ömrü (gün)"), null=True, blank=True)
    rotation = models.CharField(
        _("tüketim yöntemi"), max_length=4, choices=Rotation.choices, default=Rotation.FEFO
    )

    default_supplier = models.ForeignKey(
        "inventory.Supplier",
        verbose_name=_("varsayılan tedarikçi"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="default_ingredients",
    )
    is_active = models.BooleanField(_("aktif"), default=True, db_index=True)
    notes = models.TextField(_("notlar"), blank=True)

    class Meta:
        verbose_name = _("Malzeme")
        verbose_name_plural = _("Malzemeler")
        ordering = ["name"]
        indexes = [models.Index(fields=["is_active", "name"])]

    def __str__(self) -> str:
        return f"{self.name} ({self.base_unit.code})"

    def save(self, *args, **kwargs):
        if self.sku == "":
            self.sku = None
        super().save(*args, **kwargs)

    # ------------------------------------------------------ miktarlar
    @property
    def total_on_hand(self) -> Decimal:
        """Tüm depolardaki toplam miktar (temel birimde)."""
        total = self.stock_items.aggregate(t=Sum("quantity"))["t"]
        return q3(total or 0)

    def on_hand_at(self, warehouse: Warehouse) -> Decimal:
        item = self.stock_items.filter(warehouse=warehouse).first()
        return q3(item.quantity if item else 0)

    @property
    def average_cost(self) -> Decimal:
        """Ağırlıklı ortalama birim maliyet (temel birim başına)."""
        batches = self.batches.filter(remaining_quantity__gt=0)
        total_qty = Decimal("0")
        total_val = Decimal("0")
        for batch in batches:
            total_qty += batch.remaining_quantity
            total_val += batch.remaining_quantity * batch.unit_cost
        if total_qty > 0:
            return money(total_val / total_qty)
        last = self.batches.order_by("-received_at").first()
        return money(last.unit_cost) if last else Decimal("0.00")

    @property
    def stock_value(self) -> Decimal:
        return money(self.total_on_hand * self.average_cost)

    @property
    def is_below_critical(self) -> bool:
        return self.critical_level > 0 and self.total_on_hand <= self.critical_level

    @property
    def is_out_of_stock(self) -> bool:
        return self.total_on_hand <= 0

    @property
    def stock_status(self) -> str:
        if self.is_out_of_stock:
            return "out"
        if self.is_below_critical:
            return "critical"
        if self.critical_level > 0 and self.total_on_hand <= self.critical_level * Decimal("1.5"):
            return "low"
        return "ok"

    @property
    def expiring_soon(self):
        """7 gün içinde son kullanma tarihi dolacak partiler."""
        limit = timezone.localdate() + timedelta(days=7)
        return self.batches.filter(
            remaining_quantity__gt=0, expiry_date__isnull=False, expiry_date__lte=limit
        ).order_by("expiry_date")

    def daily_consumption_average(self, days: int = 30) -> Decimal:
        """Son `days` gündeki ortalama günlük tüketim (temel birim)."""
        since = timezone.now() - timedelta(days=days)
        consumed = self.movements.filter(
            created_at__gte=since,
            movement_type__in=[
                StockMovement.Type.SALE,
                StockMovement.Type.WASTE,
                StockMovement.Type.PRODUCTION,
            ],
        ).aggregate(t=Sum("quantity"))["t"] or Decimal("0")
        return q3(safe_divide(abs(consumed), days))

    def days_until_stockout(self, days: int = 30) -> int | None:
        """Mevcut tüketim hızıyla stok kaç gün yeter?"""
        rate = self.daily_consumption_average(days)
        if rate <= 0:
            return None
        return int(safe_divide(self.total_on_hand, rate))


class StockItem(models.Model):
    """Depo bazında özet stok miktarı (hızlı okuma için)."""

    ingredient = models.ForeignKey(
        Ingredient, verbose_name=_("malzeme"), on_delete=models.CASCADE, related_name="stock_items"
    )
    warehouse = models.ForeignKey(
        Warehouse, verbose_name=_("depo"), on_delete=models.CASCADE, related_name="stock_items"
    )
    quantity = models.DecimalField(
        _("miktar"), max_digits=16, decimal_places=3, default=Decimal("0.000")
    )
    updated_at = models.DateTimeField(_("güncellenme"), auto_now=True)

    class Meta:
        verbose_name = _("Depo stoğu")
        verbose_name_plural = _("Depo stokları")
        constraints = [
            models.UniqueConstraint(
                fields=["ingredient", "warehouse"], name="uniq_stock_per_warehouse"
            )
        ]
        indexes = [models.Index(fields=["warehouse", "ingredient"])]

    def __str__(self) -> str:
        return f"{self.ingredient.name} @ {self.warehouse.code}: {self.quantity}"


class StockBatch(TimeStampedModel):
    """Stok partisi (lot). FIFO/FEFO ve son kullanma takibi için."""

    ingredient = models.ForeignKey(
        Ingredient, verbose_name=_("malzeme"), on_delete=models.CASCADE, related_name="batches"
    )
    warehouse = models.ForeignKey(
        Warehouse, verbose_name=_("depo"), on_delete=models.PROTECT, related_name="batches"
    )
    lot_code = models.CharField(_("parti kodu"), max_length=60, blank=True)
    initial_quantity = models.DecimalField(_("giriş miktarı"), max_digits=16, decimal_places=3)
    remaining_quantity = models.DecimalField(
        _("kalan miktar"), max_digits=16, decimal_places=3, db_index=True
    )
    unit_cost = models.DecimalField(
        _("birim maliyet"),
        max_digits=14,
        decimal_places=4,
        default=Decimal("0.0000"),
        help_text=_("Temel birim başına maliyet."),
    )
    received_at = models.DateTimeField(_("giriş zamanı"), default=timezone.now, db_index=True)
    expiry_date = models.DateField(_("son kullanma"), null=True, blank=True, db_index=True)
    supplier = models.ForeignKey(
        "inventory.Supplier",
        verbose_name=_("tedarikçi"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="batches",
    )

    class Meta:
        verbose_name = _("Stok partisi")
        verbose_name_plural = _("Stok partileri")
        ordering = ["expiry_date", "received_at"]
        indexes = [
            models.Index(fields=["ingredient", "warehouse", "remaining_quantity"]),
            models.Index(fields=["expiry_date"]),
        ]

    def __str__(self) -> str:
        return f"{self.ingredient.name} lot {self.lot_code or self.pk}"

    @property
    def is_expired(self) -> bool:
        return bool(self.expiry_date and self.expiry_date < timezone.localdate())

    @property
    def days_to_expiry(self) -> int | None:
        if not self.expiry_date:
            return None
        return (self.expiry_date - timezone.localdate()).days

    @property
    def value(self) -> Decimal:
        return money(self.remaining_quantity * self.unit_cost)


class StockMovement(TimeStampedModel):
    """Her stok değişikliğinin değişmez kaydı.

    Miktar işareti: giriş pozitif, çıkış negatif.
    """

    class Type(models.TextChoices):
        PURCHASE = "purchase", _("Satın alma girişi")
        SALE = "sale", _("Satış (reçete düşümü)")
        WASTE = "waste", _("Fire / israf")
        ADJUSTMENT = "adjustment", _("Sayım düzeltmesi")
        TRANSFER_IN = "transfer_in", _("Depo transferi (giriş)")
        TRANSFER_OUT = "transfer_out", _("Depo transferi (çıkış)")
        RETURN = "return", _("Tedarikçiye iade")
        PRODUCTION = "production", _("Üretim tüketimi")
        VOID_RESTOCK = "void_restock", _("İptal / iade geri yükleme")
        OPENING = "opening", _("Açılış stoğu")

    ingredient = models.ForeignKey(
        Ingredient, verbose_name=_("malzeme"), on_delete=models.PROTECT, related_name="movements"
    )
    warehouse = models.ForeignKey(
        Warehouse, verbose_name=_("depo"), on_delete=models.PROTECT, related_name="movements"
    )
    batch = models.ForeignKey(
        StockBatch,
        verbose_name=_("parti"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="movements",
    )
    movement_type = models.CharField(
        _("hareket türü"), max_length=16, choices=Type.choices, db_index=True
    )
    quantity = models.DecimalField(
        _("miktar"),
        max_digits=16,
        decimal_places=3,
        help_text=_("Temel birimde. Çıkışlar negatiftir."),
    )
    unit_cost = models.DecimalField(
        _("birim maliyet"), max_digits=14, decimal_places=4, default=Decimal("0.0000")
    )
    balance_after = models.DecimalField(
        _("işlem sonrası bakiye"), max_digits=16, decimal_places=3, default=Decimal("0.000")
    )
    reference_type = models.CharField(_("kaynak türü"), max_length=60, blank=True)
    reference_id = models.CharField(_("kaynak kimliği"), max_length=64, blank=True, db_index=True)
    note = models.CharField(_("not"), max_length=300, blank=True)

    class Meta:
        verbose_name = _("Stok hareketi")
        verbose_name_plural = _("Stok hareketleri")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["ingredient", "-created_at"]),
            models.Index(fields=["movement_type", "-created_at"]),
            models.Index(fields=["reference_type", "reference_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.get_movement_type_display()} {self.ingredient.name} {self.quantity}"

    @property
    def value(self) -> Decimal:
        return money(abs(self.quantity) * self.unit_cost)


class Supplier(SoftDeleteModel):
    name = models.CharField(_("ad"), max_length=200, unique=True)
    contact_name = models.CharField(_("yetkili"), max_length=120, blank=True)
    phone = models.CharField(_("telefon"), max_length=20, blank=True)
    email = models.EmailField(_("e-posta"), blank=True)
    address = models.TextField(_("adres"), blank=True)
    tax_number = models.CharField(_("vergi no"), max_length=20, blank=True)
    payment_terms_days = models.PositiveIntegerField(_("vade (gün)"), default=0)
    lead_time_days = models.PositiveIntegerField(_("teslim süresi (gün)"), default=1)
    rating = models.PositiveSmallIntegerField(
        _("değerlendirme"), default=3, help_text=_("1-5 arası")
    )
    is_active = models.BooleanField(_("aktif"), default=True)
    notes = models.TextField(_("notlar"), blank=True)

    class Meta:
        verbose_name = _("Tedarikçi")
        verbose_name_plural = _("Tedarikçiler")
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class SupplierPrice(TimeStampedModel):
    """Tedarikçi-malzeme fiyat listesi ve geçmişi."""

    supplier = models.ForeignKey(
        Supplier, verbose_name=_("tedarikçi"), on_delete=models.CASCADE, related_name="prices"
    )
    ingredient = models.ForeignKey(
        Ingredient,
        verbose_name=_("malzeme"),
        on_delete=models.CASCADE,
        related_name="supplier_prices",
    )
    unit = models.ForeignKey(UnitOfMeasure, verbose_name=_("birim"), on_delete=models.PROTECT)
    price = models.DecimalField(_("birim fiyat"), max_digits=12, decimal_places=4)
    minimum_order_quantity = models.DecimalField(
        _("asgari sipariş"), max_digits=12, decimal_places=3, default=Decimal("0.000")
    )
    valid_from = models.DateField(_("geçerlilik başlangıcı"), default=timezone.localdate)
    is_active = models.BooleanField(_("aktif"), default=True)

    class Meta:
        verbose_name = _("Tedarikçi fiyatı")
        verbose_name_plural = _("Tedarikçi fiyatları")
        ordering = ["-valid_from"]

    def __str__(self) -> str:
        return f"{self.supplier.name} · {self.ingredient.name}: {self.price}"

    @property
    def base_unit_price(self) -> Decimal:
        """Temel birim başına fiyat."""
        return money(safe_divide(self.price, self.unit.factor_to_base))


class PurchaseOrder(SoftDeleteModel):
    """Satın alma talebi / siparişi."""

    class Status(models.TextChoices):
        DRAFT = "draft", _("Taslak")
        REQUESTED = "requested", _("Talep edildi")
        APPROVED = "approved", _("Onaylandı")
        ORDERED = "ordered", _("Sipariş verildi")
        PARTIAL = "partial", _("Kısmi teslim")
        RECEIVED = "received", _("Teslim alındı")
        CANCELLED = "cancelled", _("İptal")

    number = models.CharField(_("belge no"), max_length=32, unique=True, db_index=True)
    supplier = models.ForeignKey(
        Supplier,
        verbose_name=_("tedarikçi"),
        on_delete=models.PROTECT,
        related_name="purchase_orders",
    )
    warehouse = models.ForeignKey(
        Warehouse,
        verbose_name=_("teslim deposu"),
        on_delete=models.PROTECT,
        related_name="purchase_orders",
    )
    status = models.CharField(
        _("durum"), max_length=12, choices=Status.choices, default=Status.DRAFT, db_index=True
    )
    expected_date = models.DateField(_("beklenen teslim"), null=True, blank=True)
    received_at = models.DateTimeField(_("teslim zamanı"), null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("onaylayan"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_purchase_orders",
    )
    approved_at = models.DateTimeField(_("onay zamanı"), null=True, blank=True)
    invoice_number = models.CharField(_("fatura no"), max_length=60, blank=True)
    notes = models.TextField(_("notlar"), blank=True)

    class Meta:
        verbose_name = _("Satın alma siparişi")
        verbose_name_plural = _("Satın alma siparişleri")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.number} · {self.supplier.name}"

    def save(self, *args, **kwargs):
        if not self.number:
            from apps.core.utils import daily_sequence_number

            self.number = daily_sequence_number(PurchaseOrder, "number", "SA-")
        super().save(*args, **kwargs)

    @property
    def subtotal(self) -> Decimal:
        return money(sum((line.line_total for line in self.lines.all()), Decimal("0.00")))

    @property
    def tax_total(self) -> Decimal:
        return money(sum((line.tax_amount for line in self.lines.all()), Decimal("0.00")))

    @property
    def grand_total(self) -> Decimal:
        return money(self.subtotal + self.tax_total)

    @property
    def is_editable(self) -> bool:
        return self.status in {self.Status.DRAFT, self.Status.REQUESTED}


class PurchaseOrderLine(models.Model):
    order = models.ForeignKey(
        PurchaseOrder, verbose_name=_("sipariş"), on_delete=models.CASCADE, related_name="lines"
    )
    ingredient = models.ForeignKey(
        Ingredient,
        verbose_name=_("malzeme"),
        on_delete=models.PROTECT,
        related_name="purchase_lines",
    )
    unit = models.ForeignKey(UnitOfMeasure, verbose_name=_("birim"), on_delete=models.PROTECT)
    quantity = models.DecimalField(
        _("miktar"), max_digits=14, decimal_places=3, validators=[MinValueValidator(Decimal("0"))]
    )
    received_quantity = models.DecimalField(
        _("teslim alınan"), max_digits=14, decimal_places=3, default=Decimal("0.000")
    )
    unit_price = models.DecimalField(_("birim fiyat"), max_digits=12, decimal_places=4)
    tax_rate = models.DecimalField(
        _("KDV (%)"), max_digits=5, decimal_places=2, default=Decimal("10.00")
    )
    expiry_date = models.DateField(_("son kullanma"), null=True, blank=True)
    lot_code = models.CharField(_("parti kodu"), max_length=60, blank=True)

    class Meta:
        verbose_name = _("Satın alma satırı")
        verbose_name_plural = _("Satın alma satırları")

    def __str__(self) -> str:
        return f"{self.ingredient.name} x {self.quantity} {self.unit.code}"

    @property
    def line_total(self) -> Decimal:
        return money(self.quantity * self.unit_price)

    @property
    def tax_amount(self) -> Decimal:
        return money(self.line_total * self.tax_rate / Decimal("100"))

    @property
    def base_quantity(self) -> Decimal:
        return self.unit.to_base(self.quantity)

    @property
    def base_unit_cost(self) -> Decimal:
        return money(safe_divide(self.unit_price, self.unit.factor_to_base))

    @property
    def is_fully_received(self) -> bool:
        return self.received_quantity >= self.quantity


class StockCount(TimeStampedModel):
    """Fiziksel stok sayımı."""

    class Status(models.TextChoices):
        OPEN = "open", _("Devam ediyor")
        APPLIED = "applied", _("Uygulandı")
        CANCELLED = "cancelled", _("İptal")

    number = models.CharField(_("sayım no"), max_length=32, unique=True)
    warehouse = models.ForeignKey(
        Warehouse, verbose_name=_("depo"), on_delete=models.PROTECT, related_name="counts"
    )
    status = models.CharField(
        _("durum"), max_length=10, choices=Status.choices, default=Status.OPEN
    )
    counted_at = models.DateTimeField(_("sayım zamanı"), default=timezone.now)
    applied_at = models.DateTimeField(_("uygulanma zamanı"), null=True, blank=True)
    notes = models.TextField(_("notlar"), blank=True)

    class Meta:
        verbose_name = _("Stok sayımı")
        verbose_name_plural = _("Stok sayımları")
        ordering = ["-counted_at"]

    def __str__(self) -> str:
        return f"{self.number} · {self.warehouse.name}"

    def save(self, *args, **kwargs):
        if not self.number:
            from apps.core.utils import daily_sequence_number

            self.number = daily_sequence_number(StockCount, "number", "SAY-")
        super().save(*args, **kwargs)

    @property
    def total_variance_value(self) -> Decimal:
        return money(sum((line.variance_value for line in self.lines.all()), Decimal("0.00")))


class StockCountLine(models.Model):
    count = models.ForeignKey(
        StockCount, verbose_name=_("sayım"), on_delete=models.CASCADE, related_name="lines"
    )
    ingredient = models.ForeignKey(
        Ingredient, verbose_name=_("malzeme"), on_delete=models.PROTECT, related_name="count_lines"
    )
    expected_quantity = models.DecimalField(
        _("sistem miktarı"), max_digits=16, decimal_places=3, default=Decimal("0.000")
    )
    counted_quantity = models.DecimalField(
        _("sayılan miktar"), max_digits=16, decimal_places=3, default=Decimal("0.000")
    )
    note = models.CharField(_("not"), max_length=200, blank=True)

    class Meta:
        verbose_name = _("Sayım satırı")
        verbose_name_plural = _("Sayım satırları")
        constraints = [
            models.UniqueConstraint(
                fields=["count", "ingredient"], name="uniq_ingredient_per_count"
            )
        ]

    def __str__(self) -> str:
        return f"{self.ingredient.name}: {self.counted_quantity}"

    @property
    def variance(self) -> Decimal:
        return q3(self.counted_quantity - self.expected_quantity)

    @property
    def variance_value(self) -> Decimal:
        return money(self.variance * self.ingredient.average_cost)


class WasteRecord(TimeStampedModel):
    """Fire, bozulma ve israf kaydı."""

    class Reason(models.TextChoices):
        EXPIRED = "expired", _("Son kullanma tarihi geçti")
        SPOILED = "spoiled", _("Bozulma")
        BROKEN = "broken", _("Kırılma / dökülme")
        PREP_ERROR = "prep_error", _("Hazırlık hatası")
        CUSTOMER_RETURN = "customer_return", _("Müşteri iadesi")
        OVERPRODUCTION = "overproduction", _("Fazla üretim")
        THEFT = "theft", _("Kayıp / hırsızlık şüphesi")
        OTHER = "other", _("Diğer")

    ingredient = models.ForeignKey(
        Ingredient,
        verbose_name=_("malzeme"),
        on_delete=models.PROTECT,
        related_name="waste_records",
    )
    warehouse = models.ForeignKey(
        Warehouse, verbose_name=_("depo"), on_delete=models.PROTECT, related_name="waste_records"
    )
    quantity = models.DecimalField(
        _("miktar"), max_digits=14, decimal_places=3, validators=[MinValueValidator(Decimal("0"))]
    )
    reason = models.CharField(_("neden"), max_length=20, choices=Reason.choices)
    cost_value = models.DecimalField(
        _("maliyet tutarı"), max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    occurred_at = models.DateTimeField(_("oluşma zamanı"), default=timezone.now, db_index=True)
    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("bildiren"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="waste_reports",
    )
    note = models.CharField(_("açıklama"), max_length=300, blank=True)

    class Meta:
        verbose_name = _("Fire kaydı")
        verbose_name_plural = _("Fire kayıtları")
        ordering = ["-occurred_at"]
        indexes = [models.Index(fields=["-occurred_at", "reason"])]

    def __str__(self) -> str:
        return f"{self.ingredient.name} {self.quantity} · {self.get_reason_display()}"
