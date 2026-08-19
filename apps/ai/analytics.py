"""Akıllı analizler.

Tasarım ilkesi
--------------
Sayısal hesaplar **deterministik Python koduyla** yapılır; yapay zekâ
yalnızca sonuçları yorumlar. Böylece bir sayı asla modelin uydurmasına
bağlı olmaz ve AI erişilemese bile analizler çalışmaya devam eder
(`ai_available: False` ile döner).
"""

from __future__ import annotations

import json
import logging
import statistics
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, F, Sum
from django.utils import timezone

from apps.ai import prompts
from apps.ai.gateway import AIUnavailable, ask
from apps.ai.models import AIInsight, AITask
from apps.core.utils import money, safe_divide

logger = logging.getLogger("apps.ai")


def _confidence(data_points: int, minimum: int = 30) -> str:
    if data_points >= minimum * 3:
        return AIInsight.Confidence.HIGH
    if data_points >= minimum:
        return AIInsight.Confidence.MEDIUM
    return AIInsight.Confidence.LOW


def _narrate(system: str, payload: dict, *, feature: str, user=None, task=AITask.REASONING):
    """Hazır sayısal veriyi yapay zekâya yorumlatır. Başarısızlık akışı durdurmaz."""
    try:
        response = ask(
            json.dumps(payload, ensure_ascii=False, default=str),
            system=system,
            task=task,
            feature=feature,
            user=user,
            temperature=0.2,
        )
        return True, response.text, response.provider, response.model
    except AIUnavailable as exc:
        return False, str(exc), "", ""
    except Exception as exc:  # pragma: no cover
        logger.exception("AI yorumlama hatası")
        return False, f"Analiz yorumlanamadı: {exc}", "", ""


# ------------------------------------------------------------------
#  1) Menü mühendisliği
# ------------------------------------------------------------------
def menu_engineering(days: int = 30, *, user=None, narrate: bool = True) -> dict:
    """Ürünleri satış hacmi ve kâr marjına göre 4 gruba ayırır."""
    from apps.reports.services import profitability_report

    end = timezone.localdate()
    start = end - timedelta(days=days)
    rows = profitability_report(start, end, limit=500)
    if not rows:
        return {
            "ok": False,
            "message": "Bu dönemde satış verisi bulunamadı.",
            "groups": {},
            "ai_available": False,
        }

    quantities = [float(r["quantity"]) for r in rows]
    margins = [float(r["margin_percent"]) for r in rows]
    median_qty = statistics.median(quantities)
    median_margin = statistics.median(margins)

    groups: dict[str, list] = {"star": [], "plowhorse": [], "puzzle": [], "dog": []}
    for row in rows:
        high_volume = float(row["quantity"]) >= median_qty
        high_margin = float(row["margin_percent"]) >= median_margin
        if high_volume and high_margin:
            key = "star"
        elif high_volume:
            key = "plowhorse"
        elif high_margin:
            key = "puzzle"
        else:
            key = "dog"
        groups[key].append(
            {
                "name": row["product"].name,
                "category": row["product"].category.name,
                "quantity": float(row["quantity"]),
                "revenue": float(row["revenue"]),
                "margin_percent": row["margin_percent"],
                "food_cost_percent": float(row["food_cost_percent"]),
                "has_recipe": row["has_recipe"],
            }
        )

    payload = {
        "donem_gun": days,
        "urun_sayisi": len(rows),
        "medyan_satis_adedi": round(median_qty, 1),
        "medyan_marj_yuzde": round(median_margin, 1),
        "gruplar": {k: sorted(v, key=lambda x: -x["revenue"])[:10] for k, v in groups.items()},
        "recetesiz_urun_sayisi": sum(1 for r in rows if not r["has_recipe"]),
    }

    result = {
        "ok": True,
        "period_days": days,
        "median_quantity": round(median_qty, 1),
        "median_margin": round(median_margin, 1),
        "groups": groups,
        "counts": {k: len(v) for k, v in groups.items()},
        "data_points": len(rows),
        "confidence": _confidence(len(rows), 20),
        "ai_available": False,
        "narrative": "",
    }

    if narrate:
        ok, text, provider, model = _narrate(
            prompts.MENU_ENGINEERING, payload, feature="menu_engineering", user=user
        )
        result["ai_available"] = ok
        result["narrative"] = text
        if ok:
            AIInsight.objects.create(
                kind=AIInsight.Kind.MENU_ENGINEERING,
                title=f"Menü mühendisliği analizi ({days} gün)",
                summary=text[:4000],
                details=payload,
                confidence=result["confidence"],
                data_points=len(rows),
                limitations=(
                    "Sınıflandırma medyan değerlere göre yapılır; mevsimsellik, kampanya "
                    "etkisi ve reçetesi girilmemiş ürünler sonucu etkileyebilir."
                ),
                period_start=start,
                period_end=end,
                provider=provider,
                model=model,
            )
    return result


