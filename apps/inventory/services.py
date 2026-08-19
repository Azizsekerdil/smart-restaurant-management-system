"""Stok servisleri: giriş, çıkış, FIFO/FEFO tüketim, reçete düşümü.

Tüm stok değişiklikleri bu modül üzerinden yapılmalıdır. Doğrudan
`StockItem.quantity` güncellemek hareket kaydı bırakmayacağı için
yasaktır.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.core.models import Notification
from apps.core.services import notify
from apps.core.utils import money
from apps.core.utils import quantity as q3
from apps.inventory.models import (
    Ingredient,
    StockBatch,
    StockItem,
    StockMovement,
    Warehouse,
    WasteRecord,
)

logger = logging.getLogger("apps.inventory")


class InsufficientStock(Exception):
    """Yeterli stok yok ve negatife düşmeye izin verilmedi."""

    def __init__(self, ingredient: Ingredient, requested: Decimal, available: Decimal):
        self.ingredient = ingredient
        self.requested = requested
        self.available = available
        super().__init__(
            f"'{ingredient.name}' için yeterli stok yok. "
            f"İstenen: {requested} {ingredient.base_unit.code}, "
            f"mevcut: {available} {ingredient.base_unit.code}."
        )


@dataclass
class ConsumptionResult:
    """Bir tüketim işleminin sonucu."""

    ingredient: Ingredient
    consumed: Decimal = Decimal("0.000")
    cost: Decimal = Decimal("0.00")
    shortfall: Decimal = Decimal("0.000")
    batches_used: list[tuple[int, Decimal]] = field(default_factory=list)


def _get_or_create_stock_item(ingredient: Ingredient, warehouse: Warehouse) -> StockItem:
    item, _created = StockItem.objects.select_for_update().get_or_create(
        ingredient=ingredient, warehouse=warehouse, defaults={"quantity": Decimal("0.000")}
    )
    return item


@transaction.atomic
def receive_stock(
    ingredient: Ingredient,
    warehouse: Warehouse,
    quantity: Decimal,
    unit_cost: Decimal,
    *,
    movement_type: str = StockMovement.Type.PURCHASE,
    expiry_date=None,
    lot_code: str = "",
    supplier=None,
    reference_type: str = "",
    reference_id: str = "",
    note: str = "",
    user=None,
) -> StockBatch:
    """Depoya stok girişi yapar ve yeni bir parti oluşturur.

    `quantity` ve `unit_cost` malzemenin **temel biriminde** olmalıdır.
    """
    quantity = q3(quantity)
    if quantity <= 0:
        raise ValueError("Giriş miktarı sıfırdan büyük olmalıdır.")

    if expiry_date is None and ingredient.is_perishable and ingredient.shelf_life_days:
        expiry_date = timezone.localdate() + timedelta(days=ingredient.shelf_life_days)

    batch = StockBatch.objects.create(
        ingredient=ingredient,
        warehouse=warehouse,
        lot_code=lot_code,
        initial_quantity=quantity,
        remaining_quantity=quantity,
        unit_cost=Decimal(str(unit_cost)),
        expiry_date=expiry_date,
        supplier=supplier,
        created_by=user,
    )

    item = _get_or_create_stock_item(ingredient, warehouse)
    StockItem.objects.filter(pk=item.pk).update(quantity=F("quantity") + quantity)
    item.refresh_from_db(fields=["quantity"])

    StockMovement.objects.create(
        ingredient=ingredient,
        warehouse=warehouse,
        batch=batch,
        movement_type=movement_type,
        quantity=quantity,
        unit_cost=Decimal(str(unit_cost)),
        balance_after=item.quantity,
        reference_type=reference_type,
        reference_id=str(reference_id or ""),
        note=note[:300],
        created_by=user,
    )

    # Stok geri geldiyse, otomatik kapatılmış ürünleri tekrar açmayı dene.
    _reopen_products_for(ingredient)
    return batch


@transaction.atomic
def consume_stock(
    ingredient: Ingredient,
    warehouse: Warehouse,
    quantity: Decimal,
    *,
    movement_type: str = StockMovement.Type.SALE,
    reference_type: str = "",
    reference_id: str = "",
    note: str = "",
    user=None,
    allow_negative: bool = True,
) -> ConsumptionResult:
    """Stoktan düşer; partileri FIFO veya FEFO sırasına göre tüketir.

    `allow_negative=True` iken (POS için varsayılan) stok yetmese bile
    satış engellenmez; eksik kalan miktar `shortfall` olarak raporlanır ve
    hareket kaydı yine oluşturulur. Bu, gerçek restoran işleyişinde stok
    kaydı gecikmelerinin satışı durdurmaması içindir.
    """
    quantity = q3(quantity)
    result = ConsumptionResult(ingredient=ingredient)
    if quantity <= 0:
        return result

    available = ingredient.on_hand_at(warehouse)
    if quantity > available and not allow_negative:
        raise InsufficientStock(ingredient, quantity, available)

    order_fields = (
        ["expiry_date", "received_at"]
        if ingredient.rotation == Ingredient.Rotation.FEFO
        else ["received_at"]
    )
    batches = list(
        StockBatch.objects.select_for_update()
        .filter(ingredient=ingredient, warehouse=warehouse, remaining_quantity__gt=0)
        .order_by(*order_fields)
    )

    remaining = quantity
    total_cost = Decimal("0.00")
    for batch in batches:
        if remaining <= 0:
            break
        take = min(batch.remaining_quantity, remaining)
        batch.remaining_quantity = q3(batch.remaining_quantity - take)
        batch.save(update_fields=["remaining_quantity", "updated_at"])
        total_cost += take * batch.unit_cost
        result.batches_used.append((batch.pk, take))
        remaining = q3(remaining - take)

    result.shortfall = remaining if remaining > 0 else Decimal("0.000")
    result.consumed = q3(quantity - result.shortfall)

    # Parti bulunamayan kısım için son bilinen maliyeti kullan.
    if result.shortfall > 0:
        total_cost += result.shortfall * ingredient.average_cost
        logger.warning(
            "Stok yetersiz: %s için %s eksik (%s)",
            ingredient.name,
            result.shortfall,
            reference_type,
        )

    result.cost = money(total_cost)

    item = _get_or_create_stock_item(ingredient, warehouse)
    StockItem.objects.filter(pk=item.pk).update(quantity=F("quantity") - quantity)
    item.refresh_from_db(fields=["quantity"])

    avg_cost = money(total_cost / quantity) if quantity else Decimal("0.00")
    StockMovement.objects.create(
        ingredient=ingredient,
        warehouse=warehouse,
        batch=None,
        movement_type=movement_type,
        quantity=-quantity,
        unit_cost=avg_cost,
        balance_after=item.quantity,
        reference_type=reference_type,
        reference_id=str(reference_id or ""),
        note=note[:300],
        created_by=user,
    )

    _check_critical_level(ingredient)
    return result


@transaction.atomic
def adjust_stock(
    ingredient: Ingredient,
    warehouse: Warehouse,
    new_quantity: Decimal,
    *,
    note: str = "",
    user=None,
    reference_type: str = "stock_count",
    reference_id: str = "",
) -> StockMovement:
    """Sayım sonucu stoğu mutlak bir değere ayarlar."""
    new_quantity = q3(new_quantity)
    current = ingredient.on_hand_at(warehouse)
    delta = q3(new_quantity - current)

    if delta == 0:
        item = _get_or_create_stock_item(ingredient, warehouse)
        return StockMovement.objects.create(
            ingredient=ingredient,
            warehouse=warehouse,
            movement_type=StockMovement.Type.ADJUSTMENT,
            quantity=Decimal("0.000"),
            unit_cost=ingredient.average_cost,
            balance_after=item.quantity,
            reference_type=reference_type,
            reference_id=str(reference_id or ""),
            note=note[:300] or "Sayım farkı yok.",
            created_by=user,
        )

    if delta > 0:
        batch = receive_stock(
            ingredient,
            warehouse,
            delta,
            ingredient.average_cost,
            movement_type=StockMovement.Type.ADJUSTMENT,
            reference_type=reference_type,
            reference_id=reference_id,
            note=note or "Sayım fazlası",
            user=user,
        )
        return (
            batch.movements.first()
            or StockMovement.objects.filter(ingredient=ingredient, warehouse=warehouse)
            .order_by("-created_at")
            .first()
        )

    consume_stock(
        ingredient,
        warehouse,
        abs(delta),
        movement_type=StockMovement.Type.ADJUSTMENT,
        reference_type=reference_type,
        reference_id=reference_id,
        note=note or "Sayım eksiği",
        user=user,
    )
    return (
        StockMovement.objects.filter(ingredient=ingredient, warehouse=warehouse)
        .order_by("-created_at")
        .first()
    )


@transaction.atomic
def record_waste(
    ingredient: Ingredient,
    warehouse: Warehouse,
    quantity: Decimal,
    reason: str,
    *,
    note: str = "",
    user=None,
) -> WasteRecord:
    """Fire kaydı oluşturur ve stoktan düşer."""
    result = consume_stock(
        ingredient,
        warehouse,
        quantity,
        movement_type=StockMovement.Type.WASTE,
        reference_type="waste",
        note=f"{reason}: {note}"[:300],
        user=user,
    )
    waste = WasteRecord.objects.create(
        ingredient=ingredient,
        warehouse=warehouse,
        quantity=q3(quantity),
        reason=reason,
        cost_value=result.cost,
        reported_by=user,
        note=note[:300],
        created_by=user,
    )
    if result.cost >= Decimal("500"):
        notify(
            f"Yüksek tutarlı fire: {ingredient.name}",
            body=(
                f"{quantity} {ingredient.base_unit.code} · "
                f"{result.cost} tutarında fire kaydedildi. Neden: {waste.get_reason_display()}"
            ),
            level=Notification.Level.WARNING,
            category=Notification.Category.STOCK,
            roles=["owner", "general_manager", "restaurant_manager", "chef"],
        )
    return waste


@transaction.atomic
def transfer_stock(
    ingredient: Ingredient,
    source: Warehouse,
    target: Warehouse,
    quantity: Decimal,
    *,
    note: str = "",
    user=None,
) -> None:
    """Depolar arası transfer."""
    if source.pk == target.pk:
        raise ValueError("Kaynak ve hedef depo aynı olamaz.")
    result = consume_stock(
        ingredient,
        source,
        quantity,
        movement_type=StockMovement.Type.TRANSFER_OUT,
        reference_type="transfer",
        note=f"{target.name} deposuna transfer. {note}"[:300],
        user=user,
        allow_negative=False,
    )
    unit_cost = money(result.cost / quantity) if quantity else Decimal("0.00")
    receive_stock(
        ingredient,
        target,
        quantity,
        unit_cost,
        movement_type=StockMovement.Type.TRANSFER_IN,
        reference_type="transfer",
        note=f"{source.name} deposundan transfer. {note}"[:300],
        user=user,
    )


# ------------------------------------------------------------------
#  Reçeteye göre otomatik stok düşümü
# ------------------------------------------------------------------
@transaction.atomic
def consume_for_order_item(
    order_item, *, user=None, reverse: bool = False
) -> list[ConsumptionResult]:
    """Sipariş satırının reçetesine göre stok düşer (veya iptalde geri yükler).

    Porsiyon katsayısı ve seçilen ekstra malzemeler (modifier) dikkate
    alınır. Reçetesi olmayan ürünlerde sessizce geçilir.
    """
    from apps.catalog.models import Recipe

    warehouse = Warehouse.get_default()
    if warehouse is None:
        logger.error("Varsayılan depo tanımlı değil; stok düşümü atlandı.")
        return []

    results: list[ConsumptionResult] = []
    product = order_item.product
    recipe: Recipe | None = getattr(product, "recipe", None)

    multiplier = Decimal(str(order_item.quantity))
    if order_item.variant_id and order_item.variant:
        multiplier *= order_item.variant.recipe_multiplier

    if recipe and recipe.is_active:
        yield_qty = recipe.yield_quantity or Decimal("1")
        for item in recipe.items.select_related("ingredient", "unit"):
            if item.is_optional:
                continue
            needed = q3(item.base_quantity * multiplier / yield_qty)
            if needed <= 0:
                continue
            results.append(
                _apply(
                    item.ingredient,
                    warehouse,
                    needed,
                    reverse=reverse,
                    reference_id=order_item.pk,
                    note=f"{product.name} x{order_item.quantity}",
                    user=user,
                )
            )

    # Ekstra malzemeler
    for chosen in order_item.modifiers.select_related("modifier__ingredient"):
        modifier = chosen.modifier
        if not modifier or not modifier.ingredient_id or modifier.ingredient_quantity <= 0:
            continue
        needed = q3(modifier.ingredient_quantity * Decimal(str(order_item.quantity)))
        results.append(
            _apply(
                modifier.ingredient,
                warehouse,
                needed,
                reverse=reverse,
                reference_id=order_item.pk,
                note=f"Ekstra: {modifier.name}",
                user=user,
            )
        )

    return results


def _apply(
    ingredient: Ingredient,
    warehouse: Warehouse,
    amount: Decimal,
    *,
    reverse: bool,
    reference_id,
    note: str,
    user,
) -> ConsumptionResult:
    if reverse:
        receive_stock(
            ingredient,
            warehouse,
            amount,
            ingredient.average_cost,
            movement_type=StockMovement.Type.VOID_RESTOCK,
            reference_type="order_item",
            reference_id=reference_id,
            note=f"İptal/iade geri yükleme · {note}",
            user=user,
        )
        return ConsumptionResult(ingredient=ingredient, consumed=-amount)
    return consume_stock(
        ingredient,
        warehouse,
        amount,
        movement_type=StockMovement.Type.SALE,
        reference_type="order_item",
        reference_id=reference_id,
        note=note,
        user=user,
    )


# ------------------------------------------------------------------
#  Uyarılar ve ürün kullanılabilirliği
# ------------------------------------------------------------------
def _check_critical_level(ingredient: Ingredient) -> None:
    """Kritik seviyenin altına düşüldüyse uyarı üretir ve ürünleri kapatır."""
    if ingredient.is_out_of_stock:
        _disable_products_for(ingredient)
        notify(
            f"Stok tükendi: {ingredient.name}",
            body=(
                f"{ingredient.name} stoğu tükendi. Bu malzemeyi kullanan ürünler "
                "otomatik olarak satışa kapatıldı."
            ),
            level=Notification.Level.DANGER,
            category=Notification.Category.STOCK,
            roles=["owner", "general_manager", "restaurant_manager", "chef", "storekeeper"],
            url="/inventory/ingredients/",
            dedupe_key=f"stockout-{ingredient.pk}",
        )
    elif ingredient.is_below_critical:
        days = ingredient.days_until_stockout()
        suffix = f" Tahminî tükenme: ~{days} gün." if days is not None else ""
        notify(
            f"Kritik stok: {ingredient.name}",
            body=(
                f"Kalan: {ingredient.total_on_hand} {ingredient.base_unit.code} "
                f"(kritik seviye: {ingredient.critical_level}).{suffix}"
            ),
            level=Notification.Level.WARNING,
            category=Notification.Category.STOCK,
            roles=["owner", "general_manager", "restaurant_manager", "chef", "storekeeper"],
            url="/inventory/ingredients/",
            dedupe_key=f"critical-{ingredient.pk}",
        )


def _disable_products_for(ingredient: Ingredient) -> int:
    """Malzemesi biten ürünleri satışa kapatır."""
    from apps.catalog.models import Product

    product_ids = list(
        ingredient.recipe_items.filter(is_optional=False).values_list(
            "recipe__product_id", flat=True
        )
    )
    if not product_ids:
        return 0
    return Product.objects.filter(
        pk__in=product_ids, is_available=True, auto_disable_on_stockout=True
    ).update(
        is_available=False,
        unavailable_reason=f"'{ingredient.name}' stoğu tükendi (otomatik).",
    )


def _reopen_products_for(ingredient: Ingredient) -> int:
    """Stok girişi sonrası otomatik kapatılan ürünleri yeniden açar."""
    from apps.catalog.models import Product

    if ingredient.is_out_of_stock:
        return 0
    product_ids = list(
        ingredient.recipe_items.filter(is_optional=False).values_list(
            "recipe__product_id", flat=True
        )
    )
    reopened = 0
    for product in Product.objects.filter(
        pk__in=product_ids, is_available=False, auto_disable_on_stockout=True
    ).select_related("recipe"):
        recipe = getattr(product, "recipe", None)
        if recipe and any(
            item.ingredient.is_out_of_stock
            for item in recipe.items.select_related("ingredient")
            if not item.is_optional
        ):
            continue
        product.is_available = True
        product.unavailable_reason = ""
        product.save(update_fields=["is_available", "unavailable_reason", "updated_at"])
        reopened += 1
    return reopened


def low_stock_report(limit: int | None = None):
    """Kritik seviyedeki malzemeleri döndürür (uyarı paneli için)."""
    items = [
        ing
        for ing in Ingredient.objects.filter(is_active=True).select_related("base_unit")
        if ing.is_below_critical
    ]
    items.sort(key=lambda i: (i.total_on_hand - i.critical_level))
    return items[:limit] if limit else items


def expiring_batches(days: int = 7):
    """Yaklaşan son kullanma tarihleri (FEFO uyarısı)."""
    limit = timezone.localdate() + timedelta(days=days)
    return (
        StockBatch.objects.filter(
            remaining_quantity__gt=0, expiry_date__isnull=False, expiry_date__lte=limit
        )
        .select_related("ingredient", "warehouse", "ingredient__base_unit")
        .order_by("expiry_date")
    )
