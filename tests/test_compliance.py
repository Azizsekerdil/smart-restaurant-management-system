"""Compliance katmanı testleri (Faz F1).

Kapsam:
- AI sohbet geçmişinin maskelenerek saklanması (D1)
- Yönetim API'sinde alerji notunun izne bağlı maskelenmesi (D2)
- Personel bağlamının sensitive=True yönlendirmesi (D3)
- Public yayın kapısı kuralları
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from django.test import RequestFactory
from django.urls import reverse

ROOT = Path(__file__).resolve().parent.parent


# ------------------------------------------------------------------
#  D1 — Sohbet geçmişi maskeli saklanır
# ------------------------------------------------------------------
def test_assistant_stores_masked_conversation(client, manager, db):
    from apps.ai.models import AIConversationMessage

    client.force_login(manager)
    # DİKKAT: buradaki numara bilerek GERÇEKÇİ BİÇİMDEDİR. Maskeleme deseninin
    # gerçek bir Türk cep numarası biçimini yakaladığını kanıtlayan şey budur;
    # "0000..." gibi kurgusal bir biçimle bu test anlamsızlaşırdı. Değerin
    # kendisi uydurmadır ve hiçbir kişiye ait değildir.
    question = "Müşterim ahmet@example.invalid ve 05321234567 numarası hakkında ne biliyoruz?"
    response = client.post(reverse("ai:assistant_ask"), {"question": question})

    # Test ortamında sağlayıcı yoktur; 503 beklenir ama kullanıcı mesajı
    # yanıt denemesinden ÖNCE kaydedilir.
    assert response.status_code == 503

    message = AIConversationMessage.objects.filter(role="user").latest("created_at")
    assert "ahmet@example.invalid" not in message.content
    assert "05321234567" not in message.content
    assert "[E-POSTA]" in message.content
    assert "[TELEFON]" in message.content


def test_mask_pii_covers_expected_patterns():
    from apps.ai.gateway import mask_pii

    masked = mask_pii("e-posta a@b.com, tel 0532 123 45 67, TC 12345678901")
    assert "a@b.com" not in masked
    assert "12345678901" not in masked


# ------------------------------------------------------------------
#  D2 — Alerji notu yönetim API'sinde izne bağlı
# ------------------------------------------------------------------
@pytest.fixture
def allergic_customer(db):
    from apps.crm.models import Customer

    return Customer.objects.create(
        first_name="Ayşe",
        last_name="Örnek",
        phone="05329876543",
        allergy_notes="Fıstık alerjisi — anafilaksi riski",
    )


def _serialize_customer(customer, user):
    from apps.crm.api import CustomerSerializer

    request = RequestFactory().get("/api/customers/")
    request.user = user
    return CustomerSerializer(customer, context={"request": request}).data


def test_allergy_notes_masked_without_pii_permission(allergic_customer, cashier):
    assert not cashier.has_perm_code("customer.pii")
    data = _serialize_customer(allergic_customer, cashier)
    assert "Fıstık" not in data["allergy_notes"]
    # Servis güvenliği: kaydın VARLIĞI kaybolmaz, içerik maskelenir.
    assert data["allergy_notes"] != ""


def test_allergy_notes_visible_with_pii_permission(allergic_customer, manager):
    assert manager.has_perm_code("customer.pii")
    data = _serialize_customer(allergic_customer, manager)
    assert data["allergy_notes"] == "Fıstık alerjisi — anafilaksi riski"


def test_allergy_notes_empty_stays_empty(db, cashier):
    from apps.crm.models import Customer

    customer = Customer.objects.create(first_name="Boş", last_name="Not")
    data = _serialize_customer(customer, cashier)
    assert data["allergy_notes"] == ""


# ------------------------------------------------------------------
#  D3 — Personel bağlamı hassas yönlendirme
# ------------------------------------------------------------------
def test_build_context_marks_staff_data_sensitive(db):
    from apps.ai.views import _build_context

    context, sensitive = _build_context("Personel satış performansı nasıl?")
    assert sensitive is True
    assert "personel_satis_30gun" in context


def test_build_context_general_question_not_sensitive(db):
    from apps.ai.views import _build_context

    context, sensitive = _build_context("Bugün ciro ne kadar?")
    assert sensitive is False


# ------------------------------------------------------------------
#  Public yayın kapısı
# ------------------------------------------------------------------
@pytest.fixture(scope="module")
def release_gate():
    spec = importlib.util.spec_from_file_location(
        "public_release_check", ROOT / "scripts" / "public_release_check.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "path",
    [
        "patent/INVENTION_DISCLOSURE.md",
        ".claude/commands/ai-compliance-hsp.md",
        "PHASE_2_REPORT.md",
        "DISCOVERY_REPORT.md",
        ".env",
        "restaurant.sqlite3",
        "restaurant.sqlite3-wal",
        "backups/2026/full.zip",
        "logs/security.log",
        "media/fis.jpg",
        "Uygulama/restaurant.exe",
        "config/server.key",
    ],
)
def test_release_gate_flags_forbidden_paths(release_gate, path):
    assert any(
        pattern.search(path) for pattern, _ in release_gate.FORBIDDEN_TRACKED_PATTERNS
    ), f"Yasak yol yakalanmadı: {path}"


@pytest.mark.parametrize(
    "path",
    [
        "apps/backups/models.py",  # yedekleme MODÜLÜ kaynak kodu serbesttir
        "templates/backups/index.html",
        ".env.example",
        "media/.gitkeep",
        "apps/ai/views.py",
    ],
)
def test_release_gate_allows_legitimate_paths(release_gate, path):
    assert not any(
        pattern.search(path) for pattern, _ in release_gate.FORBIDDEN_TRACKED_PATTERNS
    ), f"Meşru yol yanlışlıkla engellendi: {path}"


def test_release_gate_required_gitignore_entries_present(release_gate):
    content = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for entry in release_gate.REQUIRED_GITIGNORE_ENTRIES:
        assert entry in content, f".gitignore'da eksik: {entry}"


def test_release_gate_internal_material_never_tracked(release_gate):
    """Dahili çalışma malzemesi public depoda izlenmemelidir.

    Depo kapsamı ve kurumsal hijyen kuralıdır: bu dosyalar ürünün parçası
    değildir ve yayımlanan depoda bulunmazlar.
    """
    tracked = release_gate._tracked_files()
    for pattern, label in release_gate.FORBIDDEN_TRACKED_PATTERNS:
        offenders = [p for p in tracked if pattern.search(p)]
        assert not offenders, f"{label}: {offenders[:5]}"


def test_release_gate_requirement_parser(release_gate, tmp_path):
    req = tmp_path / "requirements.txt"
    req.write_text(
        "Django==5.2.16\nhttpx>=0.28\npsycopg[binary]==3.2.3\n# yorum\n-r base.txt\n",
        encoding="utf-8",
    )
    assert release_gate._requirement_names(req) == ["Django", "httpx", "psycopg"]


# ==================================================================
#  Faz F2 — Saklama süresi temizliği (purge_expired_logs)
# ==================================================================
from datetime import timedelta  # noqa: E402

from django.core.management import call_command  # noqa: E402
from django.test import override_settings  # noqa: E402
from django.utils import timezone  # noqa: E402

RETENTION_90 = {
    "AUDIT_IP_DAYS": 90,
    "CONSENT_IP_DAYS": 90,
    "RESERVATION_GUEST_DAYS": 90,
    "WAITLIST_GUEST_DAYS": 90,
}


@pytest.fixture
def old_audit_log(db):
    from apps.core.models import AuditLog

    return AuditLog.objects.create(
        action=AuditLog.Action.LOGIN,
        username_snapshot="eski",
        timestamp=timezone.now() - timedelta(days=120),
        ip_address="10.0.0.1",
        user_agent="EskiTarayici/1.0",
    )


@pytest.fixture
def old_reservation(db):
    from apps.floor.models import Reservation

    reservation = Reservation.objects.create(
        code="RTEST0001",
        guest_name="Eski Misafir",
        guest_phone="05321112233",
        guest_email="eski@example.invalid",
        party_size=4,
        reserved_at=timezone.now() - timedelta(days=120),
        status=Reservation.Status.COMPLETED,
        special_requests="Cam kenarı",
        allergy_notes="Gluten",
    )
    # auto_now alanı elle eskitilir
    Reservation.objects.filter(pk=reservation.pk).update(
        updated_at=timezone.now() - timedelta(days=120)
    )
    return reservation


@override_settings(RETENTION=RETENTION_90)
def test_purge_preview_changes_nothing(old_audit_log, old_reservation):
    call_command("purge_expired_logs")

    old_audit_log.refresh_from_db()
    old_reservation.refresh_from_db()
    assert old_audit_log.ip_address == "10.0.0.1"
    assert old_reservation.guest_name == "Eski Misafir"


@override_settings(RETENTION=RETENTION_90)
def test_purge_apply_redacts_old_audit_ip_keeps_recent(old_audit_log, db):
    from apps.core.models import AuditLog

    recent = AuditLog.objects.create(
        action=AuditLog.Action.LOGIN,
        username_snapshot="yeni",
        ip_address="10.0.0.2",
        user_agent="YeniTarayici/2.0",
    )

    call_command("purge_expired_logs", "--apply")

    old_audit_log.refresh_from_db()
    recent.refresh_from_db()
    assert old_audit_log.ip_address is None
    assert old_audit_log.user_agent == ""
    # Kayıt silinmedi; olay bilgisi duruyor.
    assert old_audit_log.username_snapshot == "eski"
    assert recent.ip_address == "10.0.0.2"
    # Kanıt kaydı düşüldü.
    assert AuditLog.objects.filter(
        action=AuditLog.Action.DATA_ERASURE, description__contains="purge_expired_logs"
    ).exists()


@override_settings(RETENTION=RETENTION_90)
def test_purge_apply_redacts_consent_ip(db):
    from apps.crm.models import ConsentRecord, Customer

    customer = Customer.objects.create(first_name="Rıza", last_name="Testi")
    consent = ConsentRecord.objects.create(
        customer=customer,
        kind=ConsentRecord.Kind.MARKETING_SMS,
        granted=True,
        ip_address="10.0.0.3",
    )
    ConsentRecord.objects.filter(pk=consent.pk).update(
        created_at=timezone.now() - timedelta(days=120)
    )

    call_command("purge_expired_logs", "--apply")

    consent.refresh_from_db()
    # IP redakte edildi; rıza kanıtının kendisi (tür/karar) korunur.
    assert consent.ip_address is None
    assert consent.granted is True
    assert consent.kind == ConsentRecord.Kind.MARKETING_SMS


@override_settings(RETENTION=RETENTION_90)
def test_purge_apply_redacts_reservation_and_waitlist(old_reservation, db):
    from apps.floor.models import WaitlistEntry

    entry = WaitlistEntry.objects.create(
        guest_name="Bekleyen Misafir",
        guest_phone="05324445566",
        status=WaitlistEntry.Status.LEFT,
        note="Bebek sandalyesi",
    )
    WaitlistEntry.objects.filter(pk=entry.pk).update(
        updated_at=timezone.now() - timedelta(days=120)
    )

    call_command("purge_expired_logs", "--apply")

    old_reservation.refresh_from_db()
    entry.refresh_from_db()
    assert old_reservation.guest_name == "Anonim Misafir"
    assert old_reservation.guest_phone == ""
    assert old_reservation.guest_email == ""
    assert old_reservation.allergy_notes == ""
    # Operasyonel istatistik alanları korunur.
    assert old_reservation.party_size == 4
    assert old_reservation.status == old_reservation.Status.COMPLETED
    assert entry.guest_name == "Anonim Misafir"
    assert entry.guest_phone == ""
    assert entry.note == ""


@override_settings(RETENTION=RETENTION_90)
def test_purge_skips_active_reservations(db):
    from apps.floor.models import Reservation

    active = Reservation.objects.create(
        code="RTEST0002",
        guest_name="Aktif Misafir",
        guest_phone="05327778899",
        party_size=2,
        reserved_at=timezone.now() + timedelta(days=1),
        status=Reservation.Status.CONFIRMED,
    )
    Reservation.objects.filter(pk=active.pk).update(updated_at=timezone.now() - timedelta(days=120))

    call_command("purge_expired_logs", "--apply")

    active.refresh_from_db()
    # Sonuçlanmamış rezervasyon eskimiş olsa da redakte edilmez.
    assert active.guest_name == "Aktif Misafir"


def test_purge_disabled_by_default(old_audit_log):
    # Varsayılan RETENTION değerleri 0'dır: komut hiçbir şey değiştirmez.
    call_command("purge_expired_logs", "--apply")
    old_audit_log.refresh_from_db()
    assert old_audit_log.ip_address == "10.0.0.1"


# ==================================================================
#  Faz F2 — D7: Maaş alanları yalnızca staff.manage ile
# ==================================================================
@pytest.fixture
def head_waiter(db):
    from django.contrib.auth import get_user_model

    from apps.accounts.permissions import Role

    return get_user_model().objects.create_user(
        username="sefgarson", password="Test!2026Pass", role=Role.HEAD_WAITER
    )


def test_employee_detail_does_not_expose_salary(client, head_waiter, waiter, db):
    from decimal import Decimal

    from apps.hr.models import Employee

    employee = Employee.objects.create(
        user=waiter,
        monthly_salary=Decimal("47391.55"),
        hourly_rate=Decimal("183.77"),
    )
    assert head_waiter.has_perm_code("staff.view")
    assert not head_waiter.has_perm_code("staff.manage")

    client.force_login(head_waiter)
    response = client.get(f"/personel/{employee.pk}/")

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "47391" not in content and "47.391" not in content
    assert "183,77" not in content and "183.77" not in content


def test_employee_create_requires_staff_manage(client, head_waiter, db):
    client.force_login(head_waiter)
    response = client.get("/personel/yeni/")
    # staff.view yeterli değildir; maaş alanlarını içeren form açılmaz.
    assert response.status_code in (302, 403)


# ==================================================================
#  Faz F2 — D6: JWT refresh rotasyonunda eski token kara listeye girer
# ==================================================================
def test_jwt_refresh_rotation_blacklists_old_token(client, manager, db):
    obtain = client.post("/api/auth/token/", {"username": "mudur", "password": "Test!2026Pass"})
    assert obtain.status_code == 200
    old_refresh = obtain.json()["refresh"]

    first = client.post("/api/auth/token/refresh/", {"refresh": old_refresh})
    assert first.status_code == 200
    assert first.json()["refresh"] != old_refresh  # rotasyon açık

    replay = client.post("/api/auth/token/refresh/", {"refresh": old_refresh})
    assert replay.status_code == 401  # eski token kara listede


# ==================================================================
#  Faz F3 — Kişisel veri envanteri kodla senkron (CI kapısı)
# ==================================================================
def test_personal_data_inventory_covers_all_candidates(db):
    """Yeni bir kişisel veri adayı alanı envantere işlenmeden CI geçmez."""
    from apps.core.privacy import inventory_field_index, scan_personal_data_fields

    index = inventory_field_index()
    missing = [
        f"{model}.{field}"
        for model, field in scan_personal_data_fields()
        if (model, field) not in index
    ]
    assert not missing, (
        "Envanterde olmayan kişisel veri adayı alanlar var. "
        "docs/data_inventory.json dosyasına işleyin (gerekirse personal:false + gerekçe): "
        + ", ".join(missing)
    )


def test_personal_data_inventory_has_no_stale_entries(db):
    """Envanter, kodda artık bulunmayan alanları işaret etmemeli."""
    from apps.core.privacy import inventory_field_index, scan_personal_data_fields

    known = set(scan_personal_data_fields())
    stale = [
        f"{model}.{field}"
        for model, field in inventory_field_index()
        if (model, field) not in known
    ]
    assert not stale, "Envanterde kodda karşılığı olmayan (bayat) kayıtlar var: " + ", ".join(stale)


def test_personal_data_inventory_entries_are_complete():
    from apps.core.privacy import load_inventory

    for entry in load_inventory()["fields"]:
        for key in ("model", "field", "personal", "category", "subject", "purpose", "retention"):
            assert (
                key in entry
            ), f"Envanter kaydında '{key}' eksik: {entry.get('model')}.{entry.get('field')}"


def test_special_category_fields_flagged():
    """Alerji alanları özel nitelikli veri adayı olarak işaretli olmalı."""
    from apps.core.privacy import inventory_field_index

    index = inventory_field_index()
    for key in [("crm.Customer", "allergy_notes"), ("floor.Reservation", "allergy_notes")]:
        assert index[key].get("special_category") is True


# ==================================================================
#  Faz F3 — DSR: müşteri veri dosyası dışa aktarma
# ==================================================================
def test_customer_data_export_service_content(allergic_customer, db):
    from apps.crm.models import ConsentRecord
    from apps.crm.services import customer_data_export

    ConsentRecord.objects.create(
        customer=allergic_customer,
        kind=ConsentRecord.Kind.MARKETING_SMS,
        granted=True,
        source="test",
    )
    data = customer_data_export(allergic_customer)

    assert data["profil"]["ad"] == "Ayşe"
    assert data["profil"]["telefon"] == "05329876543"
    assert data["profil"]["alerji_notlari"].startswith("Fıstık")
    assert len(data["rizalar"]) == 1
    assert data["rizalar"][0]["verildi"] is True
    for key in ("sadakat_hareketleri", "rezervasyonlar", "siparisler", "yorumlar"):
        assert key in data


def test_customer_data_export_requires_pii_permission(client, cashier, allergic_customer):
    assert not cashier.has_perm_code("customer.pii")
    client.force_login(cashier)
    response = client.get(f"/musteri/{allergic_customer.pk}/veri-dosyasi/")
    assert response.status_code in (302, 403)


def test_customer_data_export_download_and_audit(client, manager, allergic_customer, db):
    from apps.core.models import AuditLog

    client.force_login(manager)
    response = client.get(f"/musteri/{allergic_customer.pk}/veri-dosyasi/")

    assert response.status_code == 200
    assert "attachment" in response["Content-Disposition"]
    body = response.content.decode("utf-8")
    assert "Ayşe" in body and "Fıstık" in body
    # İndirme denetim kaydına işlendi.
    assert AuditLog.objects.filter(
        action=AuditLog.Action.EXPORT, description__contains="KVKK veri dosyası"
    ).exists()


# ==================================================================
#  Faz F4 — Sağlayıcı governance metadata'sı
# ==================================================================
def test_provider_status_includes_governance():
    from apps.ai.providers import provider_status

    rows = {row["key"]: row for row in provider_status()}
    assert rows, "Sağlayıcı listesi boş olmamalı"
    for key, row in rows.items():
        gov = row["governance"]
        assert {"region", "training_use", "retention", "reviewed"} <= set(gov), key


def test_local_providers_reviewed_cloud_requires_review():
    from apps.ai.providers import provider_status

    for row in provider_status():
        gov = row["governance"]
        if row["is_local"]:
            assert gov["reviewed"] is True
            assert "çıkmaz" in gov["region"]
        else:
            # Doğrulanmamış bulut sağlayıcı REVIEW_REQUIRED taşımalı
            # (işletme .env ile doğruladıysa reviewed=True olabilir).
            if not gov["reviewed"]:
                assert "REVIEW_REQUIRED" in gov["training_use"]


# ==================================================================
#  Faz F4 — Prompt kayıt defteri
# ==================================================================
def test_all_prompts_are_registered():
    from apps.ai import prompts

    constants = set(prompts.prompt_constants())
    registered = set(prompts.PROMPT_REGISTRY)
    missing = constants - registered
    stale = registered - constants
    assert not missing, f"Kayıt defterinde olmayan istemler: {missing}"
    assert not stale, f"Kayıt defterinde bayat istemler: {stale}"


def test_registered_prompts_have_version_and_hash():
    from apps.ai.prompts import registered_prompts

    for name, meta in registered_prompts().items():
        assert meta["version"], name
        assert meta["purpose"], name
        assert len(meta["sha256_16"]) == 16, name
        assert meta["length"] > 0, name


# ==================================================================
#  Faz F4 — İçgörü gerekçe-makbuzu
# ==================================================================
def test_insight_receipt_maps_prompt_and_metadata(db):
    from apps.ai.models import AIInsight

    insight = AIInsight.objects.create(
        kind=AIInsight.Kind.DAILY_SUMMARY,
        title="Test özeti",
        summary="özet",
        provider="lmstudio",
        model="test-model",
        data_points=42,
        confidence=AIInsight.Confidence.HIGH,
    )
    receipt = insight.receipt
    assert receipt["istem"] == "DAILY_SUMMARY"
    assert receipt["istem_surumu"] == "1.0"
    assert receipt["saglayici"] == "lmstudio"
    assert receipt["veri_noktasi"] == 42
    assert receipt["uretici"] == "AI"


def test_insight_receipt_rule_based_fallback(db):
    from apps.ai.models import AIInsight

    insight = AIInsight.objects.create(
        kind=AIInsight.Kind.STOCK_FORECAST,
        title="Stok tahmini",
        summary="özet",
        generated_by_ai=False,
    )
    receipt = insight.receipt
    assert receipt["uretici"] == "kural tabanlı"
    assert receipt["istem"] == "-"


# ==================================================================
#  Yayın kapısı: dahili çalışma malzemesi public'e çıkamaz
# ==================================================================
#  Kural, tek bir dosyayı adıyla engellemekten DAHA GENİŞ tutulur:
#  ajan/asistan talimat dosyaları ve dahili durum raporları ürünün
#  parçası değildir. Adıyla engellemek, yarın eklenen bir kardeş dosyayı
#  sessizce serbest bırakıyordu.
@pytest.mark.parametrize(
    "path",
    [
        ".claude/commands/ai-compliance-hsp.md",
        ".claude/commands/baska-komut.md",
        ".claude/settings.json",
        "DISCOVERY_REPORT.md",
        "HSP_PROJECT_REVIEW.md",
        "PHASE_3_REPORT.md",
        "PUBLIC_RELEASE_READINESS.md",
        "TEST_REPORT.md",
        "PACKAGING_TEST.md",
        "IMPLEMENTATION_PLAN.md",
    ],
)
def test_release_gate_flags_internal_material(release_gate, path):
    assert any(
        pattern.search(path) for pattern, _ in release_gate.FORBIDDEN_TRACKED_PATTERNS
    ), f"Dahili malzeme yakalanmadı: {path}"


@pytest.mark.parametrize(
    "path",
    [
        "docs/known-limitations.md",
        "docs/ROPA_HAZIRLIK.md",
        "README.md",
        "SECURITY.md",
        "CHANGELOG.md",
        "AI_TRANSPARENCY.md",
    ],
)
def test_release_gate_allows_product_documentation(release_gate, path):
    """Ürün belgeleri "rapor benzeri" adlar yüzünden engellenmemeli."""
    assert not any(
        pattern.search(path) for pattern, _ in release_gate.FORBIDDEN_TRACKED_PATTERNS
    ), f"Meşru belge yanlışlıkla engellendi: {path}"
