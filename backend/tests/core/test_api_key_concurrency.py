"""Phase 18 machine credential (spec Q1) under CONCURRENCY, and the D-013 namespace it shares.

Four questions this file answers with real, running assertions:

1. **Digest collision.** Can two ``core_api_keys`` rows carry the same ``secret_sha256``?
   They must not: ``core/deps._authenticate_api_key`` selects the key with ``.one_or_none()``,
   so a second row with the same digest would turn EVERY request on that credential into a
   ``MultipleResultsFound`` 500. The global UNIQUE is what makes ``.one_or_none()`` safe.
2. **Revoke racing authentication.** Revocation must bite on the very next request (nothing
   caches the key row), and must not abort a request that already authenticated — the same
   one-check-per-request window a JWT has.
3. **Concurrent mint / concurrent revoke** for one user.
4. **D-013 principal namespace.** ``core_idempotency_keys`` is keyed ``(tenant_id, endpoint,
   key)`` with NO principal column, and ``core/idempotency.py`` reads the tenant from the D-007
   ContextVar. Phase 18 puts an EXTERNAL machine principal inside that namespace alongside the
   tenant's staff users. The collision tests below record what actually happens.

The idempotency tests drive a throwaway guarded route mounted on the SHARED app fixture, the
same technique ``tests/core/test_idempotency.py`` uses: the behaviour under test lives entirely
in ``core/idempotency.py`` + ``core/deps.py``, and a fake route reaches it without dragging a
business module's factories into tests/core. Unlike that file this one authenticates through the
REAL ``get_current_user``, because the whole question is what happens when two DIFFERENT
principals — a staff JWT and a machine API key — meet on one reservation row.
"""

import asyncio
import functools
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Annotated, Any, get_args

import pytest
import sqlalchemy as sa
from fastapi import Depends, FastAPI
from httpx import AsyncClient
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import API_KEY_PREFIX, mint_api_key
from app.core.db import get_session
from app.core.deps import CurrentUserDep
from app.core.events import run_in_uow
from app.core.idempotency import REPLAYED_HEADER, IdempotencyContext, IdempotencyKey, Idempotent
from app.core.models import ApiKey
from app.core.rbac import (
    ADMIN_ROLE_MANAGE,
    ADMIN_USER_MANAGE,
    _mask_serializer,
    require_permission,
)
from app.core.schemas import ApiModel, Page
from app.core.tenancy import system_context, tenant_context
from app.main import create_app
from app.modules.admin.models import TenantSetting
from app.modules.admin.service import grant_admin_role, provision_user
from app.modules.hr.constants import HR_EMPLOYEE_READ_COMPENSATION
from tests.conftest import ProvisionedUser

# --- Helpers ------------------------------------------------------------------

ROUTE = "/api/v1/_test/idem-settings"
ENDPOINT_ID = "test.api_key_concurrency.setting.create"


