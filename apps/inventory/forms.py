"""Stok ve satın alma formları."""

from __future__ import annotations

from django import forms

from apps.inventory.models import Ingredient, PurchaseOrder, Supplier, Warehouse

_TEXT = {"class": "form-control"}
_SELECT = {"class": "form-select"}
_CHECK = {"class": "form-check-input"}


class IngredientForm(forms.ModelForm):
    class Meta:
        model = Ingredient
        fields = [
            "name",
            "sku",
            "category",
            "base_unit",
            "purchase_unit",
            "critical_level",
            "reorder_quantity",
            "is_perishable",
            "shelf_life_days",
            "rotation",
            "default_supplier",
            "is_active",
            "notes",
        ]
        widgets = {
            "name": forms.TextInput(attrs=_TEXT),
            "sku": forms.TextInput(attrs=_TEXT),
            "category": forms.Select(attrs=_SELECT),
            "base_unit": forms.Select(attrs=_SELECT),
            "purchase_unit": forms.Select(attrs=_SELECT),
            "critical_level": forms.NumberInput(attrs={**_TEXT, "step": "0.001"}),
            "reorder_quantity": forms.NumberInput(attrs={**_TEXT, "step": "0.001"}),
            "is_perishable": forms.CheckboxInput(attrs=_CHECK),
            "shelf_life_days": forms.NumberInput(attrs=_TEXT),
            "rotation": forms.Select(attrs=_SELECT),
            "default_supplier": forms.Select(attrs=_SELECT),
            "is_active": forms.CheckboxInput(attrs=_CHECK),
            "notes": forms.Textarea(attrs={**_TEXT, "rows": 2}),
        }

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("is_perishable") and not cleaned.get("shelf_life_days"):
            self.add_error(
                "shelf_life_days", "Bozulabilir malzemeler için raf ömrü belirtilmelidir."
            )
        return cleaned


class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = [
            "name",
            "contact_name",
            "phone",
            "email",
            "address",
            "tax_number",
            "payment_terms_days",
            "lead_time_days",
            "rating",
            "is_active",
            "notes",
        ]
        widgets = {
            "name": forms.TextInput(attrs=_TEXT),
            "contact_name": forms.TextInput(attrs=_TEXT),
            "phone": forms.TextInput(attrs=_TEXT),
            "email": forms.EmailInput(attrs=_TEXT),
            "address": forms.Textarea(attrs={**_TEXT, "rows": 2}),
            "tax_number": forms.TextInput(attrs=_TEXT),
            "payment_terms_days": forms.NumberInput(attrs=_TEXT),
            "lead_time_days": forms.NumberInput(attrs=_TEXT),
            "rating": forms.NumberInput(attrs={**_TEXT, "min": "1", "max": "5"}),
            "is_active": forms.CheckboxInput(attrs=_CHECK),
            "notes": forms.Textarea(attrs={**_TEXT, "rows": 2}),
        }


class WarehouseForm(forms.ModelForm):
    class Meta:
        model = Warehouse
        fields = ["name", "code", "location", "is_default", "is_cold_storage", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs=_TEXT),
            "code": forms.TextInput(attrs=_TEXT),
            "location": forms.TextInput(attrs=_TEXT),
            "is_default": forms.CheckboxInput(attrs=_CHECK),
            "is_cold_storage": forms.CheckboxInput(attrs=_CHECK),
            "is_active": forms.CheckboxInput(attrs=_CHECK),
        }


class PurchaseOrderForm(forms.ModelForm):
    class Meta:
        model = PurchaseOrder
        fields = ["supplier", "warehouse", "expected_date", "notes"]
        widgets = {
            "supplier": forms.Select(attrs=_SELECT),
            "warehouse": forms.Select(attrs=_SELECT),
            "expected_date": forms.DateInput(attrs={**_TEXT, "type": "date"}),
            "notes": forms.Textarea(attrs={**_TEXT, "rows": 2}),
        }
