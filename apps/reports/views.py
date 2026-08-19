"""Gösterge paneli ve rapor görünümleri."""

from __future__ import annotations

from datetime import date, timedelta

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.decorators import require_permission
from apps.core.models import AuditLog
from apps.core.services import record_audit
from apps.reports import exports, services, statistics
from apps.reports.models import DailyClosing, Expense, ExpenseCategory


def _period(request) -> tuple[date, date]:
    """İstekten tarih aralığı çıkarır (varsayılan: son 30 gün)."""
    today = timezone.localdate()
    try:
        start = date.fromisoformat(request.GET.get("from", ""))
    except ValueError:
        start = today - timedelta(days=29)
    try:
        end = date.fromisoformat(request.GET.get("to", ""))
    except ValueError:
        end = today
    if end < start:
        start, end = end, start
    return start, end


@require_permission("dashboard.view")
def dashboard(request):
    """Yönetim paneli."""
    metrics = services.dashboard_metrics()
    return render(
        request,
        "reports/dashboard.html",
        {
            "page_title": "Yönetim Paneli",
            "metrics": metrics,
            "revenue_series": services.revenue_series(14),
            "hourly": services.hourly_distribution(7),
            "top_products": services.top_products(
                timezone.localdate() - timedelta(days=7), timezone.localdate(), limit=8
            ),
            "categories": services.category_breakdown(
                timezone.localdate() - timedelta(days=7), timezone.localdate()
            ),
            "payments": services.payment_breakdown(timezone.localdate(), timezone.localdate()),
            "comparison": {
                "day": services.period_comparison("day"),
                "week": services.period_comparison("week"),
                "month": services.period_comparison("month"),
            },
            "alerts": services.dashboard_alerts(),
            "can_see_financial": request.user.has_perm_code("report.financial"),
        },
    )


@require_permission("report.view")
def report_index(request):
    return render(
        request,
        "reports/index.html",
        {
            "page_title": "Raporlar",
            "can_export": request.user.has_perm_code("report.export"),
            "can_financial": request.user.has_perm_code("report.financial"),
            "can_statistics": request.user.has_perm_code("report.statistics"),
        },
    )


@require_permission("report.statistics")
def statistics_center(request):
    """Dönem karşılaştırmalı istatistik merkezi."""
    preset_key = request.GET.get("donem", "")
    presets = statistics.period_presets()
    chosen = next((p for p in presets if p["key"] == preset_key), None)

    if chosen:
        start, end = chosen["start"], chosen["end"]
    else:
        start, end = _period(request)

    data = statistics.build_statistics(start, end)
    return render(
        request,
        "reports/statistics.html",
        {
            "page_title": "İstatistik Merkezi",
            "presets": presets,
            "preset_key": chosen["key"] if chosen else "",
            "can_export": request.user.has_perm_code("report.export"),
            **data,
        },
    )


@require_permission("report.statistics")
@require_permission("report.export")
def export_statistics_excel(request):
    """İstatistik özetini Excel olarak indirir."""
    start, end = _period(request)
    data = statistics.build_statistics(start, end)

    record_audit(
        AuditLog.Action.EXPORT,
        user=request.user,
        description=f"İstatistik dışa aktarıldı ({start} – {end})",
        request=request,
    )
    return exports.statistics_workbook(data)


@require_permission("report.view")
def sales_report(request):
    start, end = _period(request)
    return render(
        request,
        "reports/sales.html",
        {
            "page_title": "Satış Raporu",
            "start": start,
            "end": end,
            "top_products": services.top_products(start, end, limit=25),
            "worst_products": services.top_products(start, end, limit=10, worst=True),
            "categories": services.category_breakdown(start, end),
            "payments": services.payment_breakdown(start, end),
            "order_types": services.order_type_breakdown(start, end),
            "staff": services.staff_sales_report(start, end),
            "series": services.revenue_series((end - start).days + 1),
        },
    )


