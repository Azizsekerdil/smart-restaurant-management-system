"""Yedekleme ve geri yükleme testleri.

Geri yükleme yıkıcı bir işlemdir; testler pytest'in geçici test
veritabanı üzerinde çalışır ve gerçek veriye dokunmaz.
"""

from __future__ import annotations

import json
import zipfile
from decimal import Decimal
from pathlib import Path

import pytest
from django.urls import reverse

from apps.backups import services
from apps.backups.models import BackupRecord, RestoreRecord
from apps.catalog.models import Category
from apps.core.models import AuditLog


@pytest.fixture
def backup_dir(tmp_path, settings):
    """Yedekler geçici klasöre yazılsın."""
    target = tmp_path / "yedekler"
    target.mkdir()
    settings.BACKUP_DIR = target
    settings.BACKUP = {**settings.BACKUP, "KEEP_LAST": 20, "ALLOW_SECRETS": False}
    return target


# ==================================================================
#  Yedek alma
# ==================================================================
@pytest.mark.django_db
def test_backup_creates_valid_archive(backup_dir, owner, category):
    result = services.create_backup(user=owner, note="test yedegi")

    assert result.record.status == BackupRecord.Status.SUCCESS
    assert result.path.is_file()
    assert result.record.size_bytes > 0
    assert result.record.checksum

    with zipfile.ZipFile(result.path) as archive:
        names = set(archive.namelist())
        assert services.MANIFEST_NAME in names
        assert services.DB_SQLITE_NAME in names
        assert services.JSON_DUMP_NAME in names
        manifest = json.loads(archive.read(services.MANIFEST_NAME).decode("utf-8"))

    assert manifest["veritabani_motoru"] == "sqlite"
    assert manifest["olusturan"] == owner.username
    assert manifest["not"] == "test yedegi"


@pytest.mark.django_db
def test_backup_checksum_matches_file(backup_dir, owner):
    result = services.create_backup(user=owner)
    assert services.verify_checksum(result.record) is True

    # Dosya bozulursa doğrulama başarısız olmalı
    with result.path.open("ab") as handle:
        handle.write(b"bozuk")
    assert services.verify_checksum(result.record) is False


@pytest.mark.django_db
def test_backup_excludes_secrets_by_default(backup_dir, owner, settings, tmp_path):
    env_file = Path(settings.DATA_DIR) / ".env"
    created = False
    if not env_file.exists():
        env_file.write_text("SECRET=deger\n", encoding="utf-8")
        created = True
    try:
        result = services.create_backup(user=owner)
        with zipfile.ZipFile(result.path) as archive:
            assert services.ENV_NAME not in archive.namelist()
        assert result.record.includes_secrets is False
        assert any(".env" in w for w in result.warnings)
    finally:
        if created:
            env_file.unlink(missing_ok=True)


@pytest.mark.django_db
def test_backup_refuses_secrets_when_disabled(backup_dir, owner, settings):
    settings.BACKUP = {**settings.BACKUP, "ALLOW_SECRETS": False}
    with pytest.raises(services.BackupError, match="kapalı"):
        services.create_backup(user=owner, include_secrets=True)


@pytest.mark.django_db
def test_backup_writes_audit_log(backup_dir, owner):
    services.create_backup(user=owner)
    entry = AuditLog.objects.filter(action=AuditLog.Action.EXPORT).first()
    assert entry is not None
    assert "Yedek alındı" in entry.description


# ==================================================================
#  Saklama politikası
# ==================================================================
@pytest.mark.django_db
def test_retention_removes_oldest(backup_dir, owner, settings):
    settings.BACKUP = {**settings.BACKUP, "KEEP_LAST": 2}
    for index in range(4):
        services.create_backup(user=owner, note=f"yedek {index}")

    remaining = BackupRecord.objects.filter(status=BackupRecord.Status.SUCCESS)
    assert remaining.count() == 2
    # En yeniler kalmalı
    assert set(remaining.values_list("note", flat=True)) == {"yedek 2", "yedek 3"}
    assert len(list(backup_dir.glob("*.zip"))) == 2


@pytest.mark.django_db
def test_retention_keeps_safety_backups(backup_dir, owner, settings):
    """Geri yükleme öncesi güvenlik yedekleri sayı sınırına takılmaz."""
    settings.BACKUP = {**settings.BACKUP, "KEEP_LAST": 1}
    services.create_backup(user=owner, kind=BackupRecord.Kind.PRE_RESTORE, note="guvenlik")
    for index in range(3):
        services.create_backup(user=owner, note=f"elle {index}")

    kinds = list(
        BackupRecord.objects.filter(status=BackupRecord.Status.SUCCESS).values_list(
            "kind", flat=True
        )
    )
    assert BackupRecord.Kind.PRE_RESTORE in kinds


