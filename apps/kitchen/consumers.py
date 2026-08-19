"""Mutfak ekranı WebSocket tüketicisi."""

from __future__ import annotations

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer


class KitchenDisplayConsumer(AsyncJsonWebsocketConsumer):
    """Bir istasyonun canlı KOT akışı.

    Bağlantı adresi: ``ws://<host>/ws/kitchen/<istasyon-kodu>/``
    ``all`` kodu tüm istasyonları dinler.
    """

    async def connect(self):
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.close(code=4401)
            return
        if not await self._can_view(user):
            await self.close(code=4403)
            return

        self.station_code = self.scope["url_route"]["kwargs"]["station"]
        self.group_name = (
            "kitchen_all" if self.station_code == "all" else f"kitchen_{self.station_code}"
        )
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send_json({"event": "connected", "station": self.station_code})

    async def disconnect(self, code):
        group = getattr(self, "group_name", None)
        if group:
            await self.channel_layer.group_discard(group, self.channel_name)

    async def receive_json(self, content, **kwargs):
        """İstemciden gelen komutlar: ping ve durum değiştirme."""
        action = content.get("action")
        if action == "ping":
            await self.send_json({"event": "pong"})
            return

        user = self.scope["user"]
        if not user.has_perm_code("kitchen.manage"):
            await self.send_json({"event": "error", "detail": "Yetkiniz yok."})
            return

        ticket_id = content.get("ticket_id")
        if action in {"start", "ready", "complete"} and ticket_id:
            result = await self._transition(ticket_id, action, user)
            if result is None:
                await self.send_json({"event": "error", "detail": "KOT bulunamadı."})

    async def kitchen_event(self, event):
        await self.send_json(event["payload"])

    # ------------------------------------------------------ yardımcılar
    @database_sync_to_async
    def _can_view(self, user) -> bool:
        return user.has_any_perm("kitchen.view", "bar.view")

    @database_sync_to_async
    def _transition(self, ticket_id: int, action: str, user):
        from apps.kitchen.models import KitchenTicket
        from apps.kitchen.services import complete_ticket, mark_ticket_ready, start_ticket

        ticket = (
            KitchenTicket.objects.filter(pk=ticket_id).select_related("station", "order").first()
        )
        if ticket is None:
            return None
        handler = {"start": start_ticket, "ready": mark_ticket_ready, "complete": complete_ticket}[
            action
        ]
        return handler(ticket, user=user)
