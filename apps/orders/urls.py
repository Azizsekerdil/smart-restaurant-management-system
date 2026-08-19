from django.urls import path

from apps.orders import views

app_name = "orders"

urlpatterns = [
    path("pos/", views.pos, name="pos"),
    path("", views.order_list, name="order_list"),
    path("<int:pk>/", views.order_detail, name="order_detail"),
    path("<int:pk>/panel/", views.order_panel, name="order_panel"),
    path("<int:pk>/fis/", views.order_receipt, name="order_receipt"),
    path("<int:pk>/fis.pdf", views.order_receipt_pdf, name="order_receipt_pdf"),
    # POS işlemleri
    path("olustur/", views.order_create, name="order_create"),
    path("<int:pk>/satir-ekle/", views.order_add_item, name="order_add_item"),
    path(
        "<int:pk>/satir/<int:item_id>/guncelle/", views.order_update_item, name="order_update_item"
    ),
    path("<int:pk>/satir/<int:item_id>/iptal/", views.order_cancel_item, name="order_cancel_item"),
    path("<int:pk>/mutfaga-gonder/", views.order_send_kitchen, name="order_send_kitchen"),
    path("<int:pk>/indirim/", views.order_apply_discount, name="order_discount"),
    path("<int:pk>/odeme/", views.order_payment, name="order_payment"),
    path("<int:pk>/iptal/", views.order_cancel, name="order_cancel"),
    path("<int:pk>/iade/", views.order_refund, name="order_refund"),
    path("<int:pk>/bol/", views.order_split, name="order_split"),
    path("<int:pk>/birlestir/", views.order_merge, name="order_merge"),
    path("<int:pk>/masa-tasi/", views.order_transfer, name="order_transfer"),
    # Teslimat
    path("teslimat/", views.delivery_board, name="delivery_board"),
    path("teslimat/<int:pk>/ata/", views.delivery_assign, name="delivery_assign"),
    path("teslimat/<int:pk>/tamamla/", views.delivery_complete, name="delivery_complete"),
    # Kasa
    path("kasa/", views.cash_session_view, name="cash_session"),
    path("kasa/ac/", views.cash_open, name="cash_open"),
    path("kasa/kapat/", views.cash_close, name="cash_close"),
    path("kasa/hareket/", views.cash_movement, name="cash_movement"),
]