@require_permission("report.financial")
def profitability_report(request):
    start, end = _period(request)
    rows = services.profitability_report(start, end, limit=200)
    no_recipe = [r for r in rows if not r["has_recipe"]]
    return render(
        request,
        "reports/profitability.html",
        {
            "page_title": "Kârlılık Raporu",
            "start": start,
            "end": end,
            "rows": rows,
            "no_recipe_count": len(no_recipe),
            "total_revenue": sum(r["revenue"] for r in rows),
            "total_cost": sum(r["total_cost"] for r in rows),
            "total_profit": sum(r["profit"] for r in rows),
        },
    )


@require_permission("report.view")
def void_report(request):
    start, end = _period(request)
    return render(
        request,
        "reports/voids.html",
        {
            "page_title": "İptal, İndirim ve İade Raporu",
            "start": start,
            "end": end,
            **services.void_discount_report(start, end),
        },
    )


@require_permission("cash.manage", "report.financial")
def daily_closing_list(request):
    closings = DailyClosing.objects.select_related("closed_by").order_by("-closing_date")[:60]
    return render(
        request,
        "reports/closing_list.html",
        {"page_title": "Gün Sonu Raporları", "closings": closings},
    )


@require_permission("cash.manage", "report.financial")
def daily_closing_detail(request, pk: int):
    closing = get_object_or_404(DailyClosing, pk=pk)
    return render(
        request,
        "reports/closing_detail.html",
        {"page_title": f"Gün Sonu — {closing.closing_date:%d.%m.%Y}", "closing": closing},
    )


@require_permission("cash.manage")
@require_POST
def daily_closing_generate(request):
    try:
        day = date.fromisoformat(request.POST.get("date", ""))
    except ValueError:
        day = timezone.localdate()
    closing = services.build_daily_closing(day, user=request.user)
    messages.success(request, f"{day:%d.%m.%Y} gün sonu raporu oluşturuldu.")
    return redirect("reports:daily_closing_detail", pk=closing.pk)


@require_permission("report.export")
def daily_closing_pdf(request, pk: int):
    closing = get_object_or_404(DailyClosing, pk=pk)
    record_audit(
        AuditLog.Action.EXPORT,
        obj=closing,
        description=f"Gün sonu raporu PDF olarak indirildi: {closing.closing_date}",
        request=request,
    )
    return exports.pdf_response(
        f"gun-sonu-{closing.closing_date:%Y%m%d}", exports.daily_closing_pdf(closing)
    )


# ------------------------------------------------------------------
#  Dışa aktarma
# ------------------------------------------------------------------
@require_permission("report.export")
def export_sales_excel(request):
    start, end = _period(request)
    record_audit(
        AuditLog.Action.EXPORT,
        description=f"Satış raporu Excel: {start} - {end}",
        request=request,
    )
    return exports.sales_report_excel(start, end)


@require_permission("report.export")
def export_sales_csv(request):
    start, end = _period(request)
    rows = [
        [p["product__name"], p["product__category__name"] or "-", p["total_quantity"], p["revenue"]]
        for p in services.top_products(start, end, limit=1000)
    ]
    record_audit(
        AuditLog.Action.EXPORT, description=f"Satış raporu CSV: {start} - {end}", request=request
    )
    return exports.csv_response(
        f"satis-{start:%Y%m%d}-{end:%Y%m%d}", ["Ürün", "Kategori", "Adet", "Ciro"], rows
    )


@require_permission("report.export")
def export_sales_pdf(request):
    start, end = _period(request)
    metrics = services.dashboard_metrics(end)
    sections = [
        {
            "heading": "Genel Özet",
            "headers": ["Kalem", "Değer"],
            "rows": [
                ["Dönem", f"{start:%d.%m.%Y} - {end:%d.%m.%Y}"],
                ["Ciro (son gün)", str(metrics["revenue"])],
                ["Sipariş sayısı", metrics["order_count"]],
                ["Ortalama adisyon", str(metrics["average_ticket"])],
                ["Doluluk oranı", f"%{metrics['occupancy_rate']}"],
                ["İptal oranı", f"%{metrics['cancel_rate']}"],
            ],
        },
        {
            "heading": "En Çok Satan Ürünler",
            "headers": ["Ürün", "Adet", "Ciro"],
            "rows": [
                [p["product__name"], p["total_quantity"], str(p["revenue"])]
                for p in services.top_products(start, end, limit=20)
            ],
        },
        {
            "heading": "Kategori Dağılımı",
            "headers": ["Kategori", "Ciro", "Pay (%)"],
            "rows": [
                [c["category"], str(c["revenue"]), c["percent"]]
                for c in services.category_breakdown(start, end)
            ],
        },
        {
            "heading": "Ödeme Yöntemleri",
            "headers": ["Yöntem", "Tutar", "İşlem"],
            "rows": [
                [p["label"], str(p["total"]), p["count"]]
                for p in services.payment_breakdown(start, end)
            ],
        },
    ]
    record_audit(
        AuditLog.Action.EXPORT, description=f"Satış raporu PDF: {start} - {end}", request=request
    )
    return exports.pdf_response(
        f"satis-raporu-{start:%Y%m%d}",
        exports.pdf_report(
            "Satış Raporu",
            sections,
            subtitle=f"{start:%d.%m.%Y} - {end:%d.%m.%Y}",
            footer_note=(
                "Bu rapor işletme içi bilgilendirme amaçlıdır ve yasal mali belge " "yerine geçmez."
            ),
        ),
    )


