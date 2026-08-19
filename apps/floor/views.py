"""Salon, masa planı ve rezervasyon görünümleri."""

from __future__ import annotations

from datetime import datetime, timedelta

from django.contrib import messages
from django.db.models import Prefetch, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.decorators import require_permission
from apps.accounts.models import User
from apps.core.models import AuditLog
from apps.core.services import record_audit
from apps.floor.forms import ReservationForm, TableForm
from apps.floor.models import Area, Reservation, Table, WaitlistEntry
from apps.orders.models import Order


@require_permission("table.view")
def table_map(request):
    """Görsel masa planı."""
    areas = Area.objects.filter(is_active=True).prefetch_related(
        Prefetch(
            "tables",
            queryset=Table.objects.filter(is_active=True)
            .select_related("assigned_waiter")
            .order_by("name"),
        )
    )
    open_orders = {
        o.table_id: o
        for o in Order.objects.exclude(
            status__in=[Order.Status.PAID, Order.Status.CANCELLED]
        ).select_related("waiter")
        if o.table_id
    }
    today = timezone.localdate()
    upcoming = (
        Reservation.objects.filter(
            reserved_at__date=today,
            status__in=[Reservation.Status.CONFIRMED, Reservation.Status.PENDING],
        )
        .prefetch_related("tables")
        .order_by("reserved_at")
    )

    stats = {
        "total": Table.objects.filter(is_active=True).count(),
        "occupied": Table.objects.filter(is_active=True, status=Table.Status.OCCUPIED).count(),
        "free": Table.objects.filter(is_active=True, status=Table.Status.FREE).count(),
        "reserved": Table.objects.filter(is_active=True, status=Table.Status.RESERVED).count(),
        "cleaning": Table.objects.filter(is_active=True, status=Table.Status.CLEANING).count(),
    }
    stats["occupancy_rate"] = (
        round(stats["occupied"] / stats["total"] * 100) if stats["total"] else 0
    )

    return render(
        request,
        "floor/table_map.html",
        {
            "page_title": "Masa Planı",
            "areas": areas,
            "open_orders": open_orders,
            "upcoming_reservations": upcoming,
            "stats": stats,
            "waiters": User.objects.filter(is_active=True).order_by("first_name"),
            "statuses": Table.Status.choices,
        },
    )


@require_permission("table.manage")
@require_POST
def table_set_status(request, pk: int):
    table = get_object_or_404(Table, pk=pk)
    new_status = request.POST.get("status")
    if new_status not in dict(Table.Status.choices):
        return JsonResponse({"ok": False, "detail": "Geçersiz durum."}, status=400)
    if new_status == Table.Status.FREE and table.active_order:
        return JsonResponse(
            {"ok": False, "detail": "Masada açık adisyon var. Önce adisyonu kapatın."}, status=400
        )
    table.status = new_status
    if new_status != Table.Status.OCCUPIED:
        table.occupied_since = None
    table.save(update_fields=["status", "occupied_since", "updated_at"])
    return JsonResponse({"ok": True, "status": table.get_status_display()})


@require_permission("table.manage")
@require_POST
def table_assign_waiter(request, pk: int):
    table = get_object_or_404(Table, pk=pk)
    waiter_id = request.POST.get("waiter_id")
    table.assigned_waiter = User.objects.filter(pk=waiter_id).first() if waiter_id else None
    table.save(update_fields=["assigned_waiter", "updated_at"])
    return JsonResponse(
        {
            "ok": True,
            "waiter": table.assigned_waiter.display_name if table.assigned_waiter else "—",
        }
    )


@require_permission("table.manage")
@require_POST
def table_merge(request, pk: int):
    """Masaları birleştirir."""
    main = get_object_or_404(Table, pk=pk)
    child_ids = [int(i) for i in request.POST.getlist("table_ids") if i]
    children = Table.objects.filter(pk__in=child_ids).exclude(pk=main.pk)
    for child in children:
        if child.active_order:
            return JsonResponse(
                {"ok": False, "detail": f"{child.name} masasında açık adisyon var."}, status=400
            )
        child.merged_into = main
        child.status = Table.Status.OCCUPIED
        child.save(update_fields=["merged_into", "status", "updated_at"])
    record_audit(
        AuditLog.Action.UPDATE,
        obj=main,
        description=f"{main.name} ile {children.count()} masa birleştirildi.",
        request=request,
    )
    return JsonResponse({"ok": True, "capacity": main.effective_capacity})


