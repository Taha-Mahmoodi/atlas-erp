"""D-013 idempotency: reservation + atomic completion via route capture.

A TEST-ONLY app exercises the full flow against a REAL audited model (TenantSetting): a guarded
POST route reserves a key, creates a setting inside run_in_uow, and captures the response. No fake
business endpoint is added to the production app (D-013: the real guarded endpoints arrive with
finance/inventory in PLAN 4/5). The side-effect-runs-exactly-once property is proven by counting
TenantSetting rows after a replay.
"""

import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.db import build_session_factory, get_session, get_session_factory
from app.core.events import run_in_uow
from app.core.idempotency import (
    STATUS_COMPLETED,
    STATUS_IN_PROGRESS,
    IdempotencyContext,
    IdempotencyKey,
    Idempotent,
    compute_request_hash,
    reserve,
)
from app.core.schemas import ApiModel
from app.core.tenancy import current_tenant_id, tenant_context
from app.main import create_app
from app.modules.admin.models import TenantSetting


class _SettingCreate(ApiModel):
    key: str
    value: dict


class _SettingRead(ApiModel):
    id: uuid.UUID
    key: str


def _build_app(engine: AsyncEngine, tenant_id: uuid.UUID, *, fail: bool = False) -> FastAPI:
    """A throwaway app with one guarded route. ``get_session`` / ``get_session_factory`` are
    overridden onto the per-test engine so the separate reservation session and the business
    session share the test DB. A tiny dependency sets the tenant context (standing in for
    get_current_user), declared before the Idempotent dependency so the context exists when
    reserve() runs."""
    app = create_app()
    factory = build_session_factory(engine)

    async def _override_session() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    async def _set_tenant() -> None:
        # ASYNC on purpose: a sync dependency runs in a threadpool, so a ContextVar set there
        # would not propagate to the async Idempotent dependency. Async keeps the set on the same
        # event-loop context (this stands in for get_current_user setting the D-007 tenant context).
        current_tenant_id.set(tenant_id)

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_session_factory] = lambda: factory

    guard = Idempotent("test.setting.create")

    @app.post("/api/v1/_test/settings", response_model=_SettingRead, status_code=201)
    async def create_setting(
        payload: _SettingCreate,
        _tenant: Annotated[None, Depends(_set_tenant)],
        session: Annotated[AsyncSession, Depends(get_session)],
        idem: Annotated[IdempotencyContext, Depends(guard)],
    ) -> _SettingRead:
        # capture() is called INSIDE the run_in_uow work so the completion UPDATE and the
        # TenantSetting INSERT land in the SAME transaction (D-013 atomicity): run_in_uow's single
        # commit persists both, or rolls both back. The read schema is captured here too.
        holder: dict[str, _SettingRead] = {}

        async def work() -> None:
            with tenant_context(tenant_id):
                setting = TenantSetting(key=payload.key, value=payload.value)
                session.add(setting)
                await session.flush()
                read = _SettingRead(id=setting.id, key=payload.key)
                if fail:
                    raise RuntimeError("business work blew up after reserve")
                holder["read"] = await idem.capture(read, status_code=201)

        await run_in_uow(session, work)
        return holder["read"]

    touch_guard = Idempotent("test.setting.touch")

    @app.post("/api/v1/_test/settings/{name}/touch", response_model=_SettingRead, status_code=201)
    async def touch_setting(
        name: str,
        _tenant: Annotated[None, Depends(_set_tenant)],
        session: Annotated[AsyncSession, Depends(get_session)],
        idem: Annotated[IdempotencyContext, Depends(touch_guard)],
    ) -> _SettingRead:
        # An ACTION route, the shape half the guarded endpoints in Atlas have: the resource is
        # named in the PATH and the body is empty. See the target-in-the-hash test below.
        holder: dict[str, _SettingRead] = {}

        async def work() -> None:
            with tenant_context(tenant_id):
                setting = TenantSetting(key=name, value={})
                session.add(setting)
                await session.flush()
                holder["read"] = await idem.capture(
                    _SettingRead(id=setting.id, key=name), status_code=201
                )

        await run_in_uow(session, work)
        return holder["read"]

    return app