# ------------------------------------------------------------------
#  2) Talep tahmini
# ------------------------------------------------------------------
def demand_forecast(
    days_ahead: int = 7, history_days: int = 60, *, user=None, narrate: bool = True
) -> dict:
    """Haftanın gününe göre hareketli ortalama ile basit talep tahmini.

    Yöntem: son `history_days` günün verisi haftanın gününe göre gruplanır,
    her grup için ortalama ve standart sapma hesaplanır. Tahmin aralığı
    ortalama ± standart sapma olarak verilir.
    """
    from apps.reports.services import paid_orders

    end = timezone.localdate()
    start = end - timedelta(days=history_days)
    orders = paid_orders(start, end).values_list("closed_at", "grand_total", "guest_count")

    by_weekday: dict[int, list[tuple[float, int]]] = {i: [] for i in range(7)}
    daily: dict[date, list] = {}
    for closed_at, total, guests in orders:
        day = timezone.localtime(closed_at).date()
        daily.setdefault(day, []).append((float(total), guests))

    for day, entries in daily.items():
        revenue = sum(e[0] for e in entries)
        by_weekday[day.weekday()].append((revenue, len(entries)))

    weekday_names = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
    forecast = []
    for offset in range(1, days_ahead + 1):
        target = end + timedelta(days=offset)
        samples = by_weekday[target.weekday()]
        if not samples:
            forecast.append(
                {
                    "date": target,
                    "weekday": weekday_names[target.weekday()],
                    "revenue_low": 0.0,
                    "revenue_high": 0.0,
                    "orders_low": 0,
                    "orders_high": 0,
                    "samples": 0,
                }
            )
            continue
        revenues = [s[0] for s in samples]
        counts = [s[1] for s in samples]
        rev_mean = statistics.mean(revenues)
        rev_std = statistics.pstdev(revenues) if len(revenues) > 1 else rev_mean * 0.2
        cnt_mean = statistics.mean(counts)
        cnt_std = statistics.pstdev(counts) if len(counts) > 1 else cnt_mean * 0.2
        forecast.append(
            {
                "date": target,
                "weekday": weekday_names[target.weekday()],
                "revenue_low": round(max(rev_mean - rev_std, 0), 2),
                "revenue_mid": round(rev_mean, 2),
                "revenue_high": round(rev_mean + rev_std, 2),
                "orders_low": int(max(cnt_mean - cnt_std, 0)),
                "orders_mid": int(cnt_mean),
                "orders_high": int(cnt_mean + cnt_std),
                "samples": len(samples),
            }
        )

    data_points = len(daily)
    result = {
        "ok": bool(daily),
        "history_days": history_days,
        "data_points": data_points,
        "forecast": forecast,
        "confidence": _confidence(data_points, 14),
        "limitations": (
            "Bu tahmin yalnızca geçmiş satış ortalamalarına dayanır. Hava durumu, "
            "resmî tatiller, yerel etkinlikler, kampanyalar ve rakip hareketleri "
            "hesaba katılmamıştır. Az veriyle yapılan tahminlerin sapması yüksektir."
        ),
        "ai_available": False,
        "narrative": "",
    }

    if not daily:
        result["message"] = (
            "Tahmin için yeterli geçmiş satış verisi yok. En az 14 günlük veri önerilir."
        )
        return result

    if narrate:
        payload = {
            "gecmis_gun_sayisi": data_points,
            "tahmin": [
                {
                    "tarih": str(f["date"]),
                    "gun": f["weekday"],
                    "ciro_araligi": [f["revenue_low"], f["revenue_high"]],
                    "siparis_araligi": [f["orders_low"], f["orders_high"]],
                    "ornek_sayisi": f["samples"],
                }
                for f in forecast
            ],
        }
        ok, text, provider, model = _narrate(
            prompts.DEMAND_FORECAST, payload, feature="demand_forecast", user=user
        )
        result["ai_available"] = ok
        result["narrative"] = text
        if ok:
            AIInsight.objects.create(
                kind=AIInsight.Kind.DEMAND_FORECAST,
                title=f"{days_ahead} günlük talep tahmini",
                summary=text[:4000],
                details=payload,
                confidence=result["confidence"],
                data_points=data_points,
                limitations=result["limitations"],
                period_start=end,
                period_end=end + timedelta(days=days_ahead),
                provider=provider,
                model=model,
            )
    return result


