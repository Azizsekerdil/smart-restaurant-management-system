from django.urls import path

from apps.crm import views

app_name = "crm"

urlpatterns = [
    path("", views.customer_list, name="customer_list"),
    path("ara/", views.customer_search, name="customer_search"),
    path("yeni/", views.customer_create, name="customer_create"),
    path("<int:pk>/", views.customer_detail, name="customer_detail"),
    path("<int:pk>/duzenle/", views.customer_edit, name="customer_edit"),
    path("<int:pk>/izin/", views.customer_consent, name="customer_consent"),
    path("<int:pk>/anonimlestir/", views.customer_anonymize, name="customer_anonymize"),
    path("<int:pk>/veri-dosyasi/", views.customer_data_export, name="customer_data_export"),
    path("<int:pk>/puan/", views.loyalty_adjust, name="loyalty_adjust"),
    path("yorumlar/", views.review_list, name="review_list"),
    path("yorumlar/ekle/", views.review_create, name="review_create"),
    path("yorumlar/<int:pk>/cozuldu/", views.review_resolve, name="review_resolve"),
    path("yorumlar/analiz/", views.review_analyze, name="review_analyze"),
    path("kampanyalar/", views.campaign_list, name="campaign_list"),
    path("kampanyalar/yeni/", views.campaign_create, name="campaign_create"),
    path("kampanyalar/<int:pk>/durum/", views.campaign_set_status, name="campaign_status"),
]
