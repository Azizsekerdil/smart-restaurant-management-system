"""Yapay zekâ REST uç noktaları."""

from __future__ import annotations

import json

from django.urls import path
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.ai import analytics, gateway, prompts
from apps.ai.models import AIInsight, AITask, AIUsageLog


def _require(request, code: str) -> bool:
    return request.user.has_perm_code(code)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def ask_endpoint(request):
    """Serbest metin sorusu sorar."""
    if not _require(request, "ai.use"):
        return Response({"detail": "Yetkiniz yok."}, status=403)
    question = (request.data.get("question") or "").strip()
    if not question:
        return Response({"detail": "question alanı zorunludur."}, status=400)
    try:
        result = gateway.ask(
            question,
            system=prompts.ASSISTANT,
            task=request.data.get("task", AITask.GENERAL),
            feature="api_ask",
            user=request.user,
            preferred_provider=request.data.get("provider", ""),
            preferred_model=request.data.get("model", ""),
            temperature=float(request.data.get("temperature", 0.3)),
        )
    except gateway.AIUnavailable as exc:
        return Response({"detail": str(exc), "code": "ai_unavailable"}, status=503)
    return Response(
        {
            "answer": result.text,
            "provider": result.provider,
            "model": result.model,
            "latency_ms": result.latency_ms,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def providers_endpoint(request):
    """Sağlayıcı durumları. API anahtarları maskeli döner."""
    if not _require(request, "ai.use"):
        return Response({"detail": "Yetkiniz yok."}, status=403)
    from apps.ai.providers import provider_status

    return Response({"providers": provider_status(), "budget": _serialize(gateway.budget_status())})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def health_endpoint(request):
    if not _require(request, "ai.use"):
        return Response({"detail": "Yetkiniz yok."}, status=403)
    key = request.data.get("provider")
    if key:
        return Response(gateway.test_provider(key))
    return Response({"results": gateway.test_all_providers()})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def analysis_endpoint(request, kind: str):
    if not _require(request, "ai.use"):
        return Response({"detail": "Yetkiniz yok."}, status=403)
    handlers = {
        "menu-engineering": lambda: analytics.menu_engineering(user=request.user),
        "demand-forecast": lambda: analytics.demand_forecast(user=request.user),
        "stock-forecast": lambda: analytics.stock_forecast(user=request.user),
        "waste": lambda: analytics.waste_analysis(user=request.user),
        "anomaly": lambda: analytics.anomaly_detection(user=request.user),
        "staffing": lambda: analytics.staffing_suggestion(user=request.user),
        "daily-summary": lambda: analytics.daily_summary(user=request.user),
    }
    handler = handlers.get(kind)
    if handler is None:
        return Response({"detail": f"Bilinmeyen analiz: {kind}"}, status=400)
    return Response(_serialize(handler()))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def usage_endpoint(request):
    if not _require(request, "ai.use"):
        return Response({"detail": "Yetkiniz yok."}, status=403)
    return Response(_serialize(AIUsageLog.statistics(int(request.query_params.get("days", 30)))))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def insights_endpoint(request):
    if not _require(request, "ai.use"):
        return Response({"detail": "Yetkiniz yok."}, status=403)
    qs = AIInsight.objects.all()[:50]
    return Response(
        [
            {
                "id": i.pk,
                "kind": i.kind,
                "title": i.title,
                "summary": i.summary,
                "confidence": i.confidence,
                "data_points": i.data_points,
                "limitations": i.limitations,
                "created_at": i.created_at,
            }
            for i in qs
        ]
    )


def _serialize(data):
    """Decimal/date içeren sözlükleri JSON uyumlu hale getirir."""
    return json.loads(json.dumps(data, default=str))


urlpatterns = [
    path("ask/", ask_endpoint, name="ai_ask"),
    path("providers/", providers_endpoint, name="ai_providers"),
    path("health/", health_endpoint, name="ai_health"),
    path("analysis/<str:kind>/", analysis_endpoint, name="ai_analysis"),
    path("usage/", usage_endpoint, name="ai_usage"),
    path("insights/", insights_endpoint, name="ai_insights"),
]
