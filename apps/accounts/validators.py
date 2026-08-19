"""Parola politikası doğrulayıcıları."""

from __future__ import annotations

import re

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _


class ComplexityValidator:
    """Parolada harf, rakam ve büyük/küçük harf çeşitliliği arar.

    Kurumsal ortamlarda tek başına uzunluk yeterli olmadığından, Django'nun
    yerleşik doğrulayıcılarına ek olarak kullanılır.
    """

    def __init__(self, min_classes: int = 3) -> None:
        self.min_classes = min_classes

    def validate(self, password: str, user=None) -> None:
        classes = 0
        if re.search(r"[a-zçğıöşü]", password):
            classes += 1
        if re.search(r"[A-ZÇĞİÖŞÜ]", password):
            classes += 1
        if re.search(r"\d", password):
            classes += 1
        if re.search(r"[^\w\s]", password):
            classes += 1

        if classes < self.min_classes:
            raise ValidationError(
                _(
                    "Parola yeterince güçlü değil. Küçük harf, büyük harf, rakam ve "
                    "özel karakter türlerinden en az %(n)d tanesini içermelidir."
                ),
                code="password_not_complex",
                params={"n": self.min_classes},
            )

        if re.search(r"(.)\1{3,}", password):
            raise ValidationError(
                _("Parolada aynı karakter 4 kereden fazla arka arkaya tekrarlanamaz."),
                code="password_repetitive",
            )

    def get_help_text(self) -> str:
        return _(
            "Parolanız küçük harf, büyük harf, rakam ve özel karakter "
            "türlerinden en az %(n)d tanesini içermelidir."
        ) % {"n": self.min_classes}
