"""Kişisel veri alanı keşfi (privacy engineering yardımcıları).

`docs/data_inventory.json` içindeki makine-okunur kişisel veri envanterinin
kodla senkron kalmasını sağlar: model alanları isim desenleriyle taranır ve
envanterde karşılığı olmayan aday alan CI'da testi kırar (bkz.
tests/test_compliance.py). Böylece yeni bir kişisel veri alanı, envantere
(ve gerekiyorsa saklama/maskeleme politikalarına) işlenmeden ana dala
giremez.

Desen eşleşmesi kaba bir sezgiseldir; nihai sınıflandırma insan kararıdır.
Envanter, yanlış-pozitifleri `"personal": false` + gerekçe ile
işaretleyebilir.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.apps import apps as django_apps

# Alan adında geçtiğinde "kişisel veri adayı" sayılan parçalar.
# Bilinçli olarak dar tutulmuştur: "name" tek başına aranmaz (Product.name
# gibi ürün adları kişisel veri değildir); insana işaret eden birleşik
# adlar aranır.
PII_NAME_PATTERNS: tuple[str, ...] = (
    "first_name",
    "last_name",
    "guest_name",
    "contact_name",
    "username_snapshot",
    "phone",
    "email",
    "address",  # ip_address dahil — ikisi de kişisel veri adayıdır
    "birth",
    "salary",
    "hourly_rate",
    "allergy",
    "emergency",
    "tax_number",
    "user_agent",
    "pin_hash",
    "avatar",
    "iban",
)

# Yalnızca proje uygulamaları taranır (Django/3. taraf tabloları değil).
LOCAL_APP_PREFIX = "apps."

INVENTORY_PATH = Path(__file__).resolve().parent.parent.parent / "docs" / "data_inventory.json"


def scan_personal_data_fields() -> list[tuple[str, str]]:
    """Yerel modellerde kişisel veri adayı alanları bulur.

    Dönüş: [("crm.Customer", "phone"), ...] — alfabetik sıralı.
    """
    found: list[tuple[str, str]] = []
    for model in django_apps.get_models():
        if not model.__module__.startswith(LOCAL_APP_PREFIX):
            continue
        label = f"{model._meta.app_label}.{model.__name__}"
        for field in model._meta.get_fields():
            if not hasattr(field, "attname"):  # reverse ilişkiler atlanır
                continue
            name = field.name
            if any(pattern in name for pattern in PII_NAME_PATTERNS):
                found.append((label, name))
    return sorted(set(found))


def load_inventory() -> dict:
    """docs/data_inventory.json içeriğini döndürür."""
    return json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))


def inventory_field_index(inventory: dict | None = None) -> dict[tuple[str, str], dict]:
    """Envanteri (model, alan) -> kayıt sözlüğü olarak indeksler."""
    inventory = inventory or load_inventory()
    return {(entry["model"], entry["field"]): entry for entry in inventory["fields"]}
