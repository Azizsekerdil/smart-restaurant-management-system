"""Stok, FIFO/FEFO tüketimi ve reçeteye göre otomatik düşüm testleri."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.inventory import services as inventory_services
from apps.inventory.models import Ingredient, StockBatch, StockMovement, WasteRecord
from apps.orders import services as order_services

pytestmark = pytest.mark.django_db


def test_receive_stock_creates_batch_and_movement(db, gram, warehouse):
    ingredient = Ingredient.objects.create(name="Şeker", base_unit=gram)
    inventory_services.receive_stock(ingredient, warehouse, Decimal("1000"), Decimal("0.05"))
    assert ingredient.total_on_hand == Decimal("1000.000")
    assert ingredient.batches.count() == 1
    assert ingredient.movements.count() == 1
    assert ingredient.average_cost == Decimal("0.05")


def test_weighted_average_cost(db, gram, warehouse):
    ingredient = Ingredient.objects.create(name="Un", base_unit=gram)
    inventory_services.receive_stock(ingredient, warehouse, Decimal("1000"), Decimal("0.10"))
    inventory_services.receive_stock(ingredient, warehouse, Decimal("1000"), Decimal("0.20"))
    assert ingredient.average_cost == Decimal("0.15")


def test_fifo_consumes_oldest_batch_first(db, gram, warehouse):
    ingredient = Ingredient.objects.create(
        name="Pirinç", base_unit=gram, rotation=Ingredient.Rotation.FIFO
    )
    first = inventory_services.receive_stock(ingredient, warehouse, Decimal("500"), Decimal("0.10"))
    second = inventory_services.receive_stock(
        ingredient, warehouse, Decimal("500"), Decimal("0.30")
    )
    StockBatch.objects.filter(pk=first.pk).update(received_at=timezone.now() - timedelta(days=5))

    result = inventory_services.consume_stock(ingredient, warehouse, Decimal("500"))
    first.refresh_from_db()
    second.refresh_from_db()
    assert first.remaining_quantity == Decimal("0.000")
    assert second.remaining_quantity == Decimal("500.000")
    assert result.cost == Decimal("50.00")  # 500 * 0.10


def test_fefo_consumes_nearest_expiry_first(db, gram, warehouse):
    ingredient = Ingredient.objects.create(
        name="Süt", base_unit=gram, rotation=Ingredient.Rotation.FEFO, is_perishable=True
    )
    later = inventory_services.receive_stock(
        ingredient,
        warehouse,
        Decimal("500"),
        Decimal("0.10"),
        expiry_date=timezone.localdate() + timedelta(days=30),
    )
    sooner = inventory_services.receive_stock(
        ingredient,
        warehouse,
        Decimal("500"),
        Decimal("0.20"),
        expiry_date=timezone.localdate() + timedelta(days=2),
    )
    inventory_services.consume_stock(ingredient, warehouse, Decimal("400"))
    later.refresh_from_db()
    sooner.refresh_from_db()
    assert sooner.remaining_quantity == Decimal("100.000")
    assert later.remaining_quantity == Decimal("500.000")


def test_consume_reports_shortfall_without_blocking(db, gram, warehouse):
    ingredient = Ingredient.objects.create(name="Tuz", base_unit=gram)
    inventory_services.receive_stock(ingredient, warehouse, Decimal("100"), Decimal("0.01"))
    result = inventory_services.consume_stock(ingredient, warehouse, Decimal("150"))
    assert result.shortfall == Decimal("50.000")
    assert ingredient.total_on_hand == Decimal("-50.000")


def test_consume_blocked_when_negative_not_allowed(db, gram, warehouse):
    ingredient = Ingredient.objects.create(name="Yağ", base_unit=gram)
    inventory_services.receive_stock(ingredient, warehouse, Decimal("100"), Decimal("0.01"))
    with pytest.raises(inventory_services.InsufficientStock):
        inventory_services.consume_stock(
            ingredient, warehouse, Decimal("150"), allow_negative=False
        )


def test_unit_conversion_to_base(db, kilogram, gram):
    assert kilogram.to_base(Decimal("2.5")) == Decimal("2500.000")
    assert kilogram.from_base(Decimal("2500")) == Decimal("2.500")


def test_recipe_deducts_stock_on_send_to_kitchen(table, waiter, pizza, flour, cheese):
    order = order_services.open_order(table=table, waiter=waiter)
    order_services.add_item(order, pizza, quantity=Decimal("2"))
    order_services.send_to_kitchen(order, user=waiter)

    flour.refresh_from_db()
    cheese.refresh_from_db()
    # 10000 - (200 * 2) = 9600 ; 5000 - (150 * 2) = 4700
    assert flour.total_on_hand == Decimal("9600.000")
    assert cheese.total_on_hand == Decimal("4700.000")


def test_waste_percent_increases_consumption(db, table, waiter, pizza, flour, gram):
    recipe_item = pizza.recipe.items.get(ingredient=flour)
    recipe_item.waste_percent = Decimal("10")
    recipe_item.save()

    order = order_services.open_order(table=table, waiter=waiter)
    order_services.add_item(order, pizza, quantity=Decimal("1"))
    order_services.send_to_kitchen(order, user=waiter)

    flour.refresh_from_db()
    # 200 g + %10 fire = 220 g
    assert flour.total_on_hand == Decimal("9780.000")


def test_cancel_restores_stock(table, waiter, manager, pizza, flour):
    order = order_services.open_order(table=table, waiter=waiter)
    item = order_services.add_item(order, pizza)
    order_services.send_to_kitchen(order, user=waiter)
    flour.refresh_from_db()
    assert flour.total_on_hand == Decimal("9800.000")

    order_services.cancel_item(item, reason="Yanlış sipariş", user=manager, restock=True)
    flour.refresh_from_db()
    assert flour.total_on_hand == Decimal("10000.000")


def test_product_auto_disabled_when_ingredient_runs_out(table, waiter, pizza, flour, warehouse):
    inventory_services.consume_stock(flour, warehouse, flour.total_on_hand)
    pizza.refresh_from_db()
    assert not pizza.is_available
    assert "Un" in pizza.unavailable_reason


def test_product_reopened_when_stock_returns(pizza, flour, warehouse):
    inventory_services.consume_stock(flour, warehouse, flour.total_on_hand)
    pizza.refresh_from_db()
    assert not pizza.is_available

    inventory_services.receive_stock(flour, warehouse, Decimal("5000"), Decimal("0.02"))
    pizza.refresh_from_db()
    assert pizza.is_available


def test_low_stock_report_lists_critical_items(db, gram, warehouse):
    ingredient = Ingredient.objects.create(
        name="Kekik", base_unit=gram, critical_level=Decimal("500")
    )
    inventory_services.receive_stock(ingredient, warehouse, Decimal("400"), Decimal("0.50"))
    assert ingredient in inventory_services.low_stock_report()


def test_stock_adjustment_from_count(db, gram, warehouse):
    ingredient = Ingredient.objects.create(name="Nohut", base_unit=gram)
    inventory_services.receive_stock(ingredient, warehouse, Decimal("1000"), Decimal("0.03"))
    inventory_services.adjust_stock(ingredient, warehouse, Decimal("950"), note="Sayım")
    assert ingredient.total_on_hand == Decimal("950.000")
    assert ingredient.movements.filter(movement_type=StockMovement.Type.ADJUSTMENT).exists()


def test_waste_record_reduces_stock_and_stores_cost(db, gram, warehouse):
    ingredient = Ingredient.objects.create(name="Marul", base_unit=gram)
    inventory_services.receive_stock(ingredient, warehouse, Decimal("1000"), Decimal("0.05"))
    waste = inventory_services.record_waste(
        ingredient, warehouse, Decimal("200"), WasteRecord.Reason.SPOILED
    )
    assert ingredient.total_on_hand == Decimal("800.000")
    assert waste.cost_value == Decimal("10.00")


def test_transfer_between_warehouses(db, gram, warehouse):
    from apps.inventory.models import Warehouse

    target = Warehouse.objects.create(name="Mutfak", code="mutfak")
    ingredient = Ingredient.objects.create(name="Zeytin", base_unit=gram)
    inventory_services.receive_stock(ingredient, warehouse, Decimal("1000"), Decimal("0.20"))
    inventory_services.transfer_stock(ingredient, warehouse, target, Decimal("300"))
    assert ingredient.on_hand_at(warehouse) == Decimal("700.000")
    assert ingredient.on_hand_at(target) == Decimal("300.000")


def test_expiring_batches_detected(db, gram, warehouse):
    ingredient = Ingredient.objects.create(name="Yoğurt", base_unit=gram, is_perishable=True)
    inventory_services.receive_stock(
        ingredient,
        warehouse,
        Decimal("500"),
        Decimal("0.08"),
        expiry_date=timezone.localdate() + timedelta(days=3),
    )
    assert inventory_services.expiring_batches(7).count() == 1
    assert inventory_services.expiring_batches(1).count() == 0
