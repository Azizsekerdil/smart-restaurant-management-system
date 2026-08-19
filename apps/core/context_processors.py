"""Şablon bağlam işlemcileri: işletme bilgisi, menü ve bildirimler."""

from __future__ import annotations

from django.conf import settings
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.core.models import Notification


def restaurant_context(request):
    user = getattr(request, "user", None)
    unread = 0
    if user is not None and user.is_authenticated:
        unread = Notification.objects.filter(
            Q(recipient=user) | Q(recipient__isnull=True), is_read=False
        ).count()

    return {
        "RESTAURANT": settings.RESTAURANT,
        "CURRENCY_SYMBOL": settings.RESTAURANT["CURRENCY_SYMBOL"],
        "APP_VERSION": "1.0.0",
        "DEVCENTER_ENABLED": settings.DEVCENTER["ENABLED"],
        "unread_notification_count": unread,
        # Kişisel veri / sağlık verisi maskesini her şablondan tek bir
        # yerden sorabilmek için. Her ekranın kendi bağlamına ayrı ayrı
        # bayrak koyması gerektiğinde, unutulan bir ekran sessiz bir veri
        # sızıntısına dönüşüyordu.
        "can_see_customer_pii": bool(
            user is not None
            and getattr(user, "is_authenticated", False)
            and user.has_perm_code("customer.pii")
        ),
        "theme_preference": (
            getattr(user, "theme_preference", "auto")
            if user is not None and user.is_authenticated
            else "auto"
        ),
    }


# (etiket, url adı, ikon, gerekli izinler)
# Etiketler gecikmeli çevrilir: modül yüklenirken dil henüz belli değildir,
# istek anında kullanıcının diline göre çözülmelidir.
NAV_ITEMS: list[tuple[str, str, str, tuple[str, ...]]] = [
    (_("Panel"), "reports:dashboard", "speedometer2", ("dashboard.view",)),
    (_("POS"), "orders:pos", "cart3", ("pos.use",)),
    (_("Masalar"), "floor:table_map", "grid-3x3-gap", ("table.view",)),
    # Çoğul biçim bilinçli: aynı metin model adı olarak da geçiyor ve
    # gettext tek çeviri verir; menüde çoğul daha doğru okunur.
    (_("Rezervasyonlar"), "floor:reservation_list", "calendar-check", ("reservation.view",)),
    (_("Siparişler"), "orders:order_list", "receipt", ("order.view",)),
    (_("Mutfak"), "kitchen:display", "fire", ("kitchen.view",)),
    (_("Menü"), "catalog:product_list", "book", ("menu.view",)),
    (_("Stok"), "inventory:ingredient_list", "box-seam", ("inventory.view",)),
    (_("Satın Alma"), "inventory:purchase_list", "truck", ("purchase.view",)),
    (_("Müşteriler"), "crm:customer_list", "people", ("customer.view",)),
    (_("Personel"), "hr:employee_list", "person-badge", ("staff.view", "shift.view")),
    (_("Raporlar"), "reports:report_index", "bar-chart", ("report.view",)),
    (_("İstatistik"), "reports:statistics", "bar-chart-line", ("report.statistics",)),
    (_("Eğitim"), "training:index", "mortarboard", ("dashboard.view",)),
    (_("Yapay Zekâ"), "ai:assistant", "stars", ("ai.use",)),
    (_("Yedekleme"), "backups:index", "archive", ("backup.view",)),
    (_("Geliştirme"), "devcenter:index", "terminal", ("devcenter.access",)),
    (_("Ayarlar"), "core:settings", "gear", ("settings.manage", "user.manage")),
]


def navigation_context(request):
    """Kullanıcının yetkisine göre filtrelenmiş menü."""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {"nav_items": []}

    items = []
    for label, url_name, icon, codes in NAV_ITEMS:
        if url_name == "devcenter:index" and not settings.DEVCENTER["ENABLED"]:
            continue
        if user.has_any_perm(*codes):
            items.append({"label": label, "url_name": url_name, "icon": icon})
    return {"nav_items": items}
