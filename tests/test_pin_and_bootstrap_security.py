"""POS PIN'i, yetkili onayı ve ilk-parola zorlaması için gerileme testleri.

Bu dosya, aşağıdaki gerçek zafiyetlerin geri gelmesini engeller:

* **Kimlik doğrulamasız hesap ele geçirme.** ``/hesap/pin/gecis/`` uç
  noktası oturum açmadan çağrılabiliyordu: saldırgan kullanıcı adını
  bilip 4 haneli PIN'i deneyerek doğrudan o kullanıcı olarak oturum
  açabiliyordu.
* **PIN kaba kuvvet saldırısı.** PIN denemeleri sayılmıyordu; 10.000
  ihtimallik alan dakikalar içinde taranabiliyordu.
* **Zayıf PIN.** 1111 / 1234 gibi PIN'ler kabul ediliyordu.
* **Geçici parola ile serbest gezinme.** ``must_change_password`` yalnızca
  giriş görünümünde bir uyarı üretiyordu; kullanıcı adres çubuğundan
  korumalı sayfalara girebiliyordu.
* **Tek kullanımlık kurulum kimliği.** `admin/admin` yalnız boş veritabanında,
  açık bootstrap komutuyla oluşturulur; ilk giriş yerel ve parola değişimi zorunludur.
"""

from __future__ import annotations

import pytest
from django.core.cache import cache
from django.core.management import call_command
from django.urls import reverse

from apps.accounts import pin_security
from apps.accounts.models import User
from apps.accounts.permissions import Role
from apps.core.models import AuditLog

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_pin_counters():
    """Her test kendi kilit sayaçlarıyla başlasın."""
    cache.clear()
    yield
    cache.clear()


# ==================================================================
#  1. Kimlik doğrulamasız PIN geçişi (hesap ele geçirme)
# ==================================================================
def test_pin_switch_rejects_anonymous_request(client, owner):
    """Oturum açmamış bir istemci PIN ile oturum AÇAMAZ."""
    owner.set_pin("5271")
    owner.save(update_fields=["pin_hash"])

    response = client.post(
        reverse("accounts:pin_switch"), {"username": owner.username, "pin": "5271"}
    )

    # Girişe yönlendirilir; oturum açılmaz.
    assert response.status_code in (302, 403)
    assert "_auth_user_id" not in client.session


def test_pin_switch_does_not_leak_user_existence_to_anonymous(client):
    response = client.post(reverse("accounts:pin_switch"), {"username": "patron", "pin": "5271"})
    assert response.status_code in (302, 403)
    assert "_auth_user_id" not in client.session


# ==================================================================
#  2. Kaba kuvvet: deneme sayısı sınırı ve kilit
# ==================================================================
def test_pin_switch_locks_after_repeated_failures(client, owner, waiter):
    owner.set_pin("5271")
    owner.save(update_fields=["pin_hash"])
    client.force_login(waiter)
    url = reverse("accounts:pin_switch")

    for _ in range(pin_security.MAX_FAILURES):
        response = client.post(url, {"username": owner.username, "pin": "9182"})
        assert response.status_code == 403

    # Kilitten sonra DOĞRU PIN bile kabul edilmez.
    locked = client.post(url, {"username": owner.username, "pin": "5271"})
    assert locked.status_code == 429
    assert locked.json()["code"] == "pin_locked"
    assert int(client.session["_auth_user_id"]) == waiter.pk  # geçiş olmadı


def test_pin_failures_are_counted_per_ip_as_well(client, owner, manager, waiter):
    """Farklı hesaplara yayılan denemeler de aynı IP'de sayılır."""
    client.force_login(waiter)
    url = reverse("accounts:pin_switch")
    for index in range(pin_security.MAX_FAILURES):
        client.post(url, {"username": f"olmayan{index}", "pin": "9182"})

    # Aynı IP'den gelen denemeler, hedef hesap değişse de sayılır.
    assert pin_security.failure_count(ip="127.0.0.1") >= pin_security.MAX_FAILURES


def test_successful_switch_resets_the_counter(client, owner, waiter):
    owner.set_pin("5271")
    owner.save(update_fields=["pin_hash"])
    client.force_login(waiter)
    url = reverse("accounts:pin_switch")

    client.post(url, {"username": owner.username, "pin": "9182"})
    response = client.post(url, {"username": owner.username, "pin": "5271"})

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert int(client.session["_auth_user_id"]) == owner.pk