# ------------------------------------------------------------------
#  3) Stok tükenme tahmini
# ------------------------------------------------------------------
def stock_forecast(*, user=None, narrate: bool = False) -> dict:
    """Tüketim hızına göre hangi malzemenin ne zaman biteceğini tahmin eder."""
    from apps.inventory.models import Ingredient

    rows = []
    for ingredient in Ingredient.objects.filter(is_active=True).select_related("base_unit"):
        daily = ingredient.daily_consumption_average(30)
        if daily <= 0:
            continue
        days_left = ingredient.days_until_stockout(30)
        rows.append(
            {
                "ingredient": ingredient,
                "name": ingredient.name,
                "on_hand": float(ingredient.total_on_hand),
                "unit": ingredient.base_unit.code,
                "daily_usage": float(daily),
                "days_left": days_left,
                "critical": days_left is not None and days_left <= 7,
                "suggested_order": float(ingredient.reorder_quantity or daily * 14),
            }
        )
    rows.sort(key=lambda r: (r["days_left"] is None, r["days_left"] or 9999))

    result = {
        "ok": True,
        "rows": rows,
        "critical_count": sum(1 for r in rows if r["critical"]),
        "data_points": len(rows),
        "confidence": _confidence(len(rows), 10),
        "limitations": (
            "Tahmin son 30 günün ortalama tüketimine dayanır. Mevsimsel talep "
            "değişimi ve menü değişiklikleri sonucu etkileyebilir."
        ),
        "ai_available": False,
        "narrative": "",
    }

    if narrate and rows:
        payload = {
            "malzemeler": [{k: v for k, v in r.items() if k != "ingredient"} for r in rows[:30]]
        }
        ok, text, provider, model = _narrate(
            prompts.COST_ANALYSIS, payload, feature="stock_forecast", user=user, task=AITask.MATH
        )
        result["ai_available"] = ok
        result["narrative"] = text
    return result


