"""Kimlik doğrulama arka uçları."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q


class EmailOrUsernameBackend(ModelBackend):
    """Kullanıcı adı veya e-posta ile giriş.

    Kullanıcı bulunamasa bile parola hash'lemesi çalıştırılır; böylece
    yanıt süresinden kullanıcı varlığı çıkarılamaz (timing attack).
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        User = get_user_model()
        identifier = username or kwargs.get("email") or kwargs.get(User.USERNAME_FIELD)
        if not identifier or not password:
            return None

        user = (
            User.objects.filter(Q(username__iexact=identifier) | Q(email__iexact=identifier))
            .order_by("pk")
            .first()
        )
        if user is None:
            User().set_password(password)  # sabit zaman davranışı
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
