"""Mutfak servisleri: KOT durum geçişleri ve canlı yayın."""

from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from apps.core.models import AuditLog, Notification
from apps.core.services import notify, record_audit
from apps.kitchen.models import KitchenTicket, TicketLine
from apps.orders.models import Order, OrderItem

logger = logging.getLogger("apps.kitchen")


def broadcast_ticket(ticket: KitchenTicket, *, event: str = "updated") -> None:
    """KOT değişikliğini ilgili istasyon kanalına ve genel kanala yayınlar."""
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        layer = get_channel_layer()
        if layer is None:
            return
        payload = {"event": event, "ticket": ticket.to_stream_dict()}
        for group in (f"kitchen_{ticket.station.code}", "kitchen_all"):
            async_to_sync(layer.group_send)(group, {"type": "kitchen.event", "payload": payload})
    except Exception:  # pragma: no cover
        logger.debug("KOT yayını yapılamadı", exc_info=True)


@transaction.atomic
def start_ticket(ticket: KitchenTicket, *, user=None) -> KitchenTicket:
    """Hazırlığa başla."""
    if ticket.status != KitchenTicket.Status.QUEUED:
        return ticket
    now = timezone.now()
    ticket.status = KitchenTicket.Status.PREPARING
    ticket.started_at = now
    ticket.started_by = user
    ticket.save(update_fields=["status", "started_at", "started_by", "updated_at"])

    ticket.lines.update(status=TicketLine.Status.PREPARING)
    OrderItem.objects.filter(ticket_lines__ticket=ticket).update(
        status=OrderItem.Status.PREPARING, started_at=now
    )
    _sync_order_status(ticket.order)
    broadcast_ticket(ticket)
    return ticket


@transaction.atomic
def mark_ticket_ready(ticket: KitchenTicket, *, user=None) -> KitchenTicket:
    """KOT'u hazır olarak işaretler ve garsonu bilgilendirir."""
    if ticket.status in {KitchenTicket.Status.COMPLETED, KitchenTicket.Status.CANCELLED}:
        return ticket
    now = timezone.now()
    if ticket.started_at is None:
        ticket.started_at = now
    ticket.status = KitchenTicket.Status.READY
    ticket.ready_at = now
    ticket.save(update_fields=["status", "started_at", "ready_at", "updated_at"])

    ticket.lines.update(status=TicketLine.Status.READY, completed_at=now)
    OrderItem.objects.filter(ticket_lines__ticket=ticket).exclude(
        status=OrderItem.Status.CANCELLED
    ).update(status=OrderItem.Status.READY, ready_at=now)

    _sync_order_status(ticket.order)
    broadcast_ticket(ticket, event="ready")

    order = ticket.order
    notify(
        f"Sipariş hazır: {ticket.table_label}",
        body=f"{ticket.number} ({ticket.station.name}) hazır. Adisyon: {order.number}",
        level=Notification.Level.SUCCESS,
        category=Notification.Category.KITCHEN,
        recipient=order.waiter,
        roles=["waiter", "head_waiter"],
        url=f"/orders/{order.pk}/",
    )
    return ticket


@transaction.atomic
def complete_ticket(ticket: KitchenTicket, *, user=None) -> KitchenTicket:
    """Servis edildi olarak işaretler."""
    now = timezone.now()
    if ticket.ready_at is None:
        ticket.ready_at = now
    ticket.status = KitchenTicket.Status.COMPLETED
    ticket.completed_at = now
    ticket.completed_by = user
    ticket.save(update_fields=["status", "ready_at", "completed_at", "completed_by", "updated_at"])
    OrderItem.objects.filter(ticket_lines__ticket=ticket).exclude(
        status=OrderItem.Status.CANCELLED
    ).update(status=OrderItem.Status.SERVED, served_at=now)
    _sync_order_status(ticket.order)
    broadcast_ticket(ticket, event="completed")
    return ticket


