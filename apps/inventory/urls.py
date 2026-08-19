from django.urls import path

from apps.inventory import views

app_name = "inventory"

urlpatterns = [
    path("", views.ingredient_list, name="ingredient_list"),
    path("malzeme/yeni/", views.ingredient_create, name="ingredient_create"),
    path("malzeme/<int:pk>/", views.ingredient_detail, name="ingredient_detail"),
    path("malzeme/<int:pk>/duzenle/", views.ingredient_edit, name="ingredient_edit"),
    path("malzeme/<int:pk>/giris/", views.stock_receive, name="stock_receive"),
    path("hareketler/", views.movement_list, name="movement_list"),
    path("uyarilar/", views.alerts, name="alerts"),
    path("fire/", views.waste_list, name="waste_list"),
    path("fire/ekle/", views.waste_create, name="waste_create"),
    path("sayim/", views.count_list, name="count_list"),
    path("sayim/olustur/", views.count_create, name="count_create"),
    path("sayim/<int:pk>/", views.count_detail, name="count_detail"),
    path("sayim/<int:pk>/kaydet/", views.count_save, name="count_save"),
    path("sayim/<int:pk>/uygula/", views.count_apply, name="count_apply"),
    path("tedarikci/", views.supplier_list, name="supplier_list"),
    path("tedarikci/yeni/", views.supplier_create, name="supplier_create"),
    path("tedarikci/<int:pk>/duzenle/", views.supplier_edit, name="supplier_edit"),
    path("satinalma/", views.purchase_list, name="purchase_list"),
    path("satinalma/yeni/", views.purchase_create, name="purchase_create"),
    path("satinalma/oneri/", views.purchase_auto_suggest, name="purchase_auto_suggest"),
    path("satinalma/<int:pk>/", views.purchase_detail, name="purchase_detail"),
    path("satinalma/<int:pk>/satir/", views.purchase_add_line, name="purchase_add_line"),
    path("satinalma/<int:pk>/onayla/", views.purchase_approve, name="purchase_approve"),
    path("satinalma/<int:pk>/teslim/", views.purchase_receive, name="purchase_receive"),
]