async def _client(app: FastAPI, *, raise_app_exceptions: bool = True) -> AsyncClient:
    # raise_app_exceptions=False is needed only for the business-failure case: the guard's
    # teardown re-raises after cleanup, and we want httpx to surface the 500 envelope the app's
    # exception handler produces rather than re-raising the error into the test (a real ASGI
    # server does the former).
    transport = ASGITransport(app=app, raise_app_exceptions=raise_app_exceptions)
    return AsyncClient(transport=transport, base_url="https://test")


async def _count_settings(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    with tenant_context(tenant_id):
        return (
            await session.execute(select(func.count()).select_from(TenantSetting))
        ).scalar_one()


async def _load_key(session: AsyncSession, tenant_id: uuid.UUID, key: str) -> IdempotencyKey | None:
    with tenant_context(tenant_id):
        return (
            await session.execute(
                select(IdempotencyKey).where(
                    IdempotencyKey.endpoint == "test.setting.create",
                    IdempotencyKey.key == key,
                )
            )
        ).scalar_one_or_none()


async def test_first_request_reserves_completes_and_stores_response(
    db_engine: AsyncEngine, db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    app = _build_app(db_engine, tenant_a)
    async with await _client(app) as client:
        response = await client.post(
            "/api/v1/_test/settings",
            headers={"Idempotency-Key": "key-1"},
            json={"key": "theme", "value": {"mode": "dark"}},
        )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["key"] == "theme"

    row = await _load_key(db_session, tenant_a, "key-1")
    assert row is not None
    assert row.status == STATUS_COMPLETED
    assert row.response_status == 201
    assert row.response_body == body
    assert await _count_settings(db_session, tenant_a) == 1


async def test_replay_same_key_same_body_returns_stored_response_without_rerunning(
    db_engine: AsyncEngine, db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    app = _build_app(db_engine, tenant_a)
    payload = {"key": "theme", "value": {"mode": "dark"}}
    async with await _client(app) as client:
        first = await client.post(
            "/api/v1/_test/settings", headers={"Idempotency-Key": "k"}, json=payload
        )
        replay = await client.post(
            "/api/v1/_test/settings", headers={"Idempotency-Key": "k"}, json=payload
        )

    assert first.status_code == 201
    assert replay.status_code == 201
    # Same stored response, marked as a replay, and the handler did NOT run again.
    assert replay.json() == first.json()
    assert replay.headers.get("Idempotency-Replayed") == "true"
    assert await _count_settings(db_session, tenant_a) == 1


async def test_replay_same_key_different_body_returns_409_key_reuse(
    db_engine: AsyncEngine, tenant_a: uuid.UUID
) -> None:
    app = _build_app(db_engine, tenant_a)
    async with await _client(app) as client:
        await client.post(
            "/api/v1/_test/settings",
            headers={"Idempotency-Key": "k"},
            json={"key": "theme", "value": {"mode": "dark"}},
        )
        reused = await client.post(
            "/api/v1/_test/settings",
            headers={"Idempotency-Key": "k"},
            json={"key": "theme", "value": {"mode": "light"}},
        )
    assert reused.status_code == 422
    assert reused.json()["error"]["code"] == "idempotency.key_reuse"


async def test_concurrent_duplicate_in_progress_returns_409(
    db_engine: AsyncEngine, db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    # Simulate a concurrent duplicate by reserving the key first (the row is left IN_PROGRESS),
    # then firing the guarded request with the same key: reserve() collides and sees IN_PROGRESS.
    factory = build_session_factory(db_engine)
    body = b'{"key":"theme","value":{"mode":"dark"}}'
    await reserve(
        factory, tenant_a, "test.setting.create", "k", compute_request_hash(body)
    )

    app = _build_app(db_engine, tenant_a)
    async with await _client(app) as client:
        response = await client.post(
            "/api/v1/_test/settings",
            headers={"Idempotency-Key": "k"},
            json={"key": "theme", "value": {"mode": "dark"}},
        )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "idempotency.in_progress"
    # No business document was created for the duplicate.
    assert await _count_settings(db_session, tenant_a) == 0


async def test_missing_idempotency_key_header_returns_400(
    db_engine: AsyncEngine, tenant_a: uuid.UUID
) -> None:
    app = _build_app(db_engine, tenant_a)
    async with await _client(app) as client:
        response = await client.post(
            "/api/v1/_test/settings",
            json={"key": "theme", "value": {"mode": "dark"}},
        )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "idempotency.key_required"


async def test_business_failure_cleans_up_reservation_and_creates_no_document(
    db_engine: AsyncEngine, db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    # Fail-closed (D-013): if the business work raises after reserve, the IN_PROGRESS reservation
    # is deleted (not left as COMPLETED) and the document is not created, so the key can be retried.
    app = _build_app(db_engine, tenant_a, fail=True)
    async with await _client(app, raise_app_exceptions=False) as client:
        response = await client.post(
            "/api/v1/_test/settings",
            headers={"Idempotency-Key": "k"},
            json={"key": "theme", "value": {"mode": "dark"}},
        )
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "common.internal_error"
    assert await _load_key(db_session, tenant_a, "k") is None
    assert await _count_settings(db_session, tenant_a) == 0

    # The same key is now free: a fresh (non-failing) handler completes it.
    ok_app = _build_app(db_engine, tenant_a)
    async with await _client(ok_app) as client:
        retry = await client.post(
            "/api/v1/_test/settings",
            headers={"Idempotency-Key": "k"},
            json={"key": "theme", "value": {"mode": "dark"}},
        )
    assert retry.status_code == 201
    row = await _load_key(db_session, tenant_a, "k")
    assert row is not None and row.status == STATUS_COMPLETED


async def test_same_key_under_two_tenants_is_independent(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    payload = {"key": "theme", "value": {"mode": "dark"}}
    app_a = _build_app(db_engine, tenant_a)
    app_b = _build_app(db_engine, tenant_b)
    async with await _client(app_a) as client_a:
        resp_a = await client_a.post(
            "/api/v1/_test/settings", headers={"Idempotency-Key": "shared"}, json=payload
        )
    async with await _client(app_b) as client_b:
        resp_b = await client_b.post(
            "/api/v1/_test/settings", headers={"Idempotency-Key": "shared"}, json=payload
        )
    # Both succeed (no cross-tenant collision) and each tenant has its own reservation + document.
    assert resp_a.status_code == 201
    assert resp_b.status_code == 201
    assert resp_a.json()["id"] != resp_b.json()["id"]
    assert (await _load_key(db_session, tenant_a, "shared")) is not None
    assert (await _load_key(db_session, tenant_b, "shared")) is not None
    assert await _count_settings(db_session, tenant_a) == 1
    assert await _count_settings(db_session, tenant_b) == 1


async def test_a_key_spent_on_one_resource_cannot_answer_for_another(
    db_engine: AsyncEngine, db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """The half of D-013's replay contract an ACTION route breaks if only the body is hashed.

    ``POST /{id}/fire``, ``/{id}/post``, ``/{id}/send`` carry NO body, so every resource on the
    route hashes b'' identically: a key spent on one document would REPLAY that document's stored
    response for a DIFFERENT one — a 2xx for work that never ran, and the one case the
    different-body 422 cannot see, because there is no body to differ. The guard therefore hashes
    the request TARGET together with the body, which turns the collision back into the ordinary
    key-reuse refusal a client retries under a fresh key.
    """
    app = _build_app(db_engine, tenant_a)
    async with await _client(app) as client:
        first = await client.post(
            "/api/v1/_test/settings/alpha/touch", headers={"Idempotency-Key": "k"}
        )
        second = await client.post(
            "/api/v1/_test/settings/beta/touch", headers={"Idempotency-Key": "k"}
        )
        replay = await client.post(
            "/api/v1/_test/settings/alpha/touch", headers={"Idempotency-Key": "k"}
        )

    assert first.status_code == 201, first.text
    assert first.json()["key"] == "alpha"
    assert second.status_code == 422, second.text
    assert second.json()["error"]["code"] == "idempotency.key_reuse"
    # The genuine retry — same key, same target — still replays verbatim and runs nothing twice.
    assert replay.status_code == 201, replay.text
    assert replay.json() == first.json()
    assert await _count_settings(db_session, tenant_a) == 1


def test_status_constants_match_decision() -> None:
    # D-013 stores status as 'in_progress' | 'completed'.
    assert STATUS_IN_PROGRESS == "in_progress"
    assert STATUS_COMPLETED == "completed"
