"""İstatistik merkezi testleri."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.orders import services as order_services
from apps.orders.models import Order, Payment
from apps.reports import statistics


@pytest.fixture
def sold_orders(db, waiter, table, pizza, cola, cash_session):
    """Bugün ve dün için ödenmiş siparişler."""
    created = []
    for day_offset, count in ((0, 3), (1, 2)):
        for index in range(count):
            order = order_services.open_order(table=table, waiter=waiter, guest_count=2)
            order_services.add_item(order, pizza, quantity=Decimal("1"), user=waiter)
            if index % 2 == 0:
                order_services.add_item(order, cola, quantity=Decimal("2"), user=waiter)
            # Stok düşümü mutfağa gönderimde olur; gerçek akış izlenir.
            order_services.send_to_kitchen(order, user=waiter)
            order.refresh_from_db()
            order_services.take_payment(
                order,
                method=Payment.Method.CASH,
                amount=order.grand_total,
                user=waiter,
            )
            order.refresh_from_db()
            if day_offset:
                stamp = order.closed_at - timedelta(days=day_offset)
                Order.objects.filter(pk=order.pk).update(closed_at=stamp, opened_at=stamp)
            created.append(order)
    return created


# ==================================================================
#  Dönem yardımcıları
# ==================================================================
def test_previous_period_is_equal_length():
    start = timezone.localdate() - timedelta(days=6)
    end = timezone.localdate()

    prev_start, prev_end = statistics.previous_period(start, end)

    assert (prev_end - prev_start).days == (end - start).days
    assert prev_end == start - timedelta(days=1)


def test_period_presets_are_ordered_and_valid():
    presets = statistics.period_presets()
    assert {p["key"] for p in presets} >= {"7", "30", "month", "year"}
    for preset in presets:
        assert preset["start"] <= preset["end"]


# ==================================================================
#  Karşılaştırma
# ==================================================================
@pytest.mark.django_db
def test_comparison_returns_metrics_for_both_periods(sold_orders):
    today = timezone.localdate()
    result = statistics.comparison(today, today)

    assert result["current"]["order_count"] == 3
    labels = {m["label"] for m in result["metrics"]}
    assert {"Ciro", "Sipariş", "Ortalama sepet"} <= labels

    revenue = next(m for m in result["metrics"] if m["key"] == "revenue")
    assert revenue["current"] > 0
    assert revenue["higher_is_better"] is True


@pytest.mark.django_db
def test_discount_metric_is_not_higher_is_better(sold_orders):
    today = timezone.localdate()
    result = statistics.comparison(today, today)
    discount = next(m for m in result["metrics"] if m["key"] == "discount")
    assert discount["higher_is_better"] is False


@pytest.mark.django_db
def test_comparison_on_empty_period_does_not_crash(db):
    today = timezone.localdate()
    result = statistics.comparison(today, today)
    assert result["current"]["order_count"] == 0
    assert result["current"]["revenue"] == Decimal("0.00")


# ==================================================================
#  Seriler
# ==================================================================
@pytest.mark.django_db
def test_daily_series_aligns_previous_period(sold_orders):
    today = timezone.localdate()
    series = statistics.daily_series(today - timedelta(days=2), today)

    assert len(series["labels"]) == 3
    assert len(series["current"]) == 3
    assert len(series["previous"]) == 3
    assert sum(series["current"]) > 0


@pytest.mark.django_db
def test_daily_series_can_skip_previous(sold_orders):
    today = timezone.localdate()
    series = statistics.daily_series(today, today, with_previous=False)
    assert "previous" not in series


@pytest.mark.django_db
def test_monthly_series_returns_parallel_lists(sold_orders):
    series = statistics.monthly_series(months=3)
    assert len(series["labels"]) == len(series["revenue"]) == len(series["orders"])


# ==================================================================
#  Gün / saat
# ==================================================================
@pytest.mark.django_db
def test_weekday_breakdown_uses_average_not_total(sold_orders):
    """Aynı gün iki kez geçtiğinde ortalama alınmalı, toplam değil."""
    today = timezone.localdate()
    rows = statistics.weekday_breakdown(today - timedelta(days=13), today)

    assert len(rows) == 7
    for row in rows:
        if row["observed_days"]:
            assert row["average_revenue"] <= row["revenue"]
        assert isinstance(row["reliable"], bool)


@pytest.mark.django_db
def test_weekday_marks_low_sample_as_unreliable(sold_orders):
    today = timezone.localdate()
    rows = statistics.weekday_breakdown(today, today)
    # Tek günlük aralıkta hiçbir gün güvenilir sayılmamalı
    assert all(not row["reliable"] for row in rows)


@pytest.mark.django_db
def test_matrix_reports_observation_counts(sold_orders):
    today = timezone.localdate()
    matrix = statistics.weekday_hour_matrix(today - timedelta(days=1), today)

    assert matrix["total_orders"] == 5
    assert matrix["min_observations"] == statistics.MIN_OBSERVATIONS
    assert len(matrix["rows"]) == 7
    for row in matrix["rows"]:
        assert len(row["cells"]) == len(matrix["hours"])
        for cell in row["cells"]:
            assert 0 <= cell["intensity"] <= 100


@pytest.mark.django_db
def test_matrix_on_empty_data_returns_default_hours(db):
    today = timezone.localdate()
    matrix = statistics.weekday_hour_matrix(today, today)
    assert matrix["total_orders"] == 0
    assert matrix["hours"]  # boş dönemde bile eksen çizilebilmeli


# ==================================================================
#  Müşteri / stok / servis
# ==================================================================
@pytest.mark.django_db
def test_customer_statistics_counts_anonymous_orders(sold_orders):
    today = timezone.localdate()
    stats = statistics.customer_statistics(today, today)

    assert stats["anonymous_orders"] == 3
    assert stats["identified_customers"] == 0
    assert stats["identification_rate"] == 0


@pytest.mark.django_db
def test_inventory_statistics_reports_consumption(sold_orders):
    today = timezone.localdate()
    stats = statistics.inventory_statistics(today, today)

    # Pizza reçetesi stoktan düşüldüğü için tüketim değeri oluşmalı
    assert stats["consumption_value"] > 0
    assert stats["waste_value"] == Decimal("0.00")
    assert stats["stock_value"] > 0


@pytest.mark.django_db
def test_service_statistics_ignores_absurd_durations(sold_orders):
    today = timezone.localdate()

    # Kapatılması unutulmuş adisyon: 20 gün açık kalmış
    stale = sold_orders[0]
    Order.objects.filter(pk=stale.pk).update(opened_at=stale.closed_at - timedelta(days=20))

    stats = statistics.service_statistics(today, today)

    assert stats["measured_orders"] == 2  # üçüncüsü elendi
    assert stats["average_service_minutes"] < 480


@pytest.mark.django_db
def test_service_statistics_on_empty_period(db):
    today = timezone.localdate()
    stats = statistics.service_statistics(today, today)
    assert stats["average_service_minutes"] == 0
    assert stats["busiest_day"] is None


# ==================================================================
#  Toplu derleme ve ekran
# ==================================================================
@pytest.mark.django_db
def test_build_statistics_returns_all_sections(sold_orders):
    today = timezone.localdate()
    data = statistics.build_statistics(today - timedelta(days=6), today)

    for key in (
        "comparison",
        "daily",
        "monthly",
        "weekday",
        "matrix",
        "categories",
        "payments",
        "payment_chart",
        "order_types",
        "staff",
        "top_products",
        "customers",
        "inventory",
        "service",
    ):
        assert key in data, f"eksik bölüm: {key}"


@pytest.mark.django_db
def test_payment_chart_is_json_serializable(sold_orders):
    import json

    today = timezone.localdate()
    data = statistics.build_statistics(today, today)
    # Decimal doğrudan json_script'e verilemez; float'a çevrilmiş olmalı
    json.dumps(data["payment_chart"])


@pytest.mark.django_db
def test_statistics_page_renders(client, owner, sold_orders):
    client.force_login(owner)
    response = client.get(reverse("reports:statistics"))

    assert response.status_code == 200
    assert "İstatistik" in response.content.decode("utf-8")


@pytest.mark.django_db
def test_statistics_preset_changes_period(client, owner, sold_orders):
    client.force_login(owner)
    response = client.get(reverse("reports:statistics"), {"donem": "7"})

    assert response.status_code == 200
    assert response.context["preset_key"] == "7"
    assert (response.context["end"] - response.context["start"]).days == 6


@pytest.mark.django_db
def test_waiter_cannot_open_statistics(client, waiter):
    client.force_login(waiter)
    assert client.get(reverse("reports:statistics")).status_code == 403


@pytest.mark.django_db
def test_accountant_can_open_statistics(client, sold_orders, db):
    from django.contrib.auth import get_user_model

    from apps.accounts.permissions import Role

    accountant = get_user_model().objects.create_user(
        username="muhasebe", password="Test!2026Pass", role=Role.ACCOUNTANT
    )
    client.force_login(accountant)
    assert client.get(reverse("reports:statistics")).status_code == 200


@pytest.mark.django_db
def test_statistics_excel_export(client, owner, sold_orders):
    client.force_login(owner)
    response = client.get(reverse("reports:export_statistics"))

    assert response.status_code == 200
    assert response["Content-Type"].startswith("application/vnd.openxmlformats-officedocument")
    assert response.content[:4] == b"PK\x03\x04"
