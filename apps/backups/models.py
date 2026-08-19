"""Yedekleme kayıtları.

Yedek dosyasının kendisi diskte (``BACKUP_DIR``) tutulur; burada yalnızca
üstveri saklanır. Böylece kayıt listesi hızlı kalır ve dosya elle silinse
bile ne zaman ne yedeklendiği izlenebilir.
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class BackupRecord(TimeStampedModel):
    """Alınmış bir yedeğin üstverisi."""

    class Kind(models.TextChoices):
        MANUAL = "manual", _("Elle")
        SCHEDULED = "scheduled", _("Otomatik")
        PRE_RESTORE = "pre_restore", _("Geri yükleme öncesi güvenlik")

    class Status(models.TextChoices):
        RUNNING = "running", _("Sürüyor")
        SUCCESS = "success", _("Başarılı")
        FAILED = "failed", _("Başarısız")

    filename = models.CharField(_("dosya adı"), max_length=200, unique=True)
    kind = models.CharField(
        _("tür"), max_length=16, choices=Kind.choices, default=Kind.MANUAL, db_index=True
    )
    status = models.CharField(
        _("durum"), max_length=10, choices=Status.choices, default=Status.RUNNING, db_index=True
    )
    size_bytes = models.BigIntegerField(_("boyut (bayt)"), default=0)
    checksum = models.CharField(
        _("SHA-256"),
        max_length=64,
        blank=True,
        help_text=_("Dosyanın bozulmadığını doğrulamak için."),
    )
    started_at = models.DateTimeField(_("başlangıç"), default=timezone.now)
    finished_at = models.DateTimeField(_("bitiş"), null=True, blank=True)

    #: Yedeğin neleri içerdiği: {"veritabani": true, "medya": 12, ...}
    contents = models.JSONField(_("içerik"), default=dict, blank=True)
    includes_secrets = models.BooleanField(
        _("gizli ayarlar dahil"),
        default=False,
        help_text=_(".env dosyası (API anahtarları) yedeğe eklendiyse işaretlidir."),
    )
    note = models.CharField(_("not"), max_length=300, blank=True)
    error_message = models.TextField(_("hata"), blank=True)

    class Meta:
        verbose_name = _("Yedek")
        verbose_name_plural = _("Yedekler")
        ordering = ["-started_at"]
        indexes = [models.Index(fields=["-started_at", "status"])]

    def __str__(self) -> str:
        return f"{self.filename} ({self.get_status_display()})"

    # ------------------------------------------------------------------
    @property
    def path(self) -> Path:
        return Path(settings.BACKUP_DIR) / self.filename

    @property
    def exists(self) -> bool:
        """Dosya hâlâ diskte mi?

        Kullanıcı yedek klasörünü elle temizlemiş olabilir; arayüz indirme
        bağlantısını buna göre gizler.
        """
        try:
            return self.path.is_file()
        except OSError:  # pragma: no cover - erişilemeyen sürücü
            return False

    @property
    def size_mb(self) -> float:
        return round(self.size_bytes / (1024 * 1024), 2)

    @property
    def duration_seconds(self) -> float | None:
        if not self.finished_at:
            return None
        return round((self.finished_at - self.started_at).total_seconds(), 1)


class RestoreRecord(TimeStampedModel):
    """Geri yükleme girişimi.

    Geri yükleme yıkıcı bir işlemdir; kim ne zaman hangi yedeği geri
    yükledi sorusunun yanıtı denetim kaydından bağımsız olarak da
    saklanır.
    """

    class Status(models.TextChoices):
        SUCCESS = "success", _("Başarılı")
        FAILED = "failed", _("Başarısız")

    source_filename = models.CharField(_("kaynak yedek"), max_length=200)
    performed_by_username = models.CharField(
        _("işlemi yapan"),
        max_length=150,
        blank=True,
        help_text=_(
            "Geri yükleme sonrası kullanıcı kaydı yedekteki hâline döner; "
            "işlemi kimin yaptığı burada metin olarak korunur."
        ),
    )
    safety_backup = models.ForeignKey(
        BackupRecord,
        verbose_name=_("güvenlik yedeği"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="restores_protected",
        help_text=_("Geri yüklemeden hemen önce alınan yedek."),
    )
    status = models.CharField(_("durum"), max_length=10, choices=Status.choices)
    error_message = models.TextField(_("hata"), blank=True)

    class Meta:
        verbose_name = _("Geri yükleme")
        verbose_name_plural = _("Geri yüklemeler")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.source_filename} -> {self.get_status_display()}"
