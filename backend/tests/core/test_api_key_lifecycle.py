"""Adversarial lifecycle review of the Phase 18 machine credential (spec Q1).

Every key here is issued through the REAL admin endpoint and then attacked: revocation
(immediate, or only after the D-009 memo's 60 s TTL?), expiry at the exact boundary on a
frozen clock, the kill switches that live on the bound user and on its tenant, revoking
twice, revoking across tenants — and the one-shot secret contract, which says the full key
leaves the API in the 201 body and nowhere else, ever.

The companion happy-path suite is tests/core/test_api_keys.py; the admin surface is
tests/modules/admin/test_api_key_endpoints.py. This file only holds the attacks.
"""

import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import sha256_hex
from app.core.models import ApiKey, AuditLog, Base, User
from app.core.rbac import ADMIN_USER_MANAGE
from app.core.tenancy import tenant_context
from app.modules.admin.models import Tenant
from tests.conftest import ProvisionedUser

_KEYS = "/api/v1/admin/api-keys"
_GUARDED = "/api/v1/admin/users"

# A fixed instant well past any real clock, with a full six-digit microsecond so it
# survives SQLite's DATETIME storage format byte for byte (D-003: aiosqlite hands
# DateTime(timezone=True) back NAIVE, which core/auth.as_utc re-attaches as UTC).
FROZEN = datetime(2030, 1, 1, 12, 0, 0, 123456, tzinfo=UTC)


