"""Sipariş iş mantığı: satır ekleme, mutfağa gönderme, ödeme, iptal, iade, bölme.

Görünümler (views) doğrudan model üzerinde işlem yapmaz; tüm kurallar
burada toplanır. Bu sayede aynı mantık hem web arayüzü, hem REST API,
hem de testler tarafından kullanılır.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.models import AuditLog, Notification
from apps.core.services import notify, record_audit
from apps.core.utils import money
from apps.orders.models import (
    CashSession,
    Coupon,
    Order,
    OrderDiscount,
    OrderItem,
    OrderItemModifier,
    Payment,
    Refund,
)

logger = logging.getLogger("apps.orders")


class OrderError(ValidationError):
    """Sipariş akışına aykırı bir işlem denendi."""


# ------------------------------------------------------------------
#  Sipariş oluşturma / satır yönetimi
# ------------------------------------------------------------------
@transaction.atomic
def open_order(
    *,
    order_type: str = Order.Type.DINE_IN,
    table=None,
    customer=None,
    waiter=None,
    guest_count: int = 1,
    note: str = "",
    cash_session: CashSession | None = None,
) -> Order:
    """Yeni adisyon açar. Masada servis ise masayı dolu işaretler."""
    if order_type == Order.Type.DINE_IN:
        if table is None:
            raise OrderError("Masada servis için masa seçilmelidir.")
        existing = table.active_order
        if existing is not None:
            return existing
        if table.status == table.Status.DISABLED:
            raise OrderError(f"{table.name} kullanım dışı.")

    order = Order.objects.create(
        order_type=order_type,
        table=table,
        area=table.area if table else None,
        customer=customer,
        waiter=waiter,
        guest_count=max(guest_count, 1),
        note=note,
        cash_session=cash_session or active_cash_session(),
        created_by=waiter,
    )
    if table is not None:
        table.mark_occupied()
        if waiter and not table.assigned_waiter_id:
            table.assigned_waiter = waiter
            table.save(update_fields=["assigned_waiter", "updated_at"])

    record_audit(
        AuditLog.Action.CREATE,
        user=waiter,
        obj=order,
        description=f"Adisyon açıldı: {order.number} ({order.get_order_type_display()})",
    )
    return order


@transaction.atomic
def add_item(
    order: Order,
    product,
    *,
    quantity: Decimal = Decimal("1"),
    variant=None,
    modifiers=None,
    note: str = "",
    seat_number: int | None = None,
    course: int = 1,
    unit_price: Decimal | None = None,
    user=None,
) -> OrderItem:
    """Adisyona ürün ekler.

    `unit_price` verilirse fiyat geçersiz kılınır (yetki kontrolü çağıran
    tarafta yapılmalıdır).
    """
    if not order.is_open:
        raise OrderError("Kapatılmış veya iptal edilmiş adisyona ürün eklenemez.")
    if not product.is_active:
        raise OrderError(f"'{product.name}' aktif değil.")
    if not product.is_available:
        reason = product.unavailable_reason or "Ürün şu anda satışa kapalı."
        raise OrderError(f"'{product.name}' eklenemez: {reason}")

    quantity = Decimal(str(quantity))
    if quantity <= 0:
        raise OrderError("Adet sıfırdan büyük olmalıdır.")

    list_price = variant.price if variant is not None else product.price
    price = money(unit_price) if unit_price is not None else money(list_price)

    item = OrderItem.objects.create(
        order=order,
        product=product,
        variant=variant,
        unit_price=price,
        original_price=money(list_price),
        tax_rate=product.tax_rate,
        quantity=quantity,
        note=note[:300],
        seat_number=seat_number,
        course=course,
        station=product.station,
        created_by=user,
    )

    for modifier in modifiers or []:
        OrderItemModifier.objects.create(
            order_item=item,
            modifier=modifier,
            modifier_name=modifier.name,
            price_delta=modifier.price_delta,
        )

    if item.is_price_overridden:
        record_audit(
            AuditLog.Action.DISCOUNT,
            user=user,
            obj=item,
            description=(
                f"{order.number} · '{product.name}' fiyatı elle değiştirildi: "
                f"{list_price} -> {price}"
            ),
            severity=AuditLog.Severity.WARNING,
        )

    order.recalculate()
    return item


@transaction.atomic
def update_item_quantity(item: OrderItem, quantity: Decimal, *, user=None) -> OrderItem:
    """Satır adedini değiştirir. Mutfağa gitmiş satırlarda azaltma iptal sayılır."""
    quantity = Decimal(str(quantity))
    if quantity <= 0:
        raise OrderError("Adet sıfırdan büyük olmalıdır. Satırı iptal etmek için iptal kullanın.")
    if item.status in {OrderItem.Status.CANCELLED}:
        raise OrderError("İptal edilmiş satır değiştirilemez.")
    if item.status != OrderItem.Status.NEW and quantity < item.quantity:
        record_audit(
            AuditLog.Action.VOID,
            user=user,
            obj=item,
            description=(
                f"{item.order.number} · '{item.product_name}' adedi mutfağa gönderildikten "
                f"sonra azaltıldı: {item.quantity} -> {quantity}"
            ),
            severity=AuditLog.Severity.WARNING,
        )
    item.quantity = quantity
    item.save(update_fields=["quantity", "updated_at"])
    item.order.recalculate()
    return item


@transaction.atomic
def cancel_item(item: OrderItem, *, reason: str, user=None, restock: bool = True) -> OrderItem:
    """Sipariş satırını iptal eder ve gerekirse stoğu geri yükler."""
    # Çağıran taraf eski bir nesne tutuyor olabilir (ör. mutfağa gönderim
    # sırasında stock_deducted güncellenmiştir). Güncel durumu oku.
    item.refresh_from_db()
    if item.status == OrderItem.Status.CANCELLED:
        return item
    if item.order.is_paid:
        raise OrderError("Ödenmiş adisyonda satır iptal edilemez; iade işlemi kullanın.")

    was_deducted = item.stock_deducted
    item.status = OrderItem.Status.CANCELLED
    item.cancel_reason = reason[:300]
    item.cancelled_by = user
    item.save(update_fields=["status", "cancel_reason", "cancelled_by", "updated_at"])

    from apps.kitchen.models import TicketLine

    TicketLine.objects.filter(order_item=item).update(status=TicketLine.Status.CANCELLED)

    if was_deducted and restock:
        from apps.inventory.services import consume_for_order_item

        consume_for_order_item(item, user=user, reverse=True)
        item.stock_deducted = False
        item.save(update_fields=["stock_deducted", "updated_at"])

    record_audit(
        AuditLog.Action.VOID,
        user=user,
        obj=item,
        description=(
            f"{item.order.number} · '{item.product_name}' x{item.quantity} iptal edildi. "
            f"Gerekçe: {reason}"
        ),
        severity=AuditLog.Severity.WARNING,
    )
    item.order.recalculate()
    _broadcast_order(item.order)
    return item


# ------------------------------------------------------------------
#  Mutfağa gönderme
# ------------------------------------------------------------------
@transaction.atomic
def send_to_kitchen(order: Order, *, user=None) -> list:
    """Yeni satırları istasyonlara göre KOT'lara böler ve mutfağa gönderir.

    Aynı anda reçeteye göre stok düşülür. Bu, "sipariş mutfağa gitti ama
    stok düşmedi" tutarsızlığını önler.
    """
    from apps.inventory.services import consume_for_order_item
    from apps.kitchen.models import KitchenTicket, Station, TicketLine
    from apps.kitchen.services import broadcast_ticket

    pending = list(
        order.items.filter(status=OrderItem.Status.NEW).select_related("product", "station")
    )
    if not pending:
        return []

    default_station = Station.objects.filter(is_active=True).order_by("sort_order").first()
    grouped: dict[tuple[int, int], list[OrderItem]] = {}
    for item in pending:
        station = item.station or item.product.station or default_station
        if station is None:
            continue
        grouped.setdefault((station.pk, item.course), []).append(item)

    now = timezone.now()
    tickets = []
    for (station_id, course), items in grouped.items():
        ticket = KitchenTicket.objects.create(
            order=order,
            station_id=station_id,
            course=course,
            note=order.kitchen_note,
            queued_at=now,
            created_by=user,
        )
        for item in items:
            TicketLine.objects.create(ticket=ticket, order_item=item)
        tickets.append(ticket)

    for item in pending:
        item.status = OrderItem.Status.SENT
        item.sent_at = now
        if not item.stock_deducted:
            consume_for_order_item(item, user=user)
            item.stock_deducted = True
        item.save(update_fields=["status", "sent_at", "stock_deducted", "updated_at"])

    if order.status in {Order.Status.DRAFT, Order.Status.OPEN}:
        order.status = Order.Status.SENT
        order.sent_at = now
        order.save(update_fields=["status", "sent_at", "updated_at"])

    for ticket in tickets:
        broadcast_ticket(ticket, event="created")

    record_audit(
        AuditLog.Action.UPDATE,
        user=user,
        obj=order,
        description=f"{order.number} mutfağa gönderildi ({len(pending)} satır, {len(tickets)} KOT).",
    )
    _broadcast_order(order)
    return tickets


# ------------------------------------------------------------------
#  İndirim
# ------------------------------------------------------------------
@transaction.atomic
def apply_coupon(order: Order, code: str, *, user=None) -> OrderDiscount:
    coupon = Coupon.objects.filter(code__iexact=code.strip()).first()
    if coupon is None:
        raise OrderError(f"'{code}' kodlu kupon bulunamadı.")
    order.recalculate()
    valid, reason = coupon.is_valid(order)
    if not valid:
        raise OrderError(reason)
    if order.discounts.filter(coupon=coupon).exists():
        raise OrderError("Bu kupon bu adisyona zaten uygulanmış.")

    amount = coupon.compute_discount(order.subtotal)
    discount = OrderDiscount.objects.create(
        order=order,
        kind=OrderDiscount.Kind.COUPON,
        coupon=coupon,
        label=coupon.name,
        percent=coupon.value if coupon.kind == Coupon.Kind.PERCENT else Decimal("0.00"),
        amount=amount,
        approved_by=user,
        created_by=user,
    )
    Coupon.objects.filter(pk=coupon.pk).update(used_count=coupon.used_count + 1)
    order.recalculate()
    record_audit(
        AuditLog.Action.DISCOUNT,
        user=user,
        obj=order,
        description=f"{order.number} · '{coupon.code}' kuponu uygulandı ({amount} ₺).",
        severity=AuditLog.Severity.NOTICE,
    )
    return discount


@transaction.atomic
def apply_manual_discount(
    order: Order,
    *,
    percent: Decimal = Decimal("0"),
    amount: Decimal = Decimal("0"),
    reason: str = "",
    user=None,
    approver=None,
) -> OrderDiscount:
    """Elle indirim uygular. Yetkili onayı çağıran tarafta doğrulanmalıdır."""
    order.recalculate()
    percent = Decimal(str(percent or 0))
    amount = Decimal(str(amount or 0))
    if percent > 0:
        computed = money(order.subtotal * percent / Decimal("100"))
    else:
        computed = money(amount)
    if computed <= 0:
        raise OrderError("İndirim tutarı sıfırdan büyük olmalıdır.")
    if computed > order.subtotal:
        raise OrderError("İndirim, ara toplamdan büyük olamaz.")

    discount = OrderDiscount.objects.create(
        order=order,
        kind=OrderDiscount.Kind.MANUAL,
        label=f"Elle indirim ({percent}%)" if percent else "Elle indirim",
        percent=percent,
        amount=computed,
        approved_by=approver or user,
        reason=reason[:300],
        created_by=user,
    )
    order.recalculate()

    severity = (
        AuditLog.Severity.CRITICAL
        if order.subtotal and computed / order.subtotal > Decimal("0.30")
        else AuditLog.Severity.WARNING
    )
    record_audit(
        AuditLog.Action.DISCOUNT,
        user=user,
        obj=order,
        description=(
            f"{order.number} · elle indirim: {computed} ₺ "
            f"(onay: {(approver or user)}). Gerekçe: {reason}"
        ),
        severity=severity,
    )
    if severity == AuditLog.Severity.CRITICAL:
        notify(
            "Yüksek oranlı indirim uygulandı",
            body=f"{order.number} adisyonunda %30'un üzerinde indirim yapıldı ({computed} ₺).",
            level=Notification.Level.WARNING,
            category=Notification.Category.FINANCE,
            roles=["owner", "general_manager", "restaurant_manager"],
        )
    return discount


# ------------------------------------------------------------------
#  Ödeme
# ------------------------------------------------------------------
def active_cash_session() -> CashSession | None:
    return CashSession.objects.filter(status=CashSession.Status.OPEN).order_by("-opened_at").first()


@transaction.atomic
def take_payment(
    order: Order,
    *,
    method: str,
    amount: Decimal,
    received: Decimal | None = None,
    reference: str = "",
    user=None,
    close_if_paid: bool = True,
) -> Payment:
    """Ödeme alır. Tutar kalan bakiyeyi aşarsa fark bahşiş/para üstü olur."""
    if order.status == Order.Status.CANCELLED:
        raise OrderError("İptal edilmiş adisyona ödeme alınamaz.")
    order.recalculate()

    amount = money(amount)
    if amount <= 0:
        raise OrderError("Ödeme tutarı sıfırdan büyük olmalıdır.")

    change = Decimal("0.00")
    if method == Payment.Method.CASH and received is not None:
        received = money(received)
        if received < amount:
            raise OrderError("Alınan nakit, ödeme tutarından az olamaz.")
        change = money(received - amount)
    else:
        received = amount

    payment = Payment.objects.create(
        order=order,
        method=method,
        amount=amount,
        received_amount=received,
        change_amount=change,
        reference=reference[:100],
        cashier=user,
        cash_session=order.cash_session or active_cash_session(),
        created_by=user,
    )

    order.recalculate()
    if close_if_paid and order.is_fully_paid and order.status != Order.Status.PAID:
        close_order(order, user=user)

    record_audit(
        AuditLog.Action.CASH,
        user=user,
        obj=payment,
        description=(
            f"{order.number} · {payment.get_method_display()} ile {amount} ₺ ödeme alındı."
        ),
    )
    return payment


@transaction.atomic
def close_order(order: Order, *, user=None) -> Order:
    """Adisyonu kapatır, masayı boşaltır, sadakat puanı işler."""
    if order.status == Order.Status.CANCELLED:
        raise OrderError("İptal edilmiş adisyon kapatılamaz.")
    order.recalculate()
    if not order.is_fully_paid:
        raise OrderError(f"Adisyon tamamen ödenmedi. Kalan bakiye: {order.balance_due} ₺")

    order.status = Order.Status.PAID
    order.closed_at = timezone.now()
    order.cashier = user or order.cashier
    order.save(update_fields=["status", "closed_at", "cashier", "updated_at"])

    if order.table_id:
        other_open = (
            Order.objects.filter(table_id=order.table_id)
            .exclude(pk=order.pk)
            .exclude(status__in=[Order.Status.PAID, Order.Status.CANCELLED])
            .exists()
        )
        if not other_open:
            order.table.mark_free(cleaning=True)

    from apps.kitchen.models import KitchenTicket

    KitchenTicket.objects.filter(order=order).exclude(
        status__in=[KitchenTicket.Status.COMPLETED, KitchenTicket.Status.CANCELLED]
    ).update(status=KitchenTicket.Status.COMPLETED, completed_at=timezone.now())

    if order.customer_id:
        from apps.crm.services import award_loyalty_points

        award_loyalty_points(order.customer, order, user=user)

    record_audit(
        AuditLog.Action.UPDATE,
        user=user,
        obj=order,
        description=f"{order.number} kapatıldı. Toplam: {order.grand_total} ₺",
    )
    _broadcast_order(order)
    return order


@transaction.atomic
def cancel_order(order: Order, *, reason: str, user=None, restock: bool = True) -> Order:
    """Tüm adisyonu iptal eder."""
    if order.status == Order.Status.PAID:
        raise OrderError("Ödenmiş adisyon iptal edilemez; iade işlemi kullanın.")
    if order.status == Order.Status.CANCELLED:
        return order

    for item in order.items.exclude(status=OrderItem.Status.CANCELLED):
        cancel_item(item, reason=reason, user=user, restock=restock)

    order.status = Order.Status.CANCELLED
    order.cancelled_at = timezone.now()
    order.cancel_reason = reason[:300]
    order.cancelled_by = user
    order.save(
        update_fields=["status", "cancelled_at", "cancel_reason", "cancelled_by", "updated_at"]
    )

    from apps.kitchen.models import KitchenTicket

    KitchenTicket.objects.filter(order=order).exclude(status=KitchenTicket.Status.COMPLETED).update(
        status=KitchenTicket.Status.CANCELLED
    )

    if order.table_id:
        order.table.mark_free(cleaning=False)

    record_audit(
        AuditLog.Action.VOID,
        user=user,
        obj=order,
        description=f"{order.number} iptal edildi. Gerekçe: {reason}",
        severity=AuditLog.Severity.CRITICAL,
    )
    notify(
        "Adisyon iptal edildi",
        body=f"{order.number} ({order.grand_total} ₺) iptal edildi. Gerekçe: {reason}",
        level=Notification.Level.WARNING,
        category=Notification.Category.FINANCE,
        roles=["owner", "general_manager", "restaurant_manager"],
    )
    _broadcast_order(order)
    return order


@transaction.atomic
def refund_order(
    order: Order,
    *,
    amount: Decimal,
    reason: str,
    description: str = "",
    method: str = Payment.Method.CASH,
    order_item: OrderItem | None = None,
    restock: bool = False,
    user=None,
    approver=None,
) -> Refund:
    """Kısmi veya tam iade yapar."""
    order.recalculate()
    amount = money(amount)
    if amount <= 0:
        raise OrderError("İade tutarı sıfırdan büyük olmalıdır.")
    refundable = money(order.paid_total - order.refunded_total)
    if amount > refundable:
        raise OrderError(f"İade tutarı ödenen tutarı aşamaz. İade edilebilir: {refundable} ₺")

    refund = Refund.objects.create(
        order=order,
        order_item=order_item,
        amount=amount,
        method=method,
        reason=reason,
        description=description[:300],
        approved_by=approver or user,
        restock=restock,
        created_by=user,
    )

    if restock and order_item is not None and order_item.stock_deducted:
        from apps.inventory.services import consume_for_order_item

        consume_for_order_item(order_item, user=user, reverse=True)
        order_item.stock_deducted = False
        order_item.save(update_fields=["stock_deducted", "updated_at"])

    order.recalculate()
    record_audit(
        AuditLog.Action.REFUND,
        user=user,
        obj=refund,
        description=(
            f"{order.number} · {amount} ₺ iade edildi ({refund.get_reason_display()}). "
            f"Onay: {(approver or user)}"
        ),
        severity=AuditLog.Severity.CRITICAL,
    )
    notify(
        "İade yapıldı",
        body=f"{order.number} adisyonunda {amount} ₺ iade işlemi gerçekleşti.",
        level=Notification.Level.WARNING,
        category=Notification.Category.FINANCE,
        roles=["owner", "general_manager", "restaurant_manager", "accountant"],
    )
    return refund


# ------------------------------------------------------------------
#  Hesap bölme / birleştirme / masa taşıma
# ------------------------------------------------------------------
@transaction.atomic
def split_order_by_items(order: Order, item_ids: list[int], *, user=None) -> Order:
    """Seçili satırları yeni bir adisyona taşır (hesap bölme)."""
    if order.is_paid:
        raise OrderError("Ödenmiş adisyon bölünemez.")
    items = list(order.items.filter(pk__in=item_ids).exclude(status=OrderItem.Status.CANCELLED))
    if not items:
        raise OrderError("Bölmek için en az bir satır seçmelisiniz.")
    if len(items) == order.active_items.count():
        raise OrderError("Tüm satırlar seçilemez; en az bir satır ana adisyonda kalmalıdır.")

    new_order = Order.objects.create(
        order_type=order.order_type,
        table=order.table,
        area=order.area,
        customer=order.customer,
        waiter=order.waiter,
        guest_count=1,
        parent_order=order,
        cash_session=order.cash_session,
        status=order.status if order.status != Order.Status.DRAFT else Order.Status.OPEN,
        created_by=user,
    )
    OrderItem.objects.filter(pk__in=[i.pk for i in items]).update(order=new_order)

    from apps.kitchen.models import KitchenTicket

    KitchenTicket.objects.filter(lines__order_item__in=items).distinct().update(order=new_order)

    order.recalculate()
    new_order.recalculate()
    record_audit(
        AuditLog.Action.UPDATE,
        user=user,
        obj=new_order,
        description=(
            f"{order.number} adisyonundan {len(items)} satır ayrılarak "
            f"{new_order.number} oluşturuldu."
        ),
        severity=AuditLog.Severity.NOTICE,
    )
    return new_order


@transaction.atomic
def split_order_evenly(order: Order, parts: int, *, user=None) -> list[dict]:
    """Hesabı eşit parçalara böler (ödeme planı önerir, yeni adisyon açmaz)."""
    if parts < 2:
        raise OrderError("En az 2 parçaya bölünebilir.")
    order.recalculate()
    share = money(order.grand_total / parts)
    plan = [{"part": i + 1, "amount": share} for i in range(parts)]
    # Yuvarlama farkını son parçaya ekle.
    difference = money(order.grand_total - share * parts)
    if difference:
        plan[-1]["amount"] = money(plan[-1]["amount"] + difference)
    return plan


@transaction.atomic
def split_order_by_seats(order: Order, *, user=None) -> list[dict]:
    """Koltuk numarasına göre hesap dökümü çıkarır."""
    order.recalculate()
    buckets: dict[int | None, Decimal] = {}
    for item in order.active_items:
        buckets.setdefault(item.seat_number, Decimal("0.00"))
        buckets[item.seat_number] += item.net_total
    return [
        {"seat": seat if seat is not None else "Ortak", "amount": money(total)}
        for seat, total in sorted(buckets.items(), key=lambda kv: (kv[0] is None, kv[0] or 0))
    ]


@transaction.atomic
def merge_orders(target: Order, source: Order, *, user=None) -> Order:
    """İki adisyonu birleştirir (kaynak adisyon iptal edilir)."""
    if target.pk == source.pk:
        raise OrderError("Adisyon kendisiyle birleştirilemez.")
    if target.is_paid or source.is_paid:
        raise OrderError("Ödenmiş adisyonlar birleştirilemez.")

    source.items.exclude(status=OrderItem.Status.CANCELLED).update(order=target)
    from apps.kitchen.models import KitchenTicket

    KitchenTicket.objects.filter(order=source).update(order=target)

    target.guest_count += source.guest_count
    target.save(update_fields=["guest_count", "updated_at"])

    source.status = Order.Status.CANCELLED
    source.cancelled_at = timezone.now()
    source.cancel_reason = f"{target.number} ile birleştirildi."
    source.cancelled_by = user
    source.save(
        update_fields=["status", "cancelled_at", "cancel_reason", "cancelled_by", "updated_at"]
    )
    if source.table_id and source.table_id != target.table_id:
        source.table.mark_free(cleaning=False)

    target.recalculate()
    record_audit(
        AuditLog.Action.UPDATE,
        user=user,
        obj=target,
        description=f"{source.number} adisyonu {target.number} ile birleştirildi.",
        severity=AuditLog.Severity.NOTICE,
    )
    return target


@transaction.atomic
def transfer_order_to_table(order: Order, table, *, user=None) -> Order:
    """Siparişi başka masaya taşır."""
    if order.is_paid:
        raise OrderError("Ödenmiş adisyon taşınamaz.")
    if table.status == table.Status.DISABLED:
        raise OrderError(f"{table.name} kullanım dışı.")
    occupant = table.active_order
    if occupant is not None and occupant.pk != order.pk:
        raise OrderError(f"{table.name} masasında zaten açık bir adisyon var ({occupant.number}).")

    old_table = order.table
    order.table = table
    order.area = table.area
    order.save(update_fields=["table", "area", "updated_at"])

    table.mark_occupied()
    if old_table and old_table.pk != table.pk:
        remaining = (
            Order.objects.filter(table=old_table)
            .exclude(status__in=[Order.Status.PAID, Order.Status.CANCELLED])
            .exists()
        )
        if not remaining:
            old_table.mark_free(cleaning=False)

    record_audit(
        AuditLog.Action.UPDATE,
        user=user,
        obj=order,
        description=(
            f"{order.number} adisyonu "
            f"{old_table.name if old_table else '-'} -> {table.name} masasına taşındı."
        ),
        severity=AuditLog.Severity.NOTICE,
    )
    return order


# ------------------------------------------------------------------
#  Canlı yayın
# ------------------------------------------------------------------
def _broadcast_order(order: Order) -> None:
    """Sipariş durum değişikliğini WebSocket ile yayınlar."""
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        layer = get_channel_layer()
        if layer is None:
            return
        async_to_sync(layer.group_send)(
            "orders",
            {
                "type": "order.event",
                "payload": {
                    "order_id": order.pk,
                    "number": order.number,
                    "status": order.status,
                    "status_label": order.get_status_display(),
                    "table": order.table.name if order.table_id else None,
                    "grand_total": str(order.grand_total),
                },
            },
        )
    except Exception:  # pragma: no cover - yayın hatası işlemi durdurmamalı
        logger.debug("Sipariş yayını yapılamadı", exc_info=True)
