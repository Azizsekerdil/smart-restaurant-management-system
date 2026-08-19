"""Yapay zekâ asistanı, içgörüler ve sağlayıcı ayarları görünümleri."""

from __future__ import annotations

import json
import math
from decimal import Decimal, InvalidOperation

from django.conf import settings as django_settings
from django.contrib import messages
from django.http import JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.decorators import require_permission
from apps.ai import analytics, gateway, prompts
from apps.ai.models import AIConversation, AIConversationMessage, AIInsight, AITask, AIUsageLog
from apps.ai.providers import AIMessage, available_providers, provider_status
from apps.core.logging_filters import mask_secrets
from apps.core.models import AuditLog
from apps.core.services import record_audit


@require_permission("ai.use")
def assistant(request):
    """Yapay zekâ asistanı sohbet ekranı."""
    conversations = AIConversation.objects.filter(user=request.user, is_archived=False)[:20]
    active = None
    if request.GET.get("c"):
        active = conversations.filter(pk=request.GET["c"]).first()

    return render(
        request,
        "ai/assistant.html",
        {
            "page_title": "Yapay Zekâ Asistanı",
            "conversations": conversations,
            "active_conversation": active,
            "messages_list": active.messages.all() if active else [],
            "providers": [p for p in provider_status() if p["configured"]],
            "tasks": AITask.choices,
            "budget": gateway.budget_status(),
            "quick_questions": [
                "Bugün en çok hangi ürün satıldı?",
                "Bu hafta cirom geçen haftaya göre nasıl?",
                "Hangi malzemeler kritik seviyede?",
                "En kârlı 5 ürünüm hangileri?",
                "Bugün kaç sipariş iptal edildi ve neden?",
                "Yarın için kaç kişilik personel planlamalıyım?",
            ],
        },
    )


@require_permission("ai.use")
@require_POST
def assistant_ask(request):
    """Asistana soru sorar; sistem verisiyle zenginleştirilmiş yanıt döner."""
    question = (request.POST.get("question") or "").strip()
    if not question:
        return JsonResponse({"ok": False, "detail": "Soru boş olamaz."}, status=400)

    conversation_id = request.POST.get("conversation_id")
    conversation = None
    if conversation_id:
        conversation = AIConversation.objects.filter(pk=conversation_id, user=request.user).first()
    if conversation is None:
        conversation = AIConversation.objects.create(
            user=request.user, title=question[:60], created_by=request.user
        )

    context_data, contains_sensitive = _build_context(question)
    history = [
        AIMessage(role=m.role, content=m.content)
        for m in conversation.messages.order_by("created_at")[:20]
    ]

    # Sohbet geçmişi kalıcı kayıttır: KVKK gereği kişisel veri ve gizli
    # değerler maskelenerek saklanır (AIUsageLog ile aynı politika).
    AIConversationMessage.objects.create(
        conversation=conversation,
        role="user",
        content=mask_secrets(gateway.mask_pii(question))[:4000],
    )

    prompt = (
        f"SORU: {question}\n\n"
        f"SİSTEM VERİLERİ (JSON):\n{json.dumps(context_data, ensure_ascii=False, default=str)}"
    )
    try:
        response = gateway.ask(
            prompt,
            system=prompts.REPORT_QA,
            task=request.POST.get("task", AITask.REASONING),
            feature="assistant",
            user=request.user,
            history=history,
            preferred_provider=request.POST.get("provider", ""),
            preferred_model=request.POST.get("model", ""),
            temperature=0.2,
            sensitive=contains_sensitive,
        )
    except gateway.AIUnavailable as exc:
        return JsonResponse(
            {"ok": False, "detail": str(exc), "conversation_id": conversation.pk}, status=503
        )

    AIConversationMessage.objects.create(
        conversation=conversation,
        role="assistant",
        content=mask_secrets(gateway.mask_pii(response.text))[:4000],
        provider=response.provider,
        model=response.model,
    )
    conversation.save(update_fields=["updated_at"])

    return JsonResponse(
        {
            "ok": True,
            "answer": response.text,
            "provider": response.provider,
            "model": response.model,
            "latency_ms": response.latency_ms,
            "tokens": response.total_tokens,
            "conversation_id": conversation.pk,
        }
    )


