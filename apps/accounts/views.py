"""Kimlik doğrulama ve kullanıcı yönetimi görünümleri."""

from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.views import LoginView
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import translation
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.accounts import pin_security
from apps.accounts.decorators import require_permission
from apps.accounts.forms import LoginForm, ProfileForm, UserForm, UserPermissionForm
from apps.accounts.models import User
from apps.accounts.permissions import Role, grouped_permissions
from apps.core.models import AuditLog
from apps.core.services import record_audit


class RestaurantLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        pending_user = form.get_user()
        remote_addr = self.request.META.get("REMOTE_ADDR", "")
        if getattr(pending_user, "must_change_password", False) and remote_addr not in {
            "127.0.0.1",
            "::1",
        }:
            form.add_error(None, "İlk giriş yalnızca bu cihazdan yapılabilir.")
            return self.form_invalid(form)
        response = super().form_valid(form)
        if not form.cleaned_data.get("remember_me"):
            self.request.session.set_expiry(0)  # tarayıcı kapanınca sona ersin
        if self.request.user.must_change_password:
            messages.warning(self.request, "Güvenlik için parolanızı değiştirmelisiniz.")
            return redirect("accounts:password_change")
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from django.conf import settings

        context["restaurant_name"] = settings.RESTAURANT["NAME"]
        context["is_first_run"] = not User.objects.exists()
        return context


@login_required
def logout_view(request):
    logout(request)
    messages.info(request, "Çıkış yaptınız. İyi çalışmalar!")
    return redirect("accounts:login")


@require_POST
def switch_language(request):
    """Üst çubuktaki dil değiştirici.

    Seçim, giriş yapmış kullanıcının **profiline** yazılır: dil tercihinin
    tek bir doğruluk kaynağı olur ve kullanıcı başka bir cihazdan girdiğinde
    de aynı dili görür (bkz. ``UserLanguageMiddleware``).

    Anonim kullanıcı (giriş ekranı) için seçim çerezde tutulur; orada
    henüz yazılacak bir profil yoktur.
    """
    language = (request.POST.get("language") or "").strip()
    if language not in dict(settings.LANGUAGES):
        return redirect(request.META.get("HTTP_REFERER") or "/")

    if request.user.is_authenticated:
        request.user.language_preference = language
        request.user.save(update_fields=["language_preference"])

    translation.activate(language)

    # Açık yönlendirme (open redirect) olmaması için hedef doğrulanır.
    target = request.POST.get("next") or request.META.get("HTTP_REFERER") or "/"
    if not url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        target = "/"

    response = redirect(target)
    response.set_cookie(
        settings.LANGUAGE_COOKIE_NAME,
        language,
        max_age=settings.LANGUAGE_COOKIE_AGE,
        samesite="Lax",
    )
    return response


@login_required
def profile(request):
    if request.method == "POST":
        form = ProfileForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Profiliniz güncellendi.")
            return redirect("accounts:profile")
    else:
        form = ProfileForm(instance=request.user)

    return render(
        request,
        "accounts/profile.html",
        {
            "form": form,
            "page_title": "Profilim",
            "permissions": sorted(request.user.effective_permissions),
        },
    )


@login_required
def password_change(request):
    if request.method == "POST":
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            from django.utils import timezone

            user.must_change_password = False
            user.password_changed_at = timezone.now()
            user.save(update_fields=["must_change_password", "password_changed_at"])
            update_session_auth_hash(request, user)
            record_audit(
                AuditLog.Action.UPDATE,
                user=user,
                obj=user,
                description="Kullanıcı parolasını değiştirdi.",
                severity=AuditLog.Severity.NOTICE,
                request=request,
            )
            messages.success(request, "Parolanız güncellendi.")
            return redirect("core:home")
    else:
        form = PasswordChangeForm(request.user)

    for field in form.fields.values():
        field.widget.attrs.setdefault("class", "form-control")
    return render(
        request, "accounts/password_change.html", {"form": form, "page_title": "Parola Değiştir"}
    )


