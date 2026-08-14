"""Machine credential (Phase 18 / spec Q1): the ApiKey row, its key string, and the
`get_current_user` branch that turns one into the ordinary request principal.

The model mirrors RefreshSession — hashed secret, revocation, expiry — and is an ordinary
TenantMixin model, so it is read and written through the D-007 filter with no bypass.

The authentication tests drive the ADMIN endpoints deliberately: they are guarded by core
RBAC keys the shared `admin_user` fixture already holds, so the whole credential can be
exercised from tests/core without importing another module's factories.
"""

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import API_KEY_PREFIX, mint_api_key, parse_api_key
from app.core.models import ApiKey, AuditLog
from app.core.rbac import ADMIN_USER_MANAGE
from app.core.tenancy import tenant_context
from app.modules.admin.models import Tenant
from tests.conftest import ProvisionedUser, QueryCounter, assert_query_budget


async def test_api_key_row_round_trips(
    db_session: AsyncSession, provisioned_user: ProvisionedUser
) -> None:
    """The model persists and reads back under the ordinary tenant filter (D-007)."""
    with tenant_context(provisioned_user.tenant_id):
        db_session.add(
            ApiKey(
                user_id=provisioned_user.user_id,
                name="website",
                prefix="atk_abc123",
                secret_sha256="0" * 64,
                scopes=["inventory.item.read"],
                expires_at=datetime.now(UTC) + timedelta(days=365),
            )
        )
        await db_session.flush()

        found = (await db_session.execute(select(ApiKey))).scalar_one()

    assert found.tenant_id == provisioned_user.tenant_id
    assert found.name == "website"
    assert found.scopes == ["inventory.item.read"]
    assert found.revoked_at is None


def test_mint_and_parse_round_trip() -> None:
    tenant_id = uuid.uuid4()
    full, digest = mint_api_key(tenant_id)
    assert full.startswith(f"atk_{tenant_id.hex}_")
    parsed = parse_api_key(full)
    assert parsed is not None
    parsed_tenant_id, parsed_digest = parsed
    assert parsed_tenant_id == tenant_id
    assert parsed_digest == digest


def test_mint_is_unpredictable() -> None:
    tenant_id = uuid.uuid4()
    a, _ = mint_api_key(tenant_id)
    b, _ = mint_api_key(tenant_id)
    assert a != b


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "atk_",
        "atk_acme",
        "notakey",
        "atk__secret",
        "Bearer atk_acme_x",
        # A non-UUID ref: the ref is the tenant id, so anything that is not one is
        # malformed and must be rejected without raising (parse feeds a 401, not a 500).
        "atk_acme_secretsecret",
        f"atk_{uuid.uuid4().hex}_",
    ],
)
def test_parse_rejects_malformed(bad: str) -> None:
    """A malformed credential must return None, never raise — deps.py turns None into a
    401, and an exception there would surface as a 500."""
    assert parse_api_key(bad) is None


# --- Authenticating a request with a key --------------------------------------

ApiKeyFactory = Callable[..., Awaitable[str]]


@pytest.fixture
def api_key_factory(db_session: AsyncSession) -> ApiKeyFactory:
    """Mint a real key for a provisioned principal and persist its row, returning the full
    key string — the only thing a client ever holds. The row goes in under the ordinary
    tenant context (D-025: fixtures use real code paths, no system_context bypass)."""

    async def _make(
        principal: ProvisionedUser,
        *,
        scopes: list[str] | None = None,
        revoked: bool = False,
        expires_at: datetime | None = None,
        tenant_ref: uuid.UUID | None = None,
    ) -> str:
        full, digest = mint_api_key(tenant_ref or principal.tenant_id)
        with tenant_context(principal.tenant_id):
            db_session.add(
                ApiKey(
                    user_id=principal.user_id,
                    name="website",
                    # Scheme + tenant ref, built from its parts like the real issuer
                    # (admin/service.create_api_key): slicing the key on its LAST
                    # underscore lands inside the urlsafe secret about half the time.
                    prefix=f"{API_KEY_PREFIX}_{(tenant_ref or principal.tenant_id).hex}",
                    secret_sha256=digest,
                    scopes=scopes,
                    expires_at=expires_at,
                    revoked_at=datetime.now(UTC) if revoked else None,
                )
            )
            await db_session.commit()
        return full

    return _make


