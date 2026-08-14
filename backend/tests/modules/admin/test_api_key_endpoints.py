"""Phase 18 / spec Q1: the admin surface over machine credentials — create, list, revoke.

Driven over the wire by the admin_client principal (holds admin.apikey.manage); the
authed_client principal (no admin keys) proves the RBAC 403. The credential itself is
tested in tests/core/test_api_keys.py — what matters here is that the secret leaves the
API exactly once, that a tenant cannot scope a key to a permission no code checks
(D-009), and that revocation is immediate and idempotent.
"""

import uuid
from datetime import datetime

from httpx import AsyncClient

from app.core.rbac import ADMIN_USER_MANAGE
from tests.conftest import ProvisionedUser, assert_query_budget

_KEYS = "/api/v1/admin/api-keys"


def _instant(raw: str) -> datetime:
    """Compare stamps as naive UTC: aiosqlite hands DateTime(timezone=True) back NAIVE, so
    a value just written serializes with a trailing Z and the same value re-read does not
    (D-003 — asyncpg returns aware values on both paths)."""
    return datetime.fromisoformat(raw).replace(tzinfo=None)


async def _create_key(client: AsyncClient, user_id: uuid.UUID, **overrides: object) -> dict:
    payload: dict[str, object] = {
        "name": "website",
        "user_id": str(user_id),
        "scopes": [ADMIN_USER_MANAGE],
    }
    payload.update(overrides)
    response = await client.post(_KEYS, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def test_create_returns_the_secret_exactly_once(
    admin_client: AsyncClient, admin_user: ProvisionedUser
) -> None:
    body = await _create_key(admin_client, admin_user.user_id)
    assert body["key"].startswith("atk_")
    assert body["prefix"] == f"atk_{admin_user.tenant_slug}"
    assert "secret_sha256" not in body

    listed = await admin_client.get(_KEYS)
    assert listed.status_code == 200, listed.text
    row = listed.json()["items"][0]
    assert row["name"] == "website"
    assert row["scopes"] == [ADMIN_USER_MANAGE]
    assert row["revoked_at"] is None
    assert "key" not in row
    assert "secret_sha256" not in row


async def test_scopes_must_exist_in_the_catalog(
    admin_client: AsyncClient, admin_user: ProvisionedUser
) -> None:
    """D-009: a tenant cannot invent a permission key no code checks."""
    response = await admin_client.post(
        _KEYS,
        json={
            "name": "bad",
            "user_id": str(admin_user.user_id),
            "scopes": ["inventory.item.invented"],
        },
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "rbac.unknown_permission"


async def test_create_for_an_unknown_user_is_404(admin_client: AsyncClient) -> None:
    """The key binds to a real core_users row; an id from another tenant is simply
    not found under the D-007 filter."""
    response = await admin_client.post(
        _KEYS, json={"name": "orphan", "user_id": str(uuid.uuid4())}
    )
    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "admin.user_not_found"


async def test_null_scopes_are_accepted(
    admin_client: AsyncClient, admin_user: ProvisionedUser
) -> None:
    """Omitting scopes means "inherit the user's permissions unnarrowed"."""
    body = await _create_key(admin_client, admin_user.user_id, scopes=None)
    assert body["scopes"] is None


async def test_revoke_takes_effect_immediately(
    admin_client: AsyncClient, admin_user: ProvisionedUser
) -> None:
    created = await _create_key(admin_client, admin_user.user_id)
    key_auth = {"Authorization": f"Bearer {created['key']}"}

    works = await admin_client.get("/api/v1/admin/users", headers=key_auth)
    assert works.status_code == 200, works.text

    revoked = await admin_client.post(f"{_KEYS}/{created['id']}/revoke")
    assert revoked.status_code == 200, revoked.text

    denied = await admin_client.get("/api/v1/admin/users", headers=key_auth)
    assert denied.status_code == 401, denied.text


async def test_revoking_twice_is_not_an_error(
    admin_client: AsyncClient, admin_user: ProvisionedUser
) -> None:
    """Idempotent: a client retrying a revoke must not get an error back."""
    created = await _create_key(admin_client, admin_user.user_id)

    first = await admin_client.post(f"{_KEYS}/{created['id']}/revoke")
    second = await admin_client.post(f"{_KEYS}/{created['id']}/revoke")

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert _instant(second.json()["revoked_at"]) == _instant(first.json()["revoked_at"])
    listed = await admin_client.get(_KEYS)
    assert _instant(listed.json()["items"][0]["revoked_at"]) == _instant(
        first.json()["revoked_at"]
    )


async def test_revoke_unknown_key_is_404(admin_client: AsyncClient) -> None:
    response = await admin_client.post(f"{_KEYS}/{uuid.uuid4()}/revoke")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "admin.api_key_not_found"


async def test_endpoints_require_the_permission(authed_client: AsyncClient) -> None:
    """A principal without admin.apikey.manage is denied all three routes (D-009)."""
    listed = await authed_client.get(_KEYS)
    created = await authed_client.post(
        _KEYS, json={"name": "x", "user_id": str(uuid.uuid4())}
    )
    revoked = await authed_client.post(f"{_KEYS}/{uuid.uuid4()}/revoke")

    assert [listed.status_code, created.status_code, revoked.status_code] == [403, 403, 403]


async def test_keys_are_tenant_isolated(
    admin_client: AsyncClient, admin_user: ProvisionedUser, user_factory
) -> None:
    """The caller sees only their OWN tenant's keys (D-007)."""
    other = await user_factory(slug="other", email="owner@other.test", admin=True)
    other_token = (
        await admin_client.post(
            "/api/v1/auth/login",
            json={
                "tenant_slug": other.tenant_slug,
                "email": other.email,
                "password": other.password,
            },
        )
    ).json()["access_token"]
    await _create_key(admin_client, admin_user.user_id)

    listed = await admin_client.get(
        _KEYS, headers={"Authorization": f"Bearer {other_token}"}
    )

    assert listed.status_code == 200, listed.text
    assert listed.json()["items"] == []


async def test_list_api_keys_query_budget(
    admin_client: AsyncClient, admin_user: ProvisionedUser, query_counter
) -> None:
    """PERFORMANCE §2 on the list endpoint: auth user load + page select, ≤3."""
    await _create_key(admin_client, admin_user.user_id)
    await assert_query_budget(admin_client, query_counter, _KEYS)
