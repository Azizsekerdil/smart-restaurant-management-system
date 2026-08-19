from django.urls import path

from apps.kitchen import views

app_name = "kitchen"

urlpatterns = [
    path("", views.display, name="display"),
    path("pano/", views.ticket_board, name="ticket_board"),
    # Özel yollar, genel <str:action> kalıbından ÖNCE tanımlanmalıdır.
    path("kot/<int:pk>/yazdir.txt", views.kot_print, name="kot_print"),
    path("kot/<int:pk>/onizleme/", views.kot_preview, name="kot_preview"),
    path("kot/<int:pk>/<str:action>/", views.ticket_transition, name="ticket_transition"),
    path("istasyonlar/", views.station_list, name="station_list"),
    path("istasyonlar/kaydet/", views.station_save, name="station_save"),
    path("performans/", views.performance, name="performance"),
]
