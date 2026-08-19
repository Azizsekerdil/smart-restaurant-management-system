"""Rapor hesaplamaları ve PDF/Excel/CSV dışa aktarma testleri."""

from __future__ import annotations

import io
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.orders import services as order_services
from apps.orders.models import Payment
from apps.reports import services as report_services

pytestmark = pytest.mark.django_db


@pytest.fixture
def sales(table, waiter, cashier, pizza, cola):
    """3 kapatılmış sipariş üretir."""
    orders = []
    for _ in range(3):
        order = order_services.open_order(table=table, waiter=waiter, guest_count=2)
        order_services.add_item(order, pizza)
        order_services.add_item(order, cola)
        order_services.take_payment(
            order, method=Payment.Method.CARD, amount=order.grand_total, user=cashier
        )
        order.refresh_from_db()
        orders.append(order)
        table.status = table.Status.FREE
        table.save()
    return orders


def test_dashboard_metrics(sales):
    metrics = report_services.dashboard_metrics()
    assert metrics["order_count"] == 3
    assert metrics["revenue"] == Decimal("750.00")  # 3 * 250
    assert metrics["average_ticket"] == Decimal("250.00")
    assert metrics["guest_count"] == 6


def test_top_products(sales):
    today = timezone.localdate()
    rows = report_services.top_products(today, today)
    names = [r["product__name"] for r in rows]
    assert "Pizza Margherita" in names
    assert "Kola" in names


def test_category_breakdown_percentages_sum(sales):
    today = timezone.localdate()
    rows = report_services.category_breakdown(today, today)
    assert rows
    assert abs(sum(r["percent"] for r in rows) - 100) < 1.5


def test_payment_breakdown(sales):
    today = timezone.localdate()
    rows = report_services.payment_breakdown(today, today)
    assert len(rows) == 1
    assert rows[0]["method"] == Payment.Method.CARD
    assert rows[0]["total"] == Decimal("750.00")


def test_profitability_uses_recipe_cost(sales):
    today = timezone.localdate()
    rows = report_services.profitability_report(today, today)
    pizza_row = next(r for r in rows if r["product"].name == "Pizza Margherita")
    assert pizza_row["unit_cost"] == Decimal("59.00")
    assert pizza_row["revenue"] == Decimal("600.00")
    assert pizza_row["total_cost"] == Decimal("177.00")
    assert pizza_row["profit"] == Decimal("423.00")


def test_staff_sales_report(sales, waiter):
    today = timezone.localdate()
    rows = report_services.staff_sales_report(today, today)
    assert rows[0]["orders"] == 3
    assert rows[0]["revenue"] == Decimal("750.00")


def test_revenue_series_has_one_entry_per_day(sales):
    series = report_services.revenue_series(7)
    assert len(series["labels"]) == 7
    assert len(series["revenue"]) == 7
    assert series["revenue"][-1] == 750.0


def test_daily_closing_snapshot(sales, cashier):
    closing = report_services.build_daily_closing(timezone.localdate(), user=cashier)
    assert closing.order_count == 3
    assert closing.gross_sales == Decimal("750.00")
    assert closing.net_sales == Decimal("750.00")
    assert "yasal mali belge" in closing.legal_notice


def test_dashboard_alerts_include_low_stock(db, gram, warehouse):
    from apps.inventory.models import Ingredient
    from apps.inventory.services import receive_stock

    ingredient = Ingredient.objects.create(
        name="Nane", base_unit=gram, critical_level=Decimal("1000")
    )
    receive_stock(ingredient, warehouse, Decimal("100"), Decimal("0.10"))
    alerts = report_services.dashboard_alerts()
    assert any("kritik seviyede" in a["title"] for a in alerts)


# ------------------------------------------------------------------ dışa aktarma
def test_excel_export_returns_valid_file(client, owner, sales):
    client.force_login(owner)
    response = client.get(reverse("reports:export_sales_excel"))
    assert response.status_code == 200
    assert "spreadsheetml" in response["Content-Type"]
    assert response.content[:2] == b"PK"  # xlsx = zip
    assert len(response.content) > 3000


def test_csv_export_has_bom_and_rows(client, owner, sales):
    client.force_login(owner)
    response = client.get(reverse("reports:export_sales_csv"))
    assert response.status_code == 200
    body = response.content.decode("utf-8-sig")
    assert "Ürün" in body
    assert "Pizza Margherita" in body


def test_pdf_export_returns_pdf(client, owner, sales):
    client.force_login(owner)
    response = client.get(reverse("reports:export_sales_pdf"))
    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert response.content[:4] == b"%PDF"


def test_inventory_excel_export(client, owner, flour):
    client.force_login(owner)
    response = client.get(reverse("reports:export_inventory_excel"))
    assert response.status_code == 200
    assert response.content[:2] == b"PK"


def test_receipt_pdf(client, owner, sales):
    client.force_login(owner)
    response = client.get(reverse("orders:order_receipt_pdf", args=[sales[0].pk]))
    assert response.status_code == 200
    assert response.content[:4] == b"%PDF"


def test_daily_closing_pdf(client, owner, sales, cashier):
    closing = report_services.build_daily_closing(timezone.localdate(), user=cashier)
    client.force_login(owner)
    response = client.get(reverse("reports:daily_closing_pdf", args=[closing.pk]))
    assert response.status_code == 200
    assert response.content[:4] == b"%PDF"


def test_export_requires_permission(client, waiter):
    client.force_login(waiter)
    response = client.get(reverse("reports:export_sales_excel"))
    assert response.status_code == 403


def test_export_is_audited(client, owner, sales):
    from apps.core.models import AuditLog

    client.force_login(owner)
    client.get(reverse("reports:export_sales_csv"))
    assert AuditLog.objects.filter(action=AuditLog.Action.EXPORT).exists()


# ==================================================================
#  PDF yazı tipi — Türkçe karakter regresyonu
# ==================================================================
def test_pdf_font_is_not_helvetica():
    """PDF için Türkçe destekli bir yazı tipi kayıtlı olmalı.

    ReportLab'ın yerleşik Helvetica'sı WinAnsi kodlaması kullanır ve
    ş, ğ, ı, İ harflerini içermez; çıktıda siyah kutu olarak görünürler.
    ç, ö, ü sorunsuz çalıştığı için hata kolayca gözden kaçar.
    """
    from apps.reports.exports import pdf_fonts

    regular, bold = pdf_fonts()
    assert (
        regular != "Helvetica"
    ), "Türkçe destekli yazı tipi bulunamadı; PDF çıktısında ş/ğ/ı/İ kaybolur"
    assert bold.endswith("-Bold")


def test_sales_pdf_keeps_turkish_letters(client, owner, sales):
    """Üretilen PDF'te Türkçe'ye özgü harfler gerçekten yer almalı."""
    pypdf = pytest.importorskip("pypdf")

    client.force_login(owner)
    response = client.get(reverse("reports:export_sales_pdf"))
    assert response.status_code == 200

    reader = pypdf.PdfReader(io.BytesIO(response.content))
    text = " ".join((page.extract_text() or "") for page in reader.pages)

    for letter in ("ş", "ğ", "ı", "İ"):
        assert letter in text, f"PDF çıktısında {letter!r} harfi yok"
