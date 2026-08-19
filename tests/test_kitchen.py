"""Mutfak ekranı (KDS) ve KOT akışı testleri."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.kitchen import services as kitchen_services
from apps.kitchen.models import KitchenTicket, TicketLine
from apps.orders import services as order_services
from apps.orders.models import Order

pytestmark = pytest.mark.django_db


def test_send_to_kitchen_splits_by_station(table, waiter, pizza, cola):
    order = order_services.open_order(table=table, waiter=waiter)
    order_services.add_item(order, pizza)  # sıcak mutfak
    order_services.add_item(order, cola)  # bar
    tickets = order_services.send_to_kitchen(order, user=waiter)
    assert len(tickets) == 2
    assert {t.station.kind for t in tickets} == {"kitchen", "bar"}


def test_send_to_kitchen_groups_by_course(table, waiter, pizza):
    order = order_services.open_order(table=table, waiter=waiter)
    order_services.add_item(order, pizza, course=1)
    order_services.add_item(order, pizza, course=2)
    tickets = order_services.send_to_kitchen(order, user=waiter)
    assert len(tickets) == 2
    assert {t.course for t in tickets} == {1, 2}


def test_second_send_only_includes_new_items(table, waiter, pizza, cola):
    order = order_services.open_order(table=table, waiter=waiter)
    order_services.add_item(order, pizza)
    order_services.send_to_kitchen(order, user=waiter)

    order_services.add_item(order, cola)
    tickets = order_services.send_to_kitchen(order, user=waiter)
    assert len(tickets) == 1
    assert tickets[0].station.kind == "bar"


def test_no_tickets_when_nothing_new(table, waiter, pizza):
    order = order_services.open_order(table=table, waiter=waiter)
    order_services.add_item(order, pizza)
    order_services.send_to_kitchen(order, user=waiter)
    assert order_services.send_to_kitchen(order, user=waiter) == []


def test_ticket_lifecycle(table, waiter, chef, pizza):
    order = order_services.open_order(table=table, waiter=waiter)
    order_services.add_item(order, pizza)
    ticket = order_services.send_to_kitchen(order, user=waiter)[0]
    assert ticket.status == KitchenTicket.Status.QUEUED

    kitchen_services.start_ticket(ticket, user=chef)
    ticket.refresh_from_db()
    assert ticket.status == KitchenTicket.Status.PREPARING
    assert ticket.started_at is not None

    kitchen_services.mark_ticket_ready(ticket, user=chef)
    ticket.refresh_from_db()
    assert ticket.status == KitchenTicket.Status.READY
    assert ticket.ready_at is not None

    kitchen_services.complete_ticket(ticket, user=chef)
    ticket.refresh_from_db()
    order.refresh_from_db()
    assert ticket.status == KitchenTicket.Status.COMPLETED
    assert order.status == Order.Status.SERVED


def test_order_status_reflects_partial_readiness(table, waiter, chef, pizza, cola):
    order = order_services.open_order(table=table, waiter=waiter)
    order_services.add_item(order, pizza)
    order_services.add_item(order, cola)
    tickets = order_services.send_to_kitchen(order, user=waiter)

    kitchen_services.mark_ticket_ready(tickets[0], user=chef)
    order.refresh_from_db()
    # Bir KOT hazır, diğeri sırada → sipariş henüz "hazır" olmamalı
    assert order.status == Order.Status.SENT


def test_all_ready_sets_order_ready(table, waiter, chef, pizza, cola):
    order = order_services.open_order(table=table, waiter=waiter)
    order_services.add_item(order, pizza)
    order_services.add_item(order, cola)
    for ticket in order_services.send_to_kitchen(order, user=waiter):
        kitchen_services.mark_ticket_ready(ticket, user=chef)
    order.refresh_from_db()
    assert order.status == Order.Status.READY


def test_urgency_escalates_with_time(table, waiter, pizza, station):
    station.warning_minutes = 5
    station.critical_minutes = 10
    station.save()

    order = order_services.open_order(table=table, waiter=waiter)
    order_services.add_item(order, pizza)
    ticket = order_services.send_to_kitchen(order, user=waiter)[0]
    assert ticket.urgency == "normal"

    KitchenTicket.objects.filter(pk=ticket.pk).update(
        queued_at=timezone.now() - timedelta(minutes=7)
    )
    ticket.refresh_from_db()
    assert ticket.urgency == "warning"

    KitchenTicket.objects.filter(pk=ticket.pk).update(
        queued_at=timezone.now() - timedelta(minutes=15)
    )
    ticket.refresh_from_db()
    assert ticket.urgency == "critical"
    assert ticket.is_delayed
    assert ticket in kitchen_services.delayed_tickets()


def test_cancelling_item_cancels_ticket_line(table, waiter, manager, pizza):
    order = order_services.open_order(table=table, waiter=waiter)
    item = order_services.add_item(order, pizza)
    order_services.send_to_kitchen(order, user=waiter)
    order_services.cancel_item(item, reason="Test", user=manager)
    assert TicketLine.objects.filter(order_item=item, status=TicketLine.Status.CANCELLED).exists()


def test_station_queue_filters_by_station(table, waiter, pizza, cola, station, bar_station):
    order = order_services.open_order(table=table, waiter=waiter)
    order_services.add_item(order, pizza)
    order_services.add_item(order, cola)
    order_services.send_to_kitchen(order, user=waiter)

    assert kitchen_services.station_queue(station.code).count() == 1
    assert kitchen_services.station_queue(bar_station.code).count() == 1
    assert kitchen_services.station_queue("all").count() == 2


def test_kot_text_contains_essentials(table, waiter, pizza):
    order = order_services.open_order(table=table, waiter=waiter)
    order_services.add_item(order, pizza, quantity=Decimal("2"), note="Az tuzlu")
    ticket = order_services.send_to_kitchen(order, user=waiter)[0]
    text = kitchen_services.kot_text(ticket)
    assert "Pizza Margherita" in text
    assert "Az tuzlu" in text
    assert ticket.number in text
    assert table.name in text


def test_bump_priority(table, waiter, chef, pizza):
    order = order_services.open_order(table=table, waiter=waiter)
    order_services.add_item(order, pizza)
    ticket = order_services.send_to_kitchen(order, user=waiter)[0]
    kitchen_services.bump_priority(ticket, user=chef)
    ticket.refresh_from_db()
    assert ticket.priority == KitchenTicket.Priority.RUSH
