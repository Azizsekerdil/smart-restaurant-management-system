"""Müşteri, sadakat, kampanya ve yorum görünümleri."""

from __future__ import annotations

from django import forms
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.decorators import require_permission
from apps.crm import services
from apps.crm.models import (
    Campaign,
    ConsentRecord,
    Customer,
    CustomerSegment,
    LoyaltyTransaction,
    Review,
)

_TEXT = {"class": "form-control"}
_SELECT = {"class": "form-select"}


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = [
            "first_name",
            "last_name",
            "phone",
            "email",
            "birth_date",
            "address",
            "company_name",
            "tax_number",
            "preferences",
            "allergy_notes",
            "internal_notes",
            "is_active",
        ]
        widgets = {
            "first_name": forms.TextInput(attrs=_TEXT),
            "last_name": forms.TextInput(attrs=_TEXT),
            "phone": forms.TextInput(attrs={**_TEXT, "inputmode": "tel"}),
            "email": forms.EmailInput(attrs=_TEXT),
            "birth_date": forms.DateInput(attrs={**_TEXT, "type": "date"}),
            "address": forms.Textarea(attrs={**_TEXT, "rows": 2}),
            "company_name": forms.TextInput(attrs=_TEXT),
            "tax_number": forms.TextInput(attrs=_TEXT),
            "preferences": forms.Textarea(attrs={**_TEXT, "rows": 2}),
            "allergy_notes": forms.TextInput(attrs=_TEXT),
            "internal_notes": forms.Textarea(attrs={**_TEXT, "rows": 2}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


@require_permission("customer.view")
def customer_list(request):
    customers = Customer.objects.filter(is_active=True)
    search = request.GET.get("q", "").strip()
    segment = request.GET.get("segment", "")
    if search:
        customers = customers.filter(
            Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
            | Q(phone__icontains=search)
            | Q(code__iexact=search)
            | Q(company_name__icontains=search)
        )
    if segment:
        customers = customers.filter(segment=segment)

    paginator = Paginator(customers.order_by("-last_visit_at", "first_name"), 30)
    page = paginator.get_page(request.GET.get("page", 1))

    return render(
        request,
        "crm/customer_list.html",
        {
            "page_title": "Müşteriler",
            "page_obj": page,
            "segments": CustomerSegment.choices,
            "filters": {"q": search, "segment": segment},
            "stats": services.customer_statistics(),
            "can_see_pii": request.user.has_perm_code("customer.pii"),
        },
    )


@require_permission("customer.view")
def customer_detail(request, pk: int):
    customer = get_object_or_404(Customer, pk=pk)
    return render(
        request,
        "crm/customer_detail.html",
        {
            "page_title": customer.full_name,
            "customer": customer,
            "orders": customer.orders.order_by("-opened_at")[:30],
            "loyalty": customer.loyalty_transactions.order_by("-created_at")[:30],
            "reviews": customer.reviews.order_by("-created_at")[:10],
            "consents": customer.consents.order_by("-created_at")[:20],
            "consent_kinds": ConsentRecord.Kind.choices,
            "can_see_pii": request.user.has_perm_code("customer.pii"),
        },
    )


@require_permission("customer.manage")
def customer_create(request):
    if request.method == "POST":
        form = CustomerForm(request.POST)
        if form.is_valid():
            customer = form.save(commit=False)
            customer.created_by = request.user
            customer.save()
            messages.success(request, f"{customer.full_name} kaydedildi ({customer.code}).")
            return redirect("crm:customer_detail", pk=customer.pk)
    else:
        form = CustomerForm()
    return render(request, "crm/customer_form.html", {"form": form, "page_title": "Yeni Müşteri"})


@require_permission("customer.manage")
def customer_edit(request, pk: int):
    customer = get_object_or_404(Customer, pk=pk)
    if request.method == "POST":
        form = CustomerForm(request.POST, instance=customer)
        if form.is_valid():
            form.save()
            messages.success(request, "Müşteri güncellendi.")
            return redirect("crm:customer_detail", pk=pk)
    else:
        form = CustomerForm(instance=customer)
    return render(
        request,
        "crm/customer_form.html",
        {"form": form, "customer": customer, "page_title": f"Düzenle: {customer.full_name}"},
    )


@require_permission("customer.manage")
@require_POST
def customer_consent(request, pk: int):
    customer = get_object_or_404(Customer, pk=pk)
    kind = request.POST.get("kind")
    granted = request.POST.get("granted") == "true"
    if kind not in dict(ConsentRecord.Kind.choices):
        return JsonResponse({"ok": False, "detail": "Geçersiz izin türü."}, status=400)
    ConsentRecord.objects.create(
        customer=customer,
        kind=kind,
        granted=granted,
        source=request.POST.get("source", "restoran"),
        ip_address=request.META.get("REMOTE_ADDR"),
    )
    return JsonResponse({"ok": True, "granted": granted})


@require_permission("customer.pii")
def customer_data_export(request, pk: int):
    """KVKK erişim/taşınabilirlik talebi: müşteri veri dosyasını indirir.

    Ham kişisel veri içerdiği için `customer.pii` izni gerektirir; her
    indirme denetim kaydına işlenir. Dosya, talebi yapan ilgili kişiye
    güvenli bir kanaldan iletilmelidir (bkz. docs/ROPA_HAZIRLIK.md).
    """
    from apps.core.models import AuditLog
    from apps.core.services import record_audit

    customer = get_object_or_404(Customer, pk=pk)
    data = services.customer_data_export(customer)
    record_audit(
        AuditLog.Action.EXPORT,
        user=request.user,
        obj=customer,
        description=f"Müşteri {customer.code} için KVKK veri dosyası indirildi (DSR).",
        severity=AuditLog.Severity.NOTICE,
        request=request,
    )
    response = JsonResponse(data, json_dumps_params={"ensure_ascii": False, "indent": 2})
    response["Content-Disposition"] = (
        f'attachment; filename="musteri-{customer.code}-veri-dosyasi.json"'
    )
    return response


@require_permission("data.erase")
@require_POST
def customer_anonymize(request, pk: int):
    """KVKK kapsamında kişisel verileri anonimleştirir."""
    customer = get_object_or_404(Customer, pk=pk)
    if customer.is_anonymized:
        messages.info(request, "Bu müşteri zaten anonimleştirilmiş.")
        return redirect("crm:customer_detail", pk=pk)
    reason = request.POST.get("reason", "Müşteri silme talebi")
    customer.anonymize(user=request.user, reason=reason)
    messages.success(
        request,
        "Müşterinin kişisel verileri geri döndürülemez şekilde anonimleştirildi. "
        "Sipariş geçmişi mali kayıt bütünlüğü için korunmuştur.",
    )
    return redirect("crm:customer_list")


@require_permission("loyalty.manage")
@require_POST
def loyalty_adjust(request, pk: int):
    customer = get_object_or_404(Customer, pk=pk)
    points = int(request.POST.get("points") or 0)
    if points == 0:
        return JsonResponse({"ok": False, "detail": "Puan sıfır olamaz."}, status=400)
    customer.loyalty_points += points
    customer.save(update_fields=["loyalty_points", "updated_at"])
    LoyaltyTransaction.objects.create(
        customer=customer,
        kind=LoyaltyTransaction.Kind.ADJUST,
        points=points,
        balance_after=customer.loyalty_points,
        description=request.POST.get("description", "Elle düzeltme")[:200],
        created_by=request.user,
    )
    return JsonResponse({"ok": True, "balance": customer.loyalty_points})


# ------------------------------------------------------------------
#  Yorumlar
# ------------------------------------------------------------------
@require_permission("customer.view")
def review_list(request):
    reviews = Review.objects.select_related("customer", "order")
    sentiment = request.GET.get("sentiment", "")
    unresolved = request.GET.get("unresolved", "")
    if sentiment:
        reviews = reviews.filter(sentiment=sentiment)
    if unresolved:
        reviews = reviews.filter(is_resolved=False, rating__lte=2)

    return render(
        request,
        "crm/review_list.html",
        {
            "page_title": "Müşteri Yorumları",
            "reviews": reviews.order_by("-created_at")[:150],
            "sentiments": Review.Sentiment.choices,
            "stats": services.review_statistics(),
            "filters": {"sentiment": sentiment, "unresolved": unresolved},
        },
    )


@require_permission("customer.manage")
@require_POST
def review_create(request):
    Review.objects.create(
        customer_id=request.POST.get("customer_id") or None,
        order_id=request.POST.get("order_id") or None,
        rating=int(request.POST.get("rating") or 5),
        comment=request.POST.get("comment", "")[:2000],
        source=request.POST.get("source", Review.Source.IN_HOUSE),
        created_by=request.user,
    )
    messages.success(request, "Yorum kaydedildi.")
    return redirect("crm:review_list")


@require_permission("customer.manage")
@require_POST
def review_resolve(request, pk: int):
    review = get_object_or_404(Review, pk=pk)
    review.is_resolved = True
    review.resolution_note = request.POST.get("note", "")[:1000]
    review.resolved_by = request.user
    review.save(update_fields=["is_resolved", "resolution_note", "resolved_by", "updated_at"])
    return JsonResponse({"ok": True})


@require_permission("ai.use")
@require_POST
def review_analyze(request):
    """Analiz edilmemiş yorumları yapay zekâ ile değerlendirir."""
    from apps.ai.analytics import analyze_reviews

    result = analyze_reviews(user=request.user, limit=int(request.POST.get("limit") or 20))
    if result["ok"]:
        messages.success(request, f"{result['analyzed']} yorum analiz edildi.")
    else:
        messages.warning(request, result["message"])
    return redirect("crm:review_list")


# ------------------------------------------------------------------
#  Kampanyalar
# ------------------------------------------------------------------
@require_permission("campaign.manage")
def campaign_list(request):
    return render(
        request,
        "crm/campaign_list.html",
        {
            "page_title": "Kampanyalar",
            "campaigns": Campaign.objects.select_related("coupon").order_by("-starts_at"),
            "churn_risk": services.churn_risk_customers(10),
        },
    )


@require_permission("campaign.manage")
@require_POST
def campaign_create(request):
    campaign = Campaign.objects.create(
        name=request.POST.get("name", "Yeni kampanya")[:200],
        description=request.POST.get("description", ""),
        target_segments=request.POST.getlist("target_segments"),
        starts_at=timezone.now(),
        created_by=request.user,
    )
    messages.success(request, f"{campaign.name} oluşturuldu.")
    return redirect("crm:campaign_list")


@require_permission("campaign.manage")
@require_POST
def campaign_set_status(request, pk: int):
    campaign = get_object_or_404(Campaign, pk=pk)
    status = request.POST.get("status")
    if status in dict(Campaign.Status.choices):
        campaign.status = status
        campaign.save(update_fields=["status", "updated_at"])
    return redirect("crm:campaign_list")


@require_permission("customer.view")
def customer_search(request):
    """POS ekranı için hızlı müşteri arama (JSON)."""
    query = request.GET.get("q", "").strip()
    if len(query) < 2:
        return JsonResponse({"results": []})
    can_see_pii = request.user.has_perm_code("customer.pii")
    customers = Customer.objects.filter(is_active=True).filter(
        Q(first_name__icontains=query)
        | Q(last_name__icontains=query)
        | Q(phone__icontains=query)
        | Q(code__iexact=query)
    )[:15]
    return JsonResponse(
        {
            "results": [
                {
                    "id": c.pk,
                    "code": c.code,
                    "name": c.full_name,
                    "phone": c.phone if can_see_pii else c.masked_phone,
                    "points": c.loyalty_points,
                    "tier": c.get_tier_display(),
                    # Alerji notu sağlık verisidir (KVKK m.6 / GDPR m.9).
                    # `customer.pii` izni olmayan kullanıcıya metin
                    # verilmez; servis güvenliği için yalnızca "kayıt var"
                    # bilgisi döner. Aynı kural DRF seri hâline
                    # getiricisinde de uygulanır (apps/crm/api.py).
                    "allergy": c.allergy_notes if can_see_pii else "",
                    "has_allergy": bool(c.allergy_notes),
                }
                for c in customers
            ]
        }
    )