@login_required
def set_pin(request):
    """Kullanıcının kendi POS PIN'ini belirlemesi."""
    if request.method == "POST":
        pin = (request.POST.get("pin") or "").strip()
        confirm = (request.POST.get("pin_confirm") or "").strip()
        if pin != confirm:
            messages.error(request, "PIN kodları eşleşmiyor.")
        else:
            try:
                request.user.set_pin(pin)
                request.user.save(update_fields=["pin_hash"])
                messages.success(request, "PIN kodunuz güncellendi.")
                return redirect("accounts:profile")
            except ValueError as exc:
                messages.error(request, str(exc))
    return render(request, "accounts/set_pin.html", {"page_title": "PIN Kodu"})


@require_POST
@login_required
def pin_switch(request):
    """POS ekranında hızlı kullanıcı değişimi (PIN ile).

    Güvenlik modeli — bu uç nokta kısa bir sırla (4-8 hane) oturum
    açtırdığı için savunma katmanları zorunludur:

    1. **Kimlik doğrulanmış oturum şart** (``login_required``). PIN,
       parolanın yerine geçen bir *giriş* yöntemi değildir; yalnızca
       zaten açılmış bir POS terminalinde vardiya devri içindir.
    2. **Deneme sınırı**: hedef kullanıcı adı ve istemci IP'si başına
       5 hatalı denemeden sonra 15 dakika kilit + artan gecikme.
    3. **En az yetki**: yalnızca POS kullanabilen (``pos.use``) ve PIN
       tanımlamış aktif hesaplara geçilebilir.
    4. **Parola değiştirme borcu** olan hesaba PIN ile geçilemez; bu
       hesap tam giriş akışından geçmelidir.
    5. Başarılı/başarısız her deneme denetim kaydına yazılır; PIN'in
       kendisi hiçbir kayda girmez.
    """
    username = (request.POST.get("username") or "").strip()
    pin = (request.POST.get("pin") or "").strip()

    lock = pin_security.state(request, username)
    if lock.locked:
        record_audit(
            AuditLog.Action.LOGIN_FAILED,
            user=request.user,
            description=f"PIN geçişi kilitli hesap için denendi: '{username}'",
            severity=AuditLog.Severity.WARNING,
            request=request,
        )
        return JsonResponse(
            {
                "ok": False,
                "code": "pin_locked",
                "detail": "Çok fazla hatalı PIN denemesi. Lütfen daha sonra tekrar deneyin.",
                "retry_after": lock.retry_after,
            },
            status=429,
        )

    user = User.objects.filter(username__iexact=username, is_active=True).first()
    pin_ok = user is not None and user.check_pin(pin)
    eligible = (
        pin_ok
        and user is not None
        and user.has_perm_code("pos.use")
        and not user.must_change_password
    )

    if not eligible:
        if user is None:
            # Kullanıcı adı yoksa da hash maliyeti ödenir: yanıt süresinden
            # hesabın varlığı çıkarılamasın.
            check_password(pin or "x", make_password("0" * 8))
        state = pin_security.record_failure(request, username)
        pin_security.apply_backoff(state.failures)
        record_audit(
            AuditLog.Action.LOGIN_FAILED,
            user=request.user,
            description=f"Başarısız PIN geçişi: '{username}'",
            severity=AuditLog.Severity.WARNING,
            request=request,
        )
        # Ayrıntı sızdırılmaz: hesap yok / PIN yanlış / yetkisiz ayrımı
        # istemciye verilmez.
        return JsonResponse(
            {"ok": False, "code": "pin_invalid", "detail": "Kullanıcı adı veya PIN hatalı."},
            status=403,
        )

    pin_security.reset(request, username)
    previous = request.user.username
    login(request, user, backend="apps.accounts.backends.EmailOrUsernameBackend")
    record_audit(
        AuditLog.Action.LOGIN,
        user=user,
        description=f"POS PIN geçişi: '{previous}' -> '{user.username}'",
        severity=AuditLog.Severity.NOTICE,
        request=request,
    )
    return JsonResponse({"ok": True, "user": user.display_name, "role": user.get_role_display()})