def _bearer(full_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {full_key}"}


async def test_api_key_authenticates(
    client: AsyncClient, admin_user: ProvisionedUser, api_key_factory: ApiKeyFactory
) -> None:
    """A key resolves to the same principal a JWT would, so a guarded route just works —
    no router, no require_permission call and no idempotency path changed."""
    full = await api_key_factory(admin_user, scopes=[ADMIN_USER_MANAGE])

    response = await client.get("/api/v1/admin/users", headers=_bearer(full))

    assert response.status_code == 200, response.text


async def test_null_scopes_inherit_the_user_unnarrowed(
    client: AsyncClient, admin_user: ProvisionedUser, api_key_factory: ApiKeyFactory
) -> None:
    """NULL scopes mean "inherit" — the key carries the user's whole permission set."""
    full = await api_key_factory(admin_user, scopes=None)

    response = await client.get("/api/v1/admin/roles", headers=_bearer(full))

    assert response.status_code == 200, response.text


async def test_scopes_narrow_the_user(
    client: AsyncClient, admin_user: ProvisionedUser, api_key_factory: ApiKeyFactory
) -> None:
    """admin_user holds admin.role.manage; this key does not, so the key cannot use it."""
    full = await api_key_factory(admin_user, scopes=[ADMIN_USER_MANAGE])

    response = await client.get("/api/v1/admin/roles", headers=_bearer(full))

    assert response.status_code == 403, response.text


async def test_scopes_never_widen_the_user(
    client: AsyncClient,
    provisioned_user: ProvisionedUser,
    api_key_factory: ApiKeyFactory,
) -> None:
    """Scopes INTERSECT the resolved permissions (D-009): provisioned_user holds no roles,
    so a key scoped to admin.user.manage still cannot call it."""
    full = await api_key_factory(provisioned_user, scopes=[ADMIN_USER_MANAGE])

    response = await client.get("/api/v1/admin/users", headers=_bearer(full))

    assert response.status_code == 403, response.text


async def test_key_lookup_is_filtered_by_the_tenant_in_the_key(
    client: AsyncClient,
    admin_user: ProvisionedUser,
    user_factory: Callable[..., Awaitable[ProvisionedUser]],
    api_key_factory: ApiKeyFactory,
) -> None:
    """The attack the design is shaped against: a tenant-B key presented with tenant A's
    ref. The ContextVar is set from the ref BEFORE the lookup, so the D-007 filter hides
    B's row and the key resolves to nothing — 401, not a cross-tenant principal."""
    victim = admin_user
    attacker = await user_factory(slug="beta", email="owner@beta.test", admin=True)
    full = await api_key_factory(
        attacker, scopes=[ADMIN_USER_MANAGE], tenant_ref=victim.tenant_id
    )

    response = await client.get("/api/v1/admin/users", headers=_bearer(full))

    assert response.status_code == 401, response.text


async def test_key_cannot_reach_another_tenant(
    client: AsyncClient,
    admin_user: ProvisionedUser,
    user_factory: Callable[..., Awaitable[ProvisionedUser]],
    api_key_factory: ApiKeyFactory,
) -> None:
    """Downstream reads inherit the tenant the key set: another tenant's user is a 404."""
    other = await user_factory(slug="beta", email="owner@beta.test", admin=True)
    full = await api_key_factory(admin_user, scopes=[ADMIN_USER_MANAGE])

    response = await client.get(
        f"/api/v1/admin/users/{other.user_id}", headers=_bearer(full)
    )

    assert response.status_code == 404, response.text


async def test_revoked_key_is_rejected(
    client: AsyncClient, admin_user: ProvisionedUser, api_key_factory: ApiKeyFactory
) -> None:
    full = await api_key_factory(admin_user, scopes=[ADMIN_USER_MANAGE], revoked=True)

    response = await client.get("/api/v1/admin/users", headers=_bearer(full))

    assert response.status_code == 401, response.text


async def test_expired_key_is_rejected(
    client: AsyncClient, admin_user: ProvisionedUser, api_key_factory: ApiKeyFactory
) -> None:
    full = await api_key_factory(
        admin_user,
        scopes=[ADMIN_USER_MANAGE],
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )

    response = await client.get("/api/v1/admin/users", headers=_bearer(full))

    assert response.status_code == 401, response.text


async def test_forged_key_is_rejected(
    client: AsyncClient, admin_user: ProvisionedUser
) -> None:
    """A forged ref (no such tenant) and a forged secret against the REAL tenant return the
    same 401 envelope, so the response is not an oracle for whether the tenant exists."""
    for raw in (
        f"atk_{uuid.uuid4().hex}_forgedsecret",  # no such tenant
        f"atk_{admin_user.tenant_id.hex}_forgedsecret",  # real tenant, no such secret
    ):
        response = await client.get("/api/v1/admin/users", headers=_bearer(raw))
        assert response.status_code == 401, response.text


async def test_key_auth_stays_within_the_query_budget(
    client: AsyncClient,
    admin_user: ProvisionedUser,
    api_key_factory: ApiKeyFactory,
    query_counter: Callable[[], QueryCounter],
) -> None:
    """PERFORMANCE §2 on the key path. Measured warm breakdown, exactly 3: the tenant-ref
    resolution, the user load with the key JOINED onto it (not a second SELECT), and the
    page select. The key fold works — auth costs a key request the same one query it costs
    a JWT request — but resolving the ref to a tenant id spends the budget's one query of
    slack, so an API-key list request sits AT the ceiling with no margin. A fourth query
    here is a real regression, never a reason to raise the budget."""
    full = await api_key_factory(admin_user, scopes=[ADMIN_USER_MANAGE])
    client.headers["Authorization"] = f"Bearer {full}"

    await assert_query_budget(client, query_counter, "/api/v1/admin/users")


async def test_key_stamps_the_audit_actor(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_user: ProvisionedUser,
    api_key_factory: ApiKeyFactory,
) -> None:
    """D-010: the key is bound to a real core_users row, so a write it makes leaves a
    resolvable actor — the reason a synthetic principal id was rejected."""
    full = await api_key_factory(admin_user, scopes=[ADMIN_USER_MANAGE])

    response = await client.post(
        "/api/v1/admin/users",
        headers=_bearer(full),
        json={"email": "kiosk@acme.test", "password": "correct-horse-battery"},
    )

    assert response.status_code == 201, response.text
    created_id = response.json()["id"]
    with tenant_context(admin_user.tenant_id):
        actors = (
            (
                await db_session.execute(
                    select(AuditLog.actor_user_id).where(
                        AuditLog.entity_table == "core_users",
                        AuditLog.entity_id == created_id,
                    )
                )
            )
            .scalars()
            .all()
        )
    assert list(actors) == [admin_user.user_id]


# --- The budget-and-contract regression net (D-069's measured claims) ----------


async def test_key_auth_costs_exactly_one_statement(
    client: AsyncClient,
    admin_user: ProvisionedUser,
    api_key_factory: ApiKeyFactory,
    query_counter: Callable[[], QueryCounter],
) -> None:
    """D-069 claims the key is loaded by JOIN onto the existing user load, never as a
    second SELECT. Pinned as an EXACT count, not a ceiling: authentication may spend one
    statement, the same one a JWT request spends, and the whole credential check — key,
    user and the tenant's is_active flag — rides in it.

    An earlier revision minted on the tenant SLUG and resolved it per request. That second
    statement fit /api/v1/admin/users (no ETag) at exactly 3 and hid there, while every
    list endpoint that also computes a collection ETag ran 4 — over PERFORMANCE §2's ≤3.
    """
    full = await api_key_factory(admin_user, scopes=[ADMIN_USER_MANAGE])
    client.headers["Authorization"] = f"Bearer {full}"
    await client.get("/api/v1/admin/users")  # warm the D-009 RBAC TTL cache

    with query_counter() as qc:
        response = await client.get("/api/v1/admin/users")

    assert response.status_code == 200, response.text
    # auth join + page select. No slug resolve, no second key SELECT.
    assert qc.count == 2, "\n".join(qc.statements)
    auth_stmt = qc.statements[0]
    assert "core_api_keys" in auth_stmt and "core_users" in auth_stmt, auth_stmt
    assert "JOIN" in auth_stmt.upper(), auth_stmt
    # The spec's "not taken" list, made mechanical: no per-request last_used_at write, so
    # a read stays a read. A stamp added later shows up here as an UPDATE, not in review.
    assert all(s.lstrip().upper().startswith("SELECT") for s in qc.statements), "\n".join(
        qc.statements
    )


async def test_inactive_tenant_cannot_use_its_keys(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_user: ProvisionedUser,
    api_key_factory: ApiKeyFactory,
) -> None:
    """Deactivating a tenant kills its machine credentials on the very NEXT request. A JWT
    is 15 minutes of exposure; a key can live a year, so this check cannot wait for an
    expiry — and folding it into the auth join is what makes it free."""
    full = await api_key_factory(admin_user, scopes=[ADMIN_USER_MANAGE])
    assert (await client.get("/api/v1/admin/users", headers=_bearer(full))).status_code == 200

    tenant = await db_session.get_one(Tenant, admin_user.tenant_id)
    tenant.is_active = False
    await db_session.commit()

    response = await client.get("/api/v1/admin/users", headers=_bearer(full))

    assert response.status_code == 401, response.text
