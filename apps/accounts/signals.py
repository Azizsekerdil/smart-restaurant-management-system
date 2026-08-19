"""Kimlik doğrulama olaylarının denetim kaydına yazılması."""

from __future__ import annotations

from django.contrib.auth.signals import (
    user_logged_in,
    user_logged_out,
    user_login_failed,
)
from django.dispatch import receiver

from apps.core.models import AuditLog
from apps.core.services import record_audit


@receiver(user_logged_in)
def on_login(sender, request, user, **kwargs):
    record_audit(
        AuditLog.Action.LOGIN,
        user=user,
        description=f"{user.display_name} sisteme giriş yaptı ({user.get_role_display()}).",
        request=request,
    )


@receiver(user_logged_out)
def on_logout(sender, request, user, **kwargs):
    if user is not None:
        record_audit(
            AuditLog.Action.LOGOUT,
            user=user,
            description=f"{user.display_name} çıkış yaptı.",
            request=request,
        )


@receiver(user_login_failed)
def on_login_failed(sender, credentials, request=None, **kwargs):
    # Parola asla kaydedilmez; yalnızca denenen kullanıcı adı tutulur.
    attempted = credentials.get("username", "?")
    record_audit(
        AuditLog.Action.LOGIN_FAILED,
        description=f"Başarısız giriş denemesi: '{attempted}'",
        severity=AuditLog.Severity.WARNING,
        request=request,
    )
