"""Stok, tedarikçi ve satın alma görünümleri."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.decorators import require_permission
from apps.core.models import AuditLog
from apps.core.services import record_audit
from apps.core.utils import money
from apps.inventory import services
from apps.inventory.forms import IngredientForm, PurchaseOrderForm, SupplierForm
from apps.inventory.models import (
    Ingredient,
    PurchaseOrder,
    PurchaseOrderLine,
    StockCount,
    StockCountLine,
    StockMovement,
    Supplier,
    UnitOfMeasure,
    Warehouse,
    WasteRecord,
)


def _dec(value, default="0"):
    try:
        return Decimal(str(value or default))
    except (InvalidOperation, ValueError):
        return Decimal(default)


@require_permission("inventory.view")
def ingredient_list(request):
    ingredients = Ingredient.objects.filter(is_active=True).select_related(
        "base_unit", "category", "default_supplier"
    )
    search = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    category = request.GET.get("category", "")

    if search:
        ingredients = ingredients.filter(Q(name__icontains=search) | Q(sku__icontains=search))
    if category:
        ingredients = ingredients.filter(category_id=category)

    rows = list(ingredients.order_by("name"))
    if status:
        rows = [i for i in rows if i.stock_status == status]

    paginator = Paginator(rows, 40)
    page = paginator.get_page(request.GET.get("page", 1))

    total_value = sum((i.stock_value for i in rows), Decimal("0.00"))
    critical = [i for i in rows if i.stock_status in {"critical", "out"}]

    from apps.inventory.models import IngredientCategory

    return render(
        request,
        "inventory/ingredient_list.html",
        {
            "page_title": "Stok Yönetimi",
            "page_obj": page,
            "categories": IngredientCategory.objects.all(),
            "filters": {"q": search, "status": status, "category": category},
            "summary": {
                "total_items": len(rows),
                "total_value": money(total_value),
                "critical_count": len(critical),
                "expiring": services.expiring_batches(7).count(),
            },
        },
    )


@require_permission("inventory.view")
def ingredient_detail(request, pk: int):
    ingredient = get_object_or_404(
        Ingredient.objects.select_related("base_unit", "category"), pk=pk
    )
    movements = ingredient.movements.select_related("warehouse").order_by("-created_at")[:60]
    return render(
        request,
        "inventory/ingredient_detail.html",
        {
            "page_title": ingredient.name,
            "ingredient": ingredient,
            "movements": movements,
            "batches": ingredient.batches.filter(remaining_quantity__gt=0).select_related(
                "warehouse"
            ),
            "stock_items": ingredient.stock_items.select_related("warehouse"),
            "days_left": ingredient.days_until_stockout(),
            "daily_usage": ingredient.daily_consumption_average(),
            "used_in": ingredient.recipe_items.select_related("recipe__product", "unit")[:30],
            "units": UnitOfMeasure.objects.all(),
            "warehouses": Warehouse.objects.filter(is_active=True),
        },
    )


@require_permission("inventory.manage")
def ingredient_create(request):
    if request.method == "POST":
        form = IngredientForm(request.POST)
        if form.is_valid():
            ingredient = form.save(commit=False)
            ingredient.created_by = request.user
            ingredient.save()
            messages.success(request, f"{ingredient.name} eklendi.")
            return redirect("inventory:ingredient_detail", pk=ingredient.pk)
    else:
        form = IngredientForm()
    return render(
        request, "inventory/ingredient_form.html", {"form": form, "page_title": "Yeni Malzeme"}
    )


@require_permission("inventory.manage")
def ingredient_edit(request, pk: int):
    ingredient = get_object_or_404(Ingredient, pk=pk)
    if request.method == "POST":
        form = IngredientForm(request.POST, instance=ingredient)
        if form.is_valid():
            form.save()
            messages.success(request, "Malzeme güncellendi.")
            return redirect("inventory:ingredient_detail", pk=pk)
    else:
        form = IngredientForm(instance=ingredient)
    return render(
        request,
        "inventory/ingredient_form.html",
        {"form": form, "ingredient": ingredient, "page_title": f"Düzenle: {ingredient.name}"},
    )


@require_permission("inventory.manage")
@require_POST
def stock_receive(request, pk: int):
    ingredient = get_object_or_404(Ingredient, pk=pk)
    warehouse = get_object_or_404(Warehouse, pk=request.POST.get("warehouse_id"))
    unit = (
        UnitOfMeasure.objects.filter(pk=request.POST.get("unit_id")).first() or ingredient.base_unit
    )
    raw_qty = _dec(request.POST.get("quantity"))
    base_qty = unit.to_base(raw_qty)
    unit_price = _dec(request.POST.get("unit_cost"))
    base_cost = unit_price / unit.factor_to_base if unit.factor_to_base else unit_price

    if base_qty <= 0:
        messages.error(request, "Miktar sıfırdan büyük olmalıdır.")
        return redirect("inventory:ingredient_detail", pk=pk)

    services.receive_stock(
        ingredient,
        warehouse,
        base_qty,
        base_cost,
        expiry_date=request.POST.get("expiry_date") or None,
        lot_code=request.POST.get("lot_code", ""),
        note=request.POST.get("note", ""),
        user=request.user,
    )
    record_audit(
        AuditLog.Action.CREATE,
        obj=ingredient,
        description=f"Stok girişi: {ingredient.name} +{base_qty} {ingredient.base_unit.code}",
        request=request,
    )
    messages.success(request, f"{ingredient.name} stoğuna {raw_qty} {unit.code} eklendi.")
    return redirect("inventory:ingredient_detail", pk=pk)


@require_permission("inventory.waste")
@require_POST
def waste_create(request):
    ingredient = get_object_or_404(Ingredient, pk=request.POST.get("ingredient_id"))
    warehouse = get_object_or_404(Warehouse, pk=request.POST.get("warehouse_id"))
    unit = (
        UnitOfMeasure.objects.filter(pk=request.POST.get("unit_id")).first() or ingredient.base_unit
    )
    quantity = unit.to_base(_dec(request.POST.get("quantity")))

    waste = services.record_waste(
        ingredient,
        warehouse,
        quantity,
        request.POST.get("reason", WasteRecord.Reason.OTHER),
        note=request.POST.get("note", ""),
        user=request.user,
    )
    messages.success(
        request, f"Fire kaydedildi: {ingredient.name} ({money(waste.cost_value)} ₺ maliyet)."
    )
    return redirect(request.POST.get("next") or "inventory:waste_list")


@require_permission("inventory.view")
def waste_list(request):
    records = WasteRecord.objects.select_related("ingredient", "warehouse", "reported_by")
    date_from = request.GET.get("from", "")
    reason = request.GET.get("reason", "")
    if date_from:
        records = records.filter(occurred_at__date__gte=date_from)
    if reason:
        records = records.filter(reason=reason)

    totals = records.aggregate(total_cost=Sum("cost_value"))
    by_reason = records.values("reason").annotate(total=Sum("cost_value")).order_by("-total")

    return render(
        request,
        "inventory/waste_list.html",
        {
            "page_title": "Fire ve İsraf",
            "records": records.order_by("-occurred_at")[:200],
            "reasons": WasteRecord.Reason.choices,
            "totals": totals,
            "by_reason": by_reason,
            "ingredients": Ingredient.objects.filter(is_active=True).order_by("name"),
            "warehouses": Warehouse.objects.filter(is_active=True),
            "filters": {"from": date_from, "reason": reason},
        },
    )


@require_permission("inventory.view")
def movement_list(request):
    movements = StockMovement.objects.select_related("ingredient", "warehouse", "created_by")
    ingredient_id = request.GET.get("ingredient", "")
    move_type = request.GET.get("type", "")
    if ingredient_id:
        movements = movements.filter(ingredient_id=ingredient_id)
    if move_type:
        movements = movements.filter(movement_type=move_type)

    paginator = Paginator(movements.order_by("-created_at")[:3000], 50)
    page = paginator.get_page(request.GET.get("page", 1))
    return render(
        request,
        "inventory/movement_list.html",
        {
            "page_title": "Stok Hareketleri",
            "page_obj": page,
            "types": StockMovement.Type.choices,
            "ingredients": Ingredient.objects.filter(is_active=True).order_by("name"),
            "filters": {"ingredient": ingredient_id, "type": move_type},
        },
    )


# ------------------------------------------------------------------
#  Sayım
# ------------------------------------------------------------------
@require_permission("inventory.count")
def count_list(request):
    counts = StockCount.objects.select_related("warehouse").order_by("-counted_at")[:50]
    return render(
        request,
        "inventory/count_list.html",
        {
            "page_title": "Stok Sayımları",
            "counts": counts,
            "warehouses": Warehouse.objects.filter(is_active=True),
        },
    )


@require_permission("inventory.count")
@require_POST
def count_create(request):
    warehouse = get_object_or_404(Warehouse, pk=request.POST.get("warehouse_id"))
    count = StockCount.objects.create(warehouse=warehouse, created_by=request.user)
    for ingredient in Ingredient.objects.filter(is_active=True):
        StockCountLine.objects.create(
            count=count,
            ingredient=ingredient,
            expected_quantity=ingredient.on_hand_at(warehouse),
            counted_quantity=ingredient.on_hand_at(warehouse),
        )
    messages.success(request, f"Sayım oluşturuldu: {count.number}")
    return redirect("inventory:count_detail", pk=count.pk)


@require_permission("inventory.count")
def count_detail(request, pk: int):
    count = get_object_or_404(StockCount, pk=pk)
    lines = count.lines.select_related("ingredient__base_unit").order_by("ingredient__name")
    return render(
        request,
        "inventory/count_detail.html",
        {"page_title": f"Sayım {count.number}", "count": count, "lines": lines},
    )


@require_permission("inventory.count")
@require_POST
def count_save(request, pk: int):
    count = get_object_or_404(StockCount, pk=pk)
    if count.status != StockCount.Status.OPEN:
        messages.error(request, "Tamamlanmış sayım değiştirilemez.")
        return redirect("inventory:count_detail", pk=pk)

    for line in count.lines.all():
        field = f"counted_{line.pk}"
        if field in request.POST:
            line.counted_quantity = _dec(request.POST[field])
            line.note = request.POST.get(f"note_{line.pk}", "")[:200]
            line.save(update_fields=["counted_quantity", "note"])
    messages.success(request, "Sayım kaydedildi.")
    return redirect("inventory:count_detail", pk=pk)


@require_permission("inventory.count")
@require_POST
def count_apply(request, pk: int):
    count = get_object_or_404(StockCount, pk=pk)
    if count.status != StockCount.Status.OPEN:
        messages.error(request, "Bu sayım zaten uygulanmış.")
        return redirect("inventory:count_detail", pk=pk)

    applied = 0
    for line in count.lines.select_related("ingredient"):
        if line.variance != 0:
            services.adjust_stock(
                line.ingredient,
                count.warehouse,
                line.counted_quantity,
                note=f"Sayım {count.number}: {line.note}",
                user=request.user,
                reference_id=str(count.pk),
            )
            applied += 1

    count.status = StockCount.Status.APPLIED
    count.applied_at = timezone.now()
    count.save(update_fields=["status", "applied_at", "updated_at"])
    record_audit(
        AuditLog.Action.UPDATE,
        obj=count,
        description=(
            f"Sayım uygulandı: {count.number}, {applied} düzeltme, "
            f"fark değeri {count.total_variance_value} ₺"
        ),
        severity=AuditLog.Severity.WARNING,
        request=request,
    )
    messages.success(request, f"Sayım uygulandı. {applied} malzemede düzeltme yapıldı.")
    return redirect("inventory:count_detail", pk=pk)


# ------------------------------------------------------------------
#  Tedarikçi ve satın alma
# ------------------------------------------------------------------
@require_permission("purchase.view")
def supplier_list(request):
    suppliers = Supplier.objects.filter(is_active=True).order_by("name")
    return render(
        request,
        "inventory/supplier_list.html",
        {"page_title": "Tedarikçiler", "suppliers": suppliers},
    )


@require_permission("supplier.manage")
def supplier_create(request):
    if request.method == "POST":
        form = SupplierForm(request.POST)
        if form.is_valid():
            supplier = form.save(commit=False)
            supplier.created_by = request.user
            supplier.save()
            messages.success(request, f"{supplier.name} eklendi.")
            return redirect("inventory:supplier_list")
    else:
        form = SupplierForm()
    return render(
        request, "inventory/supplier_form.html", {"form": form, "page_title": "Yeni Tedarikçi"}
    )


@require_permission("supplier.manage")
def supplier_edit(request, pk: int):
    supplier = get_object_or_404(Supplier, pk=pk)
    if request.method == "POST":
        form = SupplierForm(request.POST, instance=supplier)
        if form.is_valid():
            form.save()
            messages.success(request, "Tedarikçi güncellendi.")
            return redirect("inventory:supplier_list")
    else:
        form = SupplierForm(instance=supplier)
    return render(
        request,
        "inventory/supplier_form.html",
        {"form": form, "supplier": supplier, "page_title": f"Düzenle: {supplier.name}"},
    )


@require_permission("purchase.view")
def purchase_list(request):
    orders = PurchaseOrder.objects.select_related("supplier", "warehouse").order_by("-created_at")
    status = request.GET.get("status", "")
    if status:
        orders = orders.filter(status=status)
    return render(
        request,
        "inventory/purchase_list.html",
        {
            "page_title": "Satın Alma",
            "orders": orders[:100],
            "statuses": PurchaseOrder.Status.choices,
            "current_status": status,
            "suggestions": services.low_stock_report(limit=20),
        },
    )


@require_permission("purchase.manage")
def purchase_create(request):
    if request.method == "POST":
        form = PurchaseOrderForm(request.POST)
        if form.is_valid():
            order = form.save(commit=False)
            order.created_by = request.user
            order.save()
            messages.success(request, f"Satın alma siparişi oluşturuldu: {order.number}")
            return redirect("inventory:purchase_detail", pk=order.pk)
    else:
        form = PurchaseOrderForm()
    return render(
        request,
        "inventory/purchase_form.html",
        {"form": form, "page_title": "Yeni Satın Alma Siparişi"},
    )


@require_permission("purchase.view")
def purchase_detail(request, pk: int):
    order = get_object_or_404(
        PurchaseOrder.objects.select_related("supplier", "warehouse").prefetch_related(
            "lines__ingredient", "lines__unit"
        ),
        pk=pk,
    )
    return render(
        request,
        "inventory/purchase_detail.html",
        {
            "page_title": f"Satın Alma {order.number}",
            "order": order,
            "ingredients": Ingredient.objects.filter(is_active=True).order_by("name"),
            "units": UnitOfMeasure.objects.all(),
        },
    )


@require_permission("purchase.manage")
@require_POST
def purchase_add_line(request, pk: int):
    order = get_object_or_404(PurchaseOrder, pk=pk)
    if not order.is_editable:
        return JsonResponse({"ok": False, "detail": "Bu sipariş artık düzenlenemez."}, status=400)
    ingredient = get_object_or_404(Ingredient, pk=request.POST.get("ingredient_id"))
    unit = get_object_or_404(UnitOfMeasure, pk=request.POST.get("unit_id"))
    PurchaseOrderLine.objects.create(
        order=order,
        ingredient=ingredient,
        unit=unit,
        quantity=_dec(request.POST.get("quantity")),
        unit_price=_dec(request.POST.get("unit_price")),
        tax_rate=_dec(request.POST.get("tax_rate"), "10"),
        expiry_date=request.POST.get("expiry_date") or None,
        lot_code=request.POST.get("lot_code", ""),
    )
    messages.success(request, "Satır eklendi.")
    return redirect("inventory:purchase_detail", pk=pk)


@require_permission("purchase.manage")
@require_POST
def purchase_approve(request, pk: int):
    order = get_object_or_404(PurchaseOrder, pk=pk)
    order.status = PurchaseOrder.Status.APPROVED
    order.approved_by = request.user
    order.approved_at = timezone.now()
    order.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    record_audit(
        AuditLog.Action.UPDATE,
        obj=order,
        description=f"Satın alma onaylandı: {order.number} ({order.grand_total} ₺)",
        severity=AuditLog.Severity.NOTICE,
        request=request,
    )
    messages.success(request, "Satın alma siparişi onaylandı.")
    return redirect("inventory:purchase_detail", pk=pk)


@require_permission("purchase.manage")
@require_POST
def purchase_receive(request, pk: int):
    """Teslim alma: stoğa parti olarak girer."""
    order = get_object_or_404(PurchaseOrder, pk=pk)
    if order.status in {PurchaseOrder.Status.RECEIVED, PurchaseOrder.Status.CANCELLED}:
        messages.error(request, "Bu sipariş zaten kapatılmış.")
        return redirect("inventory:purchase_detail", pk=pk)

    received_any = False
    for line in order.lines.select_related("ingredient", "unit"):
        field = f"received_{line.pk}"
        if field not in request.POST:
            continue
        received = _dec(request.POST[field])
        if received <= 0:
            continue
        delta = received - line.received_quantity
        if delta <= 0:
            continue
        services.receive_stock(
            line.ingredient,
            order.warehouse,
            line.unit.to_base(delta),
            line.base_unit_cost,
            expiry_date=line.expiry_date,
            lot_code=line.lot_code or order.number,
            supplier=order.supplier,
            reference_type="purchase_order",
            reference_id=str(order.pk),
            note=f"{order.number} teslim alımı",
            user=request.user,
        )
        line.received_quantity = received
        line.save(update_fields=["received_quantity"])
        received_any = True

    if received_any:
        all_received = all(line.is_fully_received for line in order.lines.all())
        order.status = (
            PurchaseOrder.Status.RECEIVED if all_received else PurchaseOrder.Status.PARTIAL
        )
        order.received_at = timezone.now()
        order.invoice_number = request.POST.get("invoice_number", order.invoice_number)
        order.save(update_fields=["status", "received_at", "invoice_number", "updated_at"])
        record_audit(
            AuditLog.Action.UPDATE,
            obj=order,
            description=f"Satın alma teslim alındı: {order.number}",
            request=request,
        )
        messages.success(request, "Teslim alma kaydedildi ve stok güncellendi.")
    else:
        messages.warning(request, "Teslim alınacak miktar girilmedi.")
    return redirect("inventory:purchase_detail", pk=pk)


@require_permission("purchase.manage")
@require_POST
def purchase_auto_suggest(request):
    """Kritik seviyedeki malzemeler için otomatik sipariş taslağı oluşturur."""
    low = services.low_stock_report()
    if not low:
        messages.info(request, "Kritik seviyede malzeme yok.")
        return redirect("inventory:purchase_list")

    warehouse = Warehouse.get_default()
    created = 0
    by_supplier: dict[int | None, list] = {}
    for ingredient in low:
        by_supplier.setdefault(ingredient.default_supplier_id, []).append(ingredient)

    for supplier_id, items in by_supplier.items():
        supplier = Supplier.objects.filter(pk=supplier_id).first()
        if supplier is None:
            supplier = Supplier.objects.filter(is_active=True).first()
        if supplier is None:
            messages.error(request, "Önce en az bir tedarikçi tanımlayın.")
            return redirect("inventory:supplier_list")

        order = PurchaseOrder.objects.create(
            supplier=supplier,
            warehouse=warehouse,
            status=PurchaseOrder.Status.DRAFT,
            notes="Kritik stok seviyesine göre otomatik oluşturuldu.",
            created_by=request.user,
        )
        for ingredient in items:
            unit = ingredient.purchase_unit or ingredient.base_unit
            needed = ingredient.reorder_quantity or (ingredient.critical_level * 2)
            PurchaseOrderLine.objects.create(
                order=order,
                ingredient=ingredient,
                unit=unit,
                quantity=unit.from_base(needed) or Decimal("1"),
                unit_price=ingredient.average_cost * unit.factor_to_base,
            )
        created += 1

    messages.success(request, f"{created} taslak satın alma siparişi oluşturuldu.")
    return redirect("inventory:purchase_list")


@require_permission("inventory.view")
def alerts(request):
    """Stok uyarı paneli: kritik seviye ve son kullanma."""
    return render(
        request,
        "inventory/alerts.html",
        {
            "page_title": "Stok Uyarıları",
            "low_stock": services.low_stock_report(),
            "expiring": services.expiring_batches(14),
        },
    )