@require_permission("ai.use")
@require_POST
def assistant_stream(request):
    """Akış (streaming) yanıt."""
    question = (request.POST.get("question") or "").strip()
    if not question:
        return JsonResponse({"ok": False, "detail": "Soru boş olamaz."}, status=400)

    context_data, contains_sensitive = _build_context(question)
    prompt = (
        f"SORU: {question}\n\nSİSTEM VERİLERİ (JSON):\n"
        f"{json.dumps(context_data, ensure_ascii=False, default=str)}"
    )

    def generate():
        yield from gateway.stream(
            prompt,
            system=prompts.REPORT_QA,
            task=AITask.REASONING,
            feature="assistant_stream",
            user=request.user,
            sensitive=contains_sensitive,
        )

    response = StreamingHttpResponse(generate(), content_type="text/plain; charset=utf-8")
    response["X-Accel-Buffering"] = "no"
    response["Cache-Control"] = "no-cache"
    return response


def _build_context(question: str) -> tuple[dict, bool]:
    """Soruya göre ilgili sistem verilerini toplar (RAG benzeri zenginleştirme).

    Yapay zekâya tüm veritabanı verilmez; sorunun anahtar kelimelerine göre
    ilgili özetler seçilir. Bu hem token maliyetini düşürür hem de yanıt
    isabetini artırır.

    İkinci dönüş değeri bağlamın kişisel veri (ör. personel ad-soyadı)
    içerip içermediğidir; True ise istek `sensitive=True` ile yönlendirilir
    ve AI_SENSITIVE_LOCAL_ONLY açıkken yalnızca yerel modele gider.
    """
    from datetime import timedelta

    from apps.crm.services import customer_statistics, review_statistics
    from apps.inventory.services import expiring_batches, low_stock_report
    from apps.reports import services as report_services

    today = timezone.localdate()
    lower = question.lower()
    context: dict = {"bugun": str(today), "genel": {}}
    contains_sensitive = False

    metrics = report_services.dashboard_metrics(today)
    context["genel"] = {
        "bugun_ciro": float(metrics["revenue"]),
        "bugun_siparis": metrics["order_count"],
        "ortalama_adisyon": float(metrics["average_ticket"]),
        "doluluk_orani": metrics["occupancy_rate"],
        "iptal_sayisi": metrics["cancel_count"],
        "iade_tutari": float(metrics["refund_total"]),
        "hafta_ciro": float(metrics["week_revenue"]),
        "ay_ciro": float(metrics["month_revenue"]),
    }

    if any(k in lower for k in ["ürün", "urun", "sat", "menü", "menu", "popüler", "populer"]):
        context["en_cok_satanlar_7gun"] = [
            {
                "urun": p["product__name"],
                "adet": float(p["total_quantity"]),
                "ciro": float(p["revenue"]),
            }
            for p in report_services.top_products(today - timedelta(days=7), today, limit=15)
        ]
        context["bugun_satanlar"] = [
            {"urun": p["product__name"], "adet": float(p["total_quantity"])}
            for p in report_services.top_products(today, today, limit=15)
        ]

    if any(k in lower for k in ["stok", "malzeme", "tüken", "tuken", "kritik", "son kullanma"]):
        context["kritik_stok"] = [
            {
                "malzeme": i.name,
                "mevcut": float(i.total_on_hand),
                "birim": i.base_unit.code,
                "kritik_seviye": float(i.critical_level),
                "tahmini_gun": i.days_until_stockout(),
            }
            for i in low_stock_report(limit=20)
        ]
        context["son_kullanma_yaklasan"] = [
            {
                "malzeme": b.ingredient.name,
                "tarih": str(b.expiry_date),
                "kalan_gun": b.days_to_expiry,
            }
            for b in expiring_batches(7)[:20]
        ]

    if any(k in lower for k in ["kâr", "kar", "maliyet", "marj", "profit"]):
        context["karlilik_top20"] = [
            {
                "urun": r["product"].name,
                "ciro": float(r["revenue"]),
                "maliyet": float(r["total_cost"]),
                "kar": float(r["profit"]),
                "marj_yuzde": r["margin_percent"],
            }
            for r in report_services.profitability_report(
                today - timedelta(days=30), today, limit=20
            )
        ]

    if any(k in lower for k in ["personel", "garson", "vardiya", "çalışan", "calisan"]):
        # Personel ad-soyadı kişisel veridir ve mask_pii() desenleri isim
        # tanımaz; bu bağlam yalnızca sensitive=True yönlendirmesiyle gider.
        contains_sensitive = True
        context["personel_satis_30gun"] = [
            {k: (float(v) if isinstance(v, Decimal) else v) for k, v in row.items()}
            for row in report_services.staff_sales_report(today - timedelta(days=30), today)
        ]
        context["saatlik_yogunluk"] = report_services.hourly_distribution(14)

    if any(k in lower for k in ["müşteri", "musteri", "yorum", "memnuniyet", "sadakat"]):
        stats = customer_statistics()
        context["musteri"] = {
            k: (float(v) if isinstance(v, Decimal) else v) for k, v in stats.items()
        }
        context["yorumlar"] = review_statistics(30)

    if any(k in lower for k in ["ödeme", "odeme", "nakit", "kart", "kasa"]):
        context["odeme_dagilimi"] = [
            {"yontem": p["label"], "tutar": float(p["total"]), "adet": p["count"]}
            for p in report_services.payment_breakdown(today, today)
        ]

    if any(k in lower for k in ["hafta", "ay", "karşılaştır", "karsilastir", "geçen", "gecen"]):
        context["karsilastirma"] = {
            period: {
                k: (float(v) if isinstance(v, Decimal) else v)
                for k, v in report_services.period_comparison(period).items()
            }
            for period in ("day", "week", "month")
        }

    if any(k in lower for k in ["fire", "israf", "atık", "atik", "zayi"]):
        waste = analytics.waste_analysis(30, narrate=False)
        context["israf"] = {
            "toplam_maliyet": float(waste["total_cost"]),
            "ciro_orani_yuzde": waste["waste_ratio"],
            "nedene_gore": [
                {"neden": r["reason"], "tutar": float(r["total"] or 0)} for r in waste["by_reason"]
            ],
        }

    return context, contains_sensitive