def _bearer(credential: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {credential}"}


def _instant(raw: str) -> datetime:
    """Parse an API timestamp to a UTC instant. Values SQLite hands back are naive (see
    core/deps.as_utc); freshly written ones are aware — same moment, different spelling."""
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


async def _login(client: AsyncClient, principal: ProvisionedUser) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": principal.tenant_slug,
            "email": principal.email,
            "password": principal.password,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


MintKey = Callable[..., Awaitable[str]]


@pytest.fixture
def mint_key(db_session: AsyncSession) -> MintKey:
    """Persist a real key for a principal, optionally bound to another user of the same
    tenant, and return the full key string. Mirrors admin/service.create_api_key."""

    async def _make(
        principal: ProvisionedUser,
        *,
        user_id: uuid.UUID | None = None,
        scopes: list[str] | None = None,
    ) -> str:
        full, digest = mint_api_key(principal.tenant_id)
        with tenant_context(principal.tenant_id):
            db_session.add(
                ApiKey(
                    user_id=user_id or principal.user_id,
                    name="website",
                    prefix=f"{API_KEY_PREFIX}_{principal.tenant_id.hex}",
                    secret_sha256=digest,
                    scopes=scopes,
                )
            )
            await db_session.commit()
        return full

    return _make


@pytest.fixture
async def second_admin(
    db_session: AsyncSession, admin_user: ProvisionedUser
) -> ProvisionedUser:
    """A SECOND user inside the SAME tenant, also holding the Administrator role — the
    'machine user' a property's website key would be bound to. admin_user already synced
    the permission catalog, so grant_admin_role can reuse it."""
    user = await provision_user(
        db_session, admin_user.tenant_id, email="website@acme.test", password="machine-secret"
    )
    await grant_admin_role(
        db_session, admin_user.tenant_id, user.id, token_version=user.token_version
    )
    await db_session.commit()
    return ProvisionedUser(
        tenant_id=admin_user.tenant_id,
        tenant_slug=admin_user.tenant_slug,
        user_id=user.id,
        email="website@acme.test",
        password="machine-secret",
    )


class _SettingCreate(ApiModel):
    key: str
    value: dict[str, Any]


class _SettingRead(ApiModel):
    id: uuid.UUID
    key: str
    # Stamped from the authenticated principal so a replayed body visibly carries the
    # user id of whoever ACTUALLY ran the work.
    created_by: uuid.UUID


@pytest.fixture
def idem_route(app: FastAPI) -> str:
    """Mount one D-013-guarded, RBAC-guarded write route on the shared test app. Guarded by
    ADMIN_ROLE_MANAGE so a key scoped to ADMIN_USER_MANAGE alone is refused by the ordinary
    permission gate — that is how the 'does replay bypass RBAC' question gets answered."""
    guard = Idempotent(ENDPOINT_ID)

    @app.post(
        ROUTE,
        response_model=_SettingRead,
        status_code=201,
        dependencies=[Depends(require_permission(ADMIN_ROLE_MANAGE))],
    )
    async def _create(
        payload: _SettingCreate,
        current: CurrentUserDep,
        session: Annotated[AsyncSession, Depends(get_session)],
        idem: Annotated[IdempotencyContext, Depends(guard)],
    ) -> _SettingRead:
        holder: dict[str, _SettingRead] = {}

        async def work() -> None:
            setting = TenantSetting(key=payload.key, value=payload.value)
            session.add(setting)
            await session.flush()
            holder["read"] = await idem.capture(
                _SettingRead(id=setting.id, key=payload.key, created_by=current.user_id),
                status_code=201,
            )

        await run_in_uow(session, work)
        return holder["read"]

    return ROUTE


async def _count_settings(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    with tenant_context(tenant_id):
        return (
            await session.execute(sa.select(sa.func.count()).select_from(TenantSetting))
        ).scalar_one()


# --- 1. Digest collision on mint ----------------------------------------------


@pytest.mark.parametrize("cross_tenant", [False, True])
async def test_two_keys_cannot_share_a_secret_digest(
    db_session: AsyncSession,
    admin_user: ProvisionedUser,
    user_factory: Callable[..., Awaitable[ProvisionedUser]],
    cross_tenant: bool,
) -> None:
    """The UNIQUE on secret_sha256 is GLOBAL, not per-tenant, so a digest can exist at most
    once in the whole table. That is exactly what core/deps needs: it looks a credential up by
    digest with ``.one_or_none()``, which would raise MultipleResultsFound — a 500 on every
    request of that credential — if two rows ever shared one."""
    other = (
        await user_factory(slug="beta", email="owner@beta.test")
        if cross_tenant
        else admin_user
    )
    digest = "a" * 64

    def _row(principal: ProvisionedUser) -> ApiKey:
        return ApiKey(
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            name="website",
            prefix=f"{API_KEY_PREFIX}_{principal.tenant_id.hex}",
            secret_sha256=digest,
            scopes=None,
        )

    with system_context():
        db_session.add(_row(admin_user))
        await db_session.commit()
        db_session.add(_row(other))
        with pytest.raises(IntegrityError):
            await db_session.commit()
    await db_session.rollback()


async def test_colliding_mint_is_refused_and_persists_nothing(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_user: ProvisionedUser,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Force ``secrets.token_urlsafe`` to repeat itself and mint twice through the real
    endpoint. What MUST hold — and does — is that the second mint is refused and leaves no
    row, so the auth path's ``.one_or_none()`` can never meet two keys.

    OBSERVED status: 500 ``common.internal_error``. That is this codebase's DELIBERATE
    behaviour, not a Phase 18 gap: ``app/main._handle_db_guard_error`` documents that a
    DBAPIError carrying no ATLAS_* guard token "is a genuine integrity/operational fault —
    log it and return the opaque 500". Mapping this one to a 409 would mean issuing a
    bespoke handler for an event that needs 2**128 mints to see once, so the assertion is
    on the property (refused, nothing stored) rather than on the exact status — it stays
    green if a later phase does decide to translate it."""
    monkeypatch.setattr(
        "app.core.auth.secrets.token_urlsafe", lambda _n: "collide-collide-collide"
    )
    token = await _login(client, admin_user)
    body = {"name": "website", "user_id": str(admin_user.user_id)}

    first = await client.post("/api/v1/admin/api-keys", headers=_bearer(token), json=body)
    assert first.status_code == 201, first.text

    second = await client.post("/api/v1/admin/api-keys", headers=_bearer(token), json=body)

    assert second.status_code >= 400, second.text
    assert "key" not in second.json()
    with tenant_context(admin_user.tenant_id):
        stored = (
            await db_session.execute(sa.select(sa.func.count()).select_from(ApiKey))
        ).scalar_one()
    assert stored == 1
    # The one surviving key still authenticates: the failed mint did not poison it.
    ok = await client.get("/api/v1/admin/users", headers=_bearer(first.json()["key"]))
    assert ok.status_code == 200, ok.text


# --- 2. Revoke racing authentication ------------------------------------------


async def test_revoke_bites_on_the_very_next_request(
    client: AsyncClient, admin_user: ProvisionedUser, mint_key: MintKey
) -> None:
    """Nothing caches the key row (the 60s D-009 permission memo is keyed on the USER, not the
    credential), so the request immediately after a revoke is already 401."""
    full = await mint_key(admin_user, scopes=[ADMIN_USER_MANAGE])
    token = await _login(client, admin_user)

    assert (await client.get("/api/v1/admin/users", headers=_bearer(full))).status_code == 200

    listed = await client.get("/api/v1/admin/api-keys", headers=_bearer(token))
    key_id = listed.json()["items"][0]["id"]
    revoke = await client.post(
        f"/api/v1/admin/api-keys/{key_id}/revoke", headers=_bearer(token)
    )
    assert revoke.status_code == 200, revoke.text

    assert (await client.get("/api/v1/admin/users", headers=_bearer(full))).status_code == 401


async def test_revoke_racing_an_in_flight_request_does_not_abort_it(
    client: AsyncClient, app: FastAPI, admin_user: ProvisionedUser, mint_key: MintKey
) -> None:
    """The race the spec names: a request authenticates, and the revoke lands while it is still
    running. Credentials are checked ONCE per request (identical to a JWT), so the in-flight
    call completes and only the NEXT one is refused. Recorded, not fixed: re-checking mid-flight
    would mean a second query on every request and would still leave a window."""
    gate = asyncio.Event()
    entered = asyncio.Event()

    @app.get("/api/v1/_test/parked")
    async def _parked(
        current: CurrentUserDep,
        session: Annotated[AsyncSession, Depends(get_session)],
    ) -> dict[str, str]:
        # Release the read transaction the auth queries opened before parking: SQLite's
        # single-writer lock would otherwise block the concurrent revoke (D-003 - the test
        # engine is SQLite, the runtime is PostgreSQL).
        await session.rollback()
        entered.set()
        await gate.wait()
        return {"user_id": str(current.user_id)}

    full = await mint_key(admin_user, scopes=[ADMIN_USER_MANAGE])
    token = await _login(client, admin_user)
    listed = await client.get("/api/v1/admin/api-keys", headers=_bearer(token))
    key_id = listed.json()["items"][0]["id"]

    in_flight = asyncio.create_task(client.get("/api/v1/_test/parked", headers=_bearer(full)))
    await asyncio.wait_for(entered.wait(), timeout=5)
    revoke = await client.post(
        f"/api/v1/admin/api-keys/{key_id}/revoke", headers=_bearer(token)
    )
    assert revoke.status_code == 200, revoke.text
    gate.set()

    parked = await asyncio.wait_for(in_flight, timeout=5)
    assert parked.status_code == 200, parked.text
    assert (await client.get("/api/v1/admin/users", headers=_bearer(full))).status_code == 401


async def test_sequential_double_revoke_keeps_the_first_timestamp(
    client: AsyncClient, admin_user: ProvisionedUser, mint_key: MintKey
) -> None:
    """The retry case the endpoint documents: a client re-sends revoke, gets 200, and the
    stored revoked_at is UNCHANGED. Instants, not raw strings — a value SQLite hands back is
    naive while a freshly written one is aware (the aiosqlite quirk core/deps.as_utc exists
    for), so the two spellings differ by a 'Z' for the same moment (D-003 test-engine
    artifact, shared by every timestamp in the codebase)."""
    await mint_key(admin_user)
    token = await _login(client, admin_user)
    listed = await client.get("/api/v1/admin/api-keys", headers=_bearer(token))
    key_id = listed.json()["items"][0]["id"]

    first = await client.post(f"/api/v1/admin/api-keys/{key_id}/revoke", headers=_bearer(token))
    second = await client.post(f"/api/v1/admin/api-keys/{key_id}/revoke", headers=_bearer(token))

    assert (first.status_code, second.status_code) == (200, 200), (first.text, second.text)
    assert _instant(first.json()["revoked_at"]) == _instant(second.json()["revoked_at"])


async def test_simultaneous_double_revoke_is_effective_but_reports_two_timestamps(
    client: AsyncClient, admin_user: ProvisionedUser, mint_key: MintKey
) -> None:
    """Two revokes fired at the SAME time both read ``revoked_at IS NULL`` in their own
    session and both write — a textbook lost update. Recorded, not fixed.

    What holds, and is what actually matters: both answer 200, both report the key revoked,
    the key is dead afterwards, and the stored value is one of the two. What does NOT hold is
    admin/service.revoke_api_key's "FIRST timestamp" claim — under simultaneity the later
    write can win and one client is told a revocation time that is not the stored one.

    Left alone deliberately. The only fix that closes the window is an atomic
    ``UPDATE ... WHERE revoked_at IS NULL``, i.e. a Core UPDATE — and a Core UPDATE skips the
    ORM flush events that D-010 audit capture hooks, so it would silently stop auditing the
    revocation to buy a few milliseconds of timestamp precision on a credential that is
    equally dead either way. The docstrings were corrected to say *sequential* retry instead.
    """
    await mint_key(admin_user)
    token = await _login(client, admin_user)
    listed = await client.get("/api/v1/admin/api-keys", headers=_bearer(token))
    key_id = listed.json()["items"][0]["id"]

    first, second = await asyncio.gather(
        client.post(f"/api/v1/admin/api-keys/{key_id}/revoke", headers=_bearer(token)),
        client.post(f"/api/v1/admin/api-keys/{key_id}/revoke", headers=_bearer(token)),
    )

    assert (first.status_code, second.status_code) == (200, 200), (first.text, second.text)
    reported = {_instant(response.json()["revoked_at"]) for response in (first, second)}
    assert len(reported) <= 2

    after = await client.get("/api/v1/admin/api-keys", headers=_bearer(token))
    stored = after.json()["items"][0]["revoked_at"]
    assert stored is not None
    assert _instant(stored) in reported


# --- 3. Concurrent mint for one user ------------------------------------------


async def test_two_concurrent_creates_for_one_user_both_mint_usable_keys(
    client: AsyncClient, admin_user: ProvisionedUser
) -> None:
    """Nothing serializes issuance per user, and nothing should: a property replacing its
    website credential wants the old and the new key alive at once. Both keys authenticate,
    and revoking one leaves the other working."""
    token = await _login(client, admin_user)
    body = {"name": "website", "user_id": str(admin_user.user_id)}

    first, second = await asyncio.gather(
        client.post("/api/v1/admin/api-keys", headers=_bearer(token), json=body),
        client.post("/api/v1/admin/api-keys", headers=_bearer(token), json=body),
    )

    assert (first.status_code, second.status_code) == (201, 201), (first.text, second.text)
    key_a, key_b = first.json()["key"], second.json()["key"]
    assert key_a != key_b
    for credential in (key_a, key_b):
        response = await client.get("/api/v1/admin/users", headers=_bearer(credential))
        assert response.status_code == 200, response.text

    revoke = await client.post(
        f"/api/v1/admin/api-keys/{first.json()['id']}/revoke", headers=_bearer(token)
    )
    assert revoke.status_code == 200, revoke.text
    assert (await client.get("/api/v1/admin/users", headers=_bearer(key_a))).status_code == 401
    assert (await client.get("/api/v1/admin/users", headers=_bearer(key_b))).status_code == 200


# --- 4. The D-013 principal namespace -----------------------------------------


async def test_idempotency_namespace_is_shared_across_principals(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_user: ProvisionedUser,
    second_admin: ProvisionedUser,
    mint_key: MintKey,
    idem_route: str,
) -> None:
    """THE Phase 18 idempotency question. The reservation PK is (tenant_id, endpoint, key) with
    no principal column, so a staff JWT and the website's API key — two different core_users
    rows — share one namespace. Same key value + same body means the machine principal gets the
    STAFF user's stored response replayed verbatim: a 201 for a document it never created,
    stamped with the staff user's id, and no second row is written.
    """
    token = await _login(client, admin_user)
    website = await mint_key(admin_user, user_id=second_admin.user_id, scopes=[ADMIN_ROLE_MANAGE])
    shared_key = "booking-4711"
    body = {"key": "reception.banner", "value": {"text": "hi"}}

    staff = await client.post(
        idem_route, headers={**_bearer(token), "Idempotency-Key": shared_key}, json=body
    )
    assert staff.status_code == 201, staff.text
    assert staff.json()["created_by"] == str(admin_user.user_id)

    machine = await client.post(
        idem_route, headers={**_bearer(website), "Idempotency-Key": shared_key}, json=body
    )

    # What ACTUALLY happens: a verbatim replay of the other principal's response.
    assert machine.status_code == 201, machine.text
    assert machine.headers.get(REPLAYED_HEADER) == "true"
    assert machine.json() == staff.json()
    assert machine.json()["created_by"] == str(admin_user.user_id)
    # ... and the machine principal's own work never ran.
    assert await _count_settings(db_session, admin_user.tenant_id) == 1
    with tenant_context(admin_user.tenant_id):
        rows = (
            (
                await db_session.execute(
                    sa.select(IdempotencyKey).where(IdempotencyKey.key == shared_key)
                )
            )
            .scalars()
            .all()
        )
    assert len(rows) == 1


async def test_idempotency_collision_with_a_different_body_blocks_the_other_principal(
    client: AsyncClient,
    admin_user: ProvisionedUser,
    second_admin: ProvisionedUser,
    mint_key: MintKey,
    idem_route: str,
) -> None:
    """The other half of the shared namespace: same key, DIFFERENT body. The machine principal's
    legitimate, distinct request is refused 422 because a staff user already spent that key
    value on this endpoint. An external client that picks guessable keys can be denied — or can
    deny — service inside its own tenant."""
    token = await _login(client, admin_user)
    website = await mint_key(admin_user, user_id=second_admin.user_id, scopes=[ADMIN_ROLE_MANAGE])
    shared_key = "booking-4711"

    staff = await client.post(
        idem_route,
        headers={**_bearer(token), "Idempotency-Key": shared_key},
        json={"key": "reception.banner", "value": {"text": "hi"}},
    )
    assert staff.status_code == 201, staff.text

    machine = await client.post(
        idem_route,
        headers={**_bearer(website), "Idempotency-Key": shared_key},
        json={"key": "website.banner", "value": {"text": "book now"}},
    )

    assert machine.status_code == 422, machine.text
    assert machine.json()["error"]["code"] == "idempotency.key_reuse"


async def test_replay_still_passes_through_the_permission_gate(
    client: AsyncClient,
    admin_user: ProvisionedUser,
    second_admin: ProvisionedUser,
    mint_key: MintKey,
    idem_route: str,
) -> None:
    """What BOUNDS the severity of the shared namespace: the route's require_permission
    dependency is solved BEFORE the Idempotent guard (FastAPI inserts decorator-level
    dependencies at position 0), so a narrowly scoped key cannot replay a stored response for
    an endpoint it has no permission to call. Replay leaks between principals that are BOTH
    already authorised, never across the RBAC line."""
    token = await _login(client, admin_user)
    # Scoped to admin.user.manage only: the route needs admin.role.manage.
    narrow = await mint_key(admin_user, user_id=second_admin.user_id, scopes=[ADMIN_USER_MANAGE])
    shared_key = "booking-4711"
    body = {"key": "reception.banner", "value": {"text": "hi"}}

    staff = await client.post(
        idem_route, headers={**_bearer(token), "Idempotency-Key": shared_key}, json=body
    )
    assert staff.status_code == 201, staff.text

    machine = await client.post(
        idem_route, headers={**_bearer(narrow), "Idempotency-Key": shared_key}, json=body
    )

    assert machine.status_code == 403, machine.text
    assert machine.json()["error"]["code"] == "rbac.permission_denied"
    assert REPLAYED_HEADER not in machine.headers


async def test_in_progress_reservation_from_one_principal_blocks_the_other(
    client: AsyncClient,
    app: FastAPI,
    admin_user: ProvisionedUser,
    second_admin: ProvisionedUser,
    mint_key: MintKey,
    idem_route: str,
) -> None:
    """Concurrency across the principal boundary: while the staff request is still inside its
    business work, the machine principal presenting the same key gets 409 in_progress. The
    reservation row is the shared lock, and it is not scoped to a principal."""
    gate = asyncio.Event()
    entered = asyncio.Event()
    guard = Idempotent(ENDPOINT_ID)

    @app.post(
        "/api/v1/_test/idem-slow",
        status_code=201,
        dependencies=[Depends(require_permission(ADMIN_ROLE_MANAGE))],
    )
    async def _slow(
        current: CurrentUserDep,
        session: Annotated[AsyncSession, Depends(get_session)],
        idem: Annotated[IdempotencyContext, Depends(guard)],
    ) -> dict[str, str]:
        await session.rollback()
        entered.set()
        await gate.wait()
        await idem.capture({"user_id": str(current.user_id)}, status_code=201)
        await session.commit()
        return {"user_id": str(current.user_id)}

    token = await _login(client, admin_user)
    website = await mint_key(admin_user, user_id=second_admin.user_id, scopes=[ADMIN_ROLE_MANAGE])
    shared_key = "booking-4711"

    slow = asyncio.create_task(
        client.post(
            "/api/v1/_test/idem-slow",
            headers={**_bearer(token), "Idempotency-Key": shared_key},
            json={},
        )
    )
    await asyncio.wait_for(entered.wait(), timeout=5)

    machine = await client.post(
        idem_route,
        headers={**_bearer(website), "Idempotency-Key": shared_key},
        json={"key": "website.banner", "value": {"text": "book now"}},
    )
    gate.set()
    assert (await asyncio.wait_for(slow, timeout=5)).status_code == 201

    assert machine.status_code == 409, machine.text
    assert machine.json()["error"]["code"] == "idempotency.in_progress"


def _masked_permissions(annotation: Any, seen: set[type] | None = None) -> set[str]:
    """Every permission key guarding a ``Masked`` field reachable from this annotation.

    ``Masked(tp, perm)`` is ``Annotated[tp | None, WrapSerializer(partial(_mask_serializer,
    perm))]``, so the permission is the partial's first bound arg. Recurses through
    generics (``Page[T]``, ``list[T]``, unions) and nested models."""
    seen = seen if seen is not None else set()
    found: set[str] = set()
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        if annotation in seen:
            return found
        seen.add(annotation)
        for field in annotation.model_fields.values():
            for meta in field.metadata:
                func = getattr(meta, "func", None)
                if isinstance(func, functools.partial) and func.func is _mask_serializer:
                    found.add(func.args[0])
            found |= _masked_permissions(field.annotation, seen)
        return found
    for arg in get_args(annotation):
        found |= _masked_permissions(arg, seen)
    return found


def _is_idempotent(dependant: Any) -> bool:
    return isinstance(dependant.call, Idempotent) or any(
        _is_idempotent(sub) for sub in dependant.dependencies
    )


def test_no_idempotent_endpoint_serializes_a_masked_field() -> None:
    """The invariant that BOUNDS the shared-namespace finding above, pinned so it cannot rot.

    A D-013 replay re-emits a STORED response body and never runs the handler, so the
    ``Masked`` WrapSerializer (D-009) never runs either — the body was serialized under
    whatever permissions the principal who FIRST spent that key held. Combined with the
    shared (tenant, endpoint, key) namespace, the first Idempotent-guarded endpoint whose
    response carries a masked field turns replay into a field-masking bypass between two
    principals that both hold the endpoint's permission but differ on the masking one.

    Today no such endpoint exists — ``Masked(`` appears only on ``EmployeeRead`` and the
    employee routes are not idempotent — but that is a coincidence, not a design. This test
    is the alarm: if it ever fails, either drop the masked field from that response or give
    the reservation a principal column."""
    from app.modules.hr.schemas import EmployeeRead

    # Positive controls, so a green here can never mean "the detector found nothing".
    assert _masked_permissions(EmployeeRead) == {HR_EMPLOYEE_READ_COMPENSATION}
    assert _masked_permissions(Page[EmployeeRead]) == {HR_EMPLOYEE_READ_COMPENSATION}

    guarded = [
        route
        for route in create_app().routes
        if getattr(route, "dependant", None) is not None and _is_idempotent(route.dependant)
    ]
    assert len(guarded) >= 30, "idempotent routes stopped being detectable"

    offenders = {
        route.path: masked
        for route in guarded
        if (masked := _masked_permissions(route.response_model))
    }

    assert offenders == {}, (
        "Idempotent endpoints whose response carries D-009 masked fields — a replay would "
        f"emit them unmasked to another principal: {offenders}"
    )


async def test_stale_tenant_context_cannot_leak_between_requests(
    client: AsyncClient,
    admin_user: ProvisionedUser,
    user_factory: Callable[..., Awaitable[ProvisionedUser]],
    mint_key: MintKey,
) -> None:
    """_authenticate_api_key sets current_tenant_id BEFORE it knows the secret is valid, and
    never unsets it on failure. Interleave a failing tenant-A attempt with a real tenant-B call
    to prove the ContextVar cannot survive into another request (each ASGI request runs in its
    own asyncio context)."""
    beta = await user_factory(slug="beta", email="owner@beta.test", admin=True)
    beta_key = await mint_key(beta, scopes=[ADMIN_USER_MANAGE])

    forged = f"{API_KEY_PREFIX}_{admin_user.tenant_id.hex}_nosuchsecret"
    assert (await client.get("/api/v1/admin/users", headers=_bearer(forged))).status_code == 401

    ok = await client.get("/api/v1/admin/users", headers=_bearer(beta_key))
    assert ok.status_code == 200, ok.text
    emails = [item["email"] for item in ok.json()["items"]]
    assert emails == ["owner@beta.test"]
