"""Kullanıcı modeli ve yetki mantığı."""

from __future__ import annotations

from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.models import UserManager as DjangoUserManager
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.accounts.permissions import (
    ALL_PERMISSIONS,
    MANAGER_APPROVAL_PERMISSIONS,
    Role,
    permissions_for_role,
)


class UserManager(DjangoUserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault("role", Role.OWNER)
        return super().create_superuser(username, email, password, **extra_fields)

    def active_staff(self):
        return self.filter(is_active=True).exclude(role=Role.COURIER)


phone_validator = RegexValidator(
    regex=r"^[0-9+()\s\-]{7,20}$",
    message=_("Geçerli bir telefon numarası girin."),
)


class User(AbstractUser):
    """Restoran personeli / yönetici kullanıcı hesabı.

    POS terminalinde hızlı kullanıcı değişimi için parolaya ek olarak
    4-8 haneli bir PIN tanımlanabilir. PIN de hash'lenerek saklanır.
    """

    role = models.CharField(
        _("rol"), max_length=32, choices=Role.choices, default=Role.WAITER, db_index=True
    )
    phone = models.CharField(_("telefon"), max_length=20, blank=True, validators=[phone_validator])
    employee_code = models.CharField(
        _("personel kodu"), max_length=20, blank=True, unique=True, null=True
    )
    pin_hash = models.CharField(_("PIN (hash)"), max_length=128, blank=True, editable=False)

    extra_permissions = models.JSONField(
        _("ek izinler"),
        default=list,
        blank=True,
        help_text=_("Rolün ötesinde verilen izin kodları."),
    )
    denied_permissions = models.JSONField(
        _("reddedilen izinler"),
        default=list,
        blank=True,
        help_text=_("Rolde bulunsa bile bu kullanıcıya kapatılan izin kodları."),
    )

    avatar = models.ImageField(_("profil görseli"), upload_to="avatars/", blank=True, null=True)
    theme_preference = models.CharField(
        _("tema"),
        max_length=10,
        choices=[("auto", _("Sistem")), ("light", _("Açık")), ("dark", _("Koyu"))],
        default="auto",
    )
    language_preference = models.CharField(
        _("dil"), max_length=5, choices=[("tr", "Türkçe"), ("en", "English")], default="tr"
    )

    must_change_password = models.BooleanField(
        _("parola değiştirmeli"),
        default=False,
        help_text=_("İlk girişte parola değiştirmeye zorlar."),
    )
    password_changed_at = models.DateTimeField(_("parola değişim zamanı"), null=True, blank=True)
    last_activity = models.DateTimeField(_("son etkinlik"), null=True, blank=True)

    objects = UserManager()

    class Meta:
        verbose_name = _("Kullanıcı")
        verbose_name_plural = _("Kullanıcılar")
        ordering = ["first_name", "last_name", "username"]
        indexes = [models.Index(fields=["role", "is_active"])]

    def __str__(self) -> str:
        return f"{self.display_name} ({self.get_role_display()})"

    # -------------------------------------------------- görüntüleme
    @property
    def display_name(self) -> str:
        full = f"{self.first_name} {self.last_name}".strip()
        return full or self.username

    @property
    def initials(self) -> str:
        parts = [p for p in (self.first_name, self.last_name) if p]
        if parts:
            return "".join(p[0].upper() for p in parts[:2])
        return self.username[:2].upper()

    # -------------------------------------------------- PIN
    def set_pin(self, raw_pin: str | None) -> None:
        """PIN'i politikadan geçirip hash'leyerek saklar.

        Boş değer PIN'i kaldırır. Ham PIN hiçbir yerde saklanmaz ve
        günlüğe yazılmaz. Politika için bkz. ``pin_security.validate_pin``:
        PIN kısa bir sırdır; tekrar (1111), ardışık (1234) ve yaygın
        PIN'ler reddedilir, doğrulama tarafında da deneme sayısı sınırlanır.
        """
        from apps.accounts.pin_security import validate_pin

        if not raw_pin:
            self.pin_hash = ""
            return
        validate_pin(raw_pin)  # WeakPinError, ValueError alt sınıfıdır
        self.pin_hash = make_password(raw_pin)

    def check_pin(self, raw_pin: str) -> bool:
        """PIN doğrular.

        DİKKAT: Bu metot deneme sayısını SINIRLAMAZ. Ağ üzerinden gelen
        her çağrı ``apps.accounts.pin_security`` kısıtlayıcısıyla
        sarmalanmalıdır (bkz. ``views.pin_switch``,
        ``decorators.manager_approval_required``).
        """
        if not self.pin_hash or not raw_pin:
            return False
        return check_password(raw_pin, self.pin_hash)

    @property
    def has_pin(self) -> bool:
        return bool(self.pin_hash)

    # -------------------------------------------------- yetki
    @property
    def effective_permissions(self) -> frozenset[str]:
        """Rol + kullanıcıya özel eklemeler - reddedilenler."""
        if self.is_superuser:
            return ALL_PERMISSIONS
        base = set(permissions_for_role(self.role))
        base |= {p for p in (self.extra_permissions or []) if p in ALL_PERMISSIONS}
        base -= set(self.denied_permissions or [])
        return frozenset(base)

    def has_perm_code(self, code: str) -> bool:
        """İşlev bazlı izin kontrolü.

        Django'nun `has_perm` metoduyla karıştırılmaması için ayrı isim
        kullanılır; `has_perm` model/CRUD izinleri içindir.
        """
        if not self.is_active:
            return False
        if self.is_superuser:
            return True
        if code in (self.denied_permissions or []):
            return False
        return code in self.effective_permissions

    def has_any_perm(self, *codes: str) -> bool:
        return any(self.has_perm_code(c) for c in codes)

    def has_all_perms(self, *codes: str) -> bool:
        return all(self.has_perm_code(c) for c in codes)

    def can_approve(self, code: str) -> bool:
        """Bu kullanıcı, yetkili onayı gereken bir işlemi onaylayabilir mi?"""
        return code in MANAGER_APPROVAL_PERMISSIONS and self.has_perm_code(code)

    @property
    def is_manager(self) -> bool:
        return self.role in {
            Role.OWNER,
            Role.GENERAL_MANAGER,
            Role.RESTAURANT_MANAGER,
        }

    def touch_activity(self) -> None:
        self.last_activity = timezone.now()
        self.save(update_fields=["last_activity"])

    def save(self, *args, **kwargs):
        if self.employee_code == "":
            self.employee_code = None
        super().save(*args, **kwargs)


class ManagerApproval(models.Model):
    """Yetkili onayı kaydı (iptal/iade/indirim gibi hassas işlemler için)."""

    approver = models.ForeignKey(
        User, verbose_name=_("onaylayan"), on_delete=models.PROTECT, related_name="approvals_given"
    )
    requested_by = models.ForeignKey(
        User,
        verbose_name=_("talep eden"),
        on_delete=models.PROTECT,
        related_name="approvals_requested",
    )
    permission_code = models.CharField(_("izin kodu"), max_length=64)
    reason = models.CharField(_("gerekçe"), max_length=300, blank=True)
    object_type = models.CharField(_("nesne türü"), max_length=100, blank=True)
    object_id = models.CharField(_("nesne kimliği"), max_length=64, blank=True)
    created_at = models.DateTimeField(_("zaman"), auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = _("Yetkili onayı")
        verbose_name_plural = _("Yetkili onayları")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.approver} -> {self.permission_code}"
