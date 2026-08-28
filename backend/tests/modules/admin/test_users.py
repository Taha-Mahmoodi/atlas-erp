"""PLAN 14.3: the admin user-management surface — create/list users, assign a role, read a
user's roles. Driven over the wire by the admin_client principal (holds the admin keys); the
authed_client principal (no admin keys) proves the RBAC 403. Query-count assertion pins the
list endpoint at the PERFORMANCE §2 budget.
"""

import uuid

from tests.conftest import assert_query_budget

_ADMIN = "/api/v1/admin"


async def test_create_and_list_users(admin_client):
    created = await admin_client.post(
        f"{_ADMIN}/users",
        json={"email": "alice@acme.test", "password": "hunter2hunter2", "full_name": "Alice"},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["email"] == "alice@acme.test"
    assert body["full_name"] == "Alice"
    assert body["is_active"] is True
    assert "password" not in body and "password_hash" not in body

    listed = await admin_client.get(f"{_ADMIN}/users")
    assert listed.status_code == 200, listed.text
    emails = {row["email"] for row in listed.json()["items"]}
    # The seeded admin owner + the new alice are both in the caller's tenant.
    assert "alice@acme.test" in emails
    assert len(emails) >= 2


async def test_get_user_and_assign_role(admin_client):
    # Create a user + a role, then assign the role and read it back on the user.
    user_resp = await admin_client.post(
        f"{_ADMIN}/users",
        json={"email": "bob@acme.test", "password": "correcthorse1"},
    )
    user_id = user_resp.json()["id"]
    role_resp = await admin_client.post(
        f"{_ADMIN}/roles",
        json={"name": "Auditor", "permissions": ["admin.audit.read"]},
    )
    role_id = role_resp.json()["id"]

    assigned = await admin_client.post(
        f"{_ADMIN}/users/assign-role",
        json={"user_id": user_id, "role_id": role_id},
    )
    assert assigned.status_code == 201, assigned.text

    roles = await admin_client.get(f"{_ADMIN}/users/{user_id}/roles")
    assert roles.status_code == 200, roles.text
    assert [row["name"] for row in roles.json()] == ["Auditor"]


async def test_assign_role_twice_is_idempotent(admin_client):
    """#226: re-assigning a role the user already holds is a no-op, not a 500.

    The demo seed re-runs `assign-role` on every pass, so an unconditional INSERT tripped
    uq_core_user_roles_tenant_id_user_id_role_id and made `docker compose up` fail against an
    already-seeded volume.
    """
    user_id = (
        await admin_client.post(
            f"{_ADMIN}/users", json={"email": "dana@acme.test", "password": "correcthorse1"}
        )
    ).json()["id"]
    role_id = (
        await admin_client.post(
            f"{_ADMIN}/roles", json={"name": "Reviewer", "permissions": ["admin.audit.read"]}
        )
    ).json()["id"]
    body = {"user_id": user_id, "role_id": role_id}

    first = await admin_client.post(f"{_ADMIN}/users/assign-role", json=body)
    assert first.status_code == 201, first.text
    again = await admin_client.post(f"{_ADMIN}/users/assign-role", json=body)
    assert again.status_code == 201, again.text

    # Still exactly one assignment — the second call reused the row, it did not duplicate it.
    roles = await admin_client.get(f"{_ADMIN}/users/{user_id}/roles")
    assert [row["name"] for row in roles.json()] == ["Reviewer"]


async def test_get_unknown_user_is_404(admin_client):
    resp = await admin_client.get(f"{_ADMIN}/users/{uuid.uuid4()}")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "admin.user_not_found"


async def test_users_require_permission(authed_client):
    """A principal without admin.user.manage is denied (D-009)."""
    resp = await authed_client.get(f"{_ADMIN}/users")
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "rbac.permission_denied"


async def test_create_user_requires_permission(authed_client):
    resp = await authed_client.post(
        f"{_ADMIN}/users", json={"email": "x@y.test", "password": "longenough1"}
    )
    assert resp.status_code == 403


async def test_users_are_tenant_isolated(admin_client, user_factory):
    """The caller sees only their OWN tenant's users, never another tenant's (D-007)."""
    other = await user_factory(slug="other", email="owner@other.test", admin=True)
    listed = await admin_client.get(f"{_ADMIN}/users")
    emails = {row["email"] for row in listed.json()["items"]}
    assert other.email not in emails


async def test_list_users_query_budget(admin_client, query_counter):
    await admin_client.post(
        f"{_ADMIN}/users", json={"email": "c@acme.test", "password": "longenough1"}
    )
    await assert_query_budget(admin_client, query_counter, f"{_ADMIN}/users")