@transaction.atomic
def bump_priority(ticket: KitchenTicket, *, user=None) -> KitchenTicket:
    """KOT'u acil sıraya alır."""
    ticket.priority = KitchenTicket.Priority.RUSH
    ticket.save(update_fields=["priority", "updated_at"])
    record_audit(
        AuditLog.Action.UPDATE,
        user=user,
        obj=ticket,
        description=f"{ticket.number} acil sıraya alındı.",
        severity=AuditLog.Severity.NOTICE,
    )
    broadcast_ticket(ticket)
    return ticket


def _sync_order_status(order: Order) -> None:
    """Sipariş durumunu KOT'ların toplu durumuna göre günceller."""
    if order.status in {Order.Status.PAID, Order.Status.CANCELLED}:
        return
    tickets = list(order.tickets.exclude(status=KitchenTicket.Status.CANCELLED))
    if not tickets:
        return

    statuses = {t.status for t in tickets}
    if statuses <= {KitchenTicket.Status.COMPLETED}:
        new_status = Order.Status.SERVED
    elif statuses <= {KitchenTicket.Status.READY, KitchenTicket.Status.COMPLETED}:
        new_status = Order.Status.READY
    elif KitchenTicket.Status.PREPARING in statuses:
        new_status = Order.Status.PREPARING
    else:
        new_status = Order.Status.SENT

    if order.status != new_status:
        order.status = new_status
        fields = ["status", "updated_at"]
        if new_status == Order.Status.READY and order.ready_at is None:
            order.ready_at = timezone.now()
            fields.append("ready_at")
        order.save(update_fields=fields)


def delayed_tickets(threshold_minutes: int | None = None):
    """Gecikmiş KOT'ları döndürür (yönetici uyarı paneli için)."""
    active = KitchenTicket.objects.exclude(
        status__in=[KitchenTicket.Status.COMPLETED, KitchenTicket.Status.CANCELLED]
    ).select_related("station", "order", "order__table")
    if threshold_minutes is None:
        return [t for t in active if t.is_delayed]
    return [t for t in active if t.elapsed_minutes >= threshold_minutes]


def station_queue(station_code: str | None = None):
    """İstasyonun aktif KOT kuyruğu (öncelik ve bekleme sırasına göre)."""
    qs = (
        KitchenTicket.objects.exclude(
            status__in=[KitchenTicket.Status.COMPLETED, KitchenTicket.Status.CANCELLED]
        )
        .select_related("station", "order", "order__table")
        .prefetch_related("lines__order_item__modifiers", "lines__order_item__product")
    )
    if station_code and station_code != "all":
        qs = qs.filter(station__code=station_code)
    return qs.order_by("-priority", "course", "queued_at")


def kot_text(ticket: KitchenTicket) -> str:
    """Yazıcıya gönderilecek düz metin KOT çıktısı (58/80 mm fiş uyumlu)."""
    width = 40
    lines = [
        "=" * width,
        f"{ticket.station.name.upper():^{width}}",
        "=" * width,
        f"KOT   : {ticket.number}",
        f"Adisyon: {ticket.order.number}",
        f"Masa  : {ticket.table_label}",
        f"Saat  : {timezone.localtime(ticket.queued_at):%d.%m.%Y %H:%M}",
        f"Garson: {ticket.order.waiter.display_name if ticket.order.waiter_id else '-'}",
        "-" * width,
    ]
    for line in ticket.lines.select_related("order_item").prefetch_related("order_item__modifiers"):
        item = line.order_item
        if item.status == OrderItem.Status.CANCELLED:
            continue
        lines.append(f"{item.quantity:>5} x {item.product_name[:30]}")
        if item.modifier_summary:
            lines.append(f"        + {item.modifier_summary[:30]}")
        if item.note:
            lines.append(f"        ! {item.note[:30]}")
    lines.append("-" * width)
    if ticket.note:
        lines.append(f"NOT: {ticket.note}")
    if ticket.priority >= KitchenTicket.Priority.HIGH:
        lines.append(f"*** {ticket.get_priority_display().upper()} ***")
    lines.append("=" * width)
    return "\n".join(lines)
