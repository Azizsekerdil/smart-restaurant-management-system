"""İstatistik merkezi hesaplamaları.

`services.py` tek tek raporlar için tasarlanmıştır. Bu modül ise
**karşılaştırmalı** bakış sunar: seçilen dönemi bir önceki eşit uzunlukta
dönemle yan yana koyar ve eğilimleri çıkarır.

Ölçüm değil, tahmin yapan yerlerde (yoğunluk matrisi, büyüme oranı)
sonucun hangi veri hacmine dayandığı da döndürülür; az veriyle üretilmiş
bir yüzde, çok veriyle üretilmiş olanla aynı güvende değildir ve arayüz
bunu göstermek zorundadır.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, F, Sum, Value
from django.db.models.functions import Coalesce, TruncDate, TruncMonth
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.utils import end_of_day, money, safe_divide, start_of_day
from apps.orders.models import Order, OrderItem
from apps.reports.services import _change_percent, _zero, paid_orders

_DEC = DecimalField(max_digits=14, decimal_places=2)

#: Gün adları gecikmeli çevrilir: modül yüklenirken dil belli değildir,
#: istek anında kullanıcının diline göre çözülmelidir.
WEEKDAY_NAMES = [
    _("Pazartesi"),
    _("Salı"),
    _("Çarşamba"),
    _("Perşembe"),
    _("Cuma"),
    _("Cumartesi"),
    _("Pazar"),
]
WEEKDAY_SHORT = [_("Pzt"), _("Sal"), _("Çar"), _("Per"), _("Cum"), _("Cmt"), _("Paz")]

#: Bir hücrenin "anlamlı" sayılması için gereken asgari gözlem sayısı.
#: Altındaki hücreler arayüzde soluk gösterilir; tek bir günün rastlantısı
#: haftalık bir eğilim gibi okunmamalıdır.
MIN_OBSERVATIONS = 3


# ==================================================================
#  Dönem yardımcıları
# ==================================================================
def previous_period(start: date, end: date) -> tuple[date, date]:
    """Karşılaştırma için hemen önceki eşit uzunlukta dönem."""
    length = (end - start).days + 1
    previous_end = start - timedelta(days=1)
    return previous_end - timedelta(days=length - 1), previous_end


def period_presets() -> list[dict]:
    """Arayüzdeki hazır dönem seçenekleri."""
    today = timezone.localdate()
    month_start = today.replace(day=1)
    last_month_end = month_start - timedelta(days=1)
    return [
        {"key": "7", "label": _("Son 7 gün"), "start": today - timedelta(days=6), "end": today},
        {"key": "30", "label": _("Son 30 gün"), "start": today - timedelta(days=29), "end": today},
        {"key": "90", "label": _("Son 90 gün"), "start": today - timedelta(days=89), "end": today},
        {"key": "month", "label": _("Bu ay"), "start": month_start, "end": today},
        {
            "key": "last_month",
            "label": _("Geçen ay"),
            "start": last_month_end.replace(day=1),
            "end": last_month_end,
        },
        {"key": "year", "label": _("Bu yıl"), "start": today.replace(month=1, day=1), "end": today},
    ]


# ==================================================================
#  Özet ve karşılaştırma
# ==================================================================
def _aggregate_period(start: date, end: date) -> dict:
    orders = paid_orders(start, end).aggregate(
        revenue=Coalesce(Sum("grand_total"), _zero()),
        net=Coalesce(Sum(F("grand_total") - F("tax_total"), output_field=_DEC), _zero()),
        tax=Coalesce(Sum("tax_total"), _zero()),
        discount=Coalesce(Sum("order_discount_total"), _zero()),
        count=Count("id"),
        guests=Coalesce(Sum("guest_count"), Value(0)),
    )
    items = (
        OrderItem.objects.filter(
            order__status=Order.Status.PAID,
            order__closed_at__gte=start_of_day(start),
            order__closed_at__lte=end_of_day(end),
        )
        .exclude(status=OrderItem.Status.CANCELLED)
        .aggregate(quantity=Coalesce(Sum("quantity"), Value(Decimal("0"))))
    )

    count = orders["count"]
    guests = orders["guests"] or 0
    revenue = money(orders["revenue"])
    days = (end - start).days + 1

    return {
        "revenue": revenue,
        "net_revenue": money(orders["net"]),
        "tax": money(orders["tax"]),
        "discount": money(orders["discount"]),
        "order_count": count,
        "guest_count": guests,
        "item_count": items["quantity"],
        "average_ticket": money(safe_divide(revenue, max(count, 1))),
        "average_per_guest": money(safe_divide(revenue, max(guests, 1))),
        "daily_average": money(safe_divide(revenue, max(days, 1))),
        "days": days,
    }


def comparison(start: date, end: date) -> dict:
    """Seçilen dönem ile önceki eşit dönemin karşılaştırması."""
    prev_start, prev_end = previous_period(start, end)
    current = _aggregate_period(start, end)
    previous = _aggregate_period(prev_start, prev_end)

    metrics = []
    for key, label, kind in [
        ("revenue", _("Ciro"), "money"),
        ("order_count", _("Sipariş"), "count"),
        ("average_ticket", _("Ortalama sepet"), "money"),
        ("guest_count", _("Misafir"), "count"),
        ("average_per_guest", _("Kişi başı"), "money"),
        ("daily_average", _("Günlük ortalama"), "money"),
        ("discount", _("İndirim"), "money"),
        ("net_revenue", _("KDV hariç ciro"), "money"),
    ]:
        now_value = current[key]
        old_value = previous[key]
        metrics.append(
            {
                "key": key,
                "label": label,
                "kind": kind,
                "current": now_value,
                "previous": old_value,
                "change": _change_percent(Decimal(now_value), Decimal(old_value)),
                # İndirimde artış iyi bir haber değildir.
                "higher_is_better": key != "discount",
            }
        )

    return {
        "current": current,
        "previous": previous,
        "previous_start": prev_start,
        "previous_end": prev_end,
        "metrics": metrics,
    }


# ==================================================================
#  Zaman serileri
# ==================================================================
def daily_series(start: date, end: date, *, with_previous: bool = True) -> dict:
    """Günlük ciro serisi; istenirse önceki dönem de aynı eksende."""

    def _series(period_start: date, period_end: date) -> list[float]:
        rows = (
            paid_orders(period_start, period_end)
            .annotate(day=TruncDate("closed_at"))
            .values("day")
            .annotate(revenue=Coalesce(Sum("grand_total"), _zero()))
        )
        lookup = {row["day"]: float(row["revenue"]) for row in rows}
        values, cursor = [], period_start
        while cursor <= period_end:
            values.append(lookup.get(cursor, 0.0))
            cursor += timedelta(days=1)
        return values

    labels, cursor = [], start
    while cursor <= end:
        labels.append(cursor.strftime("%d.%m"))
        cursor += timedelta(days=1)

    result = {"labels": labels, "current": _series(start, end)}
    if with_previous:
        prev_start, prev_end = previous_period(start, end)
        # Önceki dönem aynı uzunlukta olduğu için etiketler hizalanır.
        result["previous"] = _series(prev_start, prev_end)
        result["previous_label"] = f"{prev_start:%d.%m} – {prev_end:%d.%m}"
    return result


def monthly_series(months: int = 12) -> dict:
    """Aylık ciro eğilimi."""
    today = timezone.localdate()
    first = (today.replace(day=1) - timedelta(days=31 * (months - 1))).replace(day=1)

    rows = (
        Order.objects.filter(status=Order.Status.PAID, closed_at__gte=start_of_day(first))
        .annotate(month=TruncMonth("closed_at"))
        .values("month")
        .annotate(revenue=Coalesce(Sum("grand_total"), _zero()), orders=Count("id"))
        .order_by("month")
    )

    labels, revenue, orders = [], [], []
    for row in rows:
        stamp = (
            timezone.localtime(row["month"]) if timezone.is_aware(row["month"]) else row["month"]
        )
        labels.append(f"{stamp.month:02d}.{stamp.year}")
        revenue.append(float(row["revenue"]))
        orders.append(row["orders"])

    return {"labels": labels, "revenue": revenue, "orders": orders}


def weekday_breakdown(start: date, end: date) -> list[dict]:
    """Haftanın günlerine göre ortalama performans.

    Toplam yerine **ortalama** kullanılır: 30 günlük bir aralıkta bazı
    günler 5 kez, bazıları 4 kez geçer; ham toplam bu yüzden yanıltıcıdır.
    """
    rows = (
        paid_orders(start, end)
        .annotate(day=TruncDate("closed_at"))
        .values("day")
        .annotate(revenue=Coalesce(Sum("grand_total"), _zero()), orders=Count("id"))
    )

    buckets: dict[int, dict] = {
        index: {"revenue": Decimal("0"), "orders": 0, "days": 0} for index in range(7)
    }
    for row in rows:
        weekday = row["day"].weekday()
        buckets[weekday]["revenue"] += row["revenue"]
        buckets[weekday]["orders"] += row["orders"]
        buckets[weekday]["days"] += 1

    best = max((b["revenue"] for b in buckets.values()), default=Decimal("0"))
    return [
        {
            "index": index,
            "name": WEEKDAY_NAMES[index],
            "short": WEEKDAY_SHORT[index],
            "revenue": money(bucket["revenue"]),
            "orders": bucket["orders"],
            "observed_days": bucket["days"],
            "average_revenue": money(safe_divide(bucket["revenue"], max(bucket["days"], 1))),
            "average_orders": round(bucket["orders"] / bucket["days"], 1) if bucket["days"] else 0,
            "share_percent": (
                round(float(safe_divide(bucket["revenue"] * 100, best)), 1) if best else 0
            ),
            "reliable": bucket["days"] >= MIN_OBSERVATIONS,
        }
        for index, bucket in buckets.items()
    ]


def weekday_hour_matrix(start: date, end: date) -> dict:
    """Gün × saat yoğunluk matrisi (personel planlaması için).

    Her hücre, o gün ve saatte gözlenen **ortalama** sipariş sayısıdır.
    Kaç kez gözlendiği de döndürülür; tek bir gözleme dayanan hücre
    güvenilir bir örüntü değildir.
    """
    orders = paid_orders(start, end).values_list("closed_at", flat=True)

    counts: dict[tuple[int, int], int] = {}
    day_seen: dict[int, set] = {index: set() for index in range(7)}

    for closed_at in orders:
        local = timezone.localtime(closed_at)
        weekday, hour = local.weekday(), local.hour
        counts[(weekday, hour)] = counts.get((weekday, hour), 0) + 1
        day_seen[weekday].add(local.date())

    # Hangi saatlerde hiç iş yok? Boş sütunları göstermemek için aralığı daralt.
    active_hours = sorted({hour for _, hour in counts}) or list(range(10, 24))
    first_hour, last_hour = active_hours[0], active_hours[-1]
    hours = list(range(first_hour, last_hour + 1))

    peak = 0.0
    rows = []
    for weekday in range(7):
        occurrences = max(len(day_seen[weekday]), 1)
        cells = []
        for hour in hours:
            total = counts.get((weekday, hour), 0)
            average = round(total / occurrences, 1)
            peak = max(peak, average)
            cells.append(
                {
                    "hour": hour,
                    "total": total,
                    "average": average,
                    "reliable": len(day_seen[weekday]) >= MIN_OBSERVATIONS,
                }
            )
        rows.append(
            {
                "weekday": weekday,
                "name": WEEKDAY_NAMES[weekday],
                "short": WEEKDAY_SHORT[weekday],
                "observed_days": len(day_seen[weekday]),
                "cells": cells,
            }
        )

    # Yoğunluğu 0-100 arasına ölçekle (renk tonu için)
    for row in rows:
        for cell in row["cells"]:
            cell["intensity"] = round(cell["average"] / peak * 100) if peak else 0

    return {
        "hours": [f"{hour:02d}" for hour in hours],
        "rows": rows,
        "peak": peak,
        "total_orders": sum(counts.values()),
        "min_observations": MIN_OBSERVATIONS,
    }


# ==================================================================
#  Müşteri istatistikleri
# ==================================================================
def customer_statistics(start: date, end: date) -> dict:
    """Müşteri davranışı: yeni/tekrar eden, en değerliler."""
    from apps.crm.models import Customer

    period_orders = paid_orders(start, end)

    identified = period_orders.exclude(customer__isnull=True)
    anonymous_count = period_orders.filter(customer__isnull=True).count()

    per_customer = (
        identified.values("customer_id")
        .annotate(revenue=Coalesce(Sum("grand_total"), _zero()), visits=Count("id"))
        .order_by("-revenue")
    )
    rows = list(per_customer)

    repeat = sum(1 for row in rows if row["visits"] > 1)
    new_customers = Customer.objects.filter(
        created_at__gte=start_of_day(start), created_at__lte=end_of_day(end)
    ).count()

    top_ids = [row["customer_id"] for row in rows[:10]]
    customers = {c.pk: c for c in Customer.objects.filter(pk__in=top_ids)}
    top = [
        {
            "customer": customers.get(row["customer_id"]),
            "revenue": money(row["revenue"]),
            "visits": row["visits"],
            "average": money(safe_divide(row["revenue"], max(row["visits"], 1))),
        }
        for row in rows[:10]
        if row["customer_id"] in customers
    ]

    identified_count = len(rows)
    total_orders = period_orders.count()

    return {
        "identified_customers": identified_count,
        "identified_orders": identified.count(),
        "anonymous_orders": anonymous_count,
        "identification_rate": (
            round(identified.count() / total_orders * 100, 1) if total_orders else 0
        ),
        "new_customers": new_customers,
        "repeat_customers": repeat,
        "repeat_rate": round(repeat / identified_count * 100, 1) if identified_count else 0,
        "average_visits": (
            round(sum(row["visits"] for row in rows) / identified_count, 1)
            if identified_count
            else 0
        ),
        "top_customers": top,
        "segments": list(
            Customer.objects.filter(is_active=True)
            .values("segment")
            .annotate(count=Count("id"), value=Coalesce(Sum("lifetime_value"), _zero()))
            .order_by("-count")
        ),
    }


# ==================================================================
#  Stok istatistikleri
# ==================================================================
def inventory_statistics(start: date, end: date) -> dict:
    """Fire, tüketim ve stok değeri."""
    from apps.inventory.models import Ingredient, StockBatch, StockMovement

    movements = StockMovement.objects.filter(
        created_at__gte=start_of_day(start), created_at__lte=end_of_day(end)
    )

    def _value(queryset) -> Decimal:
        # Miktar çıkışlarda negatiftir; parasal değeri mutlak alırız.
        total = queryset.aggregate(
            total=Coalesce(
                Sum(F("quantity") * F("unit_cost"), output_field=_DEC),
                _zero(),
            )
        )["total"]
        return money(abs(total))

    waste_value = _value(movements.filter(movement_type=StockMovement.Type.WASTE))
    consumption_value = _value(movements.filter(movement_type=StockMovement.Type.SALE))
    purchase_value = _value(movements.filter(movement_type=StockMovement.Type.PURCHASE))

    def _by_ingredient(movement_type: str) -> list[dict]:
        # NOT: takma ad "quantity" olamaz; aynı annotate içinde F("quantity")
        # model alanı yerine bu toplamaya başvurur ve hata oluşur.
        rows = list(
            movements.filter(movement_type=movement_type)
            .values("ingredient__name", "ingredient__base_unit__code")
            .annotate(
                total_quantity=Coalesce(Sum("quantity"), Value(Decimal("0"))),
                value=Coalesce(Sum(F("quantity") * F("unit_cost"), output_field=_DEC), _zero()),
            )
            # Çıkışlar negatif tutulur; en büyük çıkış en küçük değerdir.
            .order_by("value")[:10]
        )
        for row in rows:
            row["total_quantity"] = abs(row["total_quantity"])
            row["value"] = money(abs(row["value"]))
        return rows

    top_waste = _by_ingredient(StockMovement.Type.WASTE)
    top_consumed = _by_ingredient(StockMovement.Type.SALE)

    # Stok değeri parti (lot) bazında tutulur; her partinin kendi maliyeti
    # vardır ve özet tabloda birim maliyet bulunmaz.
    stock_value = money(
        StockBatch.objects.filter(remaining_quantity__gt=0).aggregate(
            total=Coalesce(
                Sum(F("remaining_quantity") * F("unit_cost"), output_field=_DEC),
                _zero(),
            )
        )["total"]
    )

    critical = (
        Ingredient.objects.filter(is_active=True, stock_items__quantity__lte=F("critical_level"))
        .distinct()
        .count()
    )

    return {
        "waste_value": waste_value,
        "consumption_value": consumption_value,
        "purchase_value": purchase_value,
        "waste_percent": (
            round(float(safe_divide(waste_value * 100, consumption_value + waste_value)), 1)
            if (consumption_value + waste_value)
            else 0
        ),
        "top_waste": top_waste,
        "top_consumed": top_consumed,
        "stock_value": stock_value,
        "critical_count": critical,
    }


# ==================================================================
#  Operasyon istatistikleri
# ==================================================================
def service_statistics(start: date, end: date) -> dict:
    """Servis hızı ve masa devir sayıları."""
    from apps.floor.models import Table

    closed = paid_orders(start, end).exclude(closed_at__isnull=True)

    durations = []
    for opened_at, closed_at in closed.values_list("opened_at", "closed_at")[:5000]:
        minutes = (closed_at - opened_at).total_seconds() / 60
        # Kapatılmayı unutulmuş adisyonlar ortalamayı bozar; 8 saatten uzun
        # olanlar veri hatası kabul edilir.
        if 0 < minutes < 480:
            durations.append(minutes)

    table_count = Table.objects.filter(is_active=True).count()
    days = (end - start).days + 1
    dine_in = closed.filter(order_type=Order.Type.DINE_IN).count()

    return {
        "average_service_minutes": round(sum(durations) / len(durations), 1) if durations else 0,
        "measured_orders": len(durations),
        "table_turnover": (round(dine_in / table_count / days, 2) if table_count and days else 0),
        "table_count": table_count,
        "busiest_day": _busiest_day(start, end),
    }


def _busiest_day(start: date, end: date) -> dict | None:
    row = (
        paid_orders(start, end)
        .annotate(day=TruncDate("closed_at"))
        .values("day")
        .annotate(revenue=Coalesce(Sum("grand_total"), _zero()), orders=Count("id"))
        .order_by("-revenue")
        .first()
    )
    if not row:
        return None
    return {
        "date": row["day"],
        "revenue": money(row["revenue"]),
        "orders": row["orders"],
        "weekday": WEEKDAY_NAMES[row["day"].weekday()],
    }


# ==================================================================
#  Toplu derleme
# ==================================================================
def build_statistics(start: date, end: date) -> dict:
    """İstatistik ekranının tüm verisi."""
    from apps.reports import services

    payments = services.payment_breakdown(start, end)
    return {
        # Grafiğe giden veri JSON'a çevrilebilir olmalı; Decimal değerler
        # doğrudan json_script'e verilemez.
        "payment_chart": [
            {"label": row["label"], "total": float(row["total"])} for row in payments
        ],
        "start": start,
        "end": end,
        "comparison": comparison(start, end),
        "daily": daily_series(start, end),
        "monthly": monthly_series(),
        "weekday": weekday_breakdown(start, end),
        "matrix": weekday_hour_matrix(start, end),
        "categories": services.category_breakdown(start, end),
        "payments": payments,
        "order_types": services.order_type_breakdown(start, end),
        "staff": services.staff_sales_report(start, end),
        "top_products": services.top_products(start, end, limit=10),
        "worst_products": services.top_products(start, end, limit=5, worst=True),
        "customers": customer_statistics(start, end),
        "inventory": inventory_statistics(start, end),
        "service": service_statistics(start, end),
    }
