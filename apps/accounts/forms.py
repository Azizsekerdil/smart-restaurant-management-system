"""Kullanıcı formları."""

from __future__ import annotations

from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User
from apps.accounts.permissions import ALL_PERMISSIONS, grouped_permissions


class LoginForm(AuthenticationForm):
    username = forms.CharField(
        label=_("Kullanıcı adı veya e-posta"),
        widget=forms.TextInput(
            attrs={
                "class": "form-control form-control-lg",
                "placeholder": "kullanici@restoran.com",
                "autofocus": True,
                "autocomplete": "username",
            }
        ),
    )
    password = forms.CharField(
        label=_("Parola"),
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control form-control-lg",
                "placeholder": "••••••••",
                "autocomplete": "current-password",
            }
        ),
    )
    remember_me = forms.BooleanField(
        label=_("Beni hatırla"),
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    error_messages = {
        "invalid_login": _("Kullanıcı adı veya parola hatalı. Büyük/küçük harfe dikkat edin."),
        "inactive": _("Bu hesap devre dışı bırakılmış. Yöneticinizle görüşün."),
    }


class PinLoginForm(forms.Form):
    """POS terminalinde hızlı kullanıcı değişimi."""

    username = forms.CharField(
        label=_("Kullanıcı"), widget=forms.TextInput(attrs={"class": "form-control"})
    )
    pin = forms.CharField(
        label=_("PIN"),
        widget=forms.PasswordInput(
            attrs={"class": "form-control", "inputmode": "numeric", "maxlength": "8"}
        ),
    )

    def clean_pin(self):
        pin = self.cleaned_data["pin"]
        if not pin.isdigit():
            raise forms.ValidationError(_("PIN yalnızca rakamlardan oluşmalıdır."))
        return pin


class UserForm(forms.ModelForm):
    """Personel hesabı oluşturma / düzenleme."""

    password1 = forms.CharField(
        label=_("Parola"),
        required=False,
        widget=forms.PasswordInput(attrs={"class": "form-control", "autocomplete": "new-password"}),
        help_text=_("Boş bırakılırsa mevcut parola korunur."),
    )
    password2 = forms.CharField(
        label=_("Parola (tekrar)"),
        required=False,
        widget=forms.PasswordInput(attrs={"class": "form-control"}),
    )
    pin = forms.CharField(
        label=_("POS PIN kodu"),
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "inputmode": "numeric"}),
        help_text=_("4-8 haneli. Hızlı kullanıcı değişimi ve yetkili onayı için."),
    )

    class Meta:
        model = User
        fields = [
            "username",
            "first_name",
            "last_name",
            "email",
            "phone",
            "role",
            "employee_code",
            "is_active",
            "must_change_password",
            "language_preference",
            "theme_preference",
        ]
        widgets = {
            "username": forms.TextInput(attrs={"class": "form-control"}),
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "phone": forms.TextInput(attrs={"class": "form-control"}),
            "role": forms.Select(attrs={"class": "form-select"}),
            "employee_code": forms.TextInput(attrs={"class": "form-control"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "must_change_password": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "language_preference": forms.Select(attrs={"class": "form-select"}),
            "theme_preference": forms.Select(attrs={"class": "form-select"}),
        }

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get("password1"), cleaned.get("password2")
        if p1 or p2:
            if p1 != p2:
                raise forms.ValidationError(_("Parolalar eşleşmiyor."))
            from django.contrib.auth.password_validation import validate_password

            validate_password(p1, self.instance)
        if not self.instance.pk and not p1:
            raise forms.ValidationError(_("Yeni kullanıcı için parola zorunludur."))
        return cleaned

    def clean_pin(self):
        pin = (self.cleaned_data.get("pin") or "").strip()
        if pin and not (pin.isdigit() and 4 <= len(pin) <= 8):
            raise forms.ValidationError(_("PIN 4-8 haneli rakamlardan oluşmalıdır."))
        return pin

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get("password1")
        if password:
            user.set_password(password)
            from django.utils import timezone

            user.password_changed_at = timezone.now()
        pin = self.cleaned_data.get("pin")
        if pin:
            user.set_pin(pin)
        if commit:
            user.save()
        return user


class UserPermissionForm(forms.ModelForm):
    """Kullanıcıya rolünün ötesinde izin verme / izin kısıtlama."""

    extra = forms.MultipleChoiceField(
        label=_("Ek izinler"), required=False, widget=forms.CheckboxSelectMultiple
    )
    denied = forms.MultipleChoiceField(
        label=_("Kapatılan izinler"), required=False, widget=forms.CheckboxSelectMultiple
    )

    class Meta:
        model = User
        fields: list[str] = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        choices = [(code, f"{code} — {label}") for code, label in sorted(ALL_PERMISSIONS_ITEMS())]
        self.fields["extra"].choices = choices
        self.fields["denied"].choices = choices
        if self.instance.pk:
            self.fields["extra"].initial = self.instance.extra_permissions or []
            self.fields["denied"].initial = self.instance.denied_permissions or []

    def save(self, commit=True):
        user = super().save(commit=False)
        user.extra_permissions = [
            c for c in self.cleaned_data.get("extra", []) if c in ALL_PERMISSIONS
        ]
        user.denied_permissions = [
            c for c in self.cleaned_data.get("denied", []) if c in ALL_PERMISSIONS
        ]
        if commit:
            user.save(update_fields=["extra_permissions", "denied_permissions"])
        return user


def ALL_PERMISSIONS_ITEMS():
    from apps.accounts.permissions import PERMISSIONS

    return PERMISSIONS.items()


class ProfileForm(forms.ModelForm):
    """Kullanıcının kendi profilini düzenlemesi."""

    class Meta:
        model = User
        fields = [
            "first_name",
            "last_name",
            "email",
            "phone",
            "avatar",
            "theme_preference",
            "language_preference",
        ]
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "phone": forms.TextInput(attrs={"class": "form-control"}),
            "avatar": forms.ClearableFileInput(
                attrs={"class": "form-control", "accept": "image/*"}
            ),
            "theme_preference": forms.Select(attrs={"class": "form-select"}),
            "language_preference": forms.Select(attrs={"class": "form-select"}),
        }

    def clean_avatar(self):
        avatar = self.cleaned_data.get("avatar")
        if avatar and hasattr(avatar, "size"):
            from apps.core.utils import validate_upload

            validate_upload(avatar)
        return avatar


def permission_groups():
    return grouped_permissions()
