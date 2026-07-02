"""PLAN 14.3: the read-only audit viewer over core_audit_log (D-010). Proves rows come back,
the filters (entity_table / action) narrow, tenant isolation holds (tenant A cannot see
tenant B's audit rows), pagination works, and the read is guarded by admin.audit.read.

Audit rows are seeded the natural way — creating a user/role over the admin API writes
INSERT rows for the audited User/Role entities (they are AuditMixin), so the viewer reads back
real capture output, not hand-inserted fixtures.
"""

from httpx import ASGITransport, AsyncClient

from tests.conftest import assert_query_budget

_ADMIN = "/api/v1/admin"


async def _seed_audit_rows(client):
    """Create a user + a role over the wire so core_audit_log gets INSERT rows for both."""
    await client.post(
        f"{_ADMIN}/users", json={"email": "audited@acme.test", "password": "longenough1"}
    )
    await client.post(f"{_ADMIN}/roles", json={"name": "AuditedRole", "permissions": []})


async def test_audit_viewer_returns_rows(admin_client):
    await _seed_audit_rows(admin_client)
    resp = await admin_client.get(f"{_ADMIN}/audit-logs")
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert len(items) >= 2
    row = items[0]
    assert {"entity_table", "entity_id", "action", "diff", "created_at"} <= row.keys()


async def test_filter_by_entity_table(admin_client):
    await _seed_audit_rows(admin_client)
    resp = await admin_client.get(f"{_ADMIN}/audit-logs?entity_table=core_users")
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert items  # at least the created user
    assert all(row["entity_table"] == "core_users" for row in items)


async def test_filter_by_action(admin_client):
    await _seed_audit_rows(admin_client)
    resp = await admin_client.get(f"{_ADMIN}/audit-logs?action=INSERT")
    assert resp.status_code == 200, resp.text
    assert all(row["action"] == "INSERT" for row in resp.json()["items"])


async def test_password_hash_never_in_diff(admin_client):
    """The capture excludes password_hash; the viewer surfaces the raw diff, so a created
    user's INSERT diff must not carry the credential (D-010)."""
    await admin_client.post(
        f"{_ADMIN}/users", json={"email": "secret@acme.test", "password": "supersecret1"}
    )
    resp = await admin_client.get(f"{_ADMIN}/audit-logs?entity_table=core_users")
    for row in resp.json()["items"]:
        new = (row["diff"] or {}).get("new", {})
        assert "password_hash" not in new


async def test_audit_is_tenant_isolated(admin_client, app, user_factory):
    """Tenant A's admin must NOT see tenant B's audit rows (D-007). Uses a SEPARATE client for
    tenant B — admin_client and the conftest `client` are the same object, so tenant B needs its
    own AsyncClient against the same app to avoid clobbering tenant A's bearer token."""
    # Seed tenant A (admin_client's tenant).
    await _seed_audit_rows(admin_client)
    # Seed tenant B through a second admin principal on its OWN client.
    other = await user_factory(slug="tenant-b-co", email="owner@b.test", admin=True)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as b_client:
        login = await b_client.post(
            "/api/v1/auth/login",
            json={
                "tenant_slug": other.tenant_slug,
                "email": other.email,
                "password": other.password,
            },
        )
        b_client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
        await b_client.post(
            f"{_ADMIN}/users", json={"email": "b-only@b.test", "password": "longenough1"}
        )
        b_view = await b_client.get(f"{_ADMIN}/audit-logs?entity_table=core_users")
        b_ids = {row["entity_id"] for row in b_view.json()["items"]}

    # Tenant A's viewer must never surface tenant B's rows.
    resp = await admin_client.get(f"{_ADMIN}/audit-logs?entity_table=core_users")
    a_ids = {row["entity_id"] for row in resp.json()["items"]}
    assert b_ids  # tenant B does see its own rows
    assert a_ids  # tenant A sees its own rows
    assert a_ids.isdisjoint(b_ids)


async def test_pagination(admin_client):
    # Seed several rows, then page with limit=1 and follow the cursor.
    for i in range(3):
        await admin_client.post(
            f"{_ADMIN}/roles", json={"name": f"Role{i}", "permissions": []}
        )
    first = await admin_client.get(f"{_ADMIN}/audit-logs?limit=1")
    assert first.status_code == 200, first.text
    body = first.json()
    assert len(body["items"]) == 1
    assert body["next_cursor"] is not None
    second = await admin_client.get(
        f"{_ADMIN}/audit-logs?limit=1&cursor={body['next_cursor']}"
    )
    assert second.status_code == 200, second.text
    assert second.json()["items"][0]["id"] != body["items"][0]["id"]


async def test_audit_requires_permission(authed_client):
    resp = await authed_client.get(f"{_ADMIN}/audit-logs")
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "rbac.permission_denied"


async def test_audit_query_budget(admin_client, query_counter):
    await _seed_audit_rows(admin_client)
    await assert_query_budget(admin_client, query_counter, f"{_ADMIN}/audit-logs")
