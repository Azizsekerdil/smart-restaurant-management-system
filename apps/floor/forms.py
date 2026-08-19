"""Salon ve rezervasyon formları."""

from __future__ import annotations

from django import forms
from django.utils import timezone

from apps.floor.models import Area, Reservation, Table

_TEXT = {"class": "form-control"}
_SELECT = {"class": "form-select"}
_CHECK = {"class": "form-check-input"}


class AreaForm(forms.ModelForm):
    class Meta:
        model = Area
        fields = [
            "name",
            "description",
            "is_outdoor",
            "is_smoking",
            "service_charge_rate",
            "sort_order",
            "is_active",
        ]
        widgets = {
            "name": forms.TextInput(attrs=_TEXT),
            "description": forms.TextInput(attrs=_TEXT),
            "is_outdoor": forms.CheckboxInput(attrs=_CHECK),
            "is_smoking": forms.CheckboxInput(attrs=_CHECK),
            "service_charge_rate": forms.NumberInput(attrs={**_TEXT, "step": "0.01"}),
            "sort_order": forms.NumberInput(attrs=_TEXT),
            "is_active": forms.CheckboxInput(attrs=_CHECK),
        }


class TableForm(forms.ModelForm):
    class Meta:
        model = Table
        fields = [
            "area",
            "name",
            "capacity",
            "shape",
            "pos_x",
            "pos_y",
            "assigned_waiter",
            "notes",
            "is_active",
        ]
        widgets = {
            "area": forms.Select(attrs=_SELECT),
            "name": forms.TextInput(attrs=_TEXT),
            "capacity": forms.NumberInput(attrs={**_TEXT, "min": "1", "max": "50"}),
            "shape": forms.Select(attrs=_SELECT),
            "pos_x": forms.NumberInput(attrs={**_TEXT, "step": "0.1", "min": "0", "max": "100"}),
            "pos_y": forms.NumberInput(attrs={**_TEXT, "step": "0.1", "min": "0", "max": "100"}),
            "assigned_waiter": forms.Select(attrs=_SELECT),
            "notes": forms.TextInput(attrs=_TEXT),
            "is_active": forms.CheckboxInput(attrs=_CHECK),
        }


class ReservationForm(forms.ModelForm):
    class Meta:
        model = Reservation
        fields = [
            "guest_name",
            "guest_phone",
            "guest_email",
            "customer",
            "party_size",
            "reserved_at",
            "duration_minutes",
            "area",
            "tables",
            "status",
            "source",
            "special_requests",
            "allergy_notes",
            "occasion",
        ]
        widgets = {
            "guest_name": forms.TextInput(attrs=_TEXT),
            "guest_phone": forms.TextInput(attrs={**_TEXT, "inputmode": "tel"}),
            "guest_email": forms.EmailInput(attrs=_TEXT),
            "customer": forms.Select(attrs=_SELECT),
            "party_size": forms.NumberInput(attrs={**_TEXT, "min": "1"}),
            "reserved_at": forms.DateTimeInput(
                attrs={**_TEXT, "type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
            "duration_minutes": forms.NumberInput(attrs={**_TEXT, "min": "15", "step": "15"}),
            "area": forms.Select(attrs=_SELECT),
            "tables": forms.SelectMultiple(attrs={**_SELECT, "size": "8"}),
            "status": forms.Select(attrs=_SELECT),
            "source": forms.Select(attrs=_SELECT),
            "special_requests": forms.Textarea(attrs={**_TEXT, "rows": 2}),
            "allergy_notes": forms.TextInput(attrs=_TEXT),
            "occasion": forms.TextInput(attrs=_TEXT),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["reserved_at"].input_formats = [
            "%Y-%m-%dT%H:%M",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
        ]
        self.fields["tables"].queryset = Table.objects.filter(is_active=True).select_related("area")

    def clean_reserved_at(self):
        value = self.cleaned_data["reserved_at"]
        if value < timezone.now() - timezone.timedelta(hours=1):
            raise forms.ValidationError("Geçmiş bir zamana rezervasyon oluşturulamaz.")
        return value

    def clean(self):
        cleaned = super().clean()
        tables = cleaned.get("tables")
        party_size = cleaned.get("party_size") or 0
        if tables:
            capacity = sum(t.capacity for t in tables)
            if capacity < party_size:
                raise forms.ValidationError(
                    f"Seçilen masaların toplam kapasitesi ({capacity}) "
                    f"kişi sayısından ({party_size}) az."
                )
        return cleaned
