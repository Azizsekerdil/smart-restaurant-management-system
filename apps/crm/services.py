"""Müşteri servisleri: sadakat puanı, segmentasyon, yorum analizi."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Avg, Count, Sum
from django.utils import timezone

from apps.core.models import SystemSetting
from apps.core.utils import money
from apps.crm.models import Customer, CustomerSegment, LoyaltyTransaction, Review

# Varsayılan sadakat kuralları (SystemSetting ile değiştirilebilir)
DEFAULT_POINTS_PER_CURRENCY = Decimal("0.10")  # 100 ₺ = 10 puan
DEFAULT_POINT_VALUE = Decimal("0.10")  # 1 puan = 0.10 ₺
DEFAULT_POINT_EXPIRY_DAYS = 365


def points_per_currency() -> Decimal:
    return Decimal(
        str(SystemSetting.get("loyalty_points_per_currency", DEFAULT_POINTS_PER_CURRENCY))
    )


def point_value() -> Decimal:
    return Decimal(str(SystemSetting.get("loyalty_point_value", DEFAULT_POINT_VALUE)))


@transaction.atomic
def award_loyalty_points(customer: Customer, order, *, user=None) -> LoyaltyTransaction | None:
    """Kapanan sipariş için sadakat puanı verir ve müşteri istatistiklerini günceller."""
    if customer is None or customer.is_anonymized:
        return None
    if LoyaltyTransaction.objects.filter(order=order, kind=LoyaltyTransaction.Kind.EARN).exists():
        return None  # aynı sipariş için iki kez puan verme

    tier_bonus = {
        Customer.Tier.BRONZE: Decimal("1.00"),
        Customer.Tier.SILVER: Decimal("1.10"),
        Customer.Tier.GOLD: Decimal("1.25"),
        Customer.Tier.PLATINUM: Decimal("1.50"),
    }.get(customer.tier, Decimal("1.00"))

    points = int(order.grand_total * points_per_currency() * tier_bonus)

    customer.visit_count += 1
    customer.lifetime_value = money(customer.lifetime_value + order.grand_total)
    customer.last_visit_at = timezone.now()
    customer.loyalty_points += points
    customer.tier = _compute_tier(customer)
    customer.segment = _compute_segment(customer)
    customer.save(
        update_fields=[
            "visit_count",
            "lifetime_value",
            "last_visit_at",
            "loyalty_points",
            "tier",
            "segment",
            "updated_at",
        ]
    )

    if points <= 0:
        return None

    return LoyaltyTransaction.objects.create(
        customer=customer,
        order=order,
        kind=LoyaltyTransaction.Kind.EARN,
        points=points,
        balance_after=customer.loyalty_points,
        description=f"{order.number} adisyonundan kazanılan puan",
        expires_at=timezone.localdate() + timedelta(days=DEFAULT_POINT_EXPIRY_DAYS),
        created_by=user,
    )


@transaction.atomic
def redeem_points(customer: Customer, points: int, order=None, *, user=None) -> Decimal:
    """Puan harcar ve karşılığı tutarı döndürür."""
    if points <= 0:
        raise ValueError("Harcanacak puan sıfırdan büyük olmalıdır.")
    if customer.loyalty_points < points:
        raise ValueError(f"Yetersiz puan. Mevcut: {customer.loyalty_points}, istenen: {points}")

    amount = money(Decimal(points) * point_value())
    customer.loyalty_points -= points
    customer.save(update_fields=["loyalty_points", "updated_at"])

    LoyaltyTransaction.objects.create(
        customer=customer,
        order=order,
        kind=LoyaltyTransaction.Kind.REDEEM,
        points=-points,
        balance_after=customer.loyalty_points,
        description=f"{points} puan kullanıldı ({amount} ₺)",
        created_by=user,
    )
    return amount


def _compute_tier(customer: Customer) -> str:
    value = customer.lifetime_value
    if value >= Decimal("25000"):
        return Customer.Tier.PLATINUM
    if value >= Decimal("10000"):
        return Customer.Tier.GOLD
    if value >= Decimal("3000"):
        return Customer.Tier.SILVER
    return Customer.Tier.BRONZE


def _compute_segment(customer: Customer) -> str:
    if customer.company_name:
        return CustomerSegment.CORPORATE
    days = customer.days_since_last_visit
    if customer.visit_count <= 1:
        return CustomerSegment.NEW
    if days is not None and days > 180:
        return CustomerSegment.LOST
    if days is not None and days > 90:
        return CustomerSegment.AT_RISK
    if customer.visit_count >= 10 or customer.lifetime_value >= Decimal("10000"):
        return CustomerSegment.VIP
    return CustomerSegment.REGULAR


def refresh_all_segments() -> dict[str, int]:
    """Tüm müşterilerin segmentini yeniden hesaplar (günlük görev)."""
    counts: dict[str, int] = {}
    for customer in Customer.objects.filter(is_active=True, is_anonymized=False):
        segment = _compute_segment(customer)
        tier = _compute_tier(customer)
        if segment != customer.segment or tier != customer.tier:
            customer.segment = segment
            customer.tier = tier
            customer.save(update_fields=["segment", "tier", "updated_at"])
        counts[segment] = counts.get(segment, 0) + 1
    return counts


def churn_risk_customers(limit: int = 20):
    """Kayıp riski yüksek müşteriler (yeniden kazanım kampanyası için)."""
    threshold = timezone.now() - timedelta(days=60)
    return Customer.objects.filter(
        is_active=True,
        is_anonymized=False,
        visit_count__gte=2,
        last_visit_at__lt=threshold,
    ).order_by("-lifetime_value")[:limit]


def review_statistics(days: int = 30) -> dict:
    """Yorum istatistikleri (panel ve AI özeti için)."""
    since = timezone.now() - timedelta(days=days)
    qs = Review.objects.filter(created_at__gte=since)
    total = qs.count()
    by_sentiment = dict(
        qs.values_list("sentiment").annotate(c=Count("id")).values_list("sentiment", "c")
    )
    topic_counts: dict[str, int] = {}
    for topics in qs.values_list("topics", flat=True):
        for topic in topics or []:
            topic_counts[topic] = topic_counts.get(topic, 0) + 1

    return {
        "period_days": days,
        "total": total,
        "average_rating": round(float(qs.aggregate(a=Avg("rating"))["a"] or 0), 2),
        "positive": by_sentiment.get(Review.Sentiment.POSITIVE, 0),
        "neutral": by_sentiment.get(Review.Sentiment.NEUTRAL, 0),
        "negative": by_sentiment.get(Review.Sentiment.NEGATIVE, 0),
        "unresolved_negative": qs.filter(rating__lte=2, is_resolved=False).count(),
        "top_topics": sorted(topic_counts.items(), key=lambda kv: -kv[1])[:10],
    }


def customer_statistics() -> dict:
    total = Customer.objects.filter(is_active=True, is_anonymized=False).count()
    by_segment = dict(
        Customer.objects.filter(is_active=True)
        .values_list("segment")
        .annotate(c=Count("id"))
        .values_list("segment", "c")
    )
    return {
        "total": total,
        "by_segment": by_segment,
        "vip_count": by_segment.get(CustomerSegment.VIP, 0),
        "at_risk_count": by_segment.get(CustomerSegment.AT_RISK, 0),
        "total_loyalty_points": Customer.objects.aggregate(t=Sum("loyalty_points"))["t"] or 0,
        "total_lifetime_value": money(
            Customer.objects.aggregate(t=Sum("lifetime_value"))["t"] or Decimal("0")
        ),
    }


def customer_data_export(customer: Customer) -> dict:
    """KVKK erişim/taşınabilirlik talebi için müşteri veri dosyası üretir.

    Müşteriye ait kişisel verileri ve işlem geçmişini makine-okunur (JSON'a
    çevrilebilir) bir sözlük olarak döndürür. Görünüm katmanı bu çıktıyı
    `customer.pii` iznine bağlar ve indirme işlemini denetim kaydına işler.
    """

    def _dt(value):
        return value.isoformat() if value else None

    return {
        "_meta": {
            "olusturulma": timezone.now().isoformat(),
            "aciklama": (
                "KVKK m.11 erişim/taşınabilirlik talebi kapsamında hazırlanan "
                "kişisel veri dosyası. Sipariş tutarları mali kayıtlardan gelir."
            ),
        },
        "profil": {
            "kod": customer.code,
            "ad": customer.first_name,
            "soyad": customer.last_name,
            "telefon": customer.phone,
            "eposta": customer.email,
            "dogum_tarihi": _dt(customer.birth_date),
            "adres": customer.address,
            "sirket": customer.company_name,
            "vergi_no": customer.tax_number,
            "tercihler": customer.preferences,
            "alerji_notlari": customer.allergy_notes,
            "segment": customer.segment,
            "seviye": customer.tier,
            "sadakat_puani": customer.loyalty_points,
            "ziyaret_sayisi": customer.visit_count,
            "son_ziyaret": _dt(customer.last_visit_at),
            "kayit_tarihi": _dt(customer.created_at),
        },
        "rizalar": [
            {
                "tur": consent.get_kind_display(),
                "verildi": consent.granted,
                "kanal": consent.source,
                "zaman": _dt(consent.created_at),
                "ip": consent.ip_address,
            }
            for consent in customer.consents.order_by("created_at")
        ],
        "sadakat_hareketleri": [
            {
                "tur": tx.get_kind_display(),
                "puan": tx.points,
                "bakiye": tx.balance_after,
                "aciklama": tx.description,
                "zaman": _dt(tx.created_at),
            }
            for tx in customer.loyalty_transactions.order_by("created_at")
        ],
        "rezervasyonlar": [
            {
                "kod": reservation.code,
                "zaman": _dt(reservation.reserved_at),
                "durum": reservation.get_status_display(),
                "kisi_sayisi": reservation.party_size,
                "ozel_istek": reservation.special_requests,
                "alerji_notu": reservation.allergy_notes,
            }
            for reservation in customer.reservations.order_by("reserved_at")
        ],
        "siparisler": [
            {
                "adisyon_no": order.number,
                "zaman": _dt(order.created_at),
                "durum": order.get_status_display(),
                "tutar": str(order.grand_total),
                "teslimat_adresi": order.delivery_address,
                "teslimat_telefonu": order.delivery_phone,
            }
            for order in customer.orders.order_by("created_at")
        ],
        "yorumlar": [
            {
                "puan": review.rating,
                "yorum": review.comment,
                "zaman": _dt(review.created_at),
            }
            for review in customer.reviews.order_by("created_at")
        ],
    }
