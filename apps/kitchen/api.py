"""Mutfak REST API."""

from __future__ import annotations

from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.decorators import HasPermissionCode
from apps.kitchen import services
from apps.kitchen.models import KitchenTicket


class KitchenTicketSerializer(serializers.ModelSerializer):
    station_name = serializers.CharField(source="station.name", read_only=True)
    order_number = serializers.CharField(source="order.number", read_only=True)
    table_label = serializers.CharField(read_only=True)
    elapsed_minutes = serializers.IntegerField(read_only=True)
    urgency = serializers.CharField(read_only=True)
    items = serializers.SerializerMethodField()

    class Meta:
        model = KitchenTicket
        fields = [
            "id",
            "number",
            "order",
            "order_number",
            "station",
            "station_name",
            "table_label",
            "status",
            "priority",
            "course",
            "note",
            "queued_at",
            "started_at",
            "ready_at",
            "elapsed_minutes",
            "urgency",
            "items",
        ]
        read_only_fields = ["number", "queued_at"]

    def get_items(self, obj) -> list[dict]:
        return [
            {
                "id": line.pk,
                "name": line.order_item.product_name,
                "quantity": str(line.order_item.quantity),
                "note": line.order_item.note,
                "modifiers": line.order_item.modifier_summary,
                "status": line.status,
            }
            for line in obj.lines.select_related("order_item").prefetch_related(
                "order_item__modifiers"
            )
        ]


class KitchenTicketViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = KitchenTicketSerializer
    permission_classes = [HasPermissionCode]
    required_permissions = ("kitchen.manage",)
    required_read_permissions = ("kitchen.view", "bar.view")
    filterset_fields = ["station", "status", "priority"]
    ordering_fields = ["queued_at", "priority"]

    def get_queryset(self):
        return (
            KitchenTicket.objects.select_related("station", "order", "order__table")
            .prefetch_related("lines__order_item__modifiers")
            .order_by("-priority", "queued_at")
        )

    @action(detail=False, methods=["get"])
    def queue(self, request):
        station = request.query_params.get("station", "all")
        tickets = services.station_queue(station)
        return Response(self.get_serializer(tickets, many=True).data)

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        ticket = services.start_ticket(self.get_object(), user=request.user)
        return Response(self.get_serializer(ticket).data)

    @action(detail=True, methods=["post"])
    def ready(self, request, pk=None):
        ticket = services.mark_ticket_ready(self.get_object(), user=request.user)
        return Response(self.get_serializer(ticket).data)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        ticket = services.complete_ticket(self.get_object(), user=request.user)
        return Response(self.get_serializer(ticket).data)

    @action(detail=False, methods=["get"])
    def delayed(self, request):
        tickets = services.delayed_tickets()
        return Response(self.get_serializer(tickets, many=True).data)