# ------------------------------------------------------------------
#  Analiz ekranları
# ------------------------------------------------------------------
@require_permission("ai.use")
def insights(request):
    kind = request.GET.get("kind", "")
    qs = AIInsight.objects.all()
    if kind:
        qs = qs.filter(kind=kind)
    return render(
        request,
        "ai/insights.html",
        {
            "page_title": "Yapay Zekâ İçgörüleri",
            "insights": qs[:60],
            "kinds": AIInsight.Kind.choices,
            "current_kind": kind,
        },
    )


@require_permission("ai.use")
def analysis_hub(request):
    """Akıllı analiz merkezi: tüm analizlerin başlatıldığı ekran."""
    return render(
        request,
        "ai/analysis_hub.html",
        {
            "page_title": "Akıllı Analizler",
            "budget": gateway.budget_status(),
            "providers_ready": bool(available_providers()),
            "recent_insights": AIInsight.objects.all()[:10],
        },
    )


@require_permission("ai.use")
@require_POST
def run_analysis(request, kind: str):
    """İstenen analizi çalıştırır ve sonucu JSON döndürür."""
    handlers = {
        "menu_engineering": lambda: analytics.menu_engineering(user=request.user),
        "demand_forecast": lambda: analytics.demand_forecast(user=request.user),
        "stock_forecast": lambda: analytics.stock_forecast(user=request.user, narrate=True),
        "waste_analysis": lambda: analytics.waste_analysis(user=request.user),
        "anomaly": lambda: analytics.anomaly_detection(user=request.user),
        "staffing": lambda: analytics.staffing_suggestion(user=request.user),
        "daily_summary": lambda: analytics.daily_summary(user=request.user),
        "campaign": lambda: analytics.campaign_suggestions(user=request.user),
    }
    handler = handlers.get(kind)
    if handler is None:
        return JsonResponse({"ok": False, "detail": "Bilinmeyen analiz türü."}, status=400)

    result = handler()
    record_audit(
        AuditLog.Action.AI_CALL,
        description=f"Akıllı analiz çalıştırıldı: {kind}",
        request=request,
    )
    return JsonResponse(json.loads(json.dumps(result, default=str)))


