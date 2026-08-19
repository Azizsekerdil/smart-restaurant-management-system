"""Müşteri REST API. Kişisel veriler yetkiye göre maskelenir."""

from __future__ import annotations

from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.decorators import HasPermissionCode
from apps.crm import services
from apps.crm.models import Customer


class CustomerSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    segment_display = serializers.CharField(source="get_segment_display", read_only=True)
    tier_display = serializers.CharField(source="get_tier_display", read_only=True)
    phone = serializers.SerializerMethodField()
    email = serializers.SerializerMethodField()
    churn_risk = serializers.CharField(read_only=True)

    class Meta:
        model = Customer
        fields = [
            "id",
            "code",
            "first_name",
            "last_name",
            "full_name",
            "phone",
            "email",
            "company_name",
            "segment",
            "segment_display",
            "tier",
            "tier_display",
            "loyalty_points",
            "lifetime_value",
            "visit_count",
            "last_visit_at",
            "allergy_notes",
            "churn_risk",
            "is_active",
        ]
        read_only_fields = ["code", "loyalty_points", "lifetime_value", "visit_count"]

    # Alerji notu özel nitelikli (sağlık) veri adayıdır. Yönetim API'sinde
    # içerik `customer.pii` iznine bağlıdır; servis güvenliği için kaydın
    # VARLIĞI korunur (boş olmayan not maskeli yer tutucuya dönüşür).
    # Servis akışları (adisyon paneli, rezervasyon, POS araması) bilinçli
    # olarak kapsam dışıdır: garsonun alerjiyi görmesi gıda güvenliğidir.
    MASKED_ALLERGY = "[alerji kaydı var — görüntülemek için customer.pii izni gerekli]"

    def _can_see_pii(self) -> bool:
        request = self.context.get("request")
        return bool(request and request.user.has_perm_code("customer.pii"))

    def get_phone(self, obj) -> str:
        return obj.phone if self._can_see_pii() else obj.masked_phone

    def get_email(self, obj) -> str:
        return obj.email if self._can_see_pii() else obj.masked_email

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not self._can_see_pii() and instance.allergy_notes:
            data["allergy_notes"] = self.MASKED_ALLERGY
        return data


class CustomerViewSet(viewsets.ModelViewSet):
    serializer_class = CustomerSerializer
    permission_classes = [HasPermissionCode]
    required_permissions = ("customer.manage",)
    required_read_permissions = ("customer.view",)
    queryset = Customer.objects.filter(is_active=True).order_by("-last_visit_at")
    filterset_fields = ["segment", "tier", "is_active"]
    search_fields = ["first_name", "last_name", "phone", "code", "company_name"]
    ordering_fields = ["lifetime_value", "visit_count", "last_visit_at"]

    @action(detail=False, methods=["get"], url_path="churn-risk")
    def churn_risk(self, request):
        return Response(self.get_serializer(services.churn_risk_customers(50), many=True).data)

    @action(detail=False, methods=["get"])
    def statistics(self, request):
        stats = services.customer_statistics()
        stats["total_lifetime_value"] = str(stats["total_lifetime_value"])
        return Response(stats)
