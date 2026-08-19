"""Çekirdek görünümler: yönlendirme, hata sayfaları, bildirimler, ayarlar."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.decorators import require_permission
from apps.core.models import AuditLog, Notification, SystemSetting
from apps.core.services import record_audit


@login_required
def home(request):
    """Kullanıcının rolüne göre en uygun başlangıç ekranına yönlendirir."""
    user = request.user
    if user.has_perm_code("dashboard.view") and user.is_manager:
        return redirect("reports:dashboard")
    if user.has_perm_code("kitchen.view") and not user.has_perm_code("pos.use"):
        return redirect("kitchen:display")
    if user.has_perm_code("pos.use"):
        return redirect("orders:pos")
    if user.has_perm_code("delivery.view"):
        return redirect("orders:delivery_board")
    return redirect("reports:dashboard")


@login_required
def notification_list(request):
    notifications = Notification.objects.filter(
        Q(recipient=request.user) | Q(recipient__isnull=True)
    ).order_by("-created_at")[:100]
    return render(
        request,
        "core/notifications.html",
        {"notifications": notifications, "page_title": "Bildirim Merkezi"},
    )


@login_required
def notification_feed(request):
    """Bildirim rozeti için hafif JSON uç noktası (HTMX ile yoklanır)."""
    qs = Notification.objects.filter(
        Q(recipient=request.user) | Q(recipient__isnull=True), is_read=False
    ).order_by("-created_at")[:10]
    return JsonResponse(
        {
            "count": qs.count(),
            "items": [
                {
                    "id": n.pk,
                    "title": n.title,
                    "body": n.body[:160],
                    "level": n.level,
                    "category": n.get_category_display(),
                    "url": n.url,
                    "created_at": n.created_at.isoformat(),
                }
                for n in qs
            ],
        }
    )


@login_required
@require_POST
def notification_mark_read(request, pk: int):
    notification = get_object_or_404(
        Notification.objects.filter(Q(recipient=request.user) | Q(recipient__isnull=True)), pk=pk
    )
    notification.mark_read()
    if request.headers.get("HX-Request"):
        return JsonResponse({"ok": True})
    return redirect("core:notifications")


@login_required
@require_POST
def notification_mark_all_read(request):
    from django.utils import timezone

    Notification.objects.filter(
        Q(recipient=request.user) | Q(recipient__isnull=True), is_read=False
    ).update(is_read=True, read_at=timezone.now())
    messages.success(request, "Tüm bildirimler okundu olarak işaretlendi.")
    return redirect("core:notifications")


@require_permission("settings.manage", "user.manage")
def settings_index(request):
    from django.conf import settings as django_settings

    grouped: dict[str, list[SystemSetting]] = {}
    for setting in SystemSetting.objects.all():
        grouped.setdefault(setting.group, []).append(setting)

    return render(
        request,
        "core/settings.html",
        {
            "page_title": "Sistem Ayarları",
            "grouped_settings": grouped,
            "restaurant": django_settings.RESTAURANT,
            "devcenter_enabled": django_settings.DEVCENTER["ENABLED"],
            "terminal_enabled": django_settings.DEVCENTER["TERMINAL_ENABLED"],
            "db_engine": django_settings.DATABASES["default"]["ENGINE"].rsplit(".", 1)[-1],
            "environment": django_settings.DJANGO_ENV,
        },
    )


@require_permission("settings.manage")
@require_POST
def settings_update(request):
    updated = 0
    for setting in SystemSetting.objects.filter(is_editable=True):
        field = f"setting_{setting.key}"
        if field in request.POST:
            new_value = request.POST[field].strip()
            if new_value != setting.value:
                old = setting.value
                setting.value = new_value
                setting.save(update_fields=["value", "updated_at"])
                record_audit(
                    AuditLog.Action.UPDATE,
                    obj=setting,
                    description=f"Ayar değiştirildi: {setting.key}",
                    changes={"eski": old, "yeni": new_value},
                    severity=AuditLog.Severity.NOTICE,
                    request=request,
                )
                updated += 1
    messages.success(request, f"{updated} ayar güncellendi.")
    return redirect("core:settings")


@require_permission("audit.view")
def audit_log(request):
    logs = AuditLog.objects.select_related("user")
    action = request.GET.get("action", "")
    severity = request.GET.get("severity", "")
    search = request.GET.get("q", "").strip()

    if action:
        logs = logs.filter(action=action)
    if severity:
        logs = logs.filter(severity=severity)
    if search:
        logs = logs.filter(
            Q(description__icontains=search)
            | Q(username_snapshot__icontains=search)
            | Q(object_type__icontains=search)
        )

    from django.core.paginator import Paginator

    paginator = Paginator(logs[:5000], 50)
    page = paginator.get_page(request.GET.get("page", 1))

    return render(
        request,
        "core/audit_log.html",
        {
            "page_title": "Denetim Kayıtları",
            "page_obj": page,
            "actions": AuditLog.Action.choices,
            "severities": AuditLog.Severity.choices,
            "current_action": action,
            "current_severity": severity,
            "search": search,
        },
    )


# ------------------------------------------------------------------
#  Hata sayfaları
# ------------------------------------------------------------------
def error_403(request, exception=None):
    return render(
        request,
        "core/403.html",
        {"message": "Bu sayfaya erişim yetkiniz bulunmuyor."},
        status=403,
    )


def error_404(request, exception=None):
    return render(
        request,
        "core/404.html",
        {"message": "Aradığınız sayfa bulunamadı."},
        status=404,
    )


def error_500(request):
    return render(
        request,
        "core/500.html",
        {"message": "Beklenmeyen bir hata oluştu. Sistem yöneticisine bildirildi."},
        status=500,
    )


def healthz(request):
    """Basit sağlık kontrolü (Docker / izleme için)."""
    from django.db import connection

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        db_ok = True
    except Exception:
        db_ok = False
    return JsonResponse({"status": "ok" if db_ok else "degraded", "database": db_ok})
