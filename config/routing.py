"""WebSocket yönlendirme tablosu."""

from django.urls import path

from apps.kitchen.consumers import KitchenDisplayConsumer
from apps.orders.consumers import OrderStreamConsumer

websocket_urlpatterns = [
    path("ws/kitchen/<slug:station>/", KitchenDisplayConsumer.as_asgi()),
    path("ws/orders/", OrderStreamConsumer.as_asgi()),
]