# ------------------------------------------------------------------
#  4) İsraf analizi
# ------------------------------------------------------------------
def waste_analysis(days: int = 30, *, user=None, narrate: bool = True) -> dict:
    from apps.inventory.models import WasteRecord

    end = timezone.localdate()
    start = end - timedelta(days=days)
    records = WasteRecord.objects.filter(occurred_at__date__gte=start)

    by_reason = list(
        records.values("reason")
        .annotate(total=Sum("cost_value"), count=Count("id"))
        .order_by("-total")
    )
    by_ingredient = list(
        records.values("ingredient__name")
        .annotate(total=Sum("cost_value"), quantity=Sum("quantity"), count=Count("id"))
        .order_by("-total")[:15]
    )
    total_cost = records.aggregate(t=Sum("cost_value"))["t"] or Decimal("0")

    from apps.reports.services import paid_orders

    revenue = paid_orders(start, end).aggregate(t=Sum("grand_total"))["t"] or Decimal("0")
    waste_ratio = float(safe_divide(total_cost * 100, revenue)) if revenue else 0.0

    reason_labels = dict(WasteRecord.Reason.choices)
    payload = {
        "donem_gun": days,
        "toplam_fire_maliyeti": float(total_cost),
        "donem_cirosu": float(revenue),
        "fire_ciro_orani_yuzde": round(waste_ratio, 2),
        "nedene_gore": [
            {
                "neden": str(reason_labels.get(r["reason"], r["reason"])),
                "tutar": float(r["total"] or 0),
                "adet": r["count"],
            }
            for r in by_reason
        ],
        "malzemeye_gore": [
            {
                "malzeme": r["ingredient__name"],
                "tutar": float(r["total"] or 0),
                "miktar": float(r["quantity"] or 0),
            }
            for r in by_ingredient
        ],
    }

    result = {
        "ok": True,
        "period_days": days,
        "total_cost": money(total_cost),
        "waste_ratio": round(waste_ratio, 2),
        "by_reason": by_reason,
        "by_ingredient": by_ingredient,
        "data_points": records.count(),
        "confidence": _confidence(records.count(), 15),
        "ai_available": False,
        "narrative": "",
    }

    if narrate and records.exists():
        ok, text, provider, model = _narrate(
            prompts.WASTE_ANALYSIS, payload, feature="waste_analysis", user=user
        )
        result["ai_available"] = ok
        result["narrative"] = text
        if ok:
            AIInsight.objects.create(
                kind=AIInsight.Kind.WASTE_ANALYSIS,
                title=f"İsraf analizi ({days} gün) — {money(total_cost)} ₺",
                summary=text[:4000],
                details=payload,
                confidence=result["confidence"],
                data_points=records.count(),
                limitations="Fire kayıtları elle girildiği için eksik veya geç kayıt olabilir.",
                period_start=start,
                period_end=end,
                provider=provider,
                model=model,
            )
    return result


# ------------------------------------------------------------------
#  5) Fiyat ve marj simülasyonu
# ------------------------------------------------------------------
def price_simulation(
    product, new_price: Decimal, *, elasticity: float = -1.0, days: int = 30
) -> dict:
    """Fiyat değişiminin kâra etkisini basit esneklik varsayımıyla hesaplar."""
    from apps.orders.models import Order, OrderItem

    end = timezone.localdate()
    start = end - timedelta(days=days)
    stats = (
        OrderItem.objects.filter(
            product=product,
            order__status=Order.Status.PAID,
            order__closed_at__date__gte=start,
        )
        .exclude(status=OrderItem.Status.CANCELLED)
        .aggregate(total_quantity=Sum("quantity"))
    )
    current_qty = Decimal(str(stats["total_quantity"] or 0))
    current_price = product.price
    unit_cost = product.recipe_cost

    if current_price == 0:
        return {"ok": False, "message": "Ürün fiyatı sıfır; simülasyon yapılamaz."}

    price_change_pct = float((new_price - current_price) / current_price * 100)
    qty_change_pct = price_change_pct * elasticity
    projected_qty = current_qty * (Decimal("1") + Decimal(str(qty_change_pct / 100)))
    projected_qty = max(projected_qty, Decimal("0"))

    current_profit = money((current_price - unit_cost) * current_qty)
    projected_profit = money((new_price - unit_cost) * projected_qty)

    return {
        "ok": True,
        "product": product.name,
        "period_days": days,
        "current_price": money(current_price),
        "new_price": money(new_price),
        "unit_cost": unit_cost,
        "current_quantity": current_qty,
        "projected_quantity": projected_qty.quantize(Decimal("0.01")),
        "current_profit": current_profit,
        "projected_profit": projected_profit,
        "profit_change": money(projected_profit - current_profit),
        "price_change_percent": round(price_change_pct, 1),
        "assumed_elasticity": elasticity,
        "data_points": int(current_qty),
        "confidence": _confidence(int(current_qty), 30),
        "limitations": (
            f"Talep esnekliği {elasticity} olarak VARSAYILMIŞTIR; gerçek değer "
            "ölçülmemiştir. Rakip fiyatları, mevsimsellik ve müşteri algısı "
            "hesaba katılmamıştır. Sonuç yalnızca kaba bir senaryodur."
        ),
    }


