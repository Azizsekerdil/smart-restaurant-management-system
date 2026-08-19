"""Kişisel ve sağlık verisi maskeleme gerilemeleri.

Alerji notu KVKK m.6 / GDPR m.9 anlamında **sağlık verisidir**. Ürün bunu
DRF seri hâline getiricisinde maskeliyordu, ancak aynı veri üç ayrı yoldan
maskesiz sızıyordu:

* ``crm:customer_search`` JSON ucu alerji metnini herkese veriyordu,
* müşteri kartı şablonu alerji metnini ``customer.view`` yetkisiyle
  gösteriyordu,
* rezervasyon API'si misafir telefonunu ve alerji notunu maskesiz
  döndürüyordu (``reservation.view`` bütün salon personelinde vardır).

Bu testler üç yolu da kapalı tutar. Uyarının VARLIĞI gizlenmez: servis
güvenliği için "alerji kaydı var" bilgisi görünmeye devam eder, yalnızca
içeriği yetkiye bağlanır.
"""

from __future__ import annotations

import json

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.crm.models import Customer
from apps.floor.models import Reservation

pytestmark = pytest.mark.django_db

ALLERGY_TEXT = "Fistik alerjisi - epinefrin tasiyor"


@pytest.fixture
def allergic_customer(db):
    return Customer.objects.create(
        first_name="Deneme",
        last_name="Misafir",
        phone="0000 000 0042",
        email="deneme.misafir@example.invalid",
        allergy_notes=ALLERGY_TEXT,
    )


# ------------------------------------------------------------------ arama ucu
def test_customer_search_hides_allergy_text_without_pii_permission(
    client, waiter, allergic_customer
):
    assert not waiter.has_perm_code("customer.pii")
    client.force_login(waiter)

    response = client.get(reverse("crm:customer_search"), {"q": "Deneme"})

    assert response.status_code == 200
    payload = json.loads(response.content)
    assert payload["results"], "arama sonucu boş dönmemeli"
    row = payload["results"][0]
    assert ALLERGY_TEXT not in json.dumps(payload, ensure_ascii=False)
    assert row["allergy"] == ""
    assert row["has_allergy"] is True  # uyarının varlığı korunur
    assert row["phone"] == allergic_customer.masked_phone


def test_customer_search_shows_allergy_text_with_pii_permission(client, manager, allergic_customer):
    assert manager.has_perm_code("customer.pii")
    client.force_login(manager)

    response = client.get(reverse("crm:customer_search"), {"q": "Deneme"})

    row = json.loads(response.content)["results"][0]
    assert row["allergy"] == ALLERGY_TEXT
    assert row["phone"] == allergic_customer.phone


# ------------------------------------------------------------------ şablonlar
def test_customer_detail_page_hides_allergy_text_without_permission(
    client, waiter, allergic_customer
):
    client.force_login(waiter)
    response = client.get(reverse("crm:customer_detail", args=[allergic_customer.pk]))
    body = response.content.decode()

    assert response.status_code == 200
    assert ALLERGY_TEXT not in body
    assert allergic_customer.phone not in body
    assert "Alerji" in body  # uyarı görünür kalır


def test_customer_detail_page_shows_allergy_text_with_permission(
    client, manager, allergic_customer
):
    client.force_login(manager)
    response = client.get(reverse("crm:customer_detail", args=[allergic_customer.pk]))
    assert ALLERGY_TEXT in response.content.decode()


def test_pos_order_panel_hides_allergy_text_without_permission(
    client, waiter, table, allergic_customer
):
    from apps.orders.services import open_order

    order = open_order(table=table, waiter=waiter, customer=allergic_customer)
    client.force_login(waiter)

    response = client.get(reverse("orders:order_detail", args=[order.pk]))

    assert response.status_code == 200
    assert ALLERGY_TEXT not in response.content.decode()


# ------------------------------------------------------------------ REST API
@pytest.fixture
def reservation(db, table, allergic_customer):
    booking = Reservation.objects.create(
        customer=allergic_customer,
        guest_name=allergic_customer.full_name,
        guest_phone="0000 000 0042",
        party_size=2,
        reserved_at=timezone.now() + timezone.timedelta(hours=3),
        allergy_notes=ALLERGY_TEXT,
    )
    booking.tables.set([table])
    return booking


