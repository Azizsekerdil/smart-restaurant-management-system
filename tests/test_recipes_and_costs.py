"""Reçete maliyeti, kâr marjı ve menü mühendisliği testleri."""

from __future__ import annotations

from decimal import Decimal

import pytest

pytestmark = pytest.mark.django_db


def test_recipe_cost_sums_ingredient_lines(pizza, flour, cheese):
    # 200 g un * 0.02 = 4.00 ; 150 g peynir * 0.30 = 45.00 ; işçilik 10.00
    assert pizza.recipe.ingredient_cost == Decimal("49.00")
    assert pizza.recipe.total_cost == Decimal("59.00")


def test_recipe_yield_divides_cost(pizza):
    pizza.recipe.yield_quantity = Decimal("2")
    pizza.recipe.save()
    assert pizza.recipe.total_cost == Decimal("29.50")


def test_tax_amount_backed_out_of_inclusive_price(pizza):
    # 200 ₺, %10 KDV dahil → KDV = 200 * 10/110 = 18.18
    assert pizza.tax_amount == Decimal("18.18")
    assert pizza.net_price == Decimal("181.82")


def test_margin_percent(pizza):
    # net 181.82, maliyet 59.00 → kâr 122.82 → marj %67.55
    assert pizza.gross_profit == Decimal("122.82")
    assert pizza.margin_percent == Decimal("67.55")


def test_food_cost_percent(pizza):
    assert pizza.food_cost_percent == Decimal("32.45")


def test_product_without_recipe_has_zero_cost(cola):
    assert cola.recipe_cost == Decimal("0.00")
    assert cola.margin_percent == Decimal("100.00")


def test_waste_percent_raises_effective_quantity(pizza, flour):
    item = pizza.recipe.items.get(ingredient=flour)
    item.waste_percent = Decimal("25")
    item.save()
    assert item.effective_quantity == Decimal("250.00")


def test_unit_conversion_in_recipe_cost(db, pizza, cheese, kilogram):
    """Kg cinsinden girilen malzeme temel birime çevrilerek fiyatlanır."""
    item = pizza.recipe.items.get(ingredient=cheese)
    item.quantity = Decimal("0.150")
    item.unit = kilogram
    item.save()
    # 0.150 kg = 150 g → 150 * 0.30 = 45.00 (değişmemeli)
    assert item.line_cost == Decimal("45.00")


def test_missing_ingredients_detected(pizza, flour, warehouse):
    from apps.inventory.services import consume_stock

    consume_stock(flour, warehouse, Decimal("9900"))  # 100 g kaldı
    missing = pizza.recipe.missing_ingredients(portions=Decimal("1"))
    assert len(missing) == 1
    assert missing[0]["ingredient"] == flour
    assert missing[0]["shortage"] == Decimal("100.000")


def test_variant_price_delta(pizza):
    from apps.catalog.models import ProductVariant

    large = ProductVariant.objects.create(
        product=pizza,
        name="Büyük",
        price_delta=Decimal("50"),
        recipe_multiplier=Decimal("1.5"),
    )
    assert large.price == Decimal("250.00")


def test_menu_engineering_classifies_products(db, pizza, cola, table, waiter, cashier):
    """Satış sonrası menü mühendisliği ürünleri gruplara ayırmalı."""
    from apps.ai.analytics import menu_engineering
    from apps.orders import services
    from apps.orders.models import Payment

    for _ in range(5):
        order = services.open_order(table=table, waiter=waiter)
        services.add_item(order, pizza)
        services.add_item(order, cola)
        services.take_payment(
            order, method=Payment.Method.CARD, amount=order.grand_total, user=cashier
        )
        table.status = table.Status.FREE
        table.save()

    result = menu_engineering(days=30, narrate=False)
    assert result["ok"]
    assert result["data_points"] == 2
    all_names = [item["name"] for group in result["groups"].values() for item in group]
    assert "Pizza Margherita" in all_names
    assert "Kola" in all_names
