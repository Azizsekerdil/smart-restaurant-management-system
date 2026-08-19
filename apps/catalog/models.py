"""Menü modelleri: kategori, ürün, porsiyon, seçenek, alerjen, reçete.

Fiyatlandırma yaklaşımı
-----------------------
Ürün fiyatı **KDV dahil** saklanır (Türkiye'de menü fiyatları böyle
gösterilir). Vergi tutarı, satır toplamından geriye doğru hesaplanır:

    kdv = brut * oran / (100 + oran)

Bu, "menüde 100 ₺ yazan ürün kasada 100 ₺" davranışını garanti eder.
"""

from __future__ import annotations

from datetime import time
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import SoftDeleteModel, TimeStampedModel
from apps.core.utils import money, safe_divide, slugify_tr


class Allergen(models.Model):
    """AB 1169/2011 ve Türk Gıda Kodeksi'ne uyumlu alerjen listesi."""

    code = models.SlugField(_("kod"), max_length=40, unique=True)
    name = models.CharField(_("ad"), max_length=100)
    icon = models.CharField(_("ikon"), max_length=40, blank=True)
    description = models.CharField(_("açıklama"), max_length=300, blank=True)

    class Meta:
        verbose_name = _("Alerjen")
        verbose_name_plural = _("Alerjenler")
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Category(TimeStampedModel):
    """Menü kategorisi (alt kategori desteklidir)."""

    name = models.CharField(_("ad"), max_length=120)
    slug = models.SlugField(_("kısa ad"), max_length=140, unique=True, blank=True)
    parent = models.ForeignKey(
        "self",
        verbose_name=_("üst kategori"),
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="children",
    )
    description = models.CharField(_("açıklama"), max_length=300, blank=True)
    color = models.CharField(
        _("renk"),
        max_length=7,
        default="#0d6efd",
        help_text=_("POS ekranındaki kategori rengi (#RRGGBB)."),
    )
    icon = models.CharField(_("ikon"), max_length=40, blank=True)
    image = models.ImageField(_("görsel"), upload_to="categories/", blank=True, null=True)
    sort_order = models.PositiveIntegerField(_("sıra"), default=100)
    is_active = models.BooleanField(_("aktif"), default=True, db_index=True)

    class Meta:
        verbose_name = _("Kategori")
        verbose_name_plural = _("Kategoriler")
        ordering = ["sort_order", "name"]
        indexes = [models.Index(fields=["is_active", "sort_order"])]

    def __str__(self) -> str:
        return f"{self.parent.name} / {self.name}" if self.parent_id else self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify_tr(self.name)[:140]
        super().save(*args, **kwargs)

    @property
    def full_path(self) -> str:
        return str(self)


