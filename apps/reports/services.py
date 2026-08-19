"""Rapor hesaplamaları.

Tüm sorgular veritabanı tarafında toplanır (aggregate) — büyük veri
setlerinde Python'a satır çekilmez.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, DecimalField, F, Sum, Value
from django.db.models.functions import Coalesce, TruncDate, TruncHour
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core.utils import end_of_day, money, safe_divide, start_of_day
from apps.orders.models import Order, OrderItem, Payment, Refund

_DEC = DecimalField(max_digits=14, decimal_places=2)


def _zero():
    return Value(Decimal("0.00"), output_field=_DEC)


def paid_orders(start: date, end: date):
    return Order.objects.filter(
        status=Order.Status.PAID,
        closed_at__gte=start_of_day(start),
        closed_at__lte=end_of_day(end),
    )


# ------------------------------------------------------------------
#  Gösterge paneli
# ------------------------------------------------------------------
def dashboard_metrics(day: date | None = None) -> dict:
    """Yönetim paneli özet kartları."""
    day = day or timezone.localdate()
    yesterday = day - timedelta(days=1)
    week_start = day - timedelta(days=day.weekday())
    month_start = day.replace(day=1)

    today_qs = paid_orders(day, day)
    yesterday_qs = paid_orders(yesterday, yesterday)

    today = today_qs.aggregate(
        revenue=Coalesce(Sum("grand_total"), _zero()),
        orders=Count("id"),
        guests=Coalesce(Sum("guest_count"), Value(0)),
        discount=Coalesce(Sum("order_discount_total"), _zero()),
        tax=Coalesce(Sum("tax_total"), _zero()),
    )
    prev = yesterday_qs.aggregate(revenue=Coalesce(Sum("grand_total"), _zero()), orders=Count("id"))

    revenue = money(today["revenue"])
    order_count = today["orders"]
    average_ticket = money(safe_divide(revenue, max(order_count, 1)))

    # Masa doluluk
    from apps.floor.models import Table

    total_tables = Table.objects.filter(is_active=True).count()
    occupied = Table.objects.filter(is_active=True, status=Table.Status.OCCUPIED).count()

    # İptal ve iade
    cancelled = Order.objects.filter(
        status=Order.Status.CANCELLED,
        cancelled_at__gte=start_of_day(day),
        cancelled_at__lte=end_of_day(day),
    ).aggregate(count=Count("id"), total=Coalesce(Sum("grand_total"), _zero()))
    refunds = Refund.objects.filter(
        created_at__gte=start_of_day(day), created_at__lte=end_of_day(day)
    ).aggregate(count=Count("id"), total=Coalesce(Sum("amount"), _zero()))

    total_today = order_count + cancelled["count"]

    return {
        "date": day,
        "revenue": revenue,
        "order_count": order_count,
        "guest_count": today["guests"],
        "average_ticket": average_ticket,
        "average_per_guest": money(safe_divide(revenue, max(today["guests"], 1))),
        "discount_total": money(today["discount"]),
        "tax_total": money(today["tax"]),
        "revenue_change_percent": _change_percent(revenue, money(prev["revenue"])),
        "order_change_percent": _change_percent(Decimal(order_count), Decimal(prev["orders"] or 0)),
        "table_total": total_tables,
        "table_occupied": occupied,
        "occupancy_rate": round(occupied / total_tables * 100) if total_tables else 0,
        "cancel_count": cancelled["count"],
        "cancel_total": money(cancelled["total"]),
        "cancel_rate": round(cancelled["count"] / total_today * 100, 1) if total_today else 0,
        "refund_count": refunds["count"],
        "refund_total": money(refunds["total"]),
        "week_revenue": money(
            paid_orders(week_start, day).aggregate(t=Coalesce(Sum("grand_total"), _zero()))["t"]
        ),
        "month_revenue": money(
            paid_orders(month_start, day).aggregate(t=Coalesce(Sum("grand_total"), _zero()))["t"]
        ),
    }


def _change_percent(current: Decimal, previous: Decimal) -> float:
    if not previous:
        return 100.0 if current else 0.0
    return round(float((current - previous) / previous * 100), 1)


def revenue_series(days: int = 14) -> dict:
    """Günlük ciro grafiği verisi."""
    end = timezone.localdate()
    start = end - timedelta(days=days - 1)
    rows = (
        paid_orders(start, end)
        .annotate(day=TruncDate("closed_at"))
        .values("day")
        .annotate(revenue=Coalesce(Sum("grand_total"), _zero()), orders=Count("id"))
        .order_by("day")
    )
    lookup = {r["day"]: r for r in rows}
    labels, revenues, orders = [], [], []
    current = start
    while current <= end:
        row = lookup.get(current)
        labels.append(current.strftime("%d.%m"))
        revenues.append(float(row["revenue"]) if row else 0.0)
        orders.append(row["orders"] if row else 0)
        current += timedelta(days=1)
    return {"labels": labels, "revenue": revenues, "orders": orders}


def hourly_distribution(days: int = 7) -> dict:
    """Saatlik yoğunluk (personel planlaması için)."""
    end = timezone.localdate()
    start = end - timedelta(days=days - 1)
    rows = (
        paid_orders(start, end)
        .annotate(hour=TruncHour("closed_at"))
        .values("hour")
        .annotate(revenue=Coalesce(Sum("grand_total"), _zero()), orders=Count("id"))
    )
    buckets: dict[int, dict] = {h: {"orders": 0, "revenue": Decimal("0")} for h in range(24)}
    for row in rows:
        hour = timezone.localtime(row["hour"]).hour
        buckets[hour]["orders"] += row["orders"]
        buckets[hour]["revenue"] += row["revenue"]
    return {
        "labels": [f"{h:02d}:00" for h in range(24)],
        "orders": [round(buckets[h]["orders"] / days, 1) for h in range(24)],
        "revenue": [float(buckets[h]["revenue"] / days) for h in range(24)],
    }


def top_products(start: date, end: date, limit: int = 10, *, worst: bool = False):
    """En çok / en az satan ürünler."""
    qs = (
        OrderItem.objects.filter(
            order__status=Order.Status.PAID,
            order__closed_at__gte=start_of_day(start),
            order__closed_at__lte=end_of_day(end),
        )
        .exclude(status=OrderItem.Status.CANCELLED)
        .values("product_id", "product__name", "product__category__name")
        # NOT: takma ad "quantity" olamaz; aynı annotate içinde F("quantity")
        # model alanı yerine bu toplama başvurur ve hata oluşur.
        .annotate(
            total_quantity=Coalesce(Sum("quantity"), Value(Decimal("0"))),
            revenue=Coalesce(Sum(F("unit_price") * F("quantity"), output_field=_DEC), _zero()),
            order_count=Count("order", distinct=True),
        )
    )
    return list(qs.order_by("total_quantity" if worst else "-total_quantity")[:limit])


def category_breakdown(start: date, end: date) -> list[dict]:
    rows = (
        OrderItem.objects.filter(
            order__status=Order.Status.PAID,
            order__closed_at__gte=start_of_day(start),
            order__closed_at__lte=end_of_day(end),
        )
        .exclude(status=OrderItem.Status.CANCELLED)
        .values("product__category__name")
        .annotate(
            revenue=Coalesce(Sum(F("unit_price") * F("quantity"), output_field=_DEC), _zero()),
            total_quantity=Coalesce(Sum("quantity"), Value(Decimal("0"))),
        )
        .order_by("-revenue")
    )
    total = sum((r["revenue"] for r in rows), Decimal("0"))
    return [
        {
            "category": r["product__category__name"] or "Kategorisiz",
            "revenue": money(r["revenue"]),
            "quantity": r["total_quantity"],
            "percent": round(float(safe_divide(r["revenue"] * 100, total)), 1) if total else 0,
        }
        for r in rows
    ]


def payment_breakdown(start: date, end: date) -> list[dict]:
    rows = (
        Payment.objects.filter(
            status=Payment.Status.COMPLETED,
            paid_at__gte=start_of_day(start),
            paid_at__lte=end_of_day(end),
        )
        .values("method")
        .annotate(total=Coalesce(Sum("amount"), _zero()), count=Count("id"))
        .order_by("-total")
    )
    labels = dict(Payment.Method.choices)
    total = sum((r["total"] for r in rows), Decimal("0"))
    return [
        {
            "method": r["method"],
            "label": str(labels.get(r["method"], r["method"])),
            "total": money(r["total"]),
            "count": r["count"],
            "percent": round(float(safe_divide(r["total"] * 100, total)), 1) if total else 0,
        }
        for r in rows
    ]


def order_type_breakdown(start: date, end: date) -> list[dict]:
    rows = (
        paid_orders(start, end)
        .values("order_type")
        .annotate(total=Coalesce(Sum("grand_total"), _zero()), count=Count("id"))
        .order_by("-total")
    )
    labels = dict(Order.Type.choices)
    return [
        {
            "type": r["order_type"],
            "label": str(labels.get(r["order_type"], r["order_type"])),
            "total": money(r["total"]),
            "count": r["count"],
        }
        for r in rows
    ]


def profitability_report(start: date, end: date, limit: int = 50) -> list[dict]:
    """Ürün bazlı kârlılık (reçete maliyetine göre)."""
    from apps.catalog.models import Product

    sales = {
        row["product_id"]: row
        for row in OrderItem.objects.filter(
            order__status=Order.Status.PAID,
            order__closed_at__gte=start_of_day(start),
            order__closed_at__lte=end_of_day(end),
        )
        .exclude(status=OrderItem.Status.CANCELLED)
        .values("product_id")
        .annotate(
            total_quantity=Coalesce(Sum("quantity"), Value(Decimal("0"))),
            revenue=Coalesce(Sum(F("unit_price") * F("quantity"), output_field=_DEC), _zero()),
        )
    }

    rows = []
    for product in Product.objects.select_related("category").prefetch_related(
        "recipe__items__ingredient", "recipe__items__unit"
    ):
        stats = sales.get(product.pk)
        if not stats:
            continue
        quantity = Decimal(stats["total_quantity"])
        revenue = money(stats["revenue"])
        unit_cost = product.recipe_cost
        total_cost = money(unit_cost * quantity)
        profit = money(revenue - total_cost)
        rows.append(
            {
                "product": product,
                "quantity": quantity,
                "revenue": revenue,
                "unit_cost": unit_cost,
                "total_cost": total_cost,
                "profit": profit,
                "margin_percent": (
                    round(float(safe_divide(profit * 100, revenue)), 1) if revenue else 0
                ),
                "food_cost_percent": product.food_cost_percent,
                "has_recipe": hasattr(product, "recipe"),
            }
        )
    rows.sort(key=lambda r: r["profit"], reverse=True)
    return rows[:limit]


def staff_sales_report(start: date, end: date) -> list[dict]:
    rows = (
        paid_orders(start, end)
        .exclude(waiter__isnull=True)
        .values("waiter_id", "waiter__first_name", "waiter__last_name", "waiter__username")
        .annotate(
            revenue=Coalesce(Sum("grand_total"), _zero()),
            orders=Count("id"),
            guests=Coalesce(Sum("guest_count"), Value(0)),
            discounts=Coalesce(Sum("order_discount_total"), _zero()),
        )
        .order_by("-revenue")
    )
    return [
        {
            "name": f"{r['waiter__first_name']} {r['waiter__last_name']}".strip()
            or r["waiter__username"],
            "revenue": money(r["revenue"]),
            "orders": r["orders"],
            "guests": r["guests"],
            "average_ticket": money(safe_divide(r["revenue"], max(r["orders"], 1))),
            "discounts": money(r["discounts"]),
        }
        for r in rows
    ]


def void_discount_report(start: date, end: date) -> dict:
    """İptal, indirim ve iade raporu (sahtekârlık tespiti için)."""
    from apps.orders.models import OrderDiscount

    cancelled_items = (
        OrderItem.objects.filter(
            status=OrderItem.Status.CANCELLED,
            updated_at__gte=start_of_day(start),
            updated_at__lte=end_of_day(end),
        )
        .values("cancelled_by__username", "cancelled_by__first_name")
        .annotate(
            count=Count("id"),
            total=Coalesce(Sum(F("unit_price") * F("quantity"), output_field=_DEC), _zero()),
        )
        .order_by("-count")
    )
    discounts = (
        OrderDiscount.objects.filter(
            created_at__gte=start_of_day(start), created_at__lte=end_of_day(end)
        )
        .values("approved_by__username", "kind")
        .annotate(count=Count("id"), total=Coalesce(Sum("amount"), _zero()))
        .order_by("-total")
    )
    refunds = (
        Refund.objects.filter(created_at__gte=start_of_day(start), created_at__lte=end_of_day(end))
        .values("reason", "approved_by__username")
        .annotate(count=Count("id"), total=Coalesce(Sum("amount"), _zero()))
        .order_by("-total")
    )
    return {
        "cancelled_items": list(cancelled_items),
        "discounts": list(discounts),
        "refunds": list(refunds),
    }


def period_comparison(period: str = "day") -> dict:
    """Bugün/bu hafta/bu ay ile önceki dönemin karşılaştırması."""
    today = timezone.localdate()
    if period == "month":
        current_start = today.replace(day=1)
        prev_end = current_start - timedelta(days=1)
        prev_start = prev_end.replace(day=1)
    elif period == "week":
        current_start = today - timedelta(days=today.weekday())
        prev_start = current_start - timedelta(days=7)
        prev_end = current_start - timedelta(days=1)
    else:
        current_start = today
        prev_start = prev_end = today - timedelta(days=1)

    current = paid_orders(current_start, today).aggregate(
        revenue=Coalesce(Sum("grand_total"), _zero()), orders=Count("id")
    )
    previous = paid_orders(prev_start, prev_end).aggregate(
        revenue=Coalesce(Sum("grand_total"), _zero()), orders=Count("id")
    )
    return {
        "period": period,
        "current_revenue": money(current["revenue"]),
        "previous_revenue": money(previous["revenue"]),
        "current_orders": current["orders"],
        "previous_orders": previous["orders"],
        "revenue_change": _change_percent(money(current["revenue"]), money(previous["revenue"])),
        "order_change": _change_percent(
            Decimal(current["orders"]), Decimal(previous["orders"] or 0)
        ),
    }


# ------------------------------------------------------------------
#  Gün sonu kapanışı
# ------------------------------------------------------------------
@transaction.atomic
def build_daily_closing(day: date, *, session=None, user=None):
    """Gün sonu kapanış özetini hesaplar ve kaydeder."""
    from apps.reports.models import DailyClosing

    orders = paid_orders(day, day)
    totals = orders.aggregate(
        count=Count("id"),
        guests=Coalesce(Sum("guest_count"), Value(0)),
        gross=Coalesce(Sum("grand_total"), _zero()),
        discount=Coalesce(Sum("order_discount_total"), _zero()),
        item_discount=Coalesce(Sum("item_discount_total"), _zero()),
        service=Coalesce(Sum("service_charge"), _zero()),
        tax=Coalesce(Sum("tax_total"), _zero()),
        tip=Coalesce(Sum("tip_total"), _zero()),
    )
    refund_total = Refund.objects.filter(
        created_at__gte=start_of_day(day), created_at__lte=end_of_day(day)
    ).aggregate(t=Coalesce(Sum("amount"), _zero()))["t"]

    voided = Order.objects.filter(
        status=Order.Status.CANCELLED,
        cancelled_at__gte=start_of_day(day),
        cancelled_at__lte=end_of_day(day),
    ).aggregate(count=Count("id"), total=Coalesce(Sum("grand_total"), _zero()))

    gross = money(totals["gross"])
    closing, _created = DailyClosing.objects.update_or_create(
        closing_date=day,
        defaults={
            "cash_session": session,
            "order_count": totals["count"],
            "guest_count": totals["guests"],
            "gross_sales": gross,
            "discount_total": money(totals["discount"] + totals["item_discount"]),
            "refund_total": money(refund_total),
            "service_charge_total": money(totals["service"]),
            "tax_total": money(totals["tax"]),
            "net_sales": money(gross - refund_total),
            "tip_total": money(totals["tip"]),
            "payment_breakdown": {r["label"]: str(r["total"]) for r in payment_breakdown(day, day)},
            "category_breakdown": {
                r["category"]: str(r["revenue"]) for r in category_breakdown(day, day)
            },
            "cash_expected": session.expected_cash if session else Decimal("0.00"),
            "cash_counted": session.counted_cash if session else Decimal("0.00"),
            "void_count": voided["count"],
            "void_total": money(voided["total"]),
            "closed_by": user,
            "created_by": user,
        },
    )
    return closing


def dashboard_alerts() -> list[dict]:
    """Panelde gösterilecek uyarılar (stok, mutfak, finans)."""
    from apps.inventory.services import expiring_batches, low_stock_report
    from apps.kitchen.services import delayed_tickets

    alerts: list[dict] = []

    low = low_stock_report(limit=5)
    if low:
        alerts.append(
            {
                "level": "warning",
                "icon": "box-seam",
                "title": _("%(count)s malzeme kritik seviyede") % {"count": len(low)},
                "detail": ", ".join(i.name for i in low[:5]),
                "url": "/stok/uyarilar/",
            }
        )

    expiring = expiring_batches(3)
    if expiring.exists():
        alerts.append(
            {
                "level": "danger",
                "icon": "calendar-x",
                "title": _("%(count)s parti 3 gün içinde son kullanma tarihine ulaşıyor")
                % {"count": expiring.count()},
                "detail": ", ".join(b.ingredient.name for b in expiring[:5]),
                "url": "/stok/uyarilar/",
            }
        )

    delayed = delayed_tickets()
    if delayed:
        alerts.append(
            {
                "level": "danger",
                "icon": "clock-history",
                "title": _("%(count)s sipariş gecikmiş durumda") % {"count": len(delayed)},
                "detail": ", ".join(f"{t.number} ({t.elapsed_minutes} dk)" for t in delayed[:5]),
                "url": "/mutfak/",
            }
        )

    from apps.crm.models import Review

    unresolved = Review.objects.filter(rating__lte=2, is_resolved=False).count()
    if unresolved:
        alerts.append(
            {
                "level": "warning",
                "icon": "chat-left-dots",
                "title": _("%(count)s olumsuz yorum çözüm bekliyor") % {"count": unresolved},
                "detail": _("Müşteri memnuniyetini korumak için yanıtlayın."),
                "url": "/musteri/yorumlar/?unresolved=1",
            }
        )

    return alerts
