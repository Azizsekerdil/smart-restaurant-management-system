"""Çekirdek modeller: ortak taban sınıflar, denetim kaydı, sistem ayarları."""

from __future__ import annotations

import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class TimeStampedModel(models.Model):
    """Oluşturma/güncelleme zamanı ve kullanıcı izini tutan taban sınıf."""

    created_at = models.DateTimeField(_("oluşturulma"), auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(_("güncellenme"), auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("oluşturan"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="%(app_label)s_%(class)s_created",
    )

    class Meta:
        abstract = True


class SoftDeleteQuerySet(models.QuerySet):
    def alive(self) -> SoftDeleteQuerySet:
        return self.filter(deleted_at__isnull=True)

    def dead(self) -> SoftDeleteQuerySet:
        return self.filter(deleted_at__isnull=False)

    def delete(self):  # type: ignore[override]
        return self.update(deleted_at=timezone.now())

    def hard_delete(self):
        return super().delete()


class SoftDeleteManager(models.Manager.from_queryset(SoftDeleteQuerySet)):  # type: ignore[misc]
    """Varsayılan olarak silinmiş kayıtları gizler."""

    def get_queryset(self) -> SoftDeleteQuerySet:
        return super().get_queryset().filter(deleted_at__isnull=True)


class SoftDeleteModel(TimeStampedModel):
    """Kalıcı silme yerine işaretleyerek silme.

    Mali kayıtların (sipariş, ödeme) izlenebilirliği için gereklidir.
    """

    deleted_at = models.DateTimeField(_("silinme"), null=True, blank=True, db_index=True)

    objects = SoftDeleteManager()
    all_objects = models.Manager.from_queryset(SoftDeleteQuerySet)()

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False):  # type: ignore[override]
        self.deleted_at = timezone.now()
        self.save(update_fields=["deleted_at", "updated_at"])

    def hard_delete(self, using=None, keep_parents=False):
        super().delete(using=using, keep_parents=keep_parents)

    def restore(self) -> None:
        self.deleted_at = None
        self.save(update_fields=["deleted_at", "updated_at"])


class AuditLog(models.Model):
    """Denetim kaydı - kim, ne zaman, neyi değiştirdi.

    Kritik işlemler (iptal, iade, indirim, yetki değişikliği, AI kullanımı,
    terminal komutu) burada saklanır. Kayıtlar değiştirilemez kabul edilir.
    """

    class Action(models.TextChoices):
        CREATE = "create", _("Oluşturma")
        UPDATE = "update", _("Güncelleme")
        DELETE = "delete", _("Silme")
        LOGIN = "login", _("Giriş")
        LOGIN_FAILED = "login_failed", _("Başarısız giriş")
        LOGOUT = "logout", _("Çıkış")
        VOID = "void", _("İptal")
        REFUND = "refund", _("İade")
        DISCOUNT = "discount", _("İndirim")
        PERMISSION = "permission", _("Yetki değişikliği")
        EXPORT = "export", _("Dışa aktarma")
        AI_CALL = "ai_call", _("AI çağrısı")
        TERMINAL = "terminal", _("Terminal komutu")
        CODE_APPLY = "code_apply", _("Kod değişikliği uygulama")
        CASH = "cash", _("Kasa işlemi")
        DATA_ERASURE = "data_erasure", _("Veri silme talebi (KVKK)")

    class Severity(models.TextChoices):
        INFO = "info", _("Bilgi")
        NOTICE = "notice", _("Dikkat")
        WARNING = "warning", _("Uyarı")
        CRITICAL = "critical", _("Kritik")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    timestamp = models.DateTimeField(_("zaman"), default=timezone.now, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("kullanıcı"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
    )
    username_snapshot = models.CharField(
        _("kullanıcı adı (anlık)"),
        max_length=150,
        blank=True,
        help_text=_("Kullanıcı silinse bile iz kaybolmaz."),
    )
    action = models.CharField(_("işlem"), max_length=24, choices=Action.choices, db_index=True)
    severity = models.CharField(
        _("önem"), max_length=10, choices=Severity.choices, default=Severity.INFO, db_index=True
    )
    object_type = models.CharField(_("nesne türü"), max_length=100, blank=True, db_index=True)
    object_id = models.CharField(_("nesne kimliği"), max_length=64, blank=True, db_index=True)
    description = models.TextField(_("açıklama"), blank=True)
    changes = models.JSONField(_("değişiklikler"), default=dict, blank=True)
    ip_address = models.GenericIPAddressField(_("IP adresi"), null=True, blank=True)
    user_agent = models.CharField(_("tarayıcı"), max_length=300, blank=True)

    class Meta:
        verbose_name = _("Denetim kaydı")
        verbose_name_plural = _("Denetim kayıtları")
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["-timestamp", "action"]),
            models.Index(fields=["object_type", "object_id"]),
        ]

    def __str__(self) -> str:
        return f"[{self.timestamp:%Y-%m-%d %H:%M}] {self.username_snapshot} · {self.get_action_display()}"

    def save(self, *args, **kwargs):
        # Kayıtlar değiştirilemez: yalnızca ilk kayıt yazılır.
        if self.pk and AuditLog.objects.filter(pk=self.pk).exists():
            raise ValueError("Denetim kayıtları değiştirilemez.")
        if self.user and not self.username_snapshot:
            self.username_snapshot = self.user.get_username()
        super().save(*args, **kwargs)


