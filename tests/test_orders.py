"""Sipariş akışı, tutar hesabı, ödeme, iptal ve iade testleri."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.orders import services
from apps.orders.models import Coupon, Order, OrderItem, Payment, Refund

pytestmark = pytest.mark.django_db


# ------------------------------------------------------------------ açılış
def test_open_order_marks_table_occupied(table, waiter):
    order = services.open_order(table=table, waiter=waiter, guest_count=2)
    table.refresh_from_db()
    assert order.status == Order.Status.OPEN
    assert table.status == table.Status.OCCUPIED
    assert table.occupied_since is not None


def test_open_order_returns_existing_order_for_table(table, waiter):
    first = services.open_order(table=table, waiter=waiter)
    second = services.open_order(table=table, waiter=waiter)
    assert first.pk == second.pk


def test_dine_in_requires_table(waiter):
    with pytest.raises(ValidationError):
        services.open_order(order_type=Order.Type.DINE_IN, table=None, waiter=waiter)


def test_takeaway_needs_no_table(waiter):
    order = services.open_order(order_type=Order.Type.TAKEAWAY, waiter=waiter)
    assert order.table_id is None
    assert order.number.startswith("P-")


# ------------------------------------------------------------------ satırlar
def test_add_item_calculates_totals(table, waiter, pizza):
    order = services.open_order(table=table, waiter=waiter)
    services.add_item(order, pizza, quantity=Decimal("2"))
    order.refresh_from_db()
    assert order.subtotal == Decimal("400.00")
    assert order.grand_total == Decimal("400.00")


def test_tax_is_calculated_from_inclusive_price(table, waiter, pizza):
    """200 ₺ KDV dahil, %10 → KDV = 200 * 10 / 110 = 18.18"""
    order = services.open_order(table=table, waiter=waiter)
    services.add_item(order, pizza, quantity=Decimal("1"))
    order.refresh_from_db()
    assert order.tax_total == Decimal("18.18")


def test_cannot_add_unavailable_product(table, waiter, pizza):
    pizza.is_available = False
    pizza.unavailable_reason = "Malzeme yok"
    pizza.save()
    order = services.open_order(table=table, waiter=waiter)
    with pytest.raises(ValidationError, match="Malzeme yok"):
        services.add_item(order, pizza)


def test_cannot_add_to_closed_order(table, waiter, cashier, pizza):
    order = services.open_order(table=table, waiter=waiter)
    services.add_item(order, pizza)
    services.take_payment(order, method=Payment.Method.CASH, amount=order.grand_total, user=cashier)
    order.refresh_from_db()
    with pytest.raises(ValidationError):
        services.add_item(order, pizza)


def test_zero_quantity_rejected(table, waiter, pizza):
    order = services.open_order(table=table, waiter=waiter)
    with pytest.raises(ValidationError):
        services.add_item(order, pizza, quantity=Decimal("0"))


def test_price_override_recorded(table, waiter, pizza):
    order = services.open_order(table=table, waiter=waiter)
    item = services.add_item(order, pizza, unit_price=Decimal("150"), user=waiter)
    assert item.is_price_overridden
    assert item.original_price == Decimal("200.00")


# ------------------------------------------------------------------ indirim
def test_manual_percent_discount(table, waiter, manager, pizza):
    order = services.open_order(table=table, waiter=waiter)
    services.add_item(order, pizza, quantity=Decimal("2"))
    services.apply_manual_discount(order, percent=Decimal("10"), reason="test", user=manager)
    order.refresh_from_db()
    assert order.order_discount_total == Decimal("40.00")
    assert order.grand_total == Decimal("360.00")


def test_discount_cannot_exceed_subtotal(table, waiter, manager, pizza):
    order = services.open_order(table=table, waiter=waiter)
    services.add_item(order, pizza)
    with pytest.raises(ValidationError):
        services.apply_manual_discount(order, amount=Decimal("999"), user=manager)


def test_coupon_applies_and_respects_max(table, waiter, pizza):
    Coupon.objects.create(
        code="TEST20",
        name="Test",
        kind=Coupon.Kind.PERCENT,
        value=Decimal("20"),
        max_discount=Decimal("30"),
    )
    order = services.open_order(table=table, waiter=waiter)
    services.add_item(order, pizza)  # 200 ₺; %20 = 40 ama üst sınır 30
    services.apply_coupon(order, "TEST20", user=waiter)
    order.refresh_from_db()
    assert order.order_discount_total == Decimal("30.00")


def test_coupon_minimum_total_enforced(table, waiter, cola):
    Coupon.objects.create(
        code="MIN500",
        name="Min",
        kind=Coupon.Kind.AMOUNT,
        value=Decimal("50"),
        minimum_order_total=Decimal("500"),
    )
    order = services.open_order(table=table, waiter=waiter)
    services.add_item(order, cola)  # 50 ₺
    with pytest.raises(ValidationError, match="asgari sipariş"):
        services.apply_coupon(order, "MIN500", user=waiter)


def test_unknown_coupon_rejected(table, waiter, pizza):
    order = services.open_order(table=table, waiter=waiter)
    services.add_item(order, pizza)
    with pytest.raises(ValidationError, match="bulunamadı"):
        services.apply_coupon(order, "YOKBOYLE", user=waiter)


def test_same_coupon_cannot_be_applied_twice(table, waiter, pizza):
    Coupon.objects.create(code="TEK", name="Tek", kind=Coupon.Kind.AMOUNT, value=Decimal("10"))
    order = services.open_order(table=table, waiter=waiter)
    services.add_item(order, pizza)
    services.apply_coupon(order, "TEK", user=waiter)
    with pytest.raises(ValidationError, match="zaten uygulanmış"):
        services.apply_coupon(order, "TEK", user=waiter)


# ------------------------------------------------------------------ ödeme
def test_cash_payment_computes_change(table, waiter, cashier, pizza):
    order = services.open_order(table=table, waiter=waiter)
    services.add_item(order, pizza)
    payment = services.take_payment(
        order,
        method=Payment.Method.CASH,
        amount=Decimal("200"),
        received=Decimal("250"),
        user=cashier,
    )
    assert payment.change_amount == Decimal("50.00")


def test_insufficient_cash_rejected(table, waiter, cashier, pizza):
    order = services.open_order(table=table, waiter=waiter)
    services.add_item(order, pizza)
    with pytest.raises(ValidationError, match="az olamaz"):
        services.take_payment(
            order,
            method=Payment.Method.CASH,
            amount=Decimal("200"),
            received=Decimal("100"),
            user=cashier,
        )


def test_split_payment_closes_only_when_fully_paid(table, waiter, cashier, pizza):
    order = services.open_order(table=table, waiter=waiter)
    services.add_item(order, pizza, quantity=Decimal("2"))  # 400 ₺
    services.take_payment(order, method=Payment.Method.CARD, amount=Decimal("150"), user=cashier)
    order.refresh_from_db()
    assert order.status != Order.Status.PAID
    assert order.balance_due == Decimal("250.00")

    services.take_payment(
        order,
        method=Payment.Method.CASH,
        amount=Decimal("250"),
        received=Decimal("250"),
        user=cashier,
    )
    order.refresh_from_db()
    assert order.status == Order.Status.PAID
    assert order.balance_due == Decimal("0.00")


def test_closing_order_frees_table(table, waiter, cashier, pizza):
    order = services.open_order(table=table, waiter=waiter)
    services.add_item(order, pizza)
    services.take_payment(order, method=Payment.Method.CARD, amount=Decimal("200"), user=cashier)
    table.refresh_from_db()
    assert table.status == table.Status.CLEANING


def test_cannot_close_unpaid_order(table, waiter, cashier, pizza):
    order = services.open_order(table=table, waiter=waiter)
    services.add_item(order, pizza)
    with pytest.raises(ValidationError, match="tamamen ödenmedi"):
        services.close_order(order, user=cashier)


# ------------------------------------------------------------------ iptal / iade
def test_cancel_item_excludes_it_from_total(table, waiter, manager, pizza, cola):
    order = services.open_order(table=table, waiter=waiter)
    item = services.add_item(order, pizza)
    services.add_item(order, cola)
    order.refresh_from_db()
    assert order.grand_total == Decimal("250.00")

    services.cancel_item(item, reason="Müşteri vazgeçti", user=manager)
    order.refresh_from_db()
    assert order.grand_total == Decimal("50.00")


def test_cancel_order_frees_table_and_marks_items(table, waiter, manager, pizza):
    order = services.open_order(table=table, waiter=waiter)
    services.add_item(order, pizza)
    services.cancel_order(order, reason="Test iptali", user=manager)
    order.refresh_from_db()
    table.refresh_from_db()
    assert order.status == Order.Status.CANCELLED
    assert table.status == table.Status.FREE
    assert order.items.filter(status=OrderItem.Status.CANCELLED).count() == 1


def test_paid_order_cannot_be_cancelled(table, waiter, cashier, manager, pizza):
    order = services.open_order(table=table, waiter=waiter)
    services.add_item(order, pizza)
    services.take_payment(order, method=Payment.Method.CARD, amount=Decimal("200"), user=cashier)
    order.refresh_from_db()
    with pytest.raises(ValidationError, match="iade işlemi"):
        services.cancel_order(order, reason="x", user=manager)


def test_refund_cannot_exceed_paid_amount(table, waiter, cashier, manager, pizza):
    order = services.open_order(table=table, waiter=waiter)
    services.add_item(order, pizza)
    services.take_payment(order, method=Payment.Method.CARD, amount=Decimal("200"), user=cashier)
    order.refresh_from_db()
    with pytest.raises(ValidationError, match="aşamaz"):
        services.refund_order(
            order, amount=Decimal("500"), reason=Refund.Reason.QUALITY, user=manager
        )


def test_partial_refund_recorded(table, waiter, cashier, manager, pizza):
    order = services.open_order(table=table, waiter=waiter)
    services.add_item(order, pizza)
    services.take_payment(order, method=Payment.Method.CARD, amount=Decimal("200"), user=cashier)
    order.refresh_from_db()
    services.refund_order(order, amount=Decimal("50"), reason=Refund.Reason.QUALITY, user=manager)
    order.refresh_from_db()
    assert order.refunded_total == Decimal("50.00")


# ------------------------------------------------------------------ bölme / taşıma
def test_split_by_items_creates_new_order(table, waiter, pizza, cola):
    order = services.open_order(table=table, waiter=waiter)
    item = services.add_item(order, pizza)
    services.add_item(order, cola)
    new_order = services.split_order_by_items(order, [item.pk], user=waiter)
    order.refresh_from_db()
    new_order.refresh_from_db()
    assert new_order.parent_order_id == order.pk
    assert new_order.grand_total == Decimal("200.00")
    assert order.grand_total == Decimal("50.00")


def test_cannot_split_all_items(table, waiter, pizza):
    order = services.open_order(table=table, waiter=waiter)
    item = services.add_item(order, pizza)
    with pytest.raises(ValidationError, match="Tüm satırlar"):
        services.split_order_by_items(order, [item.pk], user=waiter)


def test_split_evenly_covers_grand_total(table, waiter, pizza):
    order = services.open_order(table=table, waiter=waiter)
    services.add_item(order, pizza)  # 200 ₺
    plan = services.split_order_evenly(order, 3)
    assert sum(p["amount"] for p in plan) == order.grand_total


def test_transfer_order_to_another_table(table, table2, waiter, pizza):
    order = services.open_order(table=table, waiter=waiter)
    services.add_item(order, pizza)
    services.transfer_order_to_table(order, table2, user=waiter)
    order.refresh_from_db()
    table.refresh_from_db()
    table2.refresh_from_db()
    assert order.table_id == table2.pk
    assert table.status == table.Status.FREE
    assert table2.status == table2.Status.OCCUPIED


def test_transfer_blocked_when_target_busy(table, table2, waiter, pizza):
    order = services.open_order(table=table, waiter=waiter)
    services.add_item(order, pizza)
    other = services.open_order(table=table2, waiter=waiter)
    services.add_item(other, pizza)
    with pytest.raises(ValidationError, match="açık bir adisyon"):
        services.transfer_order_to_table(order, table2, user=waiter)


def test_merge_orders(table, table2, waiter, pizza, cola):
    first = services.open_order(table=table, waiter=waiter)
    services.add_item(first, pizza)
    second = services.open_order(table=table2, waiter=waiter)
    services.add_item(second, cola)

    services.merge_orders(first, second, user=waiter)
    first.refresh_from_db()
    second.refresh_from_db()
    assert first.grand_total == Decimal("250.00")
    assert second.status == Order.Status.CANCELLED


# ------------------------------------------------------------------ servis bedeli
def test_area_service_charge_applied(area, table, waiter, pizza):
    area.service_charge_rate = Decimal("10")
    area.save()
    order = services.open_order(table=table, waiter=waiter)
    services.add_item(order, pizza)
    order.recalculate()
    assert order.service_charge == Decimal("20.00")
    assert order.grand_total == Decimal("220.00")