# ==================================================================
#  Arşiv doğrulama
# ==================================================================
@pytest.mark.django_db
def test_inspect_rejects_foreign_archive(backup_dir, tmp_path):
    alien = tmp_path / "baska.zip"
    with zipfile.ZipFile(alien, "w") as archive:
        archive.writestr("okuma.txt", "bu bir yedek degil")

    with pytest.raises(services.BackupError, match="manifest"):
        services.inspect_archive(alien)


@pytest.mark.django_db
def test_inspect_rejects_corrupt_file(backup_dir, tmp_path):
    broken = tmp_path / "bozuk.zip"
    broken.write_bytes(b"bu bir zip degil")

    with pytest.raises(services.BackupError, match="bozuk"):
        services.inspect_archive(broken)


@pytest.mark.django_db
def test_extract_blocks_path_traversal(backup_dir, tmp_path):
    """Arşiv, hedef klasörün dışına dosya yazamamalı (zip slip)."""
    evil = tmp_path / "kotu.zip"
    with zipfile.ZipFile(evil, "w") as archive:
        archive.writestr("../../kacak.txt", "disari yazildi")

    destination = tmp_path / "hedef"
    destination.mkdir()
    with zipfile.ZipFile(evil) as archive, pytest.raises(services.BackupError, match="güvenli"):
        services._safe_extract(archive, destination)

    assert not (tmp_path.parent / "kacak.txt").exists()


# ==================================================================
#  Geri yükleme
# ==================================================================
@pytest.mark.django_db(transaction=True)
def test_restore_round_trip(backup_dir, owner):
    """Yedek alındıktan sonra silinen veri geri gelmeli."""
    Category.objects.create(name="Tatlılar", sort_order=5)
    before = set(Category.objects.values_list("name", flat=True))

    result = services.create_backup(user=owner, note="geri yukleme testi")

    Category.objects.all().delete()
    Category.objects.create(name="Yedekten Sonra Eklenen")
    assert set(Category.objects.values_list("name", flat=True)) != before

    restore = services.restore_backup(result.record, user=owner)

    assert restore.status == RestoreRecord.Status.SUCCESS
    assert set(Category.objects.values_list("name", flat=True)) == before


@pytest.mark.django_db(transaction=True)
def test_restore_takes_safety_backup_first(backup_dir, owner):
    result = services.create_backup(user=owner)
    restore = services.restore_backup(result.record, user=owner)

    assert restore.safety_backup is not None
    assert restore.safety_backup.kind == BackupRecord.Kind.PRE_RESTORE
    assert restore.safety_backup.path.is_file()


@pytest.mark.django_db
def test_restore_rejects_missing_file(backup_dir, owner):
    result = services.create_backup(user=owner)
    result.path.unlink()

    with pytest.raises(services.BackupError, match="bulunamadı"):
        services.restore_backup(result.record, user=owner)


@pytest.mark.django_db
def test_restore_rejects_tampered_archive(backup_dir, owner):
    result = services.create_backup(user=owner)
    with result.path.open("ab") as handle:
        handle.write(b"degistirildi")

    with pytest.raises(services.BackupError, match="sağlama"):
        services.restore_backup(result.record, user=owner)


@pytest.mark.django_db(transaction=True)
def test_restore_writes_critical_audit_log(backup_dir, owner):
    result = services.create_backup(user=owner)
    services.restore_backup(result.record, user=owner)

    entry = AuditLog.objects.filter(severity=AuditLog.Severity.CRITICAL).first()
    assert entry is not None
    assert "geri yüklendi" in entry.description


# ==================================================================
#  Yetkilendirme
# ==================================================================
@pytest.mark.django_db
def test_waiter_cannot_see_backups(client, waiter, backup_dir):
    client.force_login(waiter)
    response = client.get(reverse("backups:index"))
    assert response.status_code == 403


