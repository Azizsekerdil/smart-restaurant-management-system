"""Yedekleme arayüzü."""

from __future__ import annotations

import logging

from django.contrib import messages
from django.contrib.auth import logout
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.decorators import require_permission
from apps.backups import services
from apps.backups.models import BackupRecord, RestoreRecord
from apps.core.models import AuditLog
from apps.core.services import record_audit

logger = logging.getLogger(__name__)

#: Geri yükleme geri alınamaz. Kullanıcının yanlışlıkla tıklamasını değil,
#: bilinçli bir onayı istiyoruz.
RESTORE_CONFIRMATION = "GERİ YÜKLE"


@require_permission("backup.view")
def index(request):
    """Yedek listesi ve klasör durumu."""
    records = BackupRecord.objects.select_related("created_by").all()[:100]
    restores = RestoreRecord.objects.select_related("created_by", "safety_backup")[:10]

    elapsed = services.hours_since_last_backup()
    stale = elapsed is None or elapsed > 48

    return render(
        request,
        "backups/index.html",
        {
            "records": records,
            "restores": restores,
            "summary": services.storage_summary(),
            "hours_since": elapsed,
            "stale": stale,
            "restore_confirmation": RESTORE_CONFIRMATION,
            "is_sqlite": services.is_sqlite(),
            "can_create": request.user.has_perm_code("backup.create"),
            "can_download": request.user.has_perm_code("backup.download"),
            "can_restore": request.user.has_perm_code("backup.restore"),
        },
    )


@require_POST
@require_permission("backup.create")
def create(request):
    """Elle yedek alır."""
    include_media = request.POST.get("include_media") == "1"
    include_secrets = request.POST.get("include_secrets") == "1"
    note = (request.POST.get("note") or "").strip()

    try:
        result = services.create_backup(
            user=request.user,
            kind=BackupRecord.Kind.MANUAL,
            include_media=include_media,
            include_secrets=include_secrets,
            note=note,
            request=request,
        )
    except services.BackupError as exc:
        messages.error(request, f"Yedek alınamadı: {exc}")
        return redirect("backups:index")

    messages.success(
        request,
        f"Yedek alındı: {result.record.filename} ({result.record.size_mb} MB)",
    )
    for warning in result.warnings:
        messages.warning(request, warning)
    return redirect("backups:index")


@require_permission("backup.download")
def download(request, pk: int):
    """Yedek dosyasını indirir.

    Dosya müşteri kişisel verisi içerir; indirme ayrı bir izne bağlıdır ve
    denetim kaydına yazılır.
    """
    record = get_object_or_404(BackupRecord, pk=pk)
    if not record.exists:
        raise Http404("Yedek dosyası bulunamadı.")

    record_audit(
        AuditLog.Action.EXPORT,
        user=request.user,
        obj=record,
        description=f"Yedek dosyası indirildi: {record.filename}",
        severity=AuditLog.Severity.WARNING,
        request=request,
    )
    return FileResponse(
        record.path.open("rb"),
        as_attachment=True,
        filename=record.filename,
        content_type="application/zip",
    )


@require_permission("backup.view")
def detail(request, pk: int):
    """Yedeğin içeriğini ve bütünlüğünü gösterir."""
    record = get_object_or_404(BackupRecord.objects.select_related("created_by"), pk=pk)

    manifest = None
    error = None
    checksum_ok = None
    if record.exists:
        try:
            manifest = services.inspect_archive(record.path)
            checksum_ok = services.verify_checksum(record)
        except services.BackupError as exc:
            error = str(exc)

    return render(
        request,
        "backups/detail.html",
        {
            "record": record,
            "manifest": manifest,
            "checksum_ok": checksum_ok,
            "error": error,
            "restore_confirmation": RESTORE_CONFIRMATION,
            "can_download": request.user.has_perm_code("backup.download"),
            "can_restore": request.user.has_perm_code("backup.restore"),
        },
    )


@require_POST
@require_permission("backup.restore")
def restore(request, pk: int):
    """Yedekten geri yükler."""
    record = get_object_or_404(BackupRecord, pk=pk)

    typed = (request.POST.get("confirmation") or "").strip()
    if typed.casefold() != RESTORE_CONFIRMATION.casefold():
        messages.error(
            request,
            f"Geri yükleme iptal edildi: onay kutusuna '{RESTORE_CONFIRMATION}' yazmalısınız.",
        )
        return redirect("backups:detail", pk=record.pk)

    try:
        result = services.restore_backup(record, user=request.user, request=request)
    except services.BackupError as exc:
        messages.error(request, f"Geri yükleme başarısız: {exc}")
        return redirect("backups:detail", pk=record.pk)

    safety = result.safety_backup

    # Geri yükleme oturum tablosunu da yedekteki hâline döndürdü: bu
    # isteğin oturumu artık veritabanında yok. Django'nun oturum ara
    # katmanı isteğin sonunda oturumu kaydetmeye çalışır, satırı bulamaz
    # ve SessionInterrupted yükseltir — geri yükleme başarıyla bitmiş
    # olsa bile kullanıcı boş bir "Bad Request (400)" sayfası görür.
    #
    # Oturumu burada bilinçli olarak kapatıyoruz. Kullanıcı hesabı
    # yedekteki hâline döndüğü için yeniden giriş zaten gereklidir.
    logout(request)

    messages.success(
        request,
        f"Veriler {record.filename} yedeğinden geri yüklendi. "
        + (
            f"Önceki durum {safety.filename} olarak saklandı."
            if safety
            else "Güvenlik yedeği alınamadı."
        ),
    )
    messages.info(
        request,
        "Kullanıcı hesapları da yedekteki hâline döndüğü için oturumunuz "
        "kapatıldı. Lütfen yeniden giriş yapın.",
    )
    return redirect("accounts:login")


@require_POST
@require_permission("backup.restore")
def delete(request, pk: int):
    """Yedeği siler.

    Silme yetkisi geri yükleme ile aynı seviyededir: yedeği yok etmek de
    veri kaybı riski taşır.
    """
    record = get_object_or_404(BackupRecord, pk=pk)
    filename = record.filename

    try:
        record.path.unlink(missing_ok=True)
    except OSError as exc:
        messages.error(request, f"Dosya silinemedi: {exc}")
        return redirect("backups:index")

    record.delete()
    record_audit(
        AuditLog.Action.DELETE,
        user=request.user,
        description=f"Yedek silindi: {filename}",
        severity=AuditLog.Severity.WARNING,
        request=request,
    )
    messages.success(request, f"Yedek silindi: {filename}")
    return redirect("backups:index")