@require_permission("table.manage")
@require_POST
def table_unmerge(request, pk: int):
    main = get_object_or_404(Table, pk=pk)
    count = main.merged_tables.update(merged_into=None, status=Table.Status.FREE)
    return JsonResponse({"ok": True, "released": count})


@require_permission("table.manage")
def table_list(request):
    tables = Table.objects.select_related("area", "assigned_waiter").order_by(
        "area__sort_order", "name"
    )
    return render(
        request,
        "floor/table_list.html",
        {"page_title": "Masa Yönetimi", "tables": tables, "areas": Area.objects.all()},
    )


@require_permission("table.manage")
def table_create(request):
    if request.method == "POST":
        form = TableForm(request.POST)
        if form.is_valid():
            table = form.save(commit=False)
            table.created_by = request.user
            table.save()
            messages.success(request, f"{table.name} eklendi.")
            return redirect("floor:table_list")
    else:
        form = TableForm()
    return render(request, "floor/table_form.html", {"form": form, "page_title": "Yeni Masa"})


@require_permission("table.manage")
def table_edit(request, pk: int):
    table = get_object_or_404(Table, pk=pk)
    if request.method == "POST":
        form = TableForm(request.POST, instance=table)
        if form.is_valid():
            form.save()
            messages.success(request, "Masa güncellendi.")
            return redirect("floor:table_list")
    else:
        form = TableForm(instance=table)
    return render(
        request,
        "floor/table_form.html",
        {"form": form, "table": table, "page_title": f"Düzenle: {table.name}"},
    )


# ------------------------------------------------------------------
#  Rezervasyon
# ------------------------------------------------------------------
@require_permission("reservation.view")
def reservation_list(request):
    reservations = Reservation.objects.select_related("customer", "area").prefetch_related("tables")
    date_filter = request.GET.get("date", "")
    status = request.GET.get("status", "")
    search = request.GET.get("q", "").strip()

    if date_filter:
        reservations = reservations.filter(reserved_at__date=date_filter)
    else:
        reservations = reservations.filter(reserved_at__date__gte=timezone.localdate())
    if status:
        reservations = reservations.filter(status=status)
    if search:
        reservations = reservations.filter(
            Q(guest_name__icontains=search)
            | Q(code__icontains=search)
            | Q(guest_phone__icontains=search)
        )

    today = timezone.localdate()
    stats = {
        "today": Reservation.objects.filter(reserved_at__date=today).count(),
        "today_guests": sum(
            r.party_size for r in Reservation.objects.filter(reserved_at__date=today)
        ),
        "pending": Reservation.objects.filter(status=Reservation.Status.PENDING).count(),
        "no_show_month": Reservation.objects.filter(
            status=Reservation.Status.NO_SHOW, reserved_at__gte=timezone.now() - timedelta(days=30)
        ).count(),
    }

    return render(
        request,
        "floor/reservation_list.html",
        {
            "page_title": "Rezervasyonlar",
            "reservations": reservations.order_by("reserved_at")[:200],
            "statuses": Reservation.Status.choices,
            "filters": {"date": date_filter, "status": status, "q": search},
            "stats": stats,
            "waitlist": WaitlistEntry.objects.filter(status=WaitlistEntry.Status.WAITING),
        },
    )


@require_permission("reservation.manage")
def reservation_create(request):
    if request.method == "POST":
        form = ReservationForm(request.POST)
        if form.is_valid():
            reservation = form.save(commit=False)
            reservation.created_by = request.user
            reservation.save()
            form.save_m2m()
            for table in reservation.tables.all():
                if table.status == Table.Status.FREE:
                    table.status = Table.Status.RESERVED
                    table.save(update_fields=["status", "updated_at"])
            messages.success(
                request, f"Rezervasyon oluşturuldu: {reservation.code} ({reservation.guest_name})"
            )
            return redirect("floor:reservation_list")
    else:
        initial = {}
        if request.GET.get("date"):
            initial["reserved_at"] = request.GET["date"]
        form = ReservationForm(initial=initial)
    return render(
        request,
        "floor/reservation_form.html",
        {"form": form, "page_title": "Yeni Rezervasyon"},
    )


@require_permission("reservation.manage")
def reservation_edit(request, pk: int):
    reservation = get_object_or_404(Reservation, pk=pk)
    if request.method == "POST":
        form = ReservationForm(request.POST, instance=reservation)
        if form.is_valid():
            form.save()
            messages.success(request, "Rezervasyon güncellendi.")
            return redirect("floor:reservation_list")
    else:
        form = ReservationForm(instance=reservation)
    return render(
        request,
        "floor/reservation_form.html",
        {"form": form, "reservation": reservation, "page_title": f"Rezervasyon {reservation.code}"},
    )


