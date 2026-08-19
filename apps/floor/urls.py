from django.urls import path

from apps.floor import views

app_name = "floor"

urlpatterns = [
    path("", views.table_map, name="table_map"),
    path("masalar/", views.table_list, name="table_list"),
    path("masalar/yeni/", views.table_create, name="table_create"),
    path("masalar/<int:pk>/duzenle/", views.table_edit, name="table_edit"),
    path("masalar/<int:pk>/durum/", views.table_set_status, name="table_status"),
    path("masalar/<int:pk>/garson/", views.table_assign_waiter, name="table_assign_waiter"),
    path("masalar/<int:pk>/birlestir/", views.table_merge, name="table_merge"),
    path("masalar/<int:pk>/ayir/", views.table_unmerge, name="table_unmerge"),
    path("masalar/<int:pk>/qr.png", views.table_qr, name="table_qr"),
    path("rezervasyon/", views.reservation_list, name="reservation_list"),
    path("rezervasyon/yeni/", views.reservation_create, name="reservation_create"),
    path("rezervasyon/<int:pk>/duzenle/", views.reservation_edit, name="reservation_edit"),
    path("rezervasyon/<int:pk>/durum/", views.reservation_set_status, name="reservation_status"),
    path("rezervasyon/uygunluk/", views.reservation_availability, name="reservation_availability"),
    path("bekleme/ekle/", views.waitlist_add, name="waitlist_add"),
    path("bekleme/<int:pk>/guncelle/", views.waitlist_update, name="waitlist_update"),
]