@require_permission("menu.manage")
@require_POST
def generate_description(request, product_id: int):
    from apps.catalog.models import Product

    product = get_object_or_404(Product, pk=product_id)
    ok, text = analytics.generate_menu_description(product, user=request.user)
    if ok:
        product.ai_description = text
        product.save(update_fields=["ai_description", "updated_at"])
    return JsonResponse({"ok": ok, "description": text})


@require_permission("report.financial")
@require_POST
def price_simulation(request, product_id: int):
    from apps.catalog.models import Product

    product = get_object_or_404(Product, pk=product_id)
    # `Decimal("NaN")` ve `float("nan"/"inf")` istisna YÜKSELTMEZ. Sessizce
    # geçerlerse NaN bütün simülasyona yayılır ve mali bir ekranda anlamsız
    # bir sayı gösterilir. Bu yüzden sonluluk ayrıca denetlenir.
    try:
        new_price = Decimal(request.POST.get("new_price", "0"))
        elasticity = float(request.POST.get("elasticity", "-1.0"))
    except (ValueError, TypeError, InvalidOperation):
        return JsonResponse({"ok": False, "detail": "Geçersiz değer."}, status=400)

    if not new_price.is_finite() or not math.isfinite(elasticity):
        return JsonResponse({"ok": False, "detail": "Geçersiz değer."}, status=400)
    if new_price < 0:
        return JsonResponse({"ok": False, "detail": "Fiyat negatif olamaz."}, status=400)

    result = analytics.price_simulation(product, new_price, elasticity=elasticity)
    return JsonResponse(json.loads(json.dumps(result, default=str)))


# ------------------------------------------------------------------
#  Sağlayıcı ayarları ve testler
# ------------------------------------------------------------------
@require_permission("ai.configure")
def provider_settings(request):
    return render(
        request,
        "ai/providers.html",
        {
            "page_title": "Yapay Zekâ Sağlayıcıları",
            "providers": provider_status(),
            "budget": gateway.budget_status(),
            "usage": AIUsageLog.statistics(30),
            "ai_settings": django_settings.AI,
        },
    )


@require_permission("ai.use")
@require_POST
def test_provider(request, key: str):
    """Tek sağlayıcının bağlantısını test eder. API anahtarı gösterilmez."""
    result = gateway.test_provider(key)
    record_audit(
        AuditLog.Action.AI_CALL,
        description=(
            f"AI sağlayıcı bağlantı testi: {key} -> "
            f"{'başarılı' if result['ok'] else 'başarısız'} ({result['latency_ms']} ms)"
        ),
        request=request,
    )
    return JsonResponse(result)


@require_permission("ai.use")
@require_POST
def test_all(request):
    results = gateway.test_all_providers()
    return JsonResponse({"results": results})


@require_permission("ai.configure")
@require_POST
def reset_breakers(request):
    gateway.reset_all_breakers()
    messages.success(request, "Tüm sağlayıcı devre kesicileri sıfırlandı.")
    return redirect("ai:providers")


@require_permission("ai.use")
def usage_log(request):
    logs = AIUsageLog.objects.select_related("user").order_by("-created_at")[:200]
    return render(
        request,
        "ai/usage.html",
        {
            "page_title": "Yapay Zekâ Kullanımı",
            "logs": logs,
            "statistics": AIUsageLog.statistics(30),
            "budget": gateway.budget_status(),
        },
    )