def test_failed_pin_switch_is_audited_without_the_pin(client, owner, waiter):
    owner.set_pin("5271")
    owner.save(update_fields=["pin_hash"])
    client.force_login(waiter)

    client.post(reverse("accounts:pin_switch"), {"username": owner.username, "pin": "9182"})

    entries = AuditLog.objects.filter(action=AuditLog.Action.LOGIN_FAILED)
    assert entries.exists()
    for entry in entries:
        assert "9182" not in entry.description
        assert "5271" not in entry.description


# ==================================================================
#  3. En az yetki: kimin hesabına geçilebilir
# ==================================================================
def test_pin_switch_refused_for_account_without_pos_permission(client, waiter, db):
    accountant = User.objects.create_user(
        username="muhasebe", password="Test!2026Pass", role=Role.ACCOUNTANT
    )
    accountant.set_pin("5271")
    accountant.save()
    assert not accountant.has_perm_code("pos.use")

    client.force_login(waiter)
    response = client.post(reverse("accounts:pin_switch"), {"username": "muhasebe", "pin": "5271"})

    assert response.status_code == 403
    assert int(client.session["_auth_user_id"]) == waiter.pk


def test_pin_switch_refused_while_password_change_is_pending(client, owner, waiter):
    owner.set_pin("5271")
    owner.must_change_password = True
    owner.save(update_fields=["pin_hash", "must_change_password"])

    client.force_login(waiter)
    response = client.post(
        reverse("accounts:pin_switch"), {"username": owner.username, "pin": "5271"}
    )

    assert response.status_code == 403
    assert int(client.session["_auth_user_id"]) == waiter.pk


def test_pin_switch_refused_for_inactive_account(client, owner, waiter):
    owner.set_pin("5271")
    owner.is_active = False
    owner.save(update_fields=["pin_hash", "is_active"])

    client.force_login(waiter)
    response = client.post(
        reverse("accounts:pin_switch"), {"username": owner.username, "pin": "5271"}
    )
    assert response.status_code == 403


# ==================================================================
#  4. PIN gücü politikası
# ==================================================================
@pytest.mark.parametrize("weak", ["1111", "0000", "1234", "4321", "9999", "123456", "2580"])
def test_weak_pins_are_rejected(owner, weak):
    with pytest.raises(ValueError):
        owner.set_pin(weak)


@pytest.mark.parametrize("bad", ["", "12", "abcd", "123456789", "12a4"])
def test_malformed_pins_are_rejected(owner, bad):
    if bad == "":
        owner.set_pin(bad)  # boş değer PIN'i kaldırır, hata değildir
        assert owner.pin_hash == ""
        return
    with pytest.raises(ValueError):
        owner.set_pin(bad)


@pytest.mark.parametrize("good", ["5271", "8364", "90514", "27389461"])
def test_strong_pins_are_accepted(owner, good):
    owner.set_pin(good)
    assert owner.check_pin(good)
    assert owner.pin_hash and owner.pin_hash != good  # düz metin saklanmaz


def test_pin_is_stored_hashed_only(owner):
    owner.set_pin("5271")
    owner.save(update_fields=["pin_hash"])
    owner.refresh_from_db()
    assert "5271" not in owner.pin_hash
    assert owner.pin_hash.count("$") >= 2  # Django hash biçimi


# ==================================================================
#  5. Yetkili onayı PIN'i de sınırlanır
# ==================================================================
def test_manager_approval_pin_is_rate_limited(client, waiter, manager, table):
    """Garson, müdür PIN'ini deneyerek indirim yetkisi ELDE EDEMEZ."""
    from apps.orders.services import open_order

    manager.set_pin("8364")
    manager.save(update_fields=["pin_hash"])
    assert not waiter.has_perm_code("pos.discount")
    order = open_order(table=table, waiter=waiter)
    client.force_login(waiter)
    url = reverse("orders:order_discount", args=[order.pk])

    for _ in range(pin_security.MAX_FAILURES):
        response = client.post(
            url,
            {"percent": "50", "approver_username": manager.username, "approver_pin": "1928"},
            HTTP_ACCEPT="application/json",
        )
        assert response.status_code == 403
        assert response.json()["code"] == "approval_invalid"

    # Kilit devreye girdi: DOĞRU PIN bile artık kabul edilmez.
    locked = client.post(
        url,
        {"percent": "50", "approver_username": manager.username, "approver_pin": "8364"},
        HTTP_ACCEPT="application/json",
    )
    assert locked.status_code == 429
    assert locked.json()["code"] == "approval_locked"

    assert pin_security.failure_count(username=manager.username) >= pin_security.MAX_FAILURES