# ------------------------------------------------------------------
#  6) Anormallik / sahtekârlık tespiti
# ------------------------------------------------------------------
def anomaly_detection(days: int = 30, *, user=None, narrate: bool = True) -> dict:
    """İstatistiksel sapmalara göre incelenmesi önerilen örüntüleri bulur."""
    from apps.orders.models import OrderDiscount, OrderItem, Refund
    from apps.reports.services import paid_orders

    end = timezone.localdate()
    start = end - timedelta(days=days)
    findings: list[dict] = []

    # a) Günlük ciro sapması
    daily_revenue: dict[date, float] = {}
    for closed_at, total in paid_orders(start, end).values_list("closed_at", "grand_total"):
        day = timezone.localtime(closed_at).date()
        daily_revenue[day] = daily_revenue.get(day, 0.0) + float(total)
    if len(daily_revenue) >= 7:
        values = list(daily_revenue.values())
        mean = statistics.mean(values)
        stdev = statistics.pstdev(values)
        for day, value in sorted(daily_revenue.items()):
            if stdev > 0 and abs(value - mean) > 2 * stdev:
                findings.append(
                    {
                        "type": "revenue_outlier",
                        "severity": "medium",
                        "title": f"{day:%d.%m.%Y} cirosu ortalamadan belirgin sapıyor",
                        "detail": (
                            f"Gün cirosu {value:,.2f} ₺, dönem ortalaması {mean:,.2f} ₺ "
                            f"(sapma {abs(value - mean) / stdev:.1f} standart sapma)."
                        ),
                        "innocent_explanation": "Özel gün, grup rezervasyonu veya kampanya olabilir.",
                    }
                )

    # b) Kullanıcı bazlı iptal yoğunluğu
    voids = (
        OrderItem.objects.filter(status=OrderItem.Status.CANCELLED, updated_at__date__gte=start)
        .values("cancelled_by__username")
        .annotate(count=Count("id"), total=Sum(F("unit_price") * F("quantity")))
        .order_by("-count")
    )
    void_counts = [v["count"] for v in voids if v["cancelled_by__username"]]
    if len(void_counts) >= 3:
        mean_v = statistics.mean(void_counts)
        std_v = statistics.pstdev(void_counts)
        for row in voids:
            if not row["cancelled_by__username"]:
                continue
            if std_v > 0 and row["count"] > mean_v + 2 * std_v:
                findings.append(
                    {
                        "type": "void_concentration",
                        "severity": "high",
                        "title": f"'{row['cancelled_by__username']}' kullanıcısında iptal yoğunluğu",
                        "detail": (
                            f"{row['count']} iptal (ekip ortalaması {mean_v:.1f}), "
                            f"toplam {float(row['total'] or 0):,.2f} ₺."
                        ),
                        "innocent_explanation": (
                            "Bu kişi iptal yetkisi olan tek kişi olabilir veya yoğun "
                            "vardiyalarda çalışıyor olabilir."
                        ),
                    }
                )

    # c) Yüksek oranlı indirimler
    big_discounts = (
        OrderDiscount.objects.filter(created_at__date__gte=start, percent__gte=30)
        .select_related("order", "approved_by")
        .order_by("-amount")[:10]
    )
    for discount in big_discounts:
        findings.append(
            {
                "type": "large_discount",
                "severity": "medium",
                "title": f"%{discount.percent} indirim — {discount.order.number}",
                "detail": (
                    f"{discount.amount} ₺ indirim, onaylayan: "
                    f"{discount.approved_by.username if discount.approved_by_id else '—'}. "
                    f"Gerekçe: {discount.reason or 'belirtilmemiş'}"
                ),
                "innocent_explanation": "Şikâyet telafisi veya yönetim onaylı kampanya olabilir.",
            }
        )

    # d) İade yoğunluğu
    refunds = Refund.objects.filter(created_at__date__gte=start)
    refund_total = refunds.aggregate(t=Sum("amount"))["t"] or Decimal("0")
    revenue_total = paid_orders(start, end).aggregate(t=Sum("grand_total"))["t"] or Decimal("0")
    refund_ratio = float(safe_divide(refund_total * 100, revenue_total)) if revenue_total else 0.0
    if refund_ratio > 3:
        findings.append(
            {
                "type": "refund_ratio",
                "severity": "high",
                "title": f"İade oranı yüksek: %{refund_ratio:.1f}",
                "detail": f"{refunds.count()} iade, toplam {refund_total} ₺.",
                "innocent_explanation": "Tedarik veya ekipman sorunu yaşanmış olabilir.",
            }
        )

    result = {
        "ok": True,
        "period_days": days,
        "findings": findings,
        "data_points": len(daily_revenue),
        "confidence": _confidence(len(daily_revenue), 14),
        "disclaimer": (
            "Bu bulgular istatistiksel sapmalardır, KANIT DEĞİLDİR. Hiçbir personel "
            "hakkında suçlayıcı sonuç çıkarılmamalıdır. Her bulgu için masum bir "
            "açıklama olasılığı da belirtilmiştir."
        ),
        "ai_available": False,
        "narrative": "",
    }

    if narrate and findings:
        ok, text, provider, model = _narrate(
            prompts.ANOMALY,
            {"bulgular": findings, "donem_gun": days},
            feature="anomaly_detection",
            user=user,
        )
        result["ai_available"] = ok
        result["narrative"] = text
        if ok:
            AIInsight.objects.create(
                kind=AIInsight.Kind.ANOMALY,
                title=f"Anormallik taraması ({len(findings)} bulgu)",
                summary=text[:4000],
                details={"findings": findings},
                confidence=result["confidence"],
                data_points=len(daily_revenue),
                limitations=result["disclaimer"],
                period_start=start,
                period_end=end,
                provider=provider,
                model=model,
            )
    return result


