from django.urls import path

from apps.catalog import views

app_name = "catalog"

urlpatterns = [
    path("", views.product_list, name="product_list"),
    path("urun/yeni/", views.product_create, name="product_create"),
    path("urun/<int:pk>/", views.product_detail, name="product_detail"),
    path("urun/<int:pk>/duzenle/", views.product_edit, name="product_edit"),
    path("urun/<int:pk>/durum/", views.product_toggle_availability, name="product_toggle"),
    path("urun/<int:pk>/recete/", views.recipe_detail, name="recipe_detail"),
    path("urun/<int:pk>/recete/duzenle/", views.recipe_edit, name="recipe_edit"),
    path("kategoriler/", views.category_list, name="category_list"),
    path("kategoriler/yeni/", views.category_create, name="category_create"),
    path("kategoriler/<int:pk>/duzenle/", views.category_edit, name="category_edit"),
    path("qr/<uuid:token>/", views.qr_menu, name="qr_menu"),
]
