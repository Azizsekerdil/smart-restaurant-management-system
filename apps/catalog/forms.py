"""Menü formları."""

from __future__ import annotations

from django import forms
from django.forms import inlineformset_factory

from apps.catalog.models import Category, Product, Recipe, RecipeItem
from apps.core.utils import validate_upload

_TEXT = {"class": "form-control"}
_SELECT = {"class": "form-select"}
_CHECK = {"class": "form-check-input"}


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            "name",
            "sku",
            "barcode",
            "category",
            "kind",
            "description",
            "image",
            "price",
            "tax_rate",
            "preparation_minutes",
            "station",
            "allergens",
            "calories",
            "protein_g",
            "carbs_g",
            "fat_g",
            "is_active",
            "is_available",
            "auto_disable_on_stockout",
            "is_featured",
            "sort_order",
            "color",
        ]
        widgets = {
            "name": forms.TextInput(attrs=_TEXT),
            "sku": forms.TextInput(attrs=_TEXT),
            "barcode": forms.TextInput(attrs=_TEXT),
            "category": forms.Select(attrs=_SELECT),
            "kind": forms.Select(attrs=_SELECT),
            "description": forms.Textarea(attrs={**_TEXT, "rows": 3}),
            "image": forms.ClearableFileInput(attrs={**_TEXT, "accept": "image/*"}),
            "price": forms.NumberInput(attrs={**_TEXT, "step": "0.01", "min": "0"}),
            "tax_rate": forms.NumberInput(attrs={**_TEXT, "step": "0.01", "min": "0"}),
            "preparation_minutes": forms.NumberInput(attrs={**_TEXT, "min": "0"}),
            "station": forms.Select(attrs=_SELECT),
            "allergens": forms.CheckboxSelectMultiple,
            "calories": forms.NumberInput(attrs=_TEXT),
            "protein_g": forms.NumberInput(attrs={**_TEXT, "step": "0.1"}),
            "carbs_g": forms.NumberInput(attrs={**_TEXT, "step": "0.1"}),
            "fat_g": forms.NumberInput(attrs={**_TEXT, "step": "0.1"}),
            "is_active": forms.CheckboxInput(attrs=_CHECK),
            "is_available": forms.CheckboxInput(attrs=_CHECK),
            "auto_disable_on_stockout": forms.CheckboxInput(attrs=_CHECK),
            "is_featured": forms.CheckboxInput(attrs=_CHECK),
            "sort_order": forms.NumberInput(attrs=_TEXT),
            "color": forms.TextInput(attrs={**_TEXT, "type": "color"}),
        }

    def clean_image(self):
        image = self.cleaned_data.get("image")
        if image and hasattr(image, "size"):
            validate_upload(image)
        return image


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = [
            "name",
            "parent",
            "description",
            "color",
            "icon",
            "image",
            "sort_order",
            "is_active",
        ]
        widgets = {
            "name": forms.TextInput(attrs=_TEXT),
            "parent": forms.Select(attrs=_SELECT),
            "description": forms.TextInput(attrs=_TEXT),
            "color": forms.TextInput(attrs={**_TEXT, "type": "color"}),
            "icon": forms.TextInput(attrs=_TEXT),
            "image": forms.ClearableFileInput(attrs={**_TEXT, "accept": "image/*"}),
            "sort_order": forms.NumberInput(attrs=_TEXT),
            "is_active": forms.CheckboxInput(attrs=_CHECK),
        }

    def clean(self):
        cleaned = super().clean()
        parent = cleaned.get("parent")
        if parent and self.instance.pk and parent.pk == self.instance.pk:
            raise forms.ValidationError("Kategori kendisinin alt kategorisi olamaz.")
        return cleaned


class RecipeItemForm(forms.ModelForm):
    class Meta:
        model = RecipeItem
        fields = ["ingredient", "quantity", "unit", "waste_percent", "is_optional", "note"]
        widgets = {
            "ingredient": forms.Select(attrs={**_SELECT, "data-role": "ingredient"}),
            "quantity": forms.NumberInput(attrs={**_TEXT, "step": "0.001", "min": "0"}),
            "unit": forms.Select(attrs=_SELECT),
            "waste_percent": forms.NumberInput(attrs={**_TEXT, "step": "0.01", "min": "0"}),
            "is_optional": forms.CheckboxInput(attrs=_CHECK),
            "note": forms.TextInput(attrs=_TEXT),
        }


RecipeItemFormSet = inlineformset_factory(
    Recipe, RecipeItem, form=RecipeItemForm, extra=3, can_delete=True
)