# ------------------------------------------------------------------
#  7) Yorum duygu analizi
# ------------------------------------------------------------------
def analyze_reviews(*, user=None, limit: int = 20) -> dict:
    """Analiz edilmemiş yorumları yapay zekâ ile sınıflandırır."""
    from apps.crm.models import Review

    pending = list(
        Review.objects.filter(sentiment=Review.Sentiment.UNKNOWN)
        .exclude(comment="")
        .order_by("-created_at")[:limit]
    )
    if not pending:
        return {"ok": True, "analyzed": 0, "message": "Analiz bekleyen yorum yok."}

    payload = {"reviews": [{"id": r.pk, "rating": r.rating, "comment": r.comment} for r in pending]}
    try:
        response = ask(
            json.dumps(payload, ensure_ascii=False),
            system=prompts.SENTIMENT,
            task=AITask.GENERAL,
            feature="review_sentiment",
            user=user,
            temperature=0.0,
            max_tokens=2000,
            json_mode=True,
            sensitive=True,  # müşteri yorumu -> yerel model tercih edilir
        )
    except AIUnavailable as exc:
        return {"ok": False, "analyzed": 0, "message": str(exc)}

    try:
        data = json.loads(_extract_json(response.text))
        results = data.get("results", [])
    except (ValueError, AttributeError):
        return {
            "ok": False,
            "analyzed": 0,
            "message": "Yapay zekâ yanıtı beklenen JSON biçiminde değil. Tekrar deneyin.",
        }

    lookup = {r.pk: r for r in pending}
    analyzed = 0
    for item in results:
        review = lookup.get(item.get("id"))
        if review is None:
            continue
        sentiment = item.get("sentiment", "neutral")
        if sentiment not in dict(Review.Sentiment.choices):
            sentiment = Review.Sentiment.NEUTRAL
        review.sentiment = sentiment
        try:
            score = max(-1.0, min(1.0, float(item.get("score", 0))))
            review.sentiment_score = Decimal(str(round(score, 3)))
        except (ValueError, TypeError):
            review.sentiment_score = None
        review.topics = [str(t)[:30] for t in (item.get("topics") or [])][:3]
        review.ai_summary = str(item.get("summary", ""))[:300]
        review.analyzed_at = timezone.now()
        review.save(
            update_fields=[
                "sentiment",
                "sentiment_score",
                "topics",
                "ai_summary",
                "analyzed_at",
                "updated_at",
            ]
        )
        analyzed += 1

    return {
        "ok": True,
        "analyzed": analyzed,
        "provider": response.provider,
        "model": response.model,
        "message": f"{analyzed} yorum analiz edildi.",
    }


