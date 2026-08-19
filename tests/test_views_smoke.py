"""Tüm ekranların hatasız açıldığını doğrulayan duman (smoke) testleri."""

from __future__ import annotations

import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db

# Yönetici (owner) tarafından açılabilmesi gereken tüm sayfalar
PAGES = [
    "core:home",
    "core:notifications",
    "core:settings",
    "core:audit_log",
    "accounts:profile",
    "accounts:password_change",
    "accounts:set_pin",
    "accounts:user_list",
    "accounts:user_create",
    "reports:dashboard",
    "reports:report_index",
    "reports:sales_report",
    "reports:profitability",
    "reports:void_report",
    "reports:daily_closing_list",
    "reports:expense_list",
    "orders:pos",
    "orders:order_list",
    "orders:delivery_board",
    "orders:cash_session",
    "floor:table_map",
    "floor:table_list",
    "floor:table_create",
    "floor:reservation_list",
    "floor:reservation_create",
    "kitchen:display",
    "kitchen:station_list",
    "kitchen:performance",
    "catalog:product_list",
    "catalog:product_create",
    "catalog:category_list",
    "catalog:category_create",
    "inventory:ingredient_list",
    "inventory:ingredient_create",
    "inventory:movement_list",
    "inventory:alerts",
    "inventory:waste_list",
    "inventory:count_list",
    "inventory:supplier_list",
    "inventory:supplier_create",
    "inventory:purchase_list",
    "inventory:purchase_create",
    "crm:customer_list",
    "crm:customer_create",
    "crm:review_list",
    "crm:campaign_list",
    "hr:employee_list",
    "hr:employee_create",
    "hr:shift_schedule",
    "hr:leave_list",
    "hr:task_list",
    "hr:performance",
    "ai:assistant",
    "ai:analysis_hub",
    "ai:insights",
    "ai:providers",
    "ai:usage_log",
    "devcenter:index",
    "devcenter:files",
    "devcenter:terminal",
    "devcenter:git",
    "devcenter:snapshots",
]


@pytest.mark.parametrize("url_name", PAGES)
def test_page_renders_for_owner(client, owner, url_name):
    client.force_login(owner)
    response = client.get(reverse(url_name), follow=True)
    assert response.status_code == 200, f"{url_name} → {response.status_code}"


def test_detail_pages_render(client, owner, table, pizza, waiter, cashier, flour):
    """Nesne detay sayfaları."""
    from apps.orders import services
    from apps.orders.models import Payment

    order = services.open_order(table=table, waiter=waiter)
    services.add_item(order, pizza)
    ticket = services.send_to_kitchen(order, user=waiter)[0]
    services.take_payment(order, method=Payment.Method.CARD, amount=order.grand_total, user=cashier)

    from apps.crm.models import Customer

    customer = Customer.objects.create(first_name="Test", last_name="Müşteri")

    client.force_login(owner)
    pages = [
        reverse("orders:order_detail", args=[order.pk]),
        reverse("orders:order_receipt", args=[order.pk]),
        reverse("orders:order_panel", args=[order.pk]),
        reverse("catalog:product_detail", args=[pizza.pk]),
        reverse("catalog:product_edit", args=[pizza.pk]),
        reverse("catalog:recipe_detail", args=[pizza.pk]),
        reverse("catalog:recipe_edit", args=[pizza.pk]),
        reverse("inventory:ingredient_detail", args=[flour.pk]),
        reverse("inventory:ingredient_edit", args=[flour.pk]),
        reverse("crm:customer_detail", args=[customer.pk]),
        reverse("crm:customer_edit", args=[customer.pk]),
        reverse("accounts:user_edit", args=[owner.pk]),
        reverse("accounts:user_permissions", args=[owner.pk]),
        reverse("floor:table_edit", args=[table.pk]),
        reverse("kitchen:kot_preview", args=[ticket.pk]),
        reverse("catalog:qr_menu", args=[table.qr_token]),
    ]
    for url in pages:
        response = client.get(url, follow=True)
        assert response.status_code == 200, f"{url} → {response.status_code}"


def test_healthz_is_public(client):
    response = client.get(reverse("core:healthz"))
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_kitchen_display_for_bartender(client, db, bar_station):
    from django.contrib.auth import get_user_model

    from apps.accounts.permissions import Role

    User = get_user_model()
    bartender = User.objects.create_user(
        username="barmen", password="Test!2026Pass", role=Role.BARTENDER
    )
    client.force_login(bartender)
    response = client.get(reverse("kitchen:display"))
    assert response.status_code == 200


def test_pos_renders_for_waiter(client, waiter, pizza, table):
    client.force_login(waiter)
    response = client.get(reverse("orders:pos"))
    assert response.status_code == 200
    assert "Pizza Margherita" in response.content.decode()


def test_notification_feed_json(client, owner):
    client.force_login(owner)
    response = client.get(reverse("core:notification_feed"))
    assert response.status_code == 200
    assert "count" in response.json()


# ------------------------------------------------------------------ REST API
def test_api_requires_authentication(client):
    response = client.get("/api/products/")
    assert response.status_code in (401, 403)


def test_api_lists_products(client, owner, pizza):
    client.force_login(owner)
    response = client.get("/api/products/")
    assert response.status_code == 200
    assert response.json()["count"] >= 1


def test_api_respects_permissions(client, waiter, pizza):
    client.force_login(waiter)
    read = client.get("/api/products/")
    assert read.status_code == 200
    write = client.post("/api/products/", {"name": "Yeni", "price": "10"})
    assert write.status_code == 403


def test_api_order_creation_and_kitchen_action(client, owner, table, pizza):
    client.force_login(owner)
    response = client.post(
        "/api/orders/",
        {"order_type": "dine_in", "table": table.pk, "guest_count": 2},
        content_type="application/json",
    )
    assert response.status_code == 201
    order_id = response.json()["id"]

    from apps.orders.models import Order, OrderItem

    order = Order.objects.get(pk=order_id)
    OrderItem.objects.create(
        order=order,
        product=pizza,
        product_name=pizza.name,
        unit_price=pizza.price,
        tax_rate=pizza.tax_rate,
        quantity=1,
        station=pizza.station,
    )
    send = client.post(f"/api/orders/{order_id}/send-to-kitchen/")
    assert send.status_code == 200
    assert send.json()["tickets"]


def test_api_ai_endpoint_reports_unavailable(client, owner):
    client.force_login(owner)
    response = client.post("/api/ai/ask/", {"question": "Merhaba"}, content_type="application/json")
    # Test ortamında sağlayıcı kapalı → 503 ve anlaşılır mesaj beklenir
    assert response.status_code == 503
    assert "LM Studio" in response.json()["detail"]


def test_api_providers_never_leak_keys(client, owner):
    client.force_login(owner)
    response = client.get("/api/ai/providers/")
    assert response.status_code == 200
    assert "nvapi-" not in response.content.decode()
