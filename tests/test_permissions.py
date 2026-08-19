"""Rol tabanlı yetkilendirme testleri."""

from __future__ import annotations

import pytest
from django.urls import reverse

from apps.accounts.permissions import ALL_PERMISSIONS, Role, permissions_for_role

pytestmark = pytest.mark.django_db


def test_owner_has_every_permission(owner):
    assert owner.effective_permissions == ALL_PERMISSIONS


def test_waiter_cannot_void_or_refund(waiter):
    assert waiter.has_perm_code("pos.use")
    assert not waiter.has_perm_code("pos.void")
    assert not waiter.has_perm_code("pos.refund")
    assert not waiter.has_perm_code("report.financial")


def test_chef_can_manage_recipes_but_not_users(chef):
    assert chef.has_perm_code("recipe.manage")
    assert chef.has_perm_code("inventory.manage")
    assert not chef.has_perm_code("user.manage")
    assert not chef.has_perm_code("pos.refund")


def test_cashier_can_manage_cash_but_not_menu(cashier):
    assert cashier.has_perm_code("cash.manage")
    assert not cashier.has_perm_code("menu.manage")


def test_manager_can_approve_sensitive_operations(manager):
    assert manager.can_approve("pos.void")
    assert manager.can_approve("pos.refund")


def test_waiter_cannot_approve(waiter):
    assert not waiter.can_approve("pos.void")


def test_extra_permission_grants_access(waiter):
    waiter.extra_permissions = ["pos.void"]
    waiter.save()
    assert waiter.has_perm_code("pos.void")


def test_denied_permission_overrides_role(manager):
    assert manager.has_perm_code("pos.refund")
    manager.denied_permissions = ["pos.refund"]
    manager.save()
    manager.refresh_from_db()
    assert not manager.has_perm_code("pos.refund")


def test_denied_beats_extra(waiter):
    """Reddedilen izin, ek izinden önce gelir."""
    waiter.extra_permissions = ["pos.void"]
    waiter.denied_permissions = ["pos.void"]
    waiter.save()
    assert not waiter.has_perm_code("pos.void")


def test_inactive_user_has_no_permissions(owner):
    owner.is_active = False
    owner.save()
    assert not owner.has_perm_code("dashboard.view")


def test_invalid_extra_permission_ignored(waiter):
    waiter.extra_permissions = ["olmayan.izin"]
    waiter.save()
    assert "olmayan.izin" not in waiter.effective_permissions


@pytest.mark.parametrize(
    "role",
    list(Role.values),
)
def test_every_role_has_dashboard_access(role):
    assert "dashboard.view" in permissions_for_role(role)


def test_waiter_blocked_from_user_management(client, waiter):
    client.force_login(waiter)
    response = client.get(reverse("accounts:user_list"))
    assert response.status_code == 403


def test_owner_reaches_user_management(client, owner):
    client.force_login(owner)
    response = client.get(reverse("accounts:user_list"))
    assert response.status_code == 200


def test_anonymous_redirected_to_login(client):
    response = client.get(reverse("reports:dashboard"))
    assert response.status_code == 302
    assert "/accounts/login/" in response["Location"]


def test_pin_verification(owner):
    assert owner.check_pin("5271")
    assert not owner.check_pin("9182")
    assert not owner.check_pin("")


def test_pin_must_be_numeric(owner):
    with pytest.raises(ValueError):
        owner.set_pin("abcd")


def test_pin_length_validated(owner):
    with pytest.raises(ValueError):
        owner.set_pin("12")
