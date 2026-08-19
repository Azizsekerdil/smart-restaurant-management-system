"""Yetki kontrolü için dekoratörler, mixin'ler ve DRF izin sınıfları."""

from __future__ import annotations

from functools import wraps

from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import render
from rest_framework.permissions import BasePermission


def _is_api(request) -> bool:
    return request.path.startswith("/api/") or request.headers.get("Accept", "").startswith(
        "application/json"
    )


def _deny(request, codes: tuple[str, ...]):
    labels = ", ".join(codes)
    if _is_api(request):
        return JsonResponse(
            {
                "detail": "Bu işlem için yetkiniz bulunmuyor.",
                "required_permissions": list(codes),
                "code": "permission_denied",
            },
            status=403,
        )
    return render(
        request,
        "core/403.html",
        {
            "required": labels,
            "message": (
                "Bu ekrana erişim yetkiniz bulunmuyor. "
                "Gerekiyorsa yöneticinizden yetki talep edin."
            ),
        },
        status=403,
    )


def require_permission(*codes: str, require_all: bool = False):
    """Görünüm (view) fonksiyonu için izin kontrolü.

    @require_permission("pos.use")
    def pos_screen(request): ...
    """

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            user = getattr(request, "user", None)
            if user is None or not user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            check = user.has_all_perms if require_all else user.has_any_perm
            if not check(*codes):
                return _deny(request, codes)
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


class PermissionRequiredMixin:
    """Sınıf tabanlı görünümler için izin kontrolü.

    `permission_codes` ve `require_all_permissions` sınıf niteliklerini
    kullanır.
    """

    permission_codes: tuple[str, ...] = ()
    require_all_permissions: bool = False

    def dispatch(self, request, *args, **kwargs):
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if self.permission_codes:
            check = user.has_all_perms if self.require_all_permissions else user.has_any_perm
            if not check(*self.permission_codes):
                return _deny(request, self.permission_codes)
        return super().dispatch(request, *args, **kwargs)  # type: ignore[misc]


class HasPermissionCode(BasePermission):
    """DRF izin sınıfı.

    Görünümde `required_permissions = ("order.view",)` tanımlayın.
    """

    message = "Bu işlem için yetkiniz bulunmuyor."

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not (user and user.is_authenticated):
            return False
        codes = getattr(view, "required_permissions", ())
        if not codes:
            return True
        if request.method in ("GET", "HEAD", "OPTIONS"):
            read_codes = getattr(view, "required_read_permissions", codes)
            return user.has_any_perm(*read_codes)
        return user.has_any_perm(*codes)


def manager_approval_required(permission_code: str):
    """Hassas işlemlerde yetkili onayı zorunlu kılar.

    Kullanıcının kendi yetkisi varsa doğrudan geçer. Yoksa istek gövdesinde
    `approver_username` + `approver_pin` beklenir; doğrulanırsa işlem
    `request.manager_approval` ile birlikte devam eder.
    """

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            from apps.accounts.models import ManagerApproval, User
            from apps.core.models import AuditLog
            from apps.core.services import record_audit

            user = request.user
            if not user.is_authenticated:
                return redirect_to_login(request.get_full_path())

            if user.has_perm_code(permission_code):
                request.manager_approval = None
                return view_func(request, *args, **kwargs)

            username = (request.POST.get("approver_username") or "").strip()
            pin = (request.POST.get("approver_pin") or "").strip()
            if not username or not pin:
                if _is_api(request):
                    return JsonResponse(
                        {
                            "detail": "Bu işlem yetkili onayı gerektiriyor.",
                            "code": "approval_required",
                            "permission": permission_code,
                        },
                        status=403,
                    )
                messages.warning(request, "Bu işlem yetkili onayı gerektiriyor.")
                return _deny(request, (permission_code,))

            from apps.accounts import pin_security

            # Yetkili PIN'i de kısa bir sırdır. Deneme sayısı sınırlanmazsa
            # düşük yetkili bir kullanıcı müdür PIN'ini kaba kuvvetle bulup
            # iptal/iade/indirim yetkisi elde edebilir.
            lock = pin_security.state(request, username)
            if lock.locked:
                record_audit(
                    AuditLog.Action.PERMISSION,
                    user=user,
                    description=(
                        f"Yetkili onayı kilitli hesap için denendi: {permission_code} "
                        f"(onaylayan olarak '{username}' denendi)"
                    ),
                    severity=AuditLog.Severity.WARNING,
                    request=request,
                )
                message = "Çok fazla hatalı PIN denemesi. Lütfen daha sonra tekrar deneyin."
                if _is_api(request):
                    return JsonResponse(
                        {
                            "detail": message,
                            "code": "approval_locked",
                            "retry_after": lock.retry_after,
                        },
                        status=429,
                    )
                messages.error(request, message)
                return _deny(request, (permission_code,))

            approver = User.objects.filter(username=username, is_active=True).first()
            if (
                approver is None
                or not approver.check_pin(pin)
                or not approver.can_approve(permission_code)
            ):
                state = pin_security.record_failure(request, username)
                pin_security.apply_backoff(state.failures)
                record_audit(
                    AuditLog.Action.PERMISSION,
                    user=user,
                    description=(
                        f"Başarısız yetkili onayı denemesi: {permission_code} "
                        f"(onaylayan olarak '{username}' denendi)"
                    ),
                    severity=AuditLog.Severity.WARNING,
                    request=request,
                )
                if _is_api(request):
                    return JsonResponse(
                        {"detail": "Onay bilgileri geçersiz.", "code": "approval_invalid"},
                        status=403,
                    )
                return _deny(request, (permission_code,))

            pin_security.reset(request, username)
            approval = ManagerApproval.objects.create(
                approver=approver,
                requested_by=user,
                permission_code=permission_code,
                reason=(request.POST.get("reason") or "")[:300],
            )
            request.manager_approval = approval
            record_audit(
                AuditLog.Action.PERMISSION,
                user=user,
                obj=approval,
                description=f"{approver.display_name} onayıyla '{permission_code}' işlemi yapıldı.",
                severity=AuditLog.Severity.NOTICE,
                request=request,
            )
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


def devcenter_enabled_required(view_func):
    """Geliştirme Merkezi kapalıysa erişimi engeller."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        from django.conf import settings

        if not settings.DEVCENTER["ENABLED"]:
            raise PermissionDenied(
                "AI Geliştirme Merkezi bu ortamda kapalıdır "
                "(.env içinde DEVCENTER_ENABLED=True yapın)."
            )
        return view_func(request, *args, **kwargs)

    return wrapper
