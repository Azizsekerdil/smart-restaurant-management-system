"""Menü yönetimi görünümleri."""

from __future__ import annotations

from decimal import Decimal

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.decorators import require_permission
from apps.catalog.forms import CategoryForm, ProductForm, RecipeItemFormSet
from apps.catalog.models import Allergen, Category, PriceHistory, Product, Recipe
from apps.core.models import AuditLog
from apps.core.services import record_audit
from apps.core.utils import money


@require_permission("menu.view")
def product_list(request):
    products = Product.objects.select_related("category", "station").prefetch_related(
        "allergens", "recipe__items__ingredient"
    )
    category_id = request.GET.get("category", "")
    search = request.GET.get("q", "").strip()
    availability = request.GET.get("availability", "")

    if category_id:
        products = products.filter(category_id=category_id)
    if search:
        products = products.filter(Q(name__icontains=search) | Q(sku__icontains=search))
    if availability == "unavailable":
        products = products.filter(is_available=False)
    elif availability == "available":
        products = products.filter(is_available=True, is_active=True)

    paginator = Paginator(products.order_by("category__sort_order", "sort_order", "name"), 30)
    page = paginator.get_page(request.GET.get("page", 1))

    return render(
        request,
        "catalog/product_list.html",
        {
            "page_title": "Menü Yönetimi",
            "page_obj": page,
            "categories": Category.objects.filter(is_active=True).order_by("sort_order"),
            "filters": {"category": category_id, "q": search, "availability": availability},
            "stats": {
                "total": Product.objects.count(),
                "active": Product.objects.filter(is_active=True).count(),
                "unavailable": Product.objects.filter(is_available=False).count(),
                "no_recipe": Product.objects.filter(recipe__isnull=True).count(),
            },
        },
    )


@require_permission("menu.view")
def product_detail(request, pk: int):
    product = get_object_or_404(
        Product.objects.select_related("category", "station").prefetch_related(
            "variants", "allergens", "modifier_groups__options", "recipe__items__ingredient"
        ),
        pk=pk,
    )
    return render(
        request,
        "catalog/product_detail.html",
        {
            "page_title": product.name,
            "product": product,
            "price_history": product.price_history.all()[:20],
        },
    )


@require_permission("menu.manage")
def product_create(request):
    if request.method == "POST":
        form = ProductForm(request.POST, request.FILES)
        if form.is_valid():
            product = form.save(commit=False)
            product.created_by = request.user
            product.save()
            form.save_m2m()
            record_audit(
                AuditLog.Action.CREATE,
                obj=product,
                description=f"Ürün eklendi: {product.name} ({product.price} ₺)",
                request=request,
            )
            messages.success(request, f"{product.name} menüye eklendi.")
            return redirect("catalog:product_detail", pk=product.pk)
    else:
        form = ProductForm()
    return render(
        request,
        "catalog/product_form.html",
        {"form": form, "page_title": "Yeni Ürün", "is_create": True},
    )


@require_permission("menu.manage")
def product_edit(request, pk: int):
    product = get_object_or_404(Product, pk=pk)
    old_price = product.price
    if request.method == "POST":
        form = ProductForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            saved = form.save()
            if old_price != saved.price:
                PriceHistory.objects.create(
                    product=saved,
                    old_price=old_price,
                    new_price=saved.price,
                    changed_by=request.user,
                    # Form alanı değil, serbest metin. SQLite `max_length`
                    # kısıtını zorlamadığı için uzunluk burada sınırlanır.
                    reason=(request.POST.get("price_reason") or "")[:300],
                )
                record_audit(
                    AuditLog.Action.UPDATE,
                    obj=saved,
                    description=f"{saved.name} fiyatı değişti: {old_price} -> {saved.price}",
                    severity=AuditLog.Severity.NOTICE,
                    request=request,
                )
            messages.success(request, f"{saved.name} güncellendi.")
            return redirect("catalog:product_detail", pk=saved.pk)
    else:
        form = ProductForm(instance=product)
    return render(
        request,
        "catalog/product_form.html",
        {"form": form, "product": product, "page_title": f"Düzenle: {product.name}"},
    )


@require_permission("menu.manage")
@require_POST
def product_toggle_availability(request, pk: int):
    product = get_object_or_404(Product, pk=pk)
    product.is_available = not product.is_available
    product.unavailable_reason = (
        "" if product.is_available else request.POST.get("reason", "Elle kapatıldı")
    )
    product.save(update_fields=["is_available", "unavailable_reason", "updated_at"])
    record_audit(
        AuditLog.Action.UPDATE,
        obj=product,
        description=(
            f"{product.name} " f"{'satışa açıldı' if product.is_available else 'satışa kapatıldı'}."
        ),
        request=request,
    )
    if request.headers.get("HX-Request"):
        return JsonResponse({"ok": True, "is_available": product.is_available})
    messages.success(request, f"{product.name} durumu güncellendi.")
    return redirect("catalog:product_list")