def _bearer(full_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {full_key}"}


async def _issue(client: AsyncClient, user_id: uuid.UUID, **overrides: object) -> dict:
    """Mint a key through the shipped issuer, not a fixture — the attacks below must run
    against exactly the row the production path writes."""
    payload: dict[str, object] = {
        "name": "website",
        "user_id": str(user_id),
        "scopes": [ADMIN_USER_MANAGE],
    }
    payload.update(overrides)
    response = await client.post(_KEYS, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def _fresh(session: AsyncSession) -> AsyncSession:
    """Drop this session's snapshot and identity map so a read sees what the APP just
    committed (the app runs on its own session against the same engine)."""
    await session.rollback()
    session.expire_all()
    return session


# --- Revocation ---------------------------------------------------------------


async def test_revocation_beats_the_warm_rbac_memo(
    admin_client: AsyncClient, admin_user: ProvisionedUser
) -> None:
    """The attack the D-009 TTL invites: authenticate once so the 60 s permission memo is
    hot for this principal, then revoke. The memo caches PERMISSIONS keyed on
    (tenant, user, token_version) — nothing about it caches the KEY row, which core/deps.py
    re-reads every request, so the very next call must 401 rather than ride the TTL out."""
    from app.core import rbac

    created = await _issue(admin_client, admin_user.user_id)
    key_auth = _bearer(created["key"])

    warm = await admin_client.get(_GUARDED, headers=key_auth)
    assert warm.status_code == 200, warm.text
    # The memo really is hot — otherwise this test would prove nothing.
    assert (admin_user.tenant_id, admin_user.user_id, 0) in rbac._CACHE

    revoked = await admin_client.post(f"{_KEYS}/{created['id']}/revoke")
    assert revoked.status_code == 200, revoked.text

    denied = await admin_client.get(_GUARDED, headers=key_auth)
    assert denied.status_code == 401, denied.text
    assert denied.json()["error"]["code"] == "auth.invalid_token"
    # And still hot: revocation did not work by accidentally flushing the cache.
    assert (admin_user.tenant_id, admin_user.user_id, 0) in rbac._CACHE


async def test_revoking_one_key_leaves_the_others_alive(
    admin_client: AsyncClient, admin_user: ProvisionedUser
) -> None:
    """Rotation depends on this: two live keys, revoke one, the other keeps working — the
    zero-downtime overlap window D-069 names as the reason not to use a service user."""
    old = await _issue(admin_client, admin_user.user_id)
    new = await _issue(admin_client, admin_user.user_id)

    assert (await admin_client.post(f"{_KEYS}/{old['id']}/revoke")).status_code == 200

    assert (await admin_client.get(_GUARDED, headers=_bearer(old["key"]))).status_code == 401
    assert (await admin_client.get(_GUARDED, headers=_bearer(new["key"]))).status_code == 200


async def test_double_revoke_does_not_resurrect_or_restamp(
    admin_client: AsyncClient, admin_user: ProvisionedUser, db_session: AsyncSession
) -> None:
    """Revoking twice must be a no-op, not a second UPDATE that moves the timestamp — an
    operator retrying a failed call must not lose the moment the credential actually died,
    and the key must stay dead across both calls."""
    created = await _issue(admin_client, admin_user.user_id)
    first = await admin_client.post(f"{_KEYS}/{created['id']}/revoke")
    assert first.status_code == 200, first.text

    with tenant_context(admin_user.tenant_id):
        stamped = (
            await (await _fresh(db_session)).execute(select(ApiKey.revoked_at))
        ).scalar_one()

    second = await admin_client.post(f"{_KEYS}/{created['id']}/revoke")
    assert second.status_code == 200, second.text

    with tenant_context(admin_user.tenant_id):
        after = (
            await (await _fresh(db_session)).execute(select(ApiKey.revoked_at))
        ).scalar_one()
    assert after == stamped
    assert (await admin_client.get(_GUARDED, headers=_bearer(created["key"]))).status_code == 401


async def test_another_tenant_cannot_revoke_this_tenants_key(
    client: AsyncClient,
    admin_client: AsyncClient,
    admin_user: ProvisionedUser,
    user_factory,
) -> None:
    """A tenant-B admin holding admin.apikey.manage aims the revoke endpoint at a
    tenant-A key id. The D-007 filter hides the row, so it is a 404 — and, the half that
    matters, A's credential is still alive afterwards (a cross-tenant denial of service
    would be as bad as a cross-tenant read)."""
    victim = await _issue(admin_client, admin_user.user_id)
    attacker = await user_factory(slug="beta", email="owner@beta.test", admin=True)
    attacker_token = (
        await client.post(
            "/api/v1/auth/login",
            json={
                "tenant_slug": attacker.tenant_slug,
                "email": attacker.email,
                "password": attacker.password,
            },
        )
    ).json()["access_token"]

    denied = await admin_client.post(
        f"{_KEYS}/{victim['id']}/revoke",
        headers={"Authorization": f"Bearer {attacker_token}"},
    )

    assert denied.status_code == 404, denied.text
    assert denied.json()["error"]["code"] == "admin.api_key_not_found"
    alive = await admin_client.get(_GUARDED, headers=_bearer(victim["key"]))
    assert alive.status_code == 200, alive.text


# --- Expiry -------------------------------------------------------------------


async def test_expiry_boundary_exactly_now_is_rejected(
    admin_client: AsyncClient, admin_user: ProvisionedUser, monkeypatch
) -> None:
    """expires_at == now is EXPIRED, not the last valid microsecond: core/deps.py compares
    with <=. Pinned on a frozen clock because the real one cannot hit the boundary."""
    created = await _issue(
        admin_client, admin_user.user_id, expires_at=FROZEN.isoformat()
    )
    monkeypatch.setattr("app.core.deps.now_utc", lambda: FROZEN)

    response = await admin_client.get(_GUARDED, headers=_bearer(created["key"]))

    assert response.status_code == 401, response.text


async def test_expiry_boundary_one_microsecond_later_still_authenticates(
    admin_client: AsyncClient, admin_user: ProvisionedUser, monkeypatch
) -> None:
    """The other side of the same boundary — the comparison must not be off by a tick in
    the fail-closed direction either, or every key dies a microsecond early."""
    created = await _issue(
        admin_client,
        admin_user.user_id,
        expires_at=(FROZEN + timedelta(microseconds=1)).isoformat(),
    )
    monkeypatch.setattr("app.core.deps.now_utc", lambda: FROZEN)

    response = await admin_client.get(_GUARDED, headers=_bearer(created["key"]))

    assert response.status_code == 200, response.text


async def test_an_expired_key_cannot_be_revived_by_listing_it(
    admin_client: AsyncClient, admin_user: ProvisionedUser
) -> None:
    """An expired key stays visible to the operator (it is history worth auditing) but is
    dead as a credential — expiry is not a soft state the list endpoint clears."""
    created = await _issue(
        admin_client,
        admin_user.user_id,
        expires_at=(datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
    )

    listed = await admin_client.get(_KEYS)
    assert [row["id"] for row in listed.json()["items"]] == [created["id"]]
    assert (await admin_client.get(_GUARDED, headers=_bearer(created["key"]))).status_code == 401


# --- Kill switches on the bound principal -------------------------------------


async def test_deactivating_the_bound_user_kills_the_key(
    admin_client: AsyncClient, admin_user: ProvisionedUser, db_session: AsyncSession
) -> None:
    """The key authenticates AS its user, so the user's own is_active flag is a kill switch
    over every key bound to it — the coarse revoke when a whole principal is compromised."""
    created = await _issue(admin_client, admin_user.user_id)
    assert (await admin_client.get(_GUARDED, headers=_bearer(created["key"]))).status_code == 200

    with tenant_context(admin_user.tenant_id):
        user = await (await _fresh(db_session)).get_one(User, admin_user.user_id)
        user.is_active = False
        await db_session.commit()

    response = await admin_client.get(_GUARDED, headers=_bearer(created["key"]))
    assert response.status_code == 401, response.text


async def test_deactivating_the_tenant_kills_the_key(
    admin_client: AsyncClient, admin_user: ProvisionedUser, db_session: AsyncSession
) -> None:
    """Suspending a whole property must strand its website's credential too, and must do so
    BEFORE any tenant-scoped query runs (core/deps.py checks tenant.is_active first)."""
    created = await _issue(admin_client, admin_user.user_id)

    tenant = await (await _fresh(db_session)).get_one(Tenant, admin_user.tenant_id)
    tenant.is_active = False
    await db_session.commit()

    response = await admin_client.get(_GUARDED, headers=_bearer(created["key"]))
    assert response.status_code == 401, response.text


async def test_token_version_bump_kills_the_jwt_but_NOT_the_key(
    admin_client: AsyncClient, admin_user: ProvisionedUser, db_session: AsyncSession
) -> None:
    """The kill switches divide by credential shape, and this pins WHICH — core/deps.py
    used to claim in a comment that a token_version bump was "a kill-switch for both
    credential shapes", and it is not.

    That division is correct, not a gap. token_version is D-008's invalidation counter for
    STATELESS tokens: a JWT cannot be revoked, so it is versioned. A key is a row and is
    revoked by revoked_at. Bumping the version would conflate "log this user out
    everywhere" (a password change) with "strand the property's website". The switch that
    DOES kill a whole principal, keys included, is user.is_active — see the test above it.

    If a future "revoke everything" endpoint ever means to include keys, this test is the
    one to change, and the change is a token_version column on core_api_keys stamped at
    mint and compared here — not a silent reinterpretation of the counter.
    """
    created = await _issue(admin_client, admin_user.user_id)
    key_auth = _bearer(created["key"])
    assert (await admin_client.get(_GUARDED, headers=key_auth)).status_code == 200

    with tenant_context(admin_user.tenant_id):
        user = await (await _fresh(db_session)).get_one(User, admin_user.user_id)
        user.token_version += 1
        await db_session.commit()

    # The JWT the admin_client fixture holds dies, as D-008 promises.
    assert (await admin_client.get(_GUARDED)).status_code == 401
    # The key does not — its own revocation is revoked_at.
    survives = await admin_client.get(_GUARDED, headers=key_auth)
    assert survives.status_code == 200, survives.text


async def test_deactivating_the_user_outranks_a_token_version_bump(
    admin_client: AsyncClient, admin_user: ProvisionedUser, db_session: AsyncSession
) -> None:
    """The consequence of the split above, stated as the operator runbook: to strand a
    compromised principal's machine credentials you clear is_active, not the version."""
    created = await _issue(admin_client, admin_user.user_id)
    key_auth = _bearer(created["key"])

    with tenant_context(admin_user.tenant_id):
        user = await (await _fresh(db_session)).get_one(User, admin_user.user_id)
        user.token_version += 1
        await db_session.commit()
    assert (await admin_client.get(_GUARDED, headers=key_auth)).status_code == 200

    with tenant_context(admin_user.tenant_id):
        user = await (await _fresh(db_session)).get_one(User, admin_user.user_id)
        user.is_active = False
        await db_session.commit()

    dead = await admin_client.get(_GUARDED, headers=key_auth)
    assert dead.status_code == 401, dead.text


# --- The one-shot secret contract ---------------------------------------------


async def test_the_full_key_is_never_persisted(
    admin_client: AsyncClient, admin_user: ProvisionedUser, db_session: AsyncSession
) -> None:
    """Only the digest is stored. Scan EVERY column of the row rather than asserting on the
    two we expect, so a later column that quietly caches part of the key fails here."""
    created = await _issue(admin_client, admin_user.user_id)
    secret = created["key"].split("_", 2)[2]

    with tenant_context(admin_user.tenant_id):
        row = (await (await _fresh(db_session)).execute(select(ApiKey))).scalar_one()
        stored = {
            attr.key: getattr(row, attr.key) for attr in inspect(ApiKey).column_attrs
        }

    # prefix is the scheme + the key's own tenant ref, rebuilt from parts — asserted
    # against the ref segment of the issued key rather than a hardcoded shape, so it holds
    # whichever ref the key carries (D-069 records the slug-vs-UUID trade).
    assert stored["prefix"] == "atk_" + created["key"].split("_", 2)[1]
    for column, value in stored.items():
        assert secret not in str(value), f"{column} contains the raw secret"
        assert created["key"] not in str(value), f"{column} contains the full key"


async def test_the_secret_reaches_no_table_in_the_database(
    admin_client: AsyncClient, admin_user: ProvisionedUser, db_session: AsyncSession
) -> None:
    """The whole schema, not just core_api_keys. This is the test that survives the changes
    most likely to break the one-shot contract by accident: wiring D-013 idempotency onto
    POST /api-keys would persist the 201 body — full key included — into
    core_idempotency_keys and make it REPLAYABLE, and any future "last response" or job
    payload column would do the same. Core selects, so the D-007 filter does not fire and
    every tenant's rows are in scope."""
    created = await _issue(admin_client, admin_user.user_id)
    secret = created["key"].split("_", 2)[2]

    await db_session.rollback()
    carriers = []
    # .tables, not .sorted_tables: nothing here needs FK order, and sorting warns about
    # the crm_leads/crm_opportunities mutual FK cycle.
    for table in Base.metadata.tables.values():
        rows = (await db_session.execute(table.select())).all()
        if any(secret in str(value) for row in rows for value in row):
            carriers.append(table.name)

    assert carriers == [], f"the raw secret was persisted in {carriers}"


async def test_the_secret_leaves_the_api_exactly_once(
    admin_client: AsyncClient, admin_user: ProvisionedUser
) -> None:
    """The 201 is the only response that may carry the key. Every other admin surface the
    holder of admin.apikey.manage can reach — the list, and the audit viewer, which is the
    one place a full row diff could surface — must contain neither the key nor its digest.
    """
    created = await _issue(admin_client, admin_user.user_id)
    secret = created["key"].split("_", 2)[2]
    digest = sha256_hex(secret)

    for url in (_KEYS, "/api/v1/admin/audit-logs"):
        response = await admin_client.get(url)
        assert response.status_code == 200, response.text
        assert secret not in response.text, f"{url} leaked the secret"
        assert digest not in response.text, f"{url} leaked the stored digest"


async def test_the_read_schema_cannot_express_the_digest() -> None:
    """A schema-level pin, not a body-level one: neither read model may GAIN a
    secret_sha256 field, whatever a future ORM change makes available to serialize."""
    from app.modules.admin.schemas import ApiKeyCreated, ApiKeyRead

    assert "secret_sha256" not in ApiKeyRead.model_fields
    assert "secret_sha256" not in ApiKeyCreated.model_fields
    assert "key" not in ApiKeyRead.model_fields
    # ApiModel does not set extra="allow", so an unexpected ORM attribute cannot ride along.
    assert ApiKeyRead.model_config.get("extra") in (None, "ignore")


async def test_a_rejected_key_is_not_echoed_back(
    admin_client: AsyncClient, admin_user: ProvisionedUser
) -> None:
    """A 401 body (and its X-Request-ID logging envelope) must never quote the credential
    that failed — error responses are the classic accidental credential sink."""
    created = await _issue(admin_client, admin_user.user_id)
    await admin_client.post(f"{_KEYS}/{created['id']}/revoke")

    denied = await admin_client.get(_GUARDED, headers=_bearer(created["key"]))

    assert denied.status_code == 401
    assert created["key"] not in denied.text
    assert created["key"].split("_", 2)[2] not in denied.text


async def test_revocation_is_audited_by_an_attributed_row_carrying_no_digest(
    admin_client: AsyncClient, admin_user: ProvisionedUser, db_session: AsyncSession
) -> None:
    """Issuing and revoking a machine credential are the two moments a lifecycle question
    gets asked of the audit log — "who gave the website this key, and who took it away".
    Both must land, both must name the operator (D-010), and neither may carry the stored
    digest: the audit viewer is ``admin.audit.read``, a different permission from the one
    that may see keys at all, so a full-row INSERT diff is exactly where the digest would
    escape the schema that deliberately hides it."""
    created = await _issue(admin_client, admin_user.user_id)
    assert (await admin_client.post(f"{_KEYS}/{created['id']}/revoke")).status_code == 200

    with tenant_context(admin_user.tenant_id):
        rows = (
            (
                await (await _fresh(db_session)).execute(
                    select(AuditLog)
                    .where(AuditLog.entity_table == "core_api_keys")
                    .order_by(AuditLog.created_at)
                )
            )
            .scalars()
            .all()
        )

    assert [row.action for row in rows] == ["INSERT", "UPDATE"]
    assert {row.actor_user_id for row in rows} == {admin_user.user_id}
    assert {row.entity_id for row in rows} == {created["id"]}
    assert rows[1].diff["revoked_at"]["old"] is None
    assert rows[1].diff["revoked_at"]["new"] is not None
    assert "secret_sha256" not in rows[0].diff["new"]
    assert "secret_sha256" not in rows[1].diff


async def test_a_scoped_key_does_not_poison_the_shared_permission_memo(
    admin_client: AsyncClient, admin_user: ProvisionedUser
) -> None:
    """Both keys resolve permissions through the SAME memo entry, then intersect their own
    scopes onto it. If the intersection ever mutated the cached set in place, the narrow
    key would silently narrow the wide one for the next 60 seconds. Order matters: narrow
    first, wide second."""
    narrow = await _issue(admin_client, admin_user.user_id, scopes=[ADMIN_USER_MANAGE])
    wide = await _issue(admin_client, admin_user.user_id, scopes=None)
    roles = "/api/v1/admin/roles"  # needs ADMIN_ROLE_MANAGE, which `narrow` drops

    assert (await admin_client.get(_GUARDED, headers=_bearer(narrow["key"]))).status_code == 200
    widened = await admin_client.get(roles, headers=_bearer(wide["key"]))
    assert widened.status_code == 200, widened.text

    # ...and the narrowing did not go the other way either: the wide key's run must not
    # have re-broadened the memo for the narrow one, nor for the JWT sharing the entry.
    assert (await admin_client.get(roles, headers=_bearer(narrow["key"]))).status_code == 403
    assert (await admin_client.get(roles)).status_code == 200