class SystemSetting(TimeStampedModel):
    """Çalışma zamanında değiştirilebilen ayarlar (arayüzden yönetilir).

    Gizli değerler burada tutulmaz; API anahtarları `.env` içindedir.
    """

    class ValueType(models.TextChoices):
        STRING = "string", _("Metin")
        INTEGER = "integer", _("Tam sayı")
        DECIMAL = "decimal", _("Ondalık")
        BOOLEAN = "boolean", _("Evet/Hayır")
        JSON = "json", _("JSON")

    key = models.SlugField(_("anahtar"), max_length=100, unique=True)
    label = models.CharField(_("etiket"), max_length=200)
    value = models.TextField(_("değer"), blank=True)
    value_type = models.CharField(
        _("tür"), max_length=10, choices=ValueType.choices, default=ValueType.STRING
    )
    group = models.CharField(_("grup"), max_length=50, default="genel", db_index=True)
    description = models.TextField(_("açıklama"), blank=True)
    is_editable = models.BooleanField(_("düzenlenebilir"), default=True)

    class Meta:
        verbose_name = _("Sistem ayarı")
        verbose_name_plural = _("Sistem ayarları")
        ordering = ["group", "key"]

    def __str__(self) -> str:
        return f"{self.label} ({self.key})"

    @property
    def typed_value(self):
        raw = (self.value or "").strip()
        if self.value_type == self.ValueType.BOOLEAN:
            return raw.lower() in {"1", "true", "yes", "evet", "on"}
        if self.value_type == self.ValueType.INTEGER:
            try:
                return int(raw)
            except ValueError:
                return 0
        if self.value_type == self.ValueType.DECIMAL:
            try:
                return Decimal(raw or "0")
            except Exception:
                return Decimal("0")
        if self.value_type == self.ValueType.JSON:
            import json

            try:
                return json.loads(raw or "{}")
            except ValueError:
                return {}
        return raw

    @classmethod
    def get(cls, key: str, default=None):
        obj = cls.objects.filter(key=key).first()
        return obj.typed_value if obj else default


class Notification(TimeStampedModel):
    """Bildirim merkezi kaydı (düşük stok, geciken sipariş, bütçe uyarısı...)."""

    class Level(models.TextChoices):
        INFO = "info", _("Bilgi")
        SUCCESS = "success", _("Başarılı")
        WARNING = "warning", _("Uyarı")
        DANGER = "danger", _("Kritik")

    class Category(models.TextChoices):
        STOCK = "stock", _("Stok")
        ORDER = "order", _("Sipariş")
        KITCHEN = "kitchen", _("Mutfak")
        RESERVATION = "reservation", _("Rezervasyon")
        FINANCE = "finance", _("Finans")
        AI = "ai", _("Yapay zekâ")
        SECURITY = "security", _("Güvenlik")
        SYSTEM = "system", _("Sistem")

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("alıcı"),
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="notifications",
        help_text=_("Boş ise yetkili tüm kullanıcılara gösterilir."),
    )
    target_roles = models.JSONField(
        _("hedef roller"),
        default=list,
        blank=True,
        help_text=_("Belirli rollere yayın yapmak için rol kodları listesi."),
    )
    level = models.CharField(_("düzey"), max_length=10, choices=Level.choices, default=Level.INFO)
    category = models.CharField(
        _("kategori"),
        max_length=20,
        choices=Category.choices,
        default=Category.SYSTEM,
        db_index=True,
    )
    title = models.CharField(_("başlık"), max_length=200)
    body = models.TextField(_("içerik"), blank=True)
    url = models.CharField(_("bağlantı"), max_length=300, blank=True)
    is_read = models.BooleanField(_("okundu"), default=False, db_index=True)
    read_at = models.DateTimeField(_("okunma zamanı"), null=True, blank=True)

    class Meta:
        verbose_name = _("Bildirim")
        verbose_name_plural = _("Bildirimler")
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["recipient", "is_read", "-created_at"])]

    def __str__(self) -> str:
        return self.title

    def mark_read(self) -> None:
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=["is_read", "read_at", "updated_at"])
