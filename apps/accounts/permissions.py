"""Rol tabanlı yetkilendirme (RBAC) tanımları.

Tasarım kararı
--------------
Django'nun yerleşik izin sistemi model/CRUD odaklıdır ve "garson kendi
masasının siparişini iptal edemez ama şef garson edebilir" gibi işlevsel
kuralları ifade etmekte zayıf kalır. Bu yüzden **işlev odaklı** bir izin
kodu kümesi tanımlanır ve roller bu kodlarla eşlenir.

Katmanlar (sırayla değerlendirilir):
 1. Süper kullanıcı  -> her şeye izinli
 2. Kullanıcıya özel reddedilen izinler (denied_permissions) -> kesin ret
 3. Kullanıcıya özel eklenen izinler (extra_permissions)     -> kesin izin
 4. Rol matrisi (ROLE_PERMISSIONS)                            -> varsayılan
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _


class Role(models.TextChoices):
    """Restoran organizasyon şemasındaki roller."""

    OWNER = "owner", _("İşletme sahibi")
    GENERAL_MANAGER = "general_manager", _("Genel müdür")
    RESTAURANT_MANAGER = "restaurant_manager", _("Restoran müdürü")
    CHEF = "chef", _("Şef")
    KITCHEN_STAFF = "kitchen_staff", _("Mutfak personeli")
    HEAD_WAITER = "head_waiter", _("Şef garson")
    WAITER = "waiter", _("Garson")
    CASHIER = "cashier", _("Kasiyer")
    BARTENDER = "bartender", _("Bar personeli")
    STOREKEEPER = "storekeeper", _("Depo / satın alma")
    ACCOUNTANT = "accountant", _("Muhasebe")
    COURIER = "courier", _("Kurye")


# ------------------------------------------------------------------
#  İzin kodları: "modul.eylem"
# ------------------------------------------------------------------
PERMISSIONS: dict[str, str] = {
    # Genel
    "dashboard.view": "Yönetim panelini görüntüle",
    "notification.view": "Bildirimleri görüntüle",
    # POS / sipariş
    "pos.use": "POS ekranını kullan, sipariş oluştur",
    "pos.discount": "Siparişe indirim uygula",
    "pos.void": "Sipariş / ürün iptali yap",
    "pos.refund": "İade işlemi yap",
    "pos.split": "Hesap böl / birleştir",
    "pos.price_override": "Ürün fiyatını elle değiştir",
    "pos.reopen": "Kapatılmış siparişi yeniden aç",
    "order.view": "Siparişleri görüntüle",
    "order.manage": "Tüm siparişleri yönet",
    # Salon
    "table.view": "Masa planını görüntüle",
    "table.manage": "Masa ve salon düzenini yönet",
    "table.transfer": "Siparişi başka masaya taşı",
    "reservation.view": "Rezervasyonları görüntüle",
    "reservation.manage": "Rezervasyon oluştur / düzenle",
    # Menü ve reçete
    "menu.view": "Menüyü görüntüle",
    "menu.manage": "Menü, kategori ve fiyatları yönet",
    "recipe.view": "Reçeteleri görüntüle",
    "recipe.manage": "Reçete ve maliyetleri yönet",
    # Stok
    "inventory.view": "Stok durumunu görüntüle",
    "inventory.manage": "Stok giriş/çıkışı yap",
    "inventory.count": "Stok sayımı yap",
    "inventory.waste": "Fire / israf kaydı gir",
    "purchase.view": "Satın alma kayıtlarını görüntüle",
    "purchase.manage": "Satın alma siparişi oluştur / onayla",
    "supplier.manage": "Tedarikçileri yönet",
    # Mutfak
    "kitchen.view": "Mutfak ekranını görüntüle",
    "kitchen.manage": "Mutfak siparişlerinin durumunu değiştir",
    "bar.view": "Bar ekranını görüntüle",
    # Müşteri
    "customer.view": "Müşterileri görüntüle",
    "customer.manage": "Müşteri kaydı oluştur / düzenle",
    "customer.pii": "Müşteri iletişim bilgilerini maskesiz gör",
    "loyalty.manage": "Sadakat puanlarını yönet",
    "campaign.manage": "Kampanya ve kuponları yönet",
    # Personel
    "staff.view": "Personel listesini görüntüle",
    "staff.manage": "Personel kaydı yönet",
    "shift.view": "Vardiya planını görüntüle",
    "shift.manage": "Vardiya planla",
    "attendance.manage": "Giriş/çıkış ve izinleri yönet",
    # Raporlama / finans
    "report.view": "Operasyonel raporları görüntüle",
    "report.financial": "Mali raporları görüntüle",
    "report.export": "Rapor dışa aktar (PDF/Excel/CSV)",
    "report.statistics": "İstatistik merkezini görüntüle",
    "cash.manage": "Kasa aç / kapat, Z raporu al",
    "accounting.view": "Muhasebe kayıtlarını görüntüle",
    "accounting.manage": "Gelir/gider kaydı gir",
    # Teslimat
    "delivery.view": "Kurye siparişlerini görüntüle",
    "delivery.manage": "Kurye atama ve teslimat yönetimi",
    # Yapay zekâ
    "ai.use": "Yapay zekâ asistanını kullan",
    "ai.configure": "Yapay zekâ sağlayıcı ayarlarını değiştir",
    # Geliştirme merkezi
    "devcenter.access": "AI Geliştirme Merkezine eriş",
    "devcenter.terminal": "Güvenli terminali kullan",
    "devcenter.apply": "Önerilen kod değişikliğini uygula",
    # Sistem
    "settings.manage": "Sistem ayarlarını yönet",
    "user.manage": "Kullanıcı ve yetkileri yönet",
    "audit.view": "Denetim kayıtlarını görüntüle",
    "data.erase": "KVKK kapsamında veri silme/anonimleştirme",
    # Yedekleme
    "backup.view": "Yedekleri listele",
    "backup.create": "Yedek oluştur",
    "backup.download": "Yedek dosyasını indir",
    "backup.restore": "Yedekten geri yükle",
}

ALL_PERMISSIONS: frozenset[str] = frozenset(PERMISSIONS)

# ------------------------------------------------------------------
#  Rol -> izin matrisi
# ------------------------------------------------------------------
_BASE = {"dashboard.view", "notification.view"}

_WAITER = _BASE | {
    "pos.use",
    "order.view",
    "table.view",
    "reservation.view",
    "menu.view",
    "customer.view",
    "kitchen.view",
    "shift.view",
}

_HEAD_WAITER = _WAITER | {
    "pos.discount",
    "pos.void",
    "pos.split",
    "table.transfer",
    "table.manage",
    "reservation.manage",
    "customer.manage",
    "order.manage",
    "staff.view",
    "report.view",
    "ai.use",
}

_CASHIER = _BASE | {
    "pos.use",
    "pos.split",
    "pos.discount",
    "order.view",
    "table.view",
    "menu.view",
    "customer.view",
    "customer.manage",
    "loyalty.manage",
    "cash.manage",
    "report.view",
    "report.export",
    "reservation.view",
}

_KITCHEN = _BASE | {
    "kitchen.view",
    "kitchen.manage",
    "menu.view",
    "recipe.view",
    "inventory.view",
    "order.view",
    "shift.view",
}

_CHEF = _KITCHEN | {
    "menu.manage",
    "recipe.manage",
    "inventory.manage",
    "inventory.count",
    "inventory.waste",
    "purchase.view",
    "purchase.manage",
    "report.view",
    "staff.view",
    "shift.manage",
    "ai.use",
}

_BARTENDER = _BASE | {
    "bar.view",
    "kitchen.view",
    "kitchen.manage",
    "menu.view",
    "recipe.view",
    "inventory.view",
    "inventory.waste",
    "order.view",
    "pos.use",
    "shift.view",
}

_STOREKEEPER = _BASE | {
    "inventory.view",
    "inventory.manage",
    "inventory.count",
    "inventory.waste",
    "purchase.view",
    "purchase.manage",
    "supplier.manage",
    "recipe.view",
    "menu.view",
    "report.view",
    "report.export",
    "ai.use",
}

_ACCOUNTANT = _BASE | {
    "report.view",
    "report.financial",
    "report.export",
    "report.statistics",
    "accounting.view",
    "accounting.manage",
    "cash.manage",
    "order.view",
    "purchase.view",
    "inventory.view",
    "customer.view",
    "staff.view",
    "audit.view",
    "ai.use",
}

_COURIER = _BASE | {"delivery.view", "delivery.manage", "order.view", "shift.view"}

_RESTAURANT_MANAGER = (
    _HEAD_WAITER
    | _CASHIER
    | _CHEF
    | _STOREKEEPER
    | {
        "pos.refund",
        "pos.reopen",
        "pos.price_override",
        "report.financial",
        "campaign.manage",
        "loyalty.manage",
        "staff.manage",
        "attendance.manage",
        "customer.pii",
        "delivery.view",
        "delivery.manage",
        "audit.view",
        "settings.manage",
        "bar.view",
        "report.statistics",
        # Yedek alabilir ve indirebilir; geri yükleme üst yönetimdedir.
        "backup.view",
        "backup.create",
        "backup.download",
    }
)

_GENERAL_MANAGER = _RESTAURANT_MANAGER | {
    "accounting.view",
    "accounting.manage",
    "user.manage",
    "ai.configure",
    "data.erase",
    # Geri yükleme mevcut veriyi değiştirir; yalnızca üst yönetim yapabilir.
    "backup.restore",
}

# İşletme sahibi tüm izinlere sahiptir (Geliştirme Merkezi dahil).
_OWNER = set(ALL_PERMISSIONS)

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    Role.OWNER: frozenset(_OWNER),
    Role.GENERAL_MANAGER: frozenset(_GENERAL_MANAGER),
    Role.RESTAURANT_MANAGER: frozenset(_RESTAURANT_MANAGER),
    Role.CHEF: frozenset(_CHEF),
    Role.KITCHEN_STAFF: frozenset(_KITCHEN),
    Role.HEAD_WAITER: frozenset(_HEAD_WAITER),
    Role.WAITER: frozenset(_WAITER),
    Role.CASHIER: frozenset(_CASHIER),
    Role.BARTENDER: frozenset(_BARTENDER),
    Role.STOREKEEPER: frozenset(_STOREKEEPER),
    Role.ACCOUNTANT: frozenset(_ACCOUNTANT),
    Role.COURIER: frozenset(_COURIER),
}

# Yetkili onayı gerektiren hassas işlemler: bu izinlere sahip olmayan bir
# kullanıcı işlemi başlatırsa, yetkili bir kullanıcının PIN'i istenir.
MANAGER_APPROVAL_PERMISSIONS = frozenset(
    {"pos.void", "pos.refund", "pos.discount", "pos.price_override", "pos.reopen"}
)


def permissions_for_role(role: str) -> frozenset[str]:
    return ROLE_PERMISSIONS.get(role, frozenset(_BASE))


def grouped_permissions() -> dict[str, list[tuple[str, str]]]:
    """İzinleri modül başlığına göre gruplar (yönetim arayüzü için)."""
    labels = {
        "dashboard": "Genel",
        "notification": "Genel",
        "pos": "POS ve Sipariş",
        "order": "POS ve Sipariş",
        "table": "Salon ve Masa",
        "reservation": "Salon ve Masa",
        "menu": "Menü ve Reçete",
        "recipe": "Menü ve Reçete",
        "inventory": "Stok ve Satın Alma",
        "purchase": "Stok ve Satın Alma",
        "supplier": "Stok ve Satın Alma",
        "kitchen": "Mutfak ve Bar",
        "bar": "Mutfak ve Bar",
        "customer": "Müşteri ve Sadakat",
        "loyalty": "Müşteri ve Sadakat",
        "campaign": "Müşteri ve Sadakat",
        "staff": "Personel",
        "shift": "Personel",
        "attendance": "Personel",
        "report": "Raporlama ve Finans",
        "cash": "Raporlama ve Finans",
        "accounting": "Raporlama ve Finans",
        "delivery": "Teslimat",
        "ai": "Yapay Zekâ",
        "devcenter": "Geliştirme Merkezi",
        "settings": "Sistem",
        "user": "Sistem",
        "audit": "Sistem",
        "data": "Sistem",
        "backup": "Sistem",
    }
    groups: dict[str, list[tuple[str, str]]] = {}
    for code, label in PERMISSIONS.items():
        module = code.split(".", 1)[0]
        groups.setdefault(labels.get(module, "Diğer"), []).append((code, label))
    return groups
