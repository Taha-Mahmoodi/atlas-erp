"""PLAN 14.3: the admin role-management surface — create/list roles, read a role WITH its
permission keys, and read the global permission catalog. RBAC 403 for a principal lacking
admin.role.manage; query-count assertion pins the role list at the PERFORMANCE §2 budget and
proves the role->permissions attach is N+1-free.
"""

import uuid

from tests.conftest import assert_query_budget

_ADMIN = "/api/v1/admin"


async def test_create_role_with_permissions(admin_client):
    created = await admin_client.post(
        f"{_ADMIN}/roles",
        json={"name": "Clerk", "permissions": ["admin.audit.read", "admin.numbering.read"]},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["name"] == "Clerk"
    assert body["is_system"] is False
    assert sorted(body["permissions"]) == ["admin.audit.read", "admin.numbering.read"]


async def test_create_role_rejects_unknown_permission(admin_client):
    resp = await admin_client.post(
        f"{_ADMIN}/roles", json={"name": "Bogus", "permissions": ["not.a.real.key"]}
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "rbac.unknown_permission"


async def test_list_roles(admin_client):
    await admin_client.post(f"{_ADMIN}/roles", json={"name": "Zeta", "permissions": []})
    listed = await admin_client.get(f"{_ADMIN}/roles")
    assert listed.status_code == 200, listed.text
    names = [row["name"] for row in listed.json()["items"]]
    # The seeded Administrator role + the new Zeta; ordered by name (stable).
    assert "Administrator" in names
    assert "Zeta" in names
    assert names == sorted(names)


async def test_get_role_with_permissions(admin_client):
    created = await admin_client.post(
        f"{_ADMIN}/roles",
        json={"name": "Viewer", "permissions": ["admin.audit.read"]},
    )
    role_id = created.json()["id"]
    detail = await admin_client.get(f"{_ADMIN}/roles/{role_id}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["permissions"] == ["admin.audit.read"]


async def test_get_unknown_role_is_404(admin_client):
    resp = await admin_client.get(f"{_ADMIN}/roles/{uuid.uuid4()}")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "admin.role_not_found"


async def test_permission_catalog_lists_the_grantable_keys(admin_client):
    resp = await admin_client.get(f"{_ADMIN}/permissions")
    assert resp.status_code == 200, resp.text
    keys = {row["key"] for row in resp.json()}
    # The admin keys plus at least one finance key prove it is the full global catalog.
    assert {"admin.user.manage", "admin.role.manage", "admin.numbering.read"} <= keys
    assert any(key.startswith("finance.") for key in keys)


async def test_default_administrator_grant_stays_narrow(admin_client):
    """#165 widened ONBOARDING's first admin to the whole catalog by passing the keys explicitly.
    ``grant_admin_role``'s DEFAULT — what seed, the test factories and any future caller get — is
    unchanged: the six ``admin.*`` keys. Spelled out literally rather than compared against
    ``_ADMIN_PERMISSION_KEYS`` so widening that constant fails here instead of agreeing with
    itself."""
    listed = await admin_client.get(f"{_ADMIN}/roles")
    role_id = next(
        row["id"] for row in listed.json()["items"] if row["name"] == "Administrator"
    )
    detail = await admin_client.get(f"{_ADMIN}/roles/{role_id}")
    assert detail.json()["permissions"] == [
        "admin.apikey.manage",
        "admin.audit.read",
        "admin.numbering.read",
        "admin.role.manage",
        "admin.tenant.manage",
        "admin.user.manage",
    ]


async def test_roles_require_permission(authed_client):
    resp = await authed_client.get(f"{_ADMIN}/roles")
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "rbac.permission_denied"


async def test_permission_catalog_requires_permission(authed_client):
    resp = await authed_client.get(f"{_ADMIN}/permissions")
    assert resp.status_code == 403


async def test_list_roles_query_budget(admin_client, query_counter):
    await admin_client.post(f"{_ADMIN}/roles", json={"name": "Extra", "permissions": []})
    await assert_query_budget(admin_client, query_counter, f"{_ADMIN}/roles")
