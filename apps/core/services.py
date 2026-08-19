"""Çekirdek servisler: denetim kaydı ve bildirim üretimi."""

from __future__ import annotations

import logging
from typing import Any

from django.db import transaction

from apps.core.logging_filters import mask_secrets
from apps.core.models import AuditLog, Notification

security_logger = logging.getLogger("apps.security")

# İstek bağlamı (middleware tarafından doldurulur)
from apps.core.middleware import get_current_request  # noqa: E402


def record_audit(
    action: str,
    *,
    user=None,
    obj: Any = None,
    description: str = "",
    changes: dict | None = None,
    severity: str = AuditLog.Severity.INFO,
    request=None,
) -> AuditLog:
    """Denetim kaydı oluşturur.

    Hassas veriler açıklama ve değişiklik alanlarında maskelenir.
    """
    request = request or get_current_request()
    if user is None and request is not None:
        candidate = getattr(request, "user", None)
        if candidate is not None and getattr(candidate, "is_authenticated", False):
            user = candidate

    ip = None
    agent = ""
    if request is not None:
        ip = _client_ip(request)
        agent = (request.META.get("HTTP_USER_AGENT") or "")[:300]

    entry = AuditLog(
        user=user,
        username_snapshot=(user.get_username() if user else "anonim"),
        action=action,
        severity=severity,
        object_type=obj.__class__.__name__ if obj is not None else "",
        object_id=str(getattr(obj, "pk", "") or ""),
        description=mask_secrets(description or "")[:4000],
        changes=_sanitize_changes(changes or {}),
        ip_address=ip,
        user_agent=agent,
    )
    entry.save()

    if severity in {AuditLog.Severity.WARNING, AuditLog.Severity.CRITICAL}:
        security_logger.warning(
            "Denetim [%s/%s] %s -> %s", action, severity, entry.username_snapshot, entry.description
        )
    return entry


def _sanitize_changes(changes: dict) -> dict:
    clean: dict[str, Any] = {}
    for key, value in changes.items():
        if isinstance(value, str):
            clean[key] = mask_secrets(value)[:1000]
        elif isinstance(value, (int, float, bool)) or value is None:
            clean[key] = value
        elif isinstance(value, dict):
            clean[key] = _sanitize_changes(value)
        else:
            clean[key] = mask_secrets(str(value))[:1000]
    return clean


def _client_ip(request) -> str | None:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def safe_internal_url(url: str) -> str:
    """Yalnızca uygulama içi göreli bir yol döndürür; değilse boş dize.

    ``javascript:``, ``data:``, ``vbscript:`` gibi şemalar ve şema-göreli
    (``//baska-site``) adresler reddedilir. Bildirim bağlantısı şablonda
    ``href`` içine basıldığı için bu, kalıcı XSS ve açık yönlendirmeye
    karşı son savunmadır.
    """
    candidate = (url or "").strip()
    if not candidate:
        return ""
    if candidate.startswith("//") or candidate.startswith("\\\\"):
        return ""
    if not candidate.startswith("/"):
        return ""
    # Denetim kaçırılmasın diye kontrol karakterleri temizlenir
    # ("java\tscript:" gibi hileler tarayıcıda hâlâ çalışabilir).
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in candidate):
        return ""
    return candidate


def notify(
    title: str,
    *,
    body: str = "",
    level: str = Notification.Level.INFO,
    category: str = Notification.Category.SYSTEM,
    recipient=None,
    roles: list[str] | None = None,
    url: str = "",
    dedupe_key: str | None = None,
) -> Notification | None:
    """Bildirim oluşturur.

    `dedupe_key` verilirse aynı okunmamış bildirim tekrar üretilmez
    (ör. aynı malzeme için düşük stok uyarısının her istekte tekrarlanmaması).
    """
    # Bildirim hedefi şablonda `<a href="...">` olarak basılır. Bugün her
    # çağıran `reverse()` sonucu veriyor; ancak tek bir gelecekteki çağıran
    # kullanıcı girdisini buraya geçirirse `javascript:` şemasıyla kalıcı
    # XSS doğar. Denetimi tek boğazda yapmak her çağıranı tek tek
    # incelemekten güvenilirdir: yalnızca uygulama içi göreli yol kabul edilir.
    url = safe_internal_url(url)

    if dedupe_key:
        exists = Notification.objects.filter(
            title=title, category=category, is_read=False, url=url
        ).exists()
        if exists:
            return None

    with transaction.atomic():
        return Notification.objects.create(
            recipient=recipient,
            target_roles=roles or [],
            level=level,
            category=category,
            title=title[:200],
            body=mask_secrets(body),
            url=url[:300],
        )