# ==================================================================
#  6. Geçici parola: değiştirilmeden hiçbir korumalı alana girilemez
# ==================================================================
PROTECTED_VIEWS = [
    "reports:dashboard",
    "orders:pos",
    "crm:customer_list",
    "reports:statistics",
    "backups:index",
    "core:settings",
]


@pytest.mark.parametrize("view_name", PROTECTED_VIEWS)
def test_protected_pages_unreachable_before_password_change(client, owner, view_name):
    owner.must_change_password = True
    owner.save(update_fields=["must_change_password"])
    client.force_login(owner)

    response = client.get(reverse(view_name))

    assert response.status_code == 302
    assert reverse("accounts:password_change") in response["Location"]


def test_api_returns_403_with_code_before_password_change(client, owner):
    owner.must_change_password = True
    owner.save(update_fields=["must_change_password"])
    client.force_login(owner)

    response = client.get("/api/", HTTP_ACCEPT="application/json")

    assert response.status_code == 403
    assert response.json()["code"] == "password_change_required"


def test_password_change_page_itself_stays_reachable(client, owner):
    owner.must_change_password = True
    owner.save(update_fields=["must_change_password"])
    client.force_login(owner)

    assert client.get(reverse("accounts:password_change")).status_code == 200
    assert client.get(reverse("accounts:logout")).status_code in (200, 302)


def test_access_is_restored_after_the_password_is_changed(client, owner):
    owner.must_change_password = True
    owner.save(update_fields=["must_change_password"])
    client.force_login(owner)

    response = client.post(
        reverse("accounts:password_change"),
        {
            "old_password": "Test!2026Pass",
            "new_password1": "Yepyeni!Parola2026",
            "new_password2": "Yepyeni!Parola2026",
        },
    )
    assert response.status_code == 302

    owner.refresh_from_db()
    assert owner.must_change_password is False
    assert not owner.check_password("Test!2026Pass")  # eski parola ölü
    assert client.get(reverse("reports:dashboard")).status_code == 200


# ==================================================================
#  7. Tek kullanımlık kurulum hesabı
# ==================================================================
@pytest.mark.parametrize(
    "username,password",
    [("admin", "admin"), ("admin", "password"), ("patron", "patron"), ("root", "root")],
)
def test_no_default_account_ships_with_the_product(client, username, password, db):
    """Hesap yalnız açık bootstrap komutuyla oluşturulur."""
    assert not User.objects.filter(username__iexact=username).exists()
    response = client.post(reverse("accounts:login"), {"username": username, "password": password})
    assert "_auth_user_id" not in client.session
    assert response.status_code == 200  # form hatayla geri döner


def test_bootstrap_command_creates_one_time_admin(db):
    call_command("bootstrap_admin")
    user = User.objects.get(username="admin")
    assert user.check_password("admin")
    assert user.password != "admin"
    assert user.must_change_password is True


def test_bootstrap_login_is_local_only(client, db):
    call_command("bootstrap_admin")
    remote = client.post(
        reverse("accounts:login"),
        {"username": "admin", "password": "admin"},
        REMOTE_ADDR="203.0.113.8",
    )
    assert remote.status_code == 200
    assert "_auth_user_id" not in client.session

    local = client.post(
        reverse("accounts:login"),
        {"username": "admin", "password": "admin"},
        REMOTE_ADDR="127.0.0.1",
    )
    assert local.status_code == 302
    assert local["Location"] == reverse("accounts:password_change")
    assert "_auth_user_id" in client.session


def test_seed_demo_password_is_not_a_fixed_literal():
    """Demo parolası kaynak kodda sabit DEĞİLDİR; her kurulumda üretilir."""
    from apps.core.management.commands.seed_demo import generate_demo_password

    first, second = generate_demo_password(), generate_demo_password()
    assert first != second
    assert len(first) >= 14


def test_demo_pins_are_not_predictable_from_the_source():
    """Demo PIN'i tohumlanmış üreteçten gelmemeli.

    `seed_demo` modülü demo verisini tekrarlanabilir kılmak için
    `random.seed(...)` çağırır. PIN de o üreteçten alınsaydı, kaynak kod
    herkese açık olduğu için her kurulumun demo PIN'i hesaplanabilirdi.
    """
    import random as stdlib_random

    from apps.core.management.commands.seed_demo import strong_demo_pin

    stdlib_random.seed(20260815)
    first = [strong_demo_pin() for _ in range(8)]
    stdlib_random.seed(20260815)
    second = [strong_demo_pin() for _ in range(8)]

    assert first != second, "PIN tohumlanmış üreteçten geliyor: tahmin edilebilir"
    for pin in first + second:
        pin_security.validate_pin(pin)  # politikaya uymalı