@require_permission("report.export")
def export_inventory_excel(request):
    from apps.inventory.models import Ingredient

    rows = []
    for ingredient in Ingredient.objects.filter(is_active=True).select_related("base_unit"):
        rows.append(
            [
                ingredient.name,
                ingredient.sku or "-",
                ingredient.base_unit.code,
                ingredient.total_on_hand,
                ingredient.critical_level,
                ingredient.average_cost,
                ingredient.stock_value,
                {"ok": "Normal", "low": "Azalıyor", "critical": "Kritik", "out": "Tükendi"}[
                    ingredient.stock_status
                ],
                ingredient.days_until_stockout() or "-",
            ]
        )
    record_audit(AuditLog.Action.EXPORT, description="Stok raporu Excel", request=request)
    return exports.excel_response(
        f"stok-{timezone.localdate():%Y%m%d}",
        {
            "Stok": (
                [
                    "Malzeme",
                    "Kod",
                    "Birim",
                    "Mevcut",
                    "Kritik Seviye",
                    "Ort. Maliyet",
                    "Stok Değeri",
                    "Durum",
                    "Tahmini Gün",
                ],
                rows,
            )
        },
        title="Stok Durum Raporu",
    )


# ------------------------------------------------------------------
#  Muhasebe
# ------------------------------------------------------------------
@require_permission("accounting.view")
def expense_list(request):
    start, end = _period(request)
    expenses = Expense.objects.select_related("category", "supplier").filter(
        expense_date__gte=start, expense_date__lte=end
    )
    from django.db.models import Sum

    by_category = expenses.values("category__name").annotate(total=Sum("amount")).order_by("-total")
    revenue = services.paid_orders(start, end).aggregate(t=Sum("grand_total"))["t"] or 0
    total_expense = expenses.aggregate(t=Sum("amount"))["t"] or 0

    return render(
        request,
        "reports/expense_list.html",
        {
            "page_title": "Gelir ve Giderler",
            "start": start,
            "end": end,
            "expenses": expenses.order_by("-expense_date")[:200],
            "by_category": by_category,
            "categories": ExpenseCategory.objects.all(),
            "revenue": revenue,
            "total_expense": total_expense,
            "net": revenue - total_expense,
            "payment_methods": Expense.PaymentMethod.choices,
        },
    )


@require_permission("accounting.manage")
@require_POST
def expense_create(request):
    from decimal import Decimal

    Expense.objects.create(
        category_id=request.POST.get("category_id"),
        description=request.POST.get("description", "")[:300],
        amount=Decimal(request.POST.get("amount") or "0"),
        tax_amount=Decimal(request.POST.get("tax_amount") or "0"),
        expense_date=request.POST.get("expense_date") or timezone.localdate(),
        payment_method=request.POST.get("payment_method", Expense.PaymentMethod.CASH),
        invoice_number=request.POST.get("invoice_number", ""),
        recorded_by=request.user,
        created_by=request.user,
    )
    messages.success(request, "Gider kaydedildi.")
    return redirect("reports:expense_list")


@require_permission("report.view")
def kitchen_performance(request):
    from apps.kitchen.views import performance

    return performance(request)