@pytest.mark.django_db
def test_manager_can_list_but_not_restore(client, manager, owner, backup_dir):
    record = services.create_backup(user=owner).record

    client.force_login(manager)
    assert client.get(reverse("backups:index")).status_code == 200

    response = client.post(
        reverse("backups:restore", args=[record.pk]),
        {"confirmation": "GERİ YÜKLE"},
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_owner_can_create_backup_from_ui(client, owner, backup_dir):
    client.force_login(owner)
    response = client.post(reverse("backups:create"), {"include_media": "1"}, follow=True)

    assert response.status_code == 200
    assert BackupRecord.objects.filter(status=BackupRecord.Status.SUCCESS).exists()


@pytest.mark.django_db
def test_restore_requires_confirmation_phrase(client, owner, backup_dir):
    record = services.create_backup(user=owner).record

    client.force_login(owner)
    response = client.post(
        reverse("backups:restore", args=[record.pk]),
        {"confirmation": "evet"},
        follow=True,
    )

    assert response.status_code == 200
    assert not RestoreRecord.objects.exists()
    assert any("onay" in str(m).lower() for m in response.context["messages"])


@pytest.mark.django_db(transaction=True)
def test_restore_logs_user_out_instead_of_failing(client, owner, backup_dir):
    """Geri yükleme oturum tablosunu da değiştirir.

    Oturum kapatılmazsa Django'nun oturum ara katmanı isteğin sonunda
    silinmiş satırı güncellemeye çalışır ve SessionInterrupted (HTTP 400)
    yükseltir; geri yükleme başarılı olsa bile kullanıcı boş bir hata
    sayfası görür.
    """
    record = services.create_backup(user=owner).record

    client.force_login(owner)
    response = client.post(
        reverse("backups:restore", args=[record.pk]),
        {"confirmation": "GERİ YÜKLE"},
    )

    assert response.status_code == 302
    assert reverse("accounts:login") in response["Location"]
    assert RestoreRecord.objects.filter(status=RestoreRecord.Status.SUCCESS).exists()

    # Oturum gerçekten kapanmış olmalı
    following = client.get(reverse("backups:index"))
    assert following.status_code in (302, 403)


@pytest.mark.django_db
def test_download_is_audited(client, owner, backup_dir):
    record = services.create_backup(user=owner).record
    AuditLog.objects.all().delete()

    client.force_login(owner)
    response = client.get(reverse("backups:download", args=[record.pk]))
    assert response.status_code == 200
    # NOT: Denetim kaydı yanıt kapatılmadan ÖNCE sorgulanır. FileResponse
    # kapanınca request_finished sinyali veritabanı bağlantısını kapatır.
    assert AuditLog.objects.filter(description__contains="indirildi").exists()
    response.close()


# ==================================================================
#  Zamanlayıcı
# ==================================================================
@pytest.mark.django_db
def test_scheduler_skips_when_recent_backup_exists(backup_dir, owner, settings):
    from apps.backups import scheduler

    settings.BACKUP = {**settings.BACKUP, "SCHEDULE_HOURS": 24}
    services.create_backup(user=owner)

    assert scheduler.run_due_backup() is False


@pytest.mark.django_db
def test_scheduler_creates_backup_when_none_exists(backup_dir, settings):
    from apps.backups import scheduler

    settings.BACKUP = {**settings.BACKUP, "SCHEDULE_HOURS": 24}
    assert scheduler.run_due_backup() is True
    assert BackupRecord.objects.filter(kind=BackupRecord.Kind.SCHEDULED).exists()


@pytest.mark.django_db
def test_scheduler_does_not_start_under_test(settings):
    from apps.backups import scheduler

    settings.BACKUP = {**settings.BACKUP, "SCHEDULE_ENABLED": True}
    assert scheduler.start_if_enabled() is False


# ==================================================================
#  Özet
# ==================================================================
@pytest.mark.django_db
def test_storage_summary_reports_counts(backup_dir, owner):
    services.create_backup(user=owner)
    summary = services.storage_summary()

    assert summary["adet"] == 1
    assert summary["toplam_mb"] >= 0
    assert summary["son_yedek"] is not None


@pytest.mark.django_db
def test_hours_since_last_backup_none_when_empty(backup_dir):
    assert services.hours_since_last_backup() is None


@pytest.mark.django_db
def test_management_command_creates_backup(backup_dir):
    from django.core.management import call_command

    call_command("backup_now", "--no-media", verbosity=0)
    assert BackupRecord.objects.filter(status=BackupRecord.Status.SUCCESS).count() == 1


@pytest.mark.django_db
def test_backup_record_helpers(backup_dir, owner):
    record = services.create_backup(user=owner).record

    assert record.exists is True
    assert record.size_mb == pytest.approx(record.size_bytes / 1024 / 1024, abs=Decimal("0.01"))
    assert record.duration_seconds is not None