# ------------------------------------------------------------------
#  Reçete
# ------------------------------------------------------------------
@require_permission("recipe.view")
def recipe_detail(request, pk: int):
    product = get_object_or_404(Product, pk=pk)
    recipe = getattr(product, "recipe", None)
    return render(
        request,
        "catalog/recipe_detail.html",
        {
            "page_title": f"Reçete: {product.name}",
            "product": product,
            "recipe": recipe,
            "missing": recipe.missing_ingredients() if recipe else [],
        },
    )


@require_permission("recipe.manage")
def recipe_edit(request, pk: int):
    product = get_object_or_404(Product, pk=pk)
    recipe, _created = Recipe.objects.get_or_create(
        product=product, defaults={"created_by": request.user}
    )
    if request.method == "POST":
        formset = RecipeItemFormSet(request.POST, instance=recipe)
        recipe.yield_quantity = Decimal(request.POST.get("yield_quantity") or "1")
        recipe.labor_cost = Decimal(request.POST.get("labor_cost") or "0")
        recipe.overhead_cost = Decimal(request.POST.get("overhead_cost") or "0")
        recipe.preparation_notes = request.POST.get("preparation_notes", "")
        if formset.is_valid():
            recipe.save()
            formset.save()
            record_audit(
                AuditLog.Action.UPDATE,
                obj=recipe,
                description=(
                    f"{product.name} reçetesi güncellendi. "
                    f"Porsiyon maliyeti: {recipe.total_cost} ₺, marj: %{product.margin_percent}"
                ),
                request=request,
            )
            messages.success(
                request,
                f"Reçete kaydedildi. Porsiyon maliyeti: {money(recipe.total_cost)} ₺ "
                f"(marj %{product.margin_percent}).",
            )
            return redirect("catalog:recipe_detail", pk=product.pk)
    else:
        formset = RecipeItemFormSet(instance=recipe)

    return render(
        request,
        "catalog/recipe_form.html",
        {
            "page_title": f"Reçete Düzenle: {product.name}",
            "product": product,
            "recipe": recipe,
            "formset": formset,
        },
    )


# ------------------------------------------------------------------
#  Kategoriler
# ------------------------------------------------------------------
@require_permission("menu.view")
def category_list(request):
    categories = (
        Category.objects.annotate(product_count=Count("products"))
        .select_related("parent")
        .order_by("sort_order", "name")
    )
    return render(
        request,
        "catalog/category_list.html",
        {"page_title": "Kategoriler", "categories": categories},
    )


@require_permission("menu.manage")
def category_create(request):
    if request.method == "POST":
        form = CategoryForm(request.POST, request.FILES)
        if form.is_valid():
            category = form.save(commit=False)
            category.created_by = request.user
            category.save()
            messages.success(request, f"{category.name} kategorisi eklendi.")
            return redirect("catalog:category_list")
    else:
        form = CategoryForm()
    return render(
        request, "catalog/category_form.html", {"form": form, "page_title": "Yeni Kategori"}
    )


@require_permission("menu.manage")
def category_edit(request, pk: int):
    category = get_object_or_404(Category, pk=pk)
    if request.method == "POST":
        form = CategoryForm(request.POST, request.FILES, instance=category)
        if form.is_valid():
            form.save()
            messages.success(request, "Kategori güncellendi.")
            return redirect("catalog:category_list")
    else:
        form = CategoryForm(instance=category)
    return render(
        request,
        "catalog/category_form.html",
        {"form": form, "page_title": f"Düzenle: {category.name}", "category": category},
    )


# ------------------------------------------------------------------
#  QR menü (müşteriye açık)
# ------------------------------------------------------------------
def qr_menu(request, token):
    """Masadaki QR koddan açılan menü. Giriş gerektirmez."""
    from apps.floor.models import Table

    table = get_object_or_404(Table, qr_token=token, is_active=True)
    categories = (
        Category.objects.filter(is_active=True, products__is_active=True)
        .distinct()
        .prefetch_related("products__allergens", "products__variants")
        .order_by("sort_order")
    )
    return render(
        request,
        "catalog/qr_menu.html",
        {
            "table": table,
            "categories": categories,
            "allergens": Allergen.objects.all(),
            "page_title": "Menü",
        },
    )
