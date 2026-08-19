"""Menü REST API."""

from __future__ import annotations

from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.decorators import HasPermissionCode
from apps.catalog.models import Category, Modifier, ModifierGroup, Product, ProductVariant


class VariantSerializer(serializers.ModelSerializer):
    price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = ProductVariant
        fields = ["id", "name", "price_delta", "price", "is_default", "is_active"]


class ModifierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Modifier
        fields = ["id", "name", "price_delta", "is_active"]


class ModifierGroupSerializer(serializers.ModelSerializer):
    options = ModifierSerializer(many=True, read_only=True)

    class Meta:
        model = ModifierGroup
        fields = ["id", "name", "min_select", "max_select", "is_required", "options"]


class ProductSerializer(serializers.ModelSerializer):
    variants = VariantSerializer(many=True, read_only=True)
    modifier_groups = ModifierGroupSerializer(many=True, read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)
    allergen_names = serializers.CharField(read_only=True)
    margin_percent = serializers.DecimalField(max_digits=6, decimal_places=2, read_only=True)
    recipe_cost = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
            "sku",
            "category",
            "category_name",
            "kind",
            "description",
            "image",
            "price",
            "tax_rate",
            "preparation_minutes",
            "is_active",
            "is_available",
            "unavailable_reason",
            "allergen_names",
            "calories",
            "recipe_cost",
            "margin_percent",
            "variants",
            "modifier_groups",
        ]


class CategorySerializer(serializers.ModelSerializer):
    product_count = serializers.IntegerField(source="products.count", read_only=True)

    class Meta:
        model = Category
        fields = [
            "id",
            "name",
            "slug",
            "parent",
            "color",
            "icon",
            "sort_order",
            "is_active",
            "product_count",
        ]


class ProductViewSet(viewsets.ModelViewSet):
    serializer_class = ProductSerializer
    permission_classes = [HasPermissionCode]
    required_permissions = ("menu.manage",)
    required_read_permissions = ("menu.view",)
    filterset_fields = ["category", "kind", "is_active", "is_available"]
    search_fields = ["name", "sku", "barcode", "description"]
    ordering_fields = ["name", "price", "sort_order"]

    def get_queryset(self):
        return (
            Product.objects.select_related("category", "station")
            .prefetch_related("variants", "modifier_groups__options", "allergens")
            .order_by("category__sort_order", "sort_order")
        )

    @action(detail=False, methods=["get"])
    def available(self, request):
        """POS için: şu anda satılabilir ürünler."""
        products = [p for p in self.get_queryset().filter(is_active=True) if p.available_now()]
        return Response(self.get_serializer(products, many=True).data)


class CategoryViewSet(viewsets.ModelViewSet):
    serializer_class = CategorySerializer
    permission_classes = [HasPermissionCode]
    required_permissions = ("menu.manage",)
    required_read_permissions = ("menu.view",)
    queryset = Category.objects.all().order_by("sort_order")
    filterset_fields = ["is_active", "parent"]
    search_fields = ["name"]
