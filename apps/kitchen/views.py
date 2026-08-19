"""Mutfak ekranı (KDS) görünümleri."""

from __future__ import annotations

from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.decorators import require_permission
from apps.kitchen import services
from apps.kitchen.models import KitchenTicket, Station


@require_permission("kitchen.view", "bar.view")
def display(request):
    """Mutfak / bar ekranı. Sesli ve görsel uyarılarla canlı KOT akışı."""
    station_code = request.GET.get("station", "all")
    stations = Station.objects.filter(is_active=True).order_by("sort_order")

    # Bar personeli yalnızca bar istasyonunu görebilir.
    if not request.user.has_perm_code("kitchen.view") and request.user.has_perm_code("bar.view"):
        stations = stations.filter(kind=Station.Kind.BAR)
        if station_code == "all" and stations.exists():
            station_code = stations.first().code

    tickets = services.station_queue(station_code)
    return render(
        request,
        "kitchen/display.html",
        {
            "page_title": "Mutfak Ekranı",
            "tickets": tickets,
            "stations": stations,
            "current_station": station_code,
            "hide_sidebar": True,
            "ws_url": f"/ws/kitchen/{station_code}/",
        },
    )


@require_permission("kitchen.view", "bar.view")
def ticket_board(request):
    """HTMX ile yenilenen KOT panosu parçası."""
    station_code = request.GET.get("station", "all")
    return render(
        request,
        "kitchen/_ticket_board.html",
        {"tickets": services.station_queue(station_code)},
    )


@require_permission("kitchen.manage")
@require_POST
def ticket_transition(request, pk: int, action: str):
    ticket = get_object_or_404(KitchenTicket.objects.select_related("station", "order"), pk=pk)
    handlers = {
        "start": services.start_ticket,
        "ready": services.mark_ticket_ready,
        "complete": services.complete_ticket,
        "rush": services.bump_priority,
    }
    handler = handlers.get(action)
    if handler is None:
        return JsonResponse({"ok": False, "detail": "Geçersiz işlem."}, status=400)
    handler(ticket, user=request.user)
    return JsonResponse(
        {"ok": True, "status": ticket.status, "status_label": ticket.get_status_display()}
    )


@require_permission("kitchen.view", "bar.view")
def kot_print(request, pk: int):
    """KOT'un düz metin çıktısı (termal yazıcıya gönderilebilir)."""
    ticket = get_object_or_404(KitchenTicket, pk=pk)
    text = services.kot_text(ticket)
    ticket.printed_at = timezone.now()
    ticket.save(update_fields=["printed_at", "updated_at"])
    response = HttpResponse(text, content_type="text/plain; charset=utf-8")
    response["Content-Disposition"] = f'inline; filename="kot-{ticket.number}.txt"'
    return response


@require_permission("kitchen.view")
def kot_preview(request, pk: int):
    """Yazdırılabilir HTML KOT."""
    ticket = get_object_or_404(
        KitchenTicket.objects.select_related("station", "order", "order__table").prefetch_related(
            "lines__order_item__modifiers"
        ),
        pk=pk,
    )
    return render(request, "kitchen/kot_print.html", {"ticket": ticket})


@require_permission("kitchen.view")
def station_list(request):
    stations = Station.objects.all().order_by("sort_order")
    return render(
        request,
        "kitchen/station_list.html",
        {
            "page_title": "İstasyonlar",
            "stations": stations,
            "delayed": services.delayed_tickets(),
        },
    )


@require_permission("kitchen.manage")
@require_POST
def station_save(request):
    station_id = request.POST.get("station_id")
    data = {
        "name": request.POST.get("name", "").strip(),
        "kind": request.POST.get("kind", Station.Kind.KITCHEN),
        "color": request.POST.get("color", "#fd7e14"),
        "warning_minutes": int(request.POST.get("warning_minutes") or 10),
        "critical_minutes": int(request.POST.get("critical_minutes") or 20),
        "printer_name": request.POST.get("printer_name", ""),
        "sort_order": int(request.POST.get("sort_order") or 100),
        "is_active": request.POST.get("is_active") == "on",
    }
    if not data["name"]:
        messages.error(request, "İstasyon adı zorunludur.")
        return redirect("kitchen:station_list")

    if station_id:
        Station.objects.filter(pk=station_id).update(**data)
        messages.success(request, "İstasyon güncellendi.")
    else:
        Station.objects.create(created_by=request.user, **data)
        messages.success(request, "İstasyon eklendi.")
    return redirect("kitchen:station_list")


@require_permission("kitchen.view")
def performance(request):
    """İstasyon bazlı hazırlık süresi performansı."""
    from datetime import timedelta

    from django.db.models import Avg, Count, F

    since = timezone.now() - timedelta(days=7)
    rows = (
        KitchenTicket.objects.filter(
            queued_at__gte=since, ready_at__isnull=False, status=KitchenTicket.Status.COMPLETED
        )
        .values("station__name", "station__critical_minutes")
        .annotate(
            ticket_count=Count("id"),
            avg_seconds=Avg(F("ready_at") - F("queued_at")),
        )
        .order_by("-ticket_count")
    )
    data = []
    for row in rows:
        seconds = row["avg_seconds"].total_seconds() if row["avg_seconds"] else 0
        data.append(
            {
                "station": row["station__name"],
                "count": row["ticket_count"],
                "avg_minutes": round(seconds / 60, 1),
                "target": row["station__critical_minutes"],
                "over_target": (seconds / 60) > row["station__critical_minutes"],
            }
        )
    return render(
        request,
        "kitchen/performance.html",
        {"page_title": "Mutfak Performansı", "rows": data, "delayed": services.delayed_tickets()},
    )
