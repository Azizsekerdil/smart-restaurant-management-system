"""Canlı sipariş akışı WebSocket tüketicisi (POS ve yönetim paneli için)."""

from __future__ import annotations

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer


class OrderStreamConsumer(AsyncJsonWebsocketConsumer):
    """Sipariş durum değişikliklerini yayınlar. Adres: ``ws://<host>/ws/orders/``"""

    group_name = "orders"

    async def connect(self):
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.close(code=4401)
            return
        if not await self._can_view(user):
            await self.close(code=4403)
            return
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send_json({"event": "connected"})

    async def disconnect(self, code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        if content.get("action") == "ping":
            await self.send_json({"event": "pong"})

    async def order_event(self, event):
        await self.send_json({"event": "order", **event["payload"]})

    @database_sync_to_async
    def _can_view(self, user) -> bool:
        return user.has_any_perm("order.view", "pos.use", "dashboard.view")
