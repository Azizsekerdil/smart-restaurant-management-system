"""Stok REST API."""

from __future__ import annotations

from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.decorators import HasPermissionCode
from apps.inventory import services
from apps.inventory.models import Ingredient, StockMovement


class IngredientSerializer(serializers.ModelSerializer):
    unit_code = serializers.CharField(source="base_unit.code", read_only=True)
    total_on_hand = serializers.DecimalField(max_digits=16, decimal_places=3, read_only=True)
    average_cost = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    stock_value = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    stock_status = serializers.CharField(read_only=True)
    days_until_stockout = serializers.SerializerMethodField()

    class Meta:
        model = Ingredient
        fields = [
            "id",
            "name",
            "sku",
            "category",
            "base_unit",
            "unit_code",
            "critical_level",
            "reorder_quantity",
            "is_perishable",
            "shelf_life_days",
            "rotation",
            "total_on_hand",
            "average_cost",
            "stock_value",
            "stock_status",
            "days_until_stockout",
            "is_active",
        ]

    def get_days_until_stockout(self, obj) -> int | None:
        return obj.days_until_stockout()


class StockMovementSerializer(serializers.ModelSerializer):
    ingredient_name = serializers.CharField(source="ingredient.name", read_only=True)
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)
    type_display = serializers.CharField(source="get_movement_type_display", read_only=True)

    class Meta:
        model = StockMovement
        fields = [
            "id",
            "ingredient",
            "ingredient_name",
            "warehouse",
            "warehouse_name",
            "movement_type",
            "type_display",
            "quantity",
            "unit_cost",
            "balance_after",
            "reference_type",
            "reference_id",
            "note",
            "created_at",
        ]
        read_only_fields = fields


class IngredientViewSet(viewsets.ModelViewSet):
    serializer_class = IngredientSerializer
    permission_classes = [HasPermissionCode]
    required_permissions = ("inventory.manage",)
    required_read_permissions = ("inventory.view",)
    queryset = Ingredient.objects.select_related("base_unit", "category").order_by("name")
    filterset_fields = ["category", "is_active", "is_perishable"]
    search_fields = ["name", "sku"]

    @action(detail=False, methods=["get"], url_path="low-stock")
    def low_stock(self, request):
        return Response(self.get_serializer(services.low_stock_report(), many=True).data)

    @action(detail=False, methods=["get"])
    def expiring(self, request):
        days = int(request.query_params.get("days", 7))
        batches = services.expiring_batches(days)
        return Response(
            [
                {
                    "ingredient": b.ingredient.name,
                    "warehouse": b.warehouse.name,
                    "quantity": str(b.remaining_quantity),
                    "expiry_date": b.expiry_date,
                    "days_to_expiry": b.days_to_expiry,
                    "value": str(b.value),
                }
                for b in batches
            ]
        )


class StockMovementViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = StockMovementSerializer
    permission_classes = [HasPermissionCode]
    required_read_permissions = ("inventory.view",)
    required_permissions = ("inventory.view",)
    queryset = StockMovement.objects.select_related("ingredient", "warehouse").order_by(
        "-created_at"
    )
    filterset_fields = ["ingredient", "warehouse", "movement_type"]