@require_permission("reservation.manage")
@require_POST
def reservation_set_status(request, pk: int):
    reservation = get_object_or_404(Reservation, pk=pk)
    new_status = request.POST.get("status")
    if new_status not in dict(Reservation.Status.choices):
        return JsonResponse({"ok": False, "detail": "Geçersiz durum."}, status=400)

    reservation.status = new_status
    fields = ["status", "updated_at"]

    if new_status == Reservation.Status.SEATED:
        reservation.seated_at = timezone.now()
        fields.append("seated_at")
        for table in reservation.tables.all():
            table.mark_occupied()
    elif new_status == Reservation.Status.COMPLETED:
        reservation.completed_at = timezone.now()
        fields.append("completed_at")
    elif new_status == Reservation.Status.NO_SHOW and reservation.customer_id:
        reservation.customer.no_show_count += 1
        reservation.customer.save(update_fields=["no_show_count"])
        for table in reservation.tables.filter(status=Table.Status.RESERVED):
            table.status = Table.Status.FREE
            table.save(update_fields=["status", "updated_at"])
    elif new_status == Reservation.Status.CANCELLED:
        reservation.cancellation_reason = request.POST.get("reason", "")[:300]
        fields.append("cancellation_reason")
        for table in reservation.tables.filter(status=Table.Status.RESERVED):
            table.status = Table.Status.FREE
            table.save(update_fields=["status", "updated_at"])

    reservation.save(update_fields=fields)
    return JsonResponse({"ok": True, "status": reservation.get_status_display()})


@require_permission("reservation.view")
def reservation_availability(request):
    """Belirli bir tarih/saatte uygun masaları döndürür."""
    date_str = request.GET.get("datetime", "")
    party_size = int(request.GET.get("party_size") or 2)
    duration = int(request.GET.get("duration") or 90)
    try:
        start = timezone.make_aware(datetime.fromisoformat(date_str))
    except (ValueError, TypeError):
        return JsonResponse({"ok": False, "detail": "Geçersiz tarih/saat."}, status=400)

    end = start + timedelta(minutes=duration)
    busy_table_ids = set(
        Reservation.objects.filter(
            status__in=[
                Reservation.Status.PENDING,
                Reservation.Status.CONFIRMED,
                Reservation.Status.SEATED,
            ],
            reserved_at__lt=end,
        )
        .filter(reserved_at__gt=start - timedelta(minutes=240))
        .values_list("tables__id", flat=True)
    )
    available = (
        Table.objects.filter(is_active=True, capacity__gte=party_size)
        .exclude(pk__in=busy_table_ids)
        .exclude(status=Table.Status.DISABLED)
        .select_related("area")
        .order_by("capacity")
    )
    return JsonResponse(
        {
            "ok": True,
            "tables": [
                {"id": t.pk, "name": t.name, "area": t.area.name, "capacity": t.capacity}
                for t in available
            ],
        }
    )


@require_permission("reservation.manage")
@require_POST
def waitlist_add(request):
    entry = WaitlistEntry.objects.create(
        guest_name=request.POST.get("guest_name", "")[:120],
        guest_phone=request.POST.get("guest_phone", "")[:20],
        party_size=int(request.POST.get("party_size") or 2),
        estimated_wait_minutes=int(request.POST.get("estimated_wait_minutes") or 15),
        note=request.POST.get("note", "")[:200],
        created_by=request.user,
    )
    messages.success(request, f"{entry.guest_name} bekleme listesine eklendi.")
    return redirect("floor:reservation_list")


@require_permission("reservation.manage")
@require_POST
def waitlist_update(request, pk: int):
    entry = get_object_or_404(WaitlistEntry, pk=pk)
    new_status = request.POST.get("status", WaitlistEntry.Status.NOTIFIED)
    entry.status = new_status
    if new_status == WaitlistEntry.Status.NOTIFIED:
        entry.notified_at = timezone.now()
    elif new_status == WaitlistEntry.Status.SEATED:
        entry.seated_at = timezone.now()
    entry.save()
    return JsonResponse({"ok": True, "status": entry.get_status_display()})


@require_permission("table.view")
def table_qr(request, pk: int):
    """Masa için QR kod görseli üretir (PNG)."""
    import io

    import qrcode
    from django.http import HttpResponse

    table = get_object_or_404(Table, pk=pk)
    url = request.build_absolute_uri(table.qr_menu_path)
    image = qrcode.make(url)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return HttpResponse(buffer.getvalue(), content_type="image/png")