# ------------------------------------------------------------------
#  Kullanıcı yönetimi
# ------------------------------------------------------------------
@require_permission("user.manage")
def user_list(request):
    users = User.objects.all().order_by("role", "first_name")
    role_filter = request.GET.get("role", "")
    search = request.GET.get("q", "").strip()
    if role_filter:
        users = users.filter(role=role_filter)
    if search:
        from django.db.models import Q

        users = users.filter(
            Q(username__icontains=search)
            | Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
            | Q(email__icontains=search)
        )
    return render(
        request,
        "accounts/user_list.html",
        {
            "page_title": "Kullanıcılar ve Yetkiler",
            "users": users,
            "roles": Role.choices,
            "current_role": role_filter,
            "search": search,
        },
    )


@require_permission("user.manage")
def user_create(request):
    if request.method == "POST":
        form = UserForm(request.POST)
        if form.is_valid():
            user = form.save()
            record_audit(
                AuditLog.Action.CREATE,
                obj=user,
                description=f"Kullanıcı oluşturuldu: {user.username} ({user.get_role_display()})",
                severity=AuditLog.Severity.NOTICE,
                request=request,
            )
            messages.success(request, f"{user.display_name} oluşturuldu.")
            return redirect("accounts:user_list")
    else:
        form = UserForm()
    return render(
        request,
        "accounts/user_form.html",
        {"form": form, "page_title": "Yeni Kullanıcı", "is_create": True},
    )


@require_permission("user.manage")
def user_edit(request, pk: int):
    user_obj = get_object_or_404(User, pk=pk)
    if request.method == "POST":
        form = UserForm(request.POST, instance=user_obj)
        if form.is_valid():
            old_role = User.objects.get(pk=pk).role
            saved = form.save()
            if old_role != saved.role:
                record_audit(
                    AuditLog.Action.PERMISSION,
                    obj=saved,
                    description=f"{saved.username} rolü değişti: {old_role} -> {saved.role}",
                    severity=AuditLog.Severity.WARNING,
                    request=request,
                )
            messages.success(request, f"{saved.display_name} güncellendi.")
            return redirect("accounts:user_list")
    else:
        form = UserForm(instance=user_obj)
    return render(
        request,
        "accounts/user_form.html",
        {
            "form": form,
            "page_title": f"Kullanıcı: {user_obj.display_name}",
            "user_obj": user_obj,
            "is_create": False,
        },
    )


@require_permission("user.manage")
def user_permissions(request, pk: int):
    user_obj = get_object_or_404(User, pk=pk)
    if request.method == "POST":
        form = UserPermissionForm(request.POST, instance=user_obj)
        if form.is_valid():
            form.save()
            record_audit(
                AuditLog.Action.PERMISSION,
                obj=user_obj,
                description=f"{user_obj.username} özel izinleri güncellendi.",
                changes={
                    "ek": user_obj.extra_permissions,
                    "kapatilan": user_obj.denied_permissions,
                },
                severity=AuditLog.Severity.WARNING,
                request=request,
            )
            messages.success(request, "İzinler güncellendi.")
            return redirect("accounts:user_list")
    else:
        form = UserPermissionForm(instance=user_obj)

    return render(
        request,
        "accounts/user_permissions.html",
        {
            "form": form,
            "user_obj": user_obj,
            "page_title": f"İzinler: {user_obj.display_name}",
            "permission_groups": grouped_permissions(),
            "role_permissions": sorted(user_obj.effective_permissions),
        },
    )


@require_permission("user.manage")
@require_POST
def user_toggle_active(request, pk: int):
    user_obj = get_object_or_404(User, pk=pk)
    if user_obj.pk == request.user.pk:
        messages.error(request, "Kendi hesabınızı devre dışı bırakamazsınız.")
        return redirect("accounts:user_list")
    user_obj.is_active = not user_obj.is_active
    user_obj.save(update_fields=["is_active"])
    record_audit(
        AuditLog.Action.UPDATE,
        obj=user_obj,
        description=(
            f"{user_obj.username} hesabı "
            f"{'etkinleştirildi' if user_obj.is_active else 'devre dışı bırakıldı'}."
        ),
        severity=AuditLog.Severity.WARNING,
        request=request,
    )
    messages.success(request, f"{user_obj.display_name} durumu güncellendi.")
    return redirect("accounts:user_list")


def lockout(request, credentials=None, *args, **kwargs):
    """django-axes kilit sayfası."""
    return render(request, "accounts/lockout.html", status=429)
