from django.urls import path

from apps.core import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("bildirimler/", views.notification_list, name="notifications"),
    path("bildirimler/akis/", views.notification_feed, name="notification_feed"),
    path("bildirimler/<int:pk>/okundu/", views.notification_mark_read, name="notification_read"),
    path(
        "bildirimler/tumu-okundu/", views.notification_mark_all_read, name="notification_read_all"
    ),
    path("ayarlar/", views.settings_index, name="settings"),
    path("ayarlar/guncelle/", views.settings_update, name="settings_update"),
    path("denetim/", views.audit_log, name="audit_log"),
    path("healthz/", views.healthz, name="healthz"),
]
