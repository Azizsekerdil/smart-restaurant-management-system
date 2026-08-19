"""Pytest ortak fikstürleri."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from apps.accounts.permissions import Role
from apps.catalog.models import Category, Product, Recipe, RecipeItem
from apps.floor.models import Area, Table
from apps.inventory.models import Ingredient, UnitOfMeasure, Warehouse
from apps.inventory.services import receive_stock
from apps.kitchen.models import Station

User = get_user_model()


@pytest.fixture(autouse=True)
def _enable_devcenter_for_tests(settings):
    """Geliştirme Merkezi'ni testler için AÇIKÇA açar.

    Ürün varsayılanı artık **kapalıdır** (bkz. ``config/settings.py``):
    ``.env`` dosyası olmayan bir kurulumda kod çalıştırma yüzeyi sessizce
    açılmamalıdır. Kök ``conftest.py`` içindeki ortam değişkeni ataması bu
    işi yapamaz — pytest-django Django ayarlarını kök conftest'ten önce
    yükler, dolayısıyla o atama ayarlara hiç yetişmez.

    Bu fikstür özelliği yalnızca test süreci içinde açar; ürün
    varsayılanını değiştirmez.
    """
    settings.DEVCENTER = {**settings.DEVCENTER, "ENABLED": True, "TERMINAL_ENABLED": True}


@pytest.fixture
def gram(db):
    return UnitOfMeasure.objects.create(
        code="g", name="Gram", dimension="mass", factor_to_base=Decimal("1"), is_base=True
    )


@pytest.fixture
def kilogram(db, gram):
    return UnitOfMeasure.objects.create(
        code="kg", name="Kilogram", dimension="mass", factor_to_base=Decimal("1000")
    )


@pytest.fixture
def piece(db):
    return UnitOfMeasure.objects.create(
        code="adet", name="Adet", dimension="count", factor_to_base=Decimal("1"), is_base=True
    )


@pytest.fixture
def warehouse(db):
    return Warehouse.objects.create(name="Ana Depo", code="ana", is_default=True)


@pytest.fixture
def station(db):
    return Station.objects.create(name="Sıcak Mutfak", kind=Station.Kind.KITCHEN)


@pytest.fixture
def bar_station(db):
    return Station.objects.create(name="Bar", kind=Station.Kind.BAR)


@pytest.fixture
def owner(db):
    user = User.objects.create_user(
        username="patron",
        password="Test!2026Pass",
        role=Role.OWNER,
        first_name="Test",
        last_name="Patron",
    )
    # PIN politikası tekrar/ardışık PIN'leri reddeder (bkz. pin_security).
    user.set_pin("5271")
    user.save()
    return user


@pytest.fixture
def manager(db):
    user = User.objects.create_user(
        username="mudur", password="Test!2026Pass", role=Role.RESTAURANT_MANAGER
    )
    user.set_pin("8364")
    user.save()
    return user


@pytest.fixture
def waiter(db):
    return User.objects.create_user(
        username="garson", password="Test!2026Pass", role=Role.WAITER, first_name="Garson"
    )


@pytest.fixture
def cashier(db):
    return User.objects.create_user(username="kasiyer", password="Test!2026Pass", role=Role.CASHIER)


@pytest.fixture
def chef(db):
    return User.objects.create_user(username="sef", password="Test!2026Pass", role=Role.CHEF)


@pytest.fixture
def category(db):
    return Category.objects.create(name="Ana Yemekler", sort_order=10)


@pytest.fixture
def flour(db, gram, warehouse):
    ingredient = Ingredient.objects.create(name="Un", base_unit=gram, critical_level=Decimal("500"))
    receive_stock(ingredient, warehouse, Decimal("10000"), Decimal("0.02"))
    return ingredient


@pytest.fixture
def cheese(db, gram, warehouse):
    ingredient = Ingredient.objects.create(
        name="Peynir",
        base_unit=gram,
        critical_level=Decimal("200"),
        is_perishable=True,
        shelf_life_days=20,
    )
    receive_stock(ingredient, warehouse, Decimal("5000"), Decimal("0.30"))
    return ingredient


@pytest.fixture
def pizza(db, category, station, flour, cheese, gram):
    """Reçetesi olan örnek ürün: 200 g un + 150 g peynir."""
    product = Product.objects.create(
        name="Pizza Margherita",
        category=category,
        price=Decimal("200.00"),
        tax_rate=Decimal("10.00"),
        station=station,
        preparation_minutes=15,
    )
    recipe = Recipe.objects.create(product=product, labor_cost=Decimal("10.00"))
    RecipeItem.objects.create(recipe=recipe, ingredient=flour, quantity=Decimal("200"), unit=gram)
    RecipeItem.objects.create(recipe=recipe, ingredient=cheese, quantity=Decimal("150"), unit=gram)
    return product


@pytest.fixture
def cola(db, category, bar_station):
    return Product.objects.create(
        name="Kola",
        category=category,
        price=Decimal("50.00"),
        tax_rate=Decimal("10.00"),
        station=bar_station,
        preparation_minutes=1,
    )


@pytest.fixture
def area(db):
    return Area.objects.create(name="İç Salon", code="ic-salon")


@pytest.fixture
def table(db, area):
    return Table.objects.create(area=area, name="S1", capacity=4)


@pytest.fixture
def table2(db, area):
    return Table.objects.create(area=area, name="S2", capacity=2)


@pytest.fixture
def cash_session(db, cashier):
    from apps.orders.models import CashSession

    return CashSession.objects.create(opened_by=cashier, opening_float=Decimal("1000"))
