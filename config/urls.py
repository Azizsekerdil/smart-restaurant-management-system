"""Kök URL yapılandırması."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from apps.core import views as core_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("i18n/", include("django.conf.urls.i18n")),
    path("", include("apps.core.urls", namespace="core")),
    path("accounts/", include("apps.accounts.urls", namespace="accounts")),
    path("panel/", include("apps.reports.urls", namespace="reports")),
    path("menu/", include("apps.catalog.urls", namespace="catalog")),
    path("stok/", include("apps.inventory.urls", namespace="inventory")),
    path("salon/", include("apps.floor.urls", namespace="floor")),
    path("siparis/", include("apps.orders.urls", namespace="orders")),
    path("mutfak/", include("apps.kitchen.urls", namespace="kitchen")),
    path("musteri/", include("apps.crm.urls", namespace="crm")),
    path("personel/", include("apps.hr.urls", namespace="hr")),
    path("yedek/", include("apps.backups.urls", namespace="backups")),
    path("egitim/", include("apps.training.urls", namespace="training")),
    path("ai/", include("apps.ai.urls", namespace="ai")),
    path("devcenter/", include("apps.devcenter.urls", namespace="devcenter")),
    path("api/", include("config.api_urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])

handler403 = core_views.error_403
handler404 = core_views.error_404
handler500 = core_views.error_500

admin.site.site_header = "Akıllı Restaurant Yönetim Sistemi"
admin.site.site_title = "Restaurant Yönetimi"
admin.site.index_title = "Sistem Yönetimi"