class Product(SoftDeleteModel):
    """Menüdeki satılabilir ürün."""

    class Kind(models.TextChoices):
        FOOD = "food", _("Yemek")
        DRINK = "drink", _("İçecek")
        ALCOHOL = "alcohol", _("Alkollü içecek")
        DESSERT = "dessert", _("Tatlı")
        COMBO = "combo", _("Menü / kombinasyon")
        OTHER = "other", _("Diğer")

    name = models.CharField(_("ad"), max_length=160, db_index=True)
    slug = models.SlugField(_("kısa ad"), max_length=180, unique=True, blank=True)
    sku = models.CharField(_("stok kodu"), max_length=40, unique=True, blank=True, null=True)
    barcode = models.CharField(_("barkod"), max_length=64, blank=True, db_index=True)
    category = models.ForeignKey(
        Category, verbose_name=_("kategori"), on_delete=models.PROTECT, related_name="products"
    )
    kind = models.CharField(_("tür"), max_length=10, choices=Kind.choices, default=Kind.FOOD)

    description = models.TextField(_("açıklama"), blank=True)
    ai_description = models.TextField(
        _("AI menü açıklaması"),
        blank=True,
        help_text=_("Yapay zekâ tarafından önerilen açıklama; onaylanıp kullanılabilir."),
    )
    image = models.ImageField(_("görsel"), upload_to="products/", blank=True, null=True)

    price = models.DecimalField(
        _("satış fiyatı (KDV dahil)"),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )
    tax_rate = models.DecimalField(
        _("KDV oranı (%)"), max_digits=5, decimal_places=2, default=Decimal("10.00")
    )

    preparation_minutes = models.PositiveIntegerField(_("hazırlık süresi (dk)"), default=10)
    station = models.ForeignKey(
        "kitchen.Station",
        verbose_name=_("hazırlık istasyonu"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="products",
    )

    allergens = models.ManyToManyField(
        Allergen, verbose_name=_("alerjenler"), blank=True, related_name="products"
    )
    calories = models.PositiveIntegerField(_("kalori (kcal)"), null=True, blank=True)
    protein_g = models.DecimalField(
        _("protein (g)"), max_digits=6, decimal_places=1, null=True, blank=True
    )
    carbs_g = models.DecimalField(
        _("karbonhidrat (g)"), max_digits=6, decimal_places=1, null=True, blank=True
    )
    fat_g = models.DecimalField(_("yağ (g)"), max_digits=6, decimal_places=1, null=True, blank=True)

    is_active = models.BooleanField(_("aktif"), default=True, db_index=True)
    is_available = models.BooleanField(
        _("satışa açık"),
        default=True,
        db_index=True,
        help_text=_("Stok tükendiğinde otomatik olarak kapatılabilir."),
    )
    auto_disable_on_stockout = models.BooleanField(_("stok bitince otomatik kapat"), default=True)
    unavailable_reason = models.CharField(_("kapatılma nedeni"), max_length=200, blank=True)

    is_featured = models.BooleanField(_("öne çıkan"), default=False)
    sort_order = models.PositiveIntegerField(_("sıra"), default=100)
    color = models.CharField(_("POS rengi"), max_length=7, blank=True)

    class Meta:
        verbose_name = _("Ürün")
        verbose_name_plural = _("Ürünler")
        ordering = ["category__sort_order", "sort_order", "name"]
        indexes = [
            models.Index(fields=["is_active", "is_available"]),
            models.Index(fields=["category", "sort_order"]),
        ]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify_tr(self.name)[:170]
            slug, counter = base, 1
            while Product.all_objects.filter(slug=slug).exclude(pk=self.pk).exists():
                counter += 1
                slug = f"{base}-{counter}"
            self.slug = slug
        if self.sku == "":
            self.sku = None
        super().save(*args, **kwargs)

    # ---------------------------------------------------------- vergi
    @property
    def tax_amount(self) -> Decimal:
        """KDV dahil fiyattan geri hesaplanan vergi tutarı."""
        rate = Decimal(self.tax_rate or 0)
        return money(self.price * rate / (Decimal("100") + rate)) if rate else Decimal("0.00")

    @property
    def net_price(self) -> Decimal:
        return money(self.price - self.tax_amount)

    # ------------------------------------------------------- maliyet
    @property
    def recipe_cost(self) -> Decimal:
        """Reçeteye göre birim maliyet. Reçete yoksa 0."""
        recipe = getattr(self, "recipe", None)
        return recipe.total_cost if recipe else Decimal("0.00")

    @property
    def gross_profit(self) -> Decimal:
        return money(self.net_price - self.recipe_cost)

    @property
    def margin_percent(self) -> Decimal:
        """Kâr marjı = (net fiyat - maliyet) / net fiyat * 100."""
        if not self.net_price:
            return Decimal("0.00")
        return money(safe_divide(self.gross_profit * 100, self.net_price))

    @property
    def food_cost_percent(self) -> Decimal:
        """Maliyet oranı: sektörde 25-35% hedeflenir."""
        if not self.net_price:
            return Decimal("0.00")
        return money(safe_divide(self.recipe_cost * 100, self.net_price))

    @property
    def allergen_names(self) -> str:
        return ", ".join(a.name for a in self.allergens.all())

    def available_now(self, at: time | None = None) -> bool:
        """Ürün şu an (veya verilen saatte) satılabilir mi?"""
        if not (self.is_active and self.is_available):
            return False
        schedules = list(self.schedules.filter(is_active=True))
        if not schedules:
            return True
        from django.utils import timezone

        now = at or timezone.localtime().time()
        weekday = timezone.localdate().weekday()
        return any(s.covers(now, weekday) for s in schedules)


class ProductVariant(TimeStampedModel):
    """Porsiyon / boy seçeneği (ör. Küçük, Orta, Büyük)."""

    product = models.ForeignKey(
        Product, verbose_name=_("ürün"), on_delete=models.CASCADE, related_name="variants"
    )
    name = models.CharField(_("ad"), max_length=80)
    price_delta = models.DecimalField(
        _("fiyat farkı"),
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text=_("Ürün fiyatına eklenecek tutar (negatif olabilir)."),
    )
    recipe_multiplier = models.DecimalField(
        _("reçete katsayısı"),
        max_digits=6,
        decimal_places=3,
        default=Decimal("1.000"),
        help_text=_("Stok düşerken reçete miktarları bu katsayıyla çarpılır."),
    )
    is_default = models.BooleanField(_("varsayılan"), default=False)
    is_active = models.BooleanField(_("aktif"), default=True)
    sort_order = models.PositiveIntegerField(_("sıra"), default=100)

    class Meta:
        verbose_name = _("Porsiyon")
        verbose_name_plural = _("Porsiyonlar")
        ordering = ["sort_order", "name"]
        constraints = [
            models.UniqueConstraint(fields=["product", "name"], name="uniq_variant_per_product")
        ]

    def __str__(self) -> str:
        return f"{self.product.name} · {self.name}"

    @property
    def price(self) -> Decimal:
        return money(self.product.price + self.price_delta)


class ModifierGroup(TimeStampedModel):
    """Seçenek grubu (ör. 'Pişirme derecesi', 'Ekstra malzeme')."""

    name = models.CharField(_("ad"), max_length=120)
    description = models.CharField(_("açıklama"), max_length=200, blank=True)
    min_select = models.PositiveSmallIntegerField(_("en az seçim"), default=0)
    max_select = models.PositiveSmallIntegerField(
        _("en çok seçim"), default=1, help_text=_("0 = sınırsız")
    )
    is_required = models.BooleanField(_("zorunlu"), default=False)
    sort_order = models.PositiveIntegerField(_("sıra"), default=100)
    products = models.ManyToManyField(
        Product, verbose_name=_("ürünler"), blank=True, related_name="modifier_groups"
    )

    class Meta:
        verbose_name = _("Seçenek grubu")
        verbose_name_plural = _("Seçenek grupları")
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        return self.name


class Modifier(TimeStampedModel):
    """Seçenek grubundaki tek bir seçenek (ör. 'Ekstra peynir +25 ₺')."""

    group = models.ForeignKey(
        ModifierGroup, verbose_name=_("grup"), on_delete=models.CASCADE, related_name="options"
    )
    name = models.CharField(_("ad"), max_length=120)
    price_delta = models.DecimalField(
        _("fiyat farkı"), max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    ingredient = models.ForeignKey(
        "inventory.Ingredient",
        verbose_name=_("bağlı malzeme"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="modifiers",
        help_text=_("Seçildiğinde stoktan düşülecek malzeme."),
    )
    ingredient_quantity = models.DecimalField(
        _("malzeme miktarı"), max_digits=10, decimal_places=3, default=Decimal("0.000")
    )
    is_active = models.BooleanField(_("aktif"), default=True)
    sort_order = models.PositiveIntegerField(_("sıra"), default=100)

    class Meta:
        verbose_name = _("Seçenek")
        verbose_name_plural = _("Seçenekler")
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        sign = "+" if self.price_delta >= 0 else ""
        return f"{self.name} ({sign}{self.price_delta})"


class Recipe(TimeStampedModel):
    """Ürünün malzeme reçetesi (maliyet ve otomatik stok düşümü için)."""

    product = models.OneToOneField(
        Product, verbose_name=_("ürün"), on_delete=models.CASCADE, related_name="recipe"
    )
    yield_quantity = models.DecimalField(
        _("verim (porsiyon)"),
        max_digits=8,
        decimal_places=3,
        default=Decimal("1.000"),
        help_text=_("Bu reçete kaç porsiyon üretir?"),
    )
    preparation_notes = models.TextField(_("hazırlık notları"), blank=True)
    labor_cost = models.DecimalField(
        _("işçilik maliyeti"), max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    overhead_cost = models.DecimalField(
        _("genel gider payı"), max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    is_active = models.BooleanField(_("aktif"), default=True)

    class Meta:
        verbose_name = _("Reçete")
        verbose_name_plural = _("Reçeteler")

    def __str__(self) -> str:
        return f"{self.product.name} reçetesi"

    @property
    def ingredient_cost(self) -> Decimal:
        return money(sum((item.line_cost for item in self.items.all()), Decimal("0.00")))

    @property
    def total_cost(self) -> Decimal:
        """Porsiyon başına toplam maliyet."""
        gross = self.ingredient_cost + self.labor_cost + self.overhead_cost
        return money(safe_divide(gross, self.yield_quantity or 1))

    def missing_ingredients(self, portions: Decimal = Decimal("1")) -> list[dict]:
        """Bu reçeteyi `portions` kez üretmek için eksik malzemeleri döndürür."""
        missing = []
        for item in self.items.select_related("ingredient"):
            needed = item.quantity * portions / (self.yield_quantity or 1)
            on_hand = item.ingredient.total_on_hand
            if on_hand < needed:
                missing.append(
                    {
                        "ingredient": item.ingredient,
                        "needed": needed,
                        "on_hand": on_hand,
                        "shortage": needed - on_hand,
                    }
                )
        return missing


class RecipeItem(models.Model):
    """Reçetedeki tek bir malzeme satırı."""

    recipe = models.ForeignKey(
        Recipe, verbose_name=_("reçete"), on_delete=models.CASCADE, related_name="items"
    )
    ingredient = models.ForeignKey(
        "inventory.Ingredient",
        verbose_name=_("malzeme"),
        on_delete=models.PROTECT,
        related_name="recipe_items",
    )
    quantity = models.DecimalField(
        _("miktar"),
        max_digits=12,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0"))],
    )
    unit = models.ForeignKey(
        "inventory.UnitOfMeasure",
        verbose_name=_("birim"),
        on_delete=models.PROTECT,
        related_name="recipe_items",
    )
    waste_percent = models.DecimalField(
        _("fire oranı (%)"),
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text=_("Hazırlık sırasındaki kayıp (soyma, temizleme vb.)."),
    )
    is_optional = models.BooleanField(_("isteğe bağlı"), default=False)
    note = models.CharField(_("not"), max_length=200, blank=True)

    class Meta:
        verbose_name = _("Reçete malzemesi")
        verbose_name_plural = _("Reçete malzemeleri")
        ordering = ["ingredient__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["recipe", "ingredient"], name="uniq_ingredient_per_recipe"
            )
        ]

    def __str__(self) -> str:
        return f"{self.ingredient.name}: {self.quantity} {self.unit.code}"

    @property
    def effective_quantity(self) -> Decimal:
        """Fire dahil, stoktan düşülecek gerçek miktar."""
        factor = Decimal("1") + (self.waste_percent / Decimal("100"))
        return self.quantity * factor

    @property
    def base_quantity(self) -> Decimal:
        """Malzemenin temel birimine çevrilmiş miktar."""
        return self.unit.to_base(self.effective_quantity)

    @property
    def line_cost(self) -> Decimal:
        return money(self.base_quantity * self.ingredient.average_cost)


class MenuSchedule(TimeStampedModel):
    """Zaman aralığına göre menü (kahvaltı, öğle menüsü, happy hour)."""

    WEEKDAYS = [
        (0, _("Pazartesi")),
        (1, _("Salı")),
        (2, _("Çarşamba")),
        (3, _("Perşembe")),
        (4, _("Cuma")),
        (5, _("Cumartesi")),
        (6, _("Pazar")),
    ]

    name = models.CharField(_("ad"), max_length=120)
    products = models.ManyToManyField(
        Product, verbose_name=_("ürünler"), blank=True, related_name="schedules"
    )
    categories = models.ManyToManyField(
        Category, verbose_name=_("kategoriler"), blank=True, related_name="schedules"
    )
    start_time = models.TimeField(_("başlangıç saati"), default=time(0, 0))
    end_time = models.TimeField(_("bitiş saati"), default=time(23, 59))
    weekdays = models.JSONField(
        _("günler"),
        default=list,
        blank=True,
        help_text=_("Boş = her gün. Örnek: [0,1,2,3,4]"),
    )
    is_active = models.BooleanField(_("aktif"), default=True)

    class Meta:
        verbose_name = _("Menü zaman planı")
        verbose_name_plural = _("Menü zaman planları")
        ordering = ["start_time"]

    def __str__(self) -> str:
        return f"{self.name} ({self.start_time:%H:%M}-{self.end_time:%H:%M})"

    def covers(self, at: time, weekday: int) -> bool:
        if self.weekdays and weekday not in self.weekdays:
            return False
        if self.start_time <= self.end_time:
            return self.start_time <= at <= self.end_time
        # Gece yarısını aşan aralık (ör. 22:00 - 02:00)
        return at >= self.start_time or at <= self.end_time


class PriceHistory(models.Model):
    """Ürün fiyat değişiklik geçmişi (kârlılık analizi ve denetim için)."""

    product = models.ForeignKey(
        Product, verbose_name=_("ürün"), on_delete=models.CASCADE, related_name="price_history"
    )
    old_price = models.DecimalField(_("eski fiyat"), max_digits=10, decimal_places=2)
    new_price = models.DecimalField(_("yeni fiyat"), max_digits=10, decimal_places=2)
    changed_at = models.DateTimeField(_("değişim zamanı"), auto_now_add=True, db_index=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("değiştiren"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    reason = models.CharField(_("gerekçe"), max_length=200, blank=True)

    class Meta:
        verbose_name = _("Fiyat geçmişi")
        verbose_name_plural = _("Fiyat geçmişi")
        ordering = ["-changed_at"]

    def __str__(self) -> str:
        return f"{self.product.name}: {self.old_price} -> {self.new_price}"
