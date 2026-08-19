"""Geliştirme Merkezi kayıtları: komut geçmişi, kod önerileri, geri alma noktaları."""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class CommandRun(TimeStampedModel):
    """Güvenli terminalde çalıştırılan komutun kaydı.

    Hiçbir komut kayıt bırakmadan çalışmaz. Çıktıdaki gizli değerler
    maskelenerek saklanır.
    """

    class Status(models.TextChoices):
        PENDING = "pending", _("Onay bekliyor")
        RUNNING = "running", _("Çalışıyor")
        SUCCESS = "success", _("Başarılı")
        FAILED = "failed", _("Başarısız")
        TIMEOUT = "timeout", _("Zaman aşımı")
        BLOCKED = "blocked", _("Engellendi")
        REJECTED = "rejected", _("Kullanıcı reddetti")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("kullanıcı"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="command_runs",
    )
    command = models.CharField(_("komut"), max_length=1000)
    working_directory = models.CharField(_("çalışma dizini"), max_length=500)
    status = models.CharField(
        _("durum"), max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    exit_code = models.IntegerField(_("çıkış kodu"), null=True, blank=True)
    stdout = models.TextField(_("standart çıktı"), blank=True)
    stderr = models.TextField(_("hata çıktısı"), blank=True)
    duration_ms = models.PositiveIntegerField(_("süre (ms)"), default=0)
    block_reason = models.CharField(_("engelleme nedeni"), max_length=300, blank=True)
    required_confirmation = models.BooleanField(_("onay gerektirdi"), default=False)
    confirmed_at = models.DateTimeField(_("onay zamanı"), null=True, blank=True)

    class Meta:
        verbose_name = _("Terminal komutu")
        verbose_name_plural = _("Terminal komutları")
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["-created_at", "status"])]

    def __str__(self) -> str:
        return f"{self.command[:60]} [{self.get_status_display()}]"

    @property
    def succeeded(self) -> bool:
        return self.status == self.Status.SUCCESS


class CodeProposal(TimeStampedModel):
    """Yapay zekânın önerdiği kod değişikliği.

    Öneri **asla** otomatik uygulanmaz. Kullanıcı diff'i görür, onaylar,
    ancak ondan sonra ve geri alma noktası oluşturularak uygulanır.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", _("Öneri hazırlandı")
        REVIEWING = "reviewing", _("İnceleniyor")
        APPROVED = "approved", _("Onaylandı")
        APPLIED = "applied", _("Uygulandı")
        REJECTED = "rejected", _("Reddedildi")
        REVERTED = "reverted", _("Geri alındı")
        FAILED = "failed", _("Uygulama başarısız")

    title = models.CharField(_("başlık"), max_length=200)
    instruction = models.TextField(_("kullanıcı talimatı"))
    status = models.CharField(
        _("durum"), max_length=10, choices=Status.choices, default=Status.DRAFT, db_index=True
    )

    provider = models.CharField(_("AI sağlayıcı"), max_length=32, blank=True)
    model = models.CharField(_("AI model"), max_length=120, blank=True)
    explanation = models.TextField(_("AI açıklaması"), blank=True)

    target_files = models.JSONField(_("hedef dosyalar"), default=list, blank=True)
    diff = models.TextField(_("birleşik diff"), blank=True)

    branch_name = models.CharField(
        _("çalışma dalı"),
        max_length=120,
        blank=True,
        help_text=_("Değişiklik doğrudan ana dala uygulanmaz."),
    )
    snapshot = models.ForeignKey(
        "devcenter.Snapshot",
        verbose_name=_("geri alma noktası"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="proposals",
    )

    created_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("talep eden"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="code_proposals",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("onaylayan"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_proposals",
    )
    approved_at = models.DateTimeField(_("onay zamanı"), null=True, blank=True)
    applied_at = models.DateTimeField(_("uygulama zamanı"), null=True, blank=True)

    tests_run = models.BooleanField(_("test çalıştırıldı"), default=False)
    tests_passed = models.BooleanField(_("testler geçti"), default=False)
    test_output = models.TextField(_("test çıktısı"), blank=True)
    rejection_reason = models.CharField(_("ret gerekçesi"), max_length=300, blank=True)

    class Meta:
        verbose_name = _("Kod önerisi")
        verbose_name_plural = _("Kod önerileri")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.title} [{self.get_status_display()}]"

    @property
    def can_apply(self) -> bool:
        """Uygulamaya hazır mı? Testler başarısızsa uygulanamaz."""
        if self.status not in {self.Status.DRAFT, self.Status.REVIEWING, self.Status.APPROVED}:
            return False
        if self.tests_run and not self.tests_passed:
            return False
        return bool(self.diff)

    @property
    def file_count(self) -> int:
        return len(self.target_files or [])


class Snapshot(TimeStampedModel):
    """Değişiklik öncesi dosya yedeği (geri alma noktası)."""

    label = models.CharField(_("etiket"), max_length=200)
    directory = models.CharField(_("yedek dizini"), max_length=500)
    files = models.JSONField(_("yedeklenen dosyalar"), default=list, blank=True)
    git_commit = models.CharField(_("git commit"), max_length=64, blank=True)
    git_branch = models.CharField(_("git dalı"), max_length=120, blank=True)
    created_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("oluşturan"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="snapshots",
    )
    is_restored = models.BooleanField(_("geri yüklendi"), default=False)
    restored_at = models.DateTimeField(_("geri yükleme zamanı"), null=True, blank=True)

    class Meta:
        verbose_name = _("Geri alma noktası")
        verbose_name_plural = _("Geri alma noktaları")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.label} ({timezone.localtime(self.created_at):%d.%m.%Y %H:%M})"

    @property
    def file_count(self) -> int:
        return len(self.files or [])
