"""Salon ve rezervasyon REST API."""

from __future__ import annotations

from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.decorators import HasPermissionCode
from apps.floor.models import Reservation, Table


class TableSerializer(serializers.ModelSerializer):
    area_name = serializers.CharField(source="area.name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    occupied_minutes = serializers.IntegerField(read_only=True)
    active_order_number = serializers.SerializerMethodField()

    class Meta:
        model = Table
        fields = [
            "id",
            "name",
            "area",
            "area_name",
            "capacity",
            "status",
            "status_display",
            "shape",
            "pos_x",
            "pos_y",
            "assigned_waiter",
            "occupied_minutes",
            "active_order_number",
            "is_active",
        ]

    def get_active_order_number(self, obj) -> str | None:
        order = obj.active_order
        return order.number if order else None


class ReservationSerializer(serializers.ModelSerializer):
    """Rezervasyon kaydı.

    Misafirin telefonu kişisel veri, alerji notu ise sağlık verisidir
    (KVKK m.6 / GDPR m.9). ``reservation.view`` izni salon personelinin
    tamamında bulunduğu için bu iki alanın **içeriği** ``customer.pii``
    iznine bağlanır: izin yoksa telefon maskelenir ve alerji metni yerine
    yalnızca "kayıt var" bilgisi döner. Kaydın varlığı gizlenmez, çünkü
    servis güvenliği için uyarı görünmelidir. Aynı kural CRM seri hâline
    getiricisindedir (``apps/crm/api.py``).

    Maskeleme ``to_representation`` içinde yapılır; alanlar yazılabilir
    kalır, böylece rezervasyon oluşturma/düzenleme bozulmaz.
    """

    status_display = serializers.CharField(source="get_status_display", read_only=True)
    table_names = serializers.SerializerMethodField()

    MASKED_ALLERGY = "[alerji kaydı var — görüntülemek için customer.pii izni gerekli]"

    def _can_see_pii(self) -> bool:
        request = self.context.get("request")
        return bool(request and request.user.has_perm_code("customer.pii"))

    @staticmethod
    def _mask_phone(phone: str) -> str:
        if not phone:
            return ""
        if len(phone) < 6:
            return "***"
        return f"{phone[:4]}***{phone[-2:]}"

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["has_allergy_note"] = bool(instance.allergy_notes)
        if not self._can_see_pii():
            data["guest_phone"] = self._mask_phone(instance.guest_phone)
            if instance.allergy_notes:
                data["allergy_notes"] = self.MASKED_ALLERGY
        return data

    class Meta:
        model = Reservation
        fields = [
            "id",
            "code",
            "guest_name",
            "guest_phone",
            "party_size",
            "reserved_at",
            "duration_minutes",
            "tables",
            "table_names",
            "area",
            "status",
            "status_display",
            "source",
            "special_requests",
            "allergy_notes",
        ]
        read_only_fields = ["code"]

    def get_table_names(self, obj) -> list[str]:
        return [t.name for t in obj.tables.all()]


class TableViewSet(viewsets.ModelViewSet):
    serializer_class = TableSerializer
    permission_classes = [HasPermissionCode]
    required_permissions = ("table.manage",)
    required_read_permissions = ("table.view",)
    queryset = Table.objects.select_related("area").order_by("area__sort_order", "name")
    filterset_fields = ["area", "status", "is_active"]
    search_fields = ["name"]

    @action(detail=False, methods=["get"])
    def map(self, request):
        """Masa planı için özet durum."""
        tables = self.get_queryset().filter(is_active=True)
        return Response(
            {
                "tables": self.get_serializer(tables, many=True).data,
                "summary": {
                    "total": tables.count(),
                    "occupied": tables.filter(status=Table.Status.OCCUPIED).count(),
                    "free": tables.filter(status=Table.Status.FREE).count(),
                },
            }
        )


class ReservationViewSet(viewsets.ModelViewSet):
    serializer_class = ReservationSerializer
    permission_classes = [HasPermissionCode]
    required_permissions = ("reservation.manage",)
    required_read_permissions = ("reservation.view",)
    queryset = Reservation.objects.prefetch_related("tables").order_by("reserved_at")
    filterset_fields = ["status", "source", "area"]
    search_fields = ["code", "guest_name", "guest_phone"]
    ordering_fields = ["reserved_at", "party_size"]

    @action(detail=False, methods=["get"])
    def today(self, request):
        from django.utils import timezone

        qs = self.get_queryset().filter(reserved_at__date=timezone.localdate())
        return Response(self.get_serializer(qs, many=True).data)
