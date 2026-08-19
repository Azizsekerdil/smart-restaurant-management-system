"""Sipariş REST API."""

from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.decorators import HasPermissionCode
from apps.orders import services
from apps.orders.models import Order, OrderItem, Payment


class OrderItemSerializer(serializers.ModelSerializer):
    modifiers = serializers.SerializerMethodField()
    net_total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = OrderItem
        fields = [
            "id",
            "product",
            "product_name",
            "variant",
            "quantity",
            "unit_price",
            "discount_percent",
            "net_total",
            "status",
            "status_display",
            "note",
            "seat_number",
            "course",
            "modifiers",
            "sent_at",
            "ready_at",
        ]
        read_only_fields = ["product_name", "sent_at", "ready_at"]

    def get_modifiers(self, obj) -> list[dict]:
        return [
            {"id": m.pk, "name": m.modifier_name, "price_delta": str(m.price_delta)}
            for m in obj.modifiers.all()
        ]


class PaymentSerializer(serializers.ModelSerializer):
    method_display = serializers.CharField(source="get_method_display", read_only=True)

    class Meta:
        model = Payment
        fields = [
            "id",
            "method",
            "method_display",
            "amount",
            "change_amount",
            "reference",
            "paid_at",
        ]


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)
    table_name = serializers.CharField(source="table.name", read_only=True, default=None)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    balance_due = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "number",
            "order_type",
            "status",
            "status_display",
            "table",
            "table_name",
            "customer",
            "waiter",
            "guest_count",
            "subtotal",
            "order_discount_total",
            "service_charge",
            "tax_total",
            "grand_total",
            "paid_total",
            "balance_due",
            "note",
            "opened_at",
            "closed_at",
            "items",
            "payments",
        ]
        read_only_fields = [
            "number",
            "subtotal",
            "order_discount_total",
            "service_charge",
            "tax_total",
            "grand_total",
            "paid_total",
            "closed_at",
        ]


class OrderViewSet(viewsets.ModelViewSet):
    """Sipariş API'si.

    Durum değiştiren işlemler (mutfağa gönder, ödeme, iptal) ayrı
    eylemlerdir; böylece iş kuralları atlanmaz.
    """

    serializer_class = OrderSerializer
    permission_classes = [HasPermissionCode]
    required_permissions = ("pos.use", "order.manage")
    required_read_permissions = ("order.view", "pos.use")
    filterset_fields = ["status", "order_type", "table", "customer"]
    search_fields = ["number", "note"]
    ordering_fields = ["opened_at", "grand_total"]

    def get_queryset(self):
        return (
            Order.objects.select_related("table", "customer", "waiter")
            .prefetch_related("items__modifiers", "payments")
            .order_by("-opened_at")
        )

    def perform_create(self, serializer):
        serializer.save(waiter=self.request.user, created_by=self.request.user)

    @action(detail=True, methods=["post"], url_path="send-to-kitchen")
    def send_to_kitchen(self, request, pk=None):
        order = self.get_object()
        tickets = services.send_to_kitchen(order, user=request.user)
        return Response(
            {"tickets": [t.number for t in tickets], "status": order.status},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"])
    def payment(self, request, pk=None):
        order = self.get_object()
        try:
            payment = services.take_payment(
                order,
                method=request.data.get("method", Payment.Method.CASH),
                amount=Decimal(str(request.data.get("amount", "0"))),
                received=(
                    Decimal(str(request.data["received"])) if request.data.get("received") else None
                ),
                reference=request.data.get("reference", ""),
                user=request.user,
            )
        except ValidationError as exc:
            return Response({"detail": exc.messages[0]}, status=status.HTTP_400_BAD_REQUEST)
        return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        if not request.user.has_perm_code("pos.void"):
            return Response({"detail": "İptal yetkiniz yok."}, status=status.HTTP_403_FORBIDDEN)
        order = self.get_object()
        reason = request.data.get("reason", "")
        if not reason:
            return Response(
                {"detail": "İptal gerekçesi zorunludur."}, status=status.HTTP_400_BAD_REQUEST
            )
        try:
            services.cancel_order(order, reason=reason, user=request.user)
        except ValidationError as exc:
            return Response({"detail": exc.messages[0]}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(order).data)

    @action(detail=False, methods=["get"])
    def open(self, request):
        """Açık adisyonlar."""
        qs = self.get_queryset().exclude(status__in=[Order.Status.PAID, Order.Status.CANCELLED])
        page = self.paginate_queryset(qs)
        serializer = self.get_serializer(page or qs, many=True)
        return self.get_paginated_response(serializer.data) if page else Response(serializer.data)