def _extract_json(text: str) -> str:
    """Model yanıtından JSON bloğunu ayıklar (```json ... ``` sarmalını temizler)."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    return cleaned[start : end + 1] if start != -1 and end != -1 else cleaned


# ------------------------------------------------------------------
#  8) Personel / vardiya önerisi
# ------------------------------------------------------------------
def staffing_suggestion(*, user=None, narrate: bool = True) -> dict:
    from apps.reports.services import hourly_distribution

    hourly = hourly_distribution(14)
    peak_hours = sorted([(i, hourly["orders"][i]) for i in range(24)], key=lambda x: -x[1])[:6]

    # Kaba kural: saatte 8 siparişe 1 servis personeli.
    suggestions = []
    for hour, orders in sorted(peak_hours):
        needed = max(1, round(orders / 8))
        suggestions.append(
            {"hour": f"{hour:02d}:00", "avg_orders": orders, "suggested_staff": needed}
        )

    result = {
        "ok": True,
        "hourly": hourly,
        "peak_hours": suggestions,
        "data_points": 14,
        "confidence": AIInsight.Confidence.MEDIUM,
        "limitations": (
            "Öneri, saatte 8 sipariş = 1 servis personeli varsayımına dayanır. "
            "Gerçek ihtiyaç; menü karmaşıklığı, salon düzeni, deneyim seviyesi ve "
            "yasal çalışma/mola kurallarına göre değişir."
        ),
        "ai_available": False,
        "narrative": "",
    }

    if narrate:
        ok, text, provider, model = _narrate(
            prompts.STAFF_SUGGESTION,
            {"yogun_saatler": suggestions, "saatlik_dagilim": hourly},
            feature="staffing",
            user=user,
        )
        result["ai_available"] = ok
        result["narrative"] = text
    return result


# ------------------------------------------------------------------
#  9) Günlük yönetici özeti
# ------------------------------------------------------------------
def daily_summary(day: date | None = None, *, user=None) -> dict:
    from apps.crm.services import review_statistics
    from apps.inventory.services import low_stock_report
    from apps.kitchen.services import delayed_tickets
    from apps.reports.services import (
        category_breakdown,
        dashboard_metrics,
        payment_breakdown,
        top_products,
    )

    day = day or timezone.localdate()
    metrics = dashboard_metrics(day)
    payload = {
        "tarih": str(day),
        "ciro": float(metrics["revenue"]),
        "siparis_sayisi": metrics["order_count"],
        "misafir_sayisi": metrics["guest_count"],
        "ortalama_adisyon": float(metrics["average_ticket"]),
        "ciro_degisim_yuzde": metrics["revenue_change_percent"],
        "doluluk_orani": metrics["occupancy_rate"],
        "iptal_sayisi": metrics["cancel_count"],
        "iade_tutari": float(metrics["refund_total"]),
        "en_cok_satanlar": [
            {"urun": p["product__name"], "adet": float(p["total_quantity"])}
            for p in top_products(day, day, limit=5)
        ],
        "kategori_dagilimi": [
            {"kategori": c["category"], "ciro": float(c["revenue"])}
            for c in category_breakdown(day, day)
        ],
        "odeme_dagilimi": [
            {"yontem": p["label"], "tutar": float(p["total"])} for p in payment_breakdown(day, day)
        ],
        "kritik_stok": [i.name for i in low_stock_report(limit=10)],
        "geciken_siparis": len(delayed_tickets()),
        "yorumlar": review_statistics(7),
    }

    ok, text, provider, model = _narrate(
        prompts.DAILY_SUMMARY, payload, feature="daily_summary", user=user, task=AITask.GENERAL
    )

    if ok:
        AIInsight.objects.create(
            kind=AIInsight.Kind.DAILY_SUMMARY,
            title=f"Günlük yönetici özeti — {day:%d.%m.%Y}",
            summary=text[:4000],
            details=payload,
            confidence=_confidence(metrics["order_count"], 20),
            data_points=metrics["order_count"],
            limitations="Özet yalnızca sisteme girilen verilere dayanır.",
            period_start=day,
            period_end=day,
            provider=provider,
            model=model,
        )

    return {
        "ok": ok,
        "date": day,
        "metrics": metrics,
        "payload": payload,
        "narrative": text,
        "ai_available": ok,
    }


# ------------------------------------------------------------------
#  10) Menü açıklaması üretimi
# ------------------------------------------------------------------
def generate_menu_description(product, *, user=None) -> tuple[bool, str]:
    ingredients = []
    recipe = getattr(product, "recipe", None)
    if recipe:
        ingredients = [item.ingredient.name for item in recipe.items.select_related("ingredient")]

    payload = {
        "urun": product.name,
        "kategori": product.category.name,
        "tur": product.get_kind_display(),
        "malzemeler": ingredients,
        "alerjenler": [a.name for a in product.allergens.all()],
        "mevcut_aciklama": product.description,
    }
    try:
        response = ask(
            json.dumps(payload, ensure_ascii=False),
            system=prompts.MENU_DESCRIPTION,
            task=AITask.GENERAL,
            feature="menu_description",
            user=user,
            temperature=0.7,
            max_tokens=200,
        )
        return True, response.text
    except AIUnavailable as exc:
        return False, str(exc)


# ------------------------------------------------------------------
#  11) Kampanya önerisi
# ------------------------------------------------------------------
def campaign_suggestions(*, user=None) -> dict:
    from apps.crm.services import churn_risk_customers, customer_statistics
    from apps.reports.services import top_products

    end = timezone.localdate()
    start = end - timedelta(days=30)
    payload = {
        "musteri_istatistikleri": {
            k: (float(v) if isinstance(v, Decimal) else v)
            for k, v in customer_statistics().items()
            if k != "by_segment"
        },
        "segment_dagilimi": customer_statistics()["by_segment"],
        "kayip_riski_musteri_sayisi": churn_risk_customers(100).count(),
        "en_cok_satanlar": [
            {"urun": p["product__name"], "adet": float(p["total_quantity"])}
            for p in top_products(start, end, limit=5)
        ],
        "en_az_satanlar": [
            {"urun": p["product__name"], "adet": float(p["total_quantity"])}
            for p in top_products(start, end, limit=5, worst=True)
        ],
    }
    ok, text, provider, model = _narrate(
        prompts.CAMPAIGN_SUGGESTION, payload, feature="campaign_suggestion", user=user
    )
    if ok:
        AIInsight.objects.create(
            kind=AIInsight.Kind.CAMPAIGN,
            title="Kampanya önerileri",
            summary=text[:4000],
            details=payload,
            confidence=AIInsight.Confidence.MEDIUM,
            data_points=payload["musteri_istatistikleri"].get("total", 0),
            limitations="Öneriler geçmiş satış ve segment verisine dayanır; pazar koşulları dikkate alınmamıştır.",
            provider=provider,
            model=model,
        )
    return {"ok": ok, "narrative": text, "payload": payload}
