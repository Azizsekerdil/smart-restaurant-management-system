"""POS ve sipariş yönetimi görünümleri."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Prefetch, Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.decorators import manager_approval_required, require_permission
from apps.catalog.models import Category, Modifier, Product, ProductVariant
from apps.core.utils import money
from apps.crm.models import Customer
from apps.floor.models import Table
from apps.orders import services
from apps.orders.models import (
    CashMovement,
    CashSession,
    Order,
    OrderItem,
    Payment,
    Refund,
)


def _decimal(value, default="0"):
    try:
        return Decimal(str(value or default))
    except (InvalidOperation, ValueError):
        return Decimal(default)


def _json_error(exc: Exception, status: int = 400):
    detail = exc.messages[0] if isinstance(exc, ValidationError) and exc.messages else str(exc)
    return JsonResponse({"ok": False, "detail": detail}, status=status)


# ------------------------------------------------------------------
#  POS ekranı
# ------------------------------------------------------------------
@require_permission("pos.use")
def pos(request):
    """Dokunmatik POS ana ekranı."""
    categories = (
        Category.objects.filter(is_active=True, parent__isnull=True)
        .prefetch_related("children")
        .order_by("sort_order")
    )
    products = (
        Product.objects.filter(is_active=True)
        .select_related("category", "station")
        .prefetch_related("variants", "modifier_groups__options", "allergens")
        .order_by("category__sort_order", "sort_order", "name")
    )
    open_orders = (
        Order.objects.filter(
            status__in=[
                Order.Status.OPEN,
                Order.Status.SENT,
                Order.Status.PREPARING,
                Order.Status.READY,
                Order.Status.SERVED,
            ]
        )
        .select_related("table", "customer", "waiter")
        .order_by("-opened_at")[:50]
    )
    tables = (
        Table.objects.filter(is_active=True)
        .select_related("area")
        .order_by("area__sort_order", "name")
    )

    active_order = None
    order_id = request.GET.get("order")
    table_id = request.GET.get("table")
    if order_id:
        active_order = Order.objects.filter(pk=order_id).first()
    elif table_id:
        table = Table.objects.filter(pk=table_id).first()
        active_order = table.active_order if table else None

    return render(
        request,
        "orders/pos.html",
        {
            "page_title": "POS",
            "categories": categories,
            "products": products,
            "open_orders": open_orders,
            "tables": tables,
            "active_order": active_order,
            "order_types": Order.Type.choices,
            "payment_methods": Payment.Method.choices,
            "cash_session": services.active_cash_session(),
            "hide_sidebar": True,
        },
    )


@require_permission("pos.use")
def order_panel(request, pk: int):
    """Adisyon detay paneli (HTMX ile POS ekranına gömülür)."""
    order = get_object_or_404(
        Order.objects.select_related("table", "customer", "waiter").prefetch_related(
            Prefetch(
                "items",
                queryset=OrderItem.objects.select_related("product", "variant").prefetch_related(
                    "modifiers"
                ),
            ),
            "payments",
            "discounts",
        ),
        pk=pk,
    )
    order.recalculate()
    return render(
        request,
        "orders/_order_panel.html",
        {"order": order, "payment_methods": Payment.Method.choices},
    )


@require_permission("pos.use")
@require_POST
def order_create(request):
    order_type = request.POST.get("order_type", Order.Type.DINE_IN)
    table = None
    if order_type == Order.Type.DINE_IN:
        table = get_object_or_404(Table, pk=request.POST.get("table_id"))
    customer = None
    if request.POST.get("customer_id"):
        customer = Customer.objects.filter(pk=request.POST["customer_id"]).first()

    try:
        order = services.open_order(
            order_type=order_type,
            table=table,
            customer=customer,
            waiter=request.user,
            guest_count=int(request.POST.get("guest_count") or 1),
            note=request.POST.get("note", ""),
        )
    except ValidationError as exc:
        return _json_error(exc)

    if request.headers.get("HX-Request") or request.headers.get("Accept") == "application/json":
        return JsonResponse({"ok": True, "order_id": order.pk, "number": order.number})
    return redirect(f"/siparis/pos/?order={order.pk}")


@require_permission("pos.use")
@require_POST
def order_add_item(request, pk: int):
    order = get_object_or_404(Order, pk=pk)
    product = get_object_or_404(Product, pk=request.POST.get("product_id"))

    variant = None
    if request.POST.get("variant_id"):
        variant = ProductVariant.objects.filter(
            pk=request.POST["variant_id"], product=product
        ).first()

    modifier_ids = request.POST.getlist("modifier_ids")
    modifiers = list(Modifier.objects.filter(pk__in=modifier_ids, is_active=True))

    unit_price = None
    if request.POST.get("unit_price"):
        if not request.user.has_perm_code("pos.price_override"):
            return JsonResponse(
                {"ok": False, "detail": "Fiyat değiştirme yetkiniz yok."}, status=403
            )
        unit_price = _decimal(request.POST["unit_price"])

    try:
        item = services.add_item(
            order,
            product,
            quantity=_decimal(request.POST.get("quantity"), "1"),
            variant=variant,
            modifiers=modifiers,
            note=request.POST.get("note", ""),
            seat_number=(
                int(request.POST["seat_number"]) if request.POST.get("seat_number") else None
            ),
            course=int(request.POST.get("course") or 1),
            unit_price=unit_price,
            user=request.user,
        )
    except ValidationError as exc:
        return _json_error(exc)

    return JsonResponse(
        {
            "ok": True,
            "item_id": item.pk,
            "grand_total": str(order.grand_total),
            "item_count": order.item_count,
        }
    )


@require_permission("pos.use")
@require_POST
def order_update_item(request, pk: int, item_id: int):
    order = get_object_or_404(Order, pk=pk)
    item = get_object_or_404(OrderItem, pk=item_id, order=order)
    try:
        services.update_item_quantity(
            item, _decimal(request.POST.get("quantity"), "1"), user=request.user
        )
    except ValidationError as exc:
        return _json_error(exc)
    return JsonResponse({"ok": True, "grand_total": str(order.grand_total)})


@require_permission("pos.use")
@manager_approval_required("pos.void")
@require_POST
def order_cancel_item(request, pk: int, item_id: int):
    order = get_object_or_404(Order, pk=pk)
    item = get_object_or_404(OrderItem, pk=item_id, order=order)
    reason = (request.POST.get("reason") or "").strip()
    if not reason:
        return JsonResponse({"ok": False, "detail": "İptal gerekçesi zorunludur."}, status=400)
    try:
        services.cancel_item(item, reason=reason, user=request.user)
    except ValidationError as exc:
        return _json_error(exc)
    return JsonResponse({"ok": True, "grand_total": str(order.grand_total)})


@require_permission("pos.use")
@require_POST
def order_send_kitchen(request, pk: int):
    order = get_object_or_404(Order, pk=pk)
    tickets = services.send_to_kitchen(order, user=request.user)
    if not tickets:
        return JsonResponse({"ok": False, "detail": "Gönderilecek yeni satır yok."}, status=400)
    return JsonResponse(
        {"ok": True, "tickets": [t.number for t in tickets], "status": order.get_status_display()}
    )


@require_permission("pos.use")
@manager_approval_required("pos.discount")
@require_POST
def order_apply_discount(request, pk: int):
    order = get_object_or_404(Order, pk=pk)
    approval = getattr(request, "manager_approval", None)
    approver = approval.approver if approval else request.user
    try:
        if request.POST.get("coupon_code"):
            discount = services.apply_coupon(order, request.POST["coupon_code"], user=request.user)
        else:
            discount = services.apply_manual_discount(
                order,
                percent=_decimal(request.POST.get("percent")),
                amount=_decimal(request.POST.get("amount")),
                reason=request.POST.get("reason", ""),
                user=request.user,
                approver=approver,
            )
    except ValidationError as exc:
        return _json_error(exc)
    return JsonResponse(
        {"ok": True, "amount": str(discount.amount), "grand_total": str(order.grand_total)}
    )


@require_permission("pos.use")
@require_POST
def order_payment(request, pk: int):
    order = get_object_or_404(Order, pk=pk)
    try:
        payment = services.take_payment(
            order,
            method=request.POST.get("method", Payment.Method.CASH),
            amount=_decimal(request.POST.get("amount")),
            received=_decimal(request.POST["received"]) if request.POST.get("received") else None,
            reference=request.POST.get("reference", ""),
            user=request.user,
        )
    except ValidationError as exc:
        return _json_error(exc)
    return JsonResponse(
        {
            "ok": True,
            "payment_id": payment.pk,
            "change": str(payment.change_amount),
            "balance_due": str(order.balance_due),
            "is_paid": order.is_paid,
        }
    )


@require_permission("pos.use")
@manager_approval_required("pos.void")
@require_POST
def order_cancel(request, pk: int):
    order = get_object_or_404(Order, pk=pk)
    reason = (request.POST.get("reason") or "").strip()
    if not reason:
        return JsonResponse({"ok": False, "detail": "İptal gerekçesi zorunludur."}, status=400)
    try:
        services.cancel_order(order, reason=reason, user=request.user)
    except ValidationError as exc:
        return _json_error(exc)
    return JsonResponse({"ok": True})


@require_permission("pos.refund")
@require_POST
def order_refund(request, pk: int):
    order = get_object_or_404(Order, pk=pk)
    item = None
    if request.POST.get("order_item_id"):
        item = OrderItem.objects.filter(pk=request.POST["order_item_id"], order=order).first()
    try:
        refund = services.refund_order(
            order,
            amount=_decimal(request.POST.get("amount")),
            reason=request.POST.get("reason", Refund.Reason.OTHER),
            description=request.POST.get("description", ""),
            method=request.POST.get("method", Payment.Method.CASH),
            order_item=item,
            restock=request.POST.get("restock") == "on",
            user=request.user,
        )
    except ValidationError as exc:
        return _json_error(exc)
    return JsonResponse({"ok": True, "refund_id": refund.pk, "amount": str(refund.amount)})


@require_permission("pos.split")
@require_POST
def order_split(request, pk: int):
    order = get_object_or_404(Order, pk=pk)
    mode = request.POST.get("mode", "items")
    try:
        if mode == "even":
            plan = services.split_order_evenly(order, int(request.POST.get("parts") or 2))
            return JsonResponse(
                {
                    "ok": True,
                    "mode": "even",
                    "plan": [{"part": p["part"], "amount": str(p["amount"])} for p in plan],
                }
            )
        if mode == "seat":
            plan = services.split_order_by_seats(order)
            return JsonResponse(
                {
                    "ok": True,
                    "mode": "seat",
                    "plan": [{"seat": str(p["seat"]), "amount": str(p["amount"])} for p in plan],
                }
            )
        item_ids = [int(i) for i in request.POST.getlist("item_ids")]
        new_order = services.split_order_by_items(order, item_ids, user=request.user)
        return JsonResponse(
            {"ok": True, "mode": "items", "new_order_id": new_order.pk, "number": new_order.number}
        )
    except (ValidationError, ValueError) as exc:
        return _json_error(exc)


@require_permission("pos.split")
@require_POST
def order_merge(request, pk: int):
    target = get_object_or_404(Order, pk=pk)
    source = get_object_or_404(Order, pk=request.POST.get("source_order_id"))
    try:
        services.merge_orders(target, source, user=request.user)
    except ValidationError as exc:
        return _json_error(exc)
    return JsonResponse({"ok": True, "grand_total": str(target.grand_total)})


@require_permission("table.transfer")
@require_POST
def order_transfer(request, pk: int):
    order = get_object_or_404(Order, pk=pk)
    table = get_object_or_404(Table, pk=request.POST.get("table_id"))
    try:
        services.transfer_order_to_table(order, table, user=request.user)
    except ValidationError as exc:
        return _json_error(exc)
    return JsonResponse({"ok": True, "table": table.name})


# ------------------------------------------------------------------
#  Sipariş listesi ve fiş
# ------------------------------------------------------------------
@require_permission("order.view")
def order_list(request):
    orders = Order.objects.select_related("table", "customer", "waiter", "cashier")
    status = request.GET.get("status", "")
    order_type = request.GET.get("type", "")
    search = request.GET.get("q", "").strip()
    date_from = request.GET.get("from", "")
    date_to = request.GET.get("to", "")

    if status:
        orders = orders.filter(status=status)
    if order_type:
        orders = orders.filter(order_type=order_type)
    if search:
        orders = orders.filter(
            Q(number__icontains=search)
            | Q(table__name__icontains=search)
            | Q(customer__first_name__icontains=search)
        )
    if date_from:
        orders = orders.filter(opened_at__date__gte=date_from)
    if date_to:
        orders = orders.filter(opened_at__date__lte=date_to)

    paginator = Paginator(orders.order_by("-opened_at"), 30)
    page = paginator.get_page(request.GET.get("page", 1))

    totals = orders.aggregate(count=Count("id"), total=Sum("grand_total"), paid=Sum("paid_total"))

    return render(
        request,
        "orders/order_list.html",
        {
            "page_title": "Siparişler",
            "page_obj": page,
            "statuses": Order.Status.choices,
            "types": Order.Type.choices,
            "filters": {
                "status": status,
                "type": order_type,
                "q": search,
                "from": date_from,
                "to": date_to,
            },
            "totals": totals,
        },
    )


@require_permission("order.view")
def order_detail(request, pk: int):
    order = get_object_or_404(
        Order.objects.select_related("table", "customer", "waiter", "cashier").prefetch_related(
            "items__modifiers", "payments", "discounts", "refunds", "tickets__station"
        ),
        pk=pk,
    )
    order.recalculate()
    return render(
        request,
        "orders/order_detail.html",
        {"page_title": f"Adisyon {order.number}", "order": order},
    )


@require_permission("order.view")
def order_receipt(request, pk: int):
    """Yazdırılabilir fiş (80 mm termal yazıcı uyumlu)."""
    order = get_object_or_404(
        Order.objects.prefetch_related("items__modifiers", "payments", "discounts"), pk=pk
    )
    order.recalculate()
    return render(request, "orders/receipt.html", {"order": order})


@require_permission("order.view")
def order_receipt_pdf(request, pk: int):
    from apps.reports.exports import order_receipt_pdf as build_pdf

    order = get_object_or_404(Order, pk=pk)
    pdf = build_pdf(order)
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="adisyon-{order.number}.pdf"'
    return response


# ------------------------------------------------------------------
#  Teslimat panosu
# ------------------------------------------------------------------
@require_permission("delivery.view")
def delivery_board(request):
    orders = (
        Order.objects.filter(order_type=Order.Type.DELIVERY)
        .exclude(status=Order.Status.CANCELLED)
        .select_related("customer", "courier")
        .order_by("-opened_at")[:100]
    )
    from apps.accounts.models import User
    from apps.accounts.permissions import Role

    couriers = User.objects.filter(role=Role.COURIER, is_active=True)
    return render(
        request,
        "orders/delivery_board.html",
        {"page_title": "Teslimat Panosu", "orders": orders, "couriers": couriers},
    )


@require_permission("delivery.manage")
@require_POST
def delivery_assign(request, pk: int):
    from apps.accounts.models import User

    order = get_object_or_404(Order, pk=pk)
    courier = get_object_or_404(User, pk=request.POST.get("courier_id"))
    order.courier = courier
    order.save(update_fields=["courier", "updated_at"])
    messages.success(request, f"{order.number} siparişi {courier.display_name} kuryesine atandı.")
    return redirect("orders:delivery_board")


@require_permission("delivery.manage")
@require_POST
def delivery_complete(request, pk: int):
    order = get_object_or_404(Order, pk=pk)
    order.delivered_at = timezone.now()
    if order.status not in {Order.Status.PAID, Order.Status.CANCELLED}:
        order.status = Order.Status.SERVED
    order.save(update_fields=["delivered_at", "status", "updated_at"])
    messages.success(request, f"{order.number} teslim edildi olarak işaretlendi.")
    return redirect("orders:delivery_board")


# ------------------------------------------------------------------
#  Kasa
# ------------------------------------------------------------------
@require_permission("cash.manage")
def cash_session_view(request):
    session = services.active_cash_session()
    recent = CashSession.objects.order_by("-opened_at")[:20]
    return render(
        request,
        "orders/cash_session.html",
        {
            "page_title": "Kasa Yönetimi",
            "session": session,
            "recent_sessions": recent,
            "movement_kinds": CashMovement.Kind.choices,
        },
    )


@require_permission("cash.manage")
@require_POST
def cash_open(request):
    if services.active_cash_session():
        messages.warning(request, "Zaten açık bir kasa oturumu var.")
        return redirect("orders:cash_session")
    session = CashSession.objects.create(
        terminal_name=request.POST.get("terminal_name", "Kasa-1"),
        opened_by=request.user,
        opening_float=_decimal(request.POST.get("opening_float")),
        created_by=request.user,
    )
    from apps.core.models import AuditLog
    from apps.core.services import record_audit

    record_audit(
        AuditLog.Action.CASH,
        obj=session,
        description=f"Kasa açıldı: {session.number}, açılış {session.opening_float} ₺",
        request=request,
    )
    messages.success(request, f"Kasa açıldı ({session.number}).")
    return redirect("orders:cash_session")


@require_permission("cash.manage")
@require_POST
def cash_close(request):
    session = services.active_cash_session()
    if session is None:
        messages.error(request, "Açık kasa oturumu yok.")
        return redirect("orders:cash_session")

    session.counted_cash = _decimal(request.POST.get("counted_cash"))
    session.status = CashSession.Status.CLOSED
    session.closed_at = timezone.now()
    session.closed_by = request.user
    session.notes = request.POST.get("notes", "")
    session.save()

    from apps.core.models import AuditLog
    from apps.core.services import record_audit
    from apps.reports.services import build_daily_closing

    variance = session.cash_variance
    record_audit(
        AuditLog.Action.CASH,
        obj=session,
        description=(
            f"Kasa kapatıldı: {session.number}. Beklenen {session.expected_cash} ₺, "
            f"sayılan {session.counted_cash} ₺, fark {variance} ₺"
        ),
        severity=(
            AuditLog.Severity.WARNING if abs(variance) > Decimal("50") else AuditLog.Severity.INFO
        ),
        request=request,
    )
    closing = build_daily_closing(timezone.localdate(), session=session, user=request.user)
    messages.success(
        request, f"Kasa kapatıldı. Fark: {money(variance)} ₺. Gün sonu raporu oluşturuldu."
    )
    return redirect("reports:daily_closing_detail", pk=closing.pk)


@require_permission("cash.manage")
@require_POST
def cash_movement(request):
    session = services.active_cash_session()
    if session is None:
        messages.error(request, "Açık kasa oturumu yok.")
        return redirect("orders:cash_session")
    kind = request.POST.get("kind", CashMovement.Kind.PAID_OUT)
    amount = _decimal(request.POST.get("amount"))
    if kind in {CashMovement.Kind.PAID_OUT, CashMovement.Kind.DROP}:
        amount = -abs(amount)
    else:
        amount = abs(amount)
    CashMovement.objects.create(
        session=session,
        kind=kind,
        amount=amount,
        reason=request.POST.get("reason", "")[:300],
        created_by=request.user,
    )
    messages.success(request, "Kasa hareketi kaydedildi.")
    return redirect("orders:cash_session")