def test_reservation_api_masks_guest_phone_and_allergy(client, waiter, reservation):
    assert waiter.has_perm_code("reservation.view")
    assert not waiter.has_perm_code("customer.pii")
    client.force_login(waiter)

    response = client.get("/api/reservations/", HTTP_ACCEPT="application/json")

    assert response.status_code == 200
    body = response.content.decode()
    assert ALLERGY_TEXT not in body
    assert "0000 000 0042" not in body
    row = response.json()["results"][0]
    assert row["has_allergy_note"] is True
    assert row["guest_phone"].endswith("***42") or "***" in row["guest_phone"]


def test_reservation_api_reveals_details_with_pii_permission(client, manager, reservation):
    client.force_login(manager)
    response = client.get("/api/reservations/", HTTP_ACCEPT="application/json")
    row = response.json()["results"][0]
    assert row["allergy_notes"] == ALLERGY_TEXT
    assert row["guest_phone"] == "0000 000 0042"


def test_reservation_can_still_be_created_through_the_api(client, manager, table):
    """Maskeleme yazma yolunu bozmamalı."""
    client.force_login(manager)
    response = client.post(
        "/api/reservations/",
        data=json.dumps(
            {
                "guest_name": "Yeni Misafir",
                "guest_phone": "0000 000 0077",
                "party_size": 2,
                "reserved_at": (timezone.now() + timezone.timedelta(days=1)).isoformat(),
                "allergy_notes": "Glutensiz",
            }
        ),
        content_type="application/json",
    )
    assert response.status_code in (200, 201), response.content
    created = Reservation.objects.get(guest_name="Yeni Misafir")
    assert created.guest_phone == "0000 000 0077"
    assert created.allergy_notes == "Glutensiz"


# ------------------------------------------------------------------ demo veri
def test_demo_data_uses_undialable_synthetic_contacts():
    """Örnek veri aranabilir numara / ulaşılabilir e-posta ÜRETMEZ."""
    from apps.core.management.commands.seed_demo import fake_email, fake_phone

    phone = fake_phone(7)
    email = fake_email("Ad.Soyad")

    assert phone.startswith("0000"), phone
    assert email.endswith("@example.invalid"), email


# ------------------------------------------------------------------ enjeksiyon
@pytest.mark.parametrize(
    "hostile",
    [
        "javascript:alert(1)",
        "JaVaScRiPt:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "//evil.example.invalid/steal",
        "https://evil.example.invalid",
        "java\tscript:alert(1)",
    ],
)
def test_notification_url_rejects_non_internal_targets(hostile):
    """Bildirim bağlantısı şablonda href'e basılır: şema kaçağı olmamalı."""
    from apps.core.services import safe_internal_url

    assert safe_internal_url(hostile) == ""


@pytest.mark.parametrize("safe", ["/panel/", "/musteri/12/", "/siparis/pos/?masa=3"])
def test_notification_url_keeps_internal_paths(safe):
    from apps.core.services import safe_internal_url

    assert safe_internal_url(safe) == safe


def test_notify_stores_only_a_sanitised_url(db):
    from apps.core.models import Notification
    from apps.core.services import notify

    notify("Uyarı", url="javascript:alert(1)")

    assert Notification.objects.get(title="Uyarı").url == ""


@pytest.mark.parametrize(
    "field,value",
    [
        ("new_price", "NaN"),
        ("new_price", "Infinity"),
        ("elasticity", "nan"),
        ("elasticity", "inf"),
        ("new_price", "-5"),
    ],
)
def test_price_simulation_rejects_non_finite_input(client, owner, pizza, field, value):
    """NaN/sonsuz bir girdi mali bir ekrana sessizce sızmamalı."""
    payload = {"new_price": "120", "elasticity": "-1.2"}
    payload[field] = value
    client.force_login(owner)

    response = client.post(
        reverse("ai:price_simulation", args=[pizza.pk]), payload, HTTP_ACCEPT="application/json"
    )

    assert response.status_code == 400, response.content
    assert response.json()["ok"] is False


def test_price_simulation_accepts_valid_input(client, owner, pizza):
    client.force_login(owner)
    response = client.post(
        reverse("ai:price_simulation", args=[pizza.pk]),
        {"new_price": "120", "elasticity": "-1.2"},
        HTTP_ACCEPT="application/json",
    )
    assert response.status_code == 200, response.content
