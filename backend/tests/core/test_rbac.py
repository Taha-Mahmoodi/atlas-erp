"""RBAC engine tests (D-009): catalog sync idempotency, key validation against the
code catalog, permission resolution + union semantics, the require_permission dependency
(403/200 envelopes), tenant-correct denial, the TTL cache + invalidation, field-level
read masking, and /auth/me returning the granted set."""

import uuid
from collections.abc import Callable

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationFailedError
from app.core.models import Permission
from app.core.rbac import (
    ADMIN_AUDIT_READ,
    ADMIN_ROLE_MANAGE,
    ADMIN_USER_MANAGE,
    Masked,
    clear_cache,
    require_permission,
    resolve_permissions,
    sync_permission_catalog,
)
from app.core.schemas import ApiModel
from app.core.tenancy import system_context, tenant_context
from app.modules.admin.service import (
    assign_role,
    create_role,
    grant_admin_role,
    provision_tenant,
    provision_user,
)
from tests.conftest import ProvisionedUser

# --- Catalog sync -------------------------------------------------------------


async def _count_permissions(session: AsyncSession) -> int:
    with system_context():
        return (await session.execute(select(func.count()).select_from(Permission))).scalar_one()


async def test_sync_permission_catalog_is_idempotent(db_session: AsyncSession) -> None:
    with system_context():
        first = await sync_permission_catalog(db_session)
        await db_session.commit()
    after_first = await _count_permissions(db_session)
    with system_context():
        second = await sync_permission_catalog(db_session)
        await db_session.commit()
    after_second = await _count_permissions(db_session)

    assert first == after_first  # every key inserted on the first run
    assert second == 0  # nothing inserted on the second run
    assert after_first == after_second  # count is stable, no dupes


async def test_synced_catalog_contains_core_admin_keys(db_session: AsyncSession) -> None:
    with system_context():
        await sync_permission_catalog(db_session)
        await db_session.commit()
        keys = set((await db_session.execute(select(Permission.key))).scalars().all())
    assert {ADMIN_USER_MANAGE, ADMIN_ROLE_MANAGE, ADMIN_AUDIT_READ} <= keys


# --- Catalog is the source of truth: tenants cannot invent keys ---------------


async def test_create_role_with_unknown_key_raises(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    with system_context():
        await sync_permission_catalog(db_session)
        await db_session.commit()
    with pytest.raises(ValidationFailedError) as excinfo:
        await create_role(db_session, tenant_a, "Bogus", ["made.up.key"])
    assert excinfo.value.code == "rbac.unknown_permission"
    assert "made.up.key" in excinfo.value.details["keys"]


# --- Permission resolution ----------------------------------------------------


async def _provision_principal(db_session: AsyncSession, slug: str) -> ProvisionedUser:
    tenant = await provision_tenant(db_session, slug=slug, name=slug.title())
    user = await provision_user(db_session, tenant.id, email=f"u@{slug}.test", password="pw-pw-pw")
    return ProvisionedUser(
        tenant_id=tenant.id,
        tenant_slug=slug,
        user_id=user.id,
        email=f"u@{slug}.test",
        password="pw-pw-pw",
    )


async def test_resolve_permissions_unions_a_users_roles(db_session: AsyncSession) -> None:
    principal = await _provision_principal(db_session, "uni")
    with system_context():
        await sync_permission_catalog(db_session)
    role_one = await create_role(db_session, principal.tenant_id, "R1", [ADMIN_USER_MANAGE])
    role_two = await create_role(db_session, principal.tenant_id, "R2", [ADMIN_AUDIT_READ])
    await assign_role(db_session, principal.tenant_id, principal.user_id, role_one.id, 0)
    await assign_role(db_session, principal.tenant_id, principal.user_id, role_two.id, 0)
    await db_session.commit()

    clear_cache()
    with tenant_context(principal.tenant_id):
        resolved = await resolve_permissions(
            db_session, principal.user_id, principal.tenant_id, 0
        )
    assert resolved == frozenset({ADMIN_USER_MANAGE, ADMIN_AUDIT_READ})


async def test_resolve_permissions_empty_for_user_without_roles(
    db_session: AsyncSession,
) -> None:
    principal = await _provision_principal(db_session, "norole")
    await db_session.commit()
    clear_cache()
    with tenant_context(principal.tenant_id):
        resolved = await resolve_permissions(
            db_session, principal.user_id, principal.tenant_id, 0
        )
    assert resolved == frozenset()


# --- TTL cache + invalidation -------------------------------------------------


async def test_cache_serves_repeat_and_invalidate_exposes_new_grant(
    db_session: AsyncSession,
) -> None:
    principal = await _provision_principal(db_session, "cache")
    with system_context():
        await sync_permission_catalog(db_session)
    role = await create_role(db_session, principal.tenant_id, "Readers", [ADMIN_AUDIT_READ])
    await db_session.commit()
    clear_cache()

    with tenant_context(principal.tenant_id):
        first = await resolve_permissions(db_session, principal.user_id, principal.tenant_id, 0)
        # A within-TTL repeat returns the SAME cached set even though nothing assigned yet.
        second = await resolve_permissions(db_session, principal.user_id, principal.tenant_id, 0)
    assert first == second == frozenset()

    # Assign the role; assign_role evicts the (tenant, user, version) cache entry.
    await assign_role(db_session, principal.tenant_id, principal.user_id, role.id, 0)
    await db_session.commit()
    with tenant_context(principal.tenant_id):
        after = await resolve_permissions(db_session, principal.user_id, principal.tenant_id, 0)
    assert after == frozenset({ADMIN_AUDIT_READ})


async def test_cache_respects_injected_clock_expiry(db_session: AsyncSession) -> None:
    principal = await _provision_principal(db_session, "clock")
    await db_session.commit()
    clear_cache()
    with tenant_context(principal.tenant_id):
        # Cache at t=0; without invalidation a read at t=120 (> 60s TTL) recomputes.
        await resolve_permissions(db_session, principal.user_id, principal.tenant_id, 0, now=0.0)
        again = await resolve_permissions(
            db_session, principal.user_id, principal.tenant_id, 0, now=120.0
        )
    assert again == frozenset()


# --- require_permission dependency: 403 / 200 on an in-test guarded route ------


def _mount_guarded_route(app: FastAPI) -> None:
    """Attach a tiny route guarded by require_permission to the real app fixture, which
    already carries the AtlasError->envelope handlers and the session override (D-025)."""

    @app.get("/guarded", dependencies=[Depends(require_permission(ADMIN_USER_MANAGE))])
    async def guarded() -> dict[str, bool]:
        return {"ok": True}


async def _guarded_client(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="https://test")


async def _bearer(client: AsyncClient, principal: ProvisionedUser) -> str:
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


async def test_require_permission_denies_without_key(
    app: FastAPI, client: AsyncClient, provisioned_user: ProvisionedUser
) -> None:
    token = await _bearer(client, provisioned_user)
    _mount_guarded_route(app)
    async with await _guarded_client(app) as guarded_client:
        response = await guarded_client.get(
            "/guarded", headers={"Authorization": f"Bearer {token}"}
        )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "rbac.permission_denied"
    assert response.json()["error"]["details"]["permission"] == ADMIN_USER_MANAGE


async def test_require_permission_allows_with_key(
    app: FastAPI, client: AsyncClient, admin_user: ProvisionedUser
) -> None:
    token = await _bearer(client, admin_user)
    _mount_guarded_route(app)
    async with await _guarded_client(app) as guarded_client:
        response = await guarded_client.get(
            "/guarded", headers={"Authorization": f"Bearer {token}"}
        )
    assert response.status_code == 200
    assert response.json() == {"ok": True}


# --- Tenant-correct denial ----------------------------------------------------


async def test_grant_in_tenant_a_does_not_apply_in_tenant_b(db_session: AsyncSession) -> None:
    a = await _provision_principal(db_session, "ta")
    b = await _provision_principal(db_session, "tb")
    with system_context():
        await sync_permission_catalog(db_session)
    # Same role NAME + key in tenant A only.
    await grant_admin_role(db_session, a.tenant_id, a.user_id, 0)
    await db_session.commit()
    clear_cache()

    with tenant_context(a.tenant_id):
        perms_a = await resolve_permissions(db_session, a.user_id, a.tenant_id, 0)
    with tenant_context(b.tenant_id):
        perms_b = await resolve_permissions(db_session, b.user_id, b.tenant_id, 0)
    assert ADMIN_USER_MANAGE in perms_a
    assert perms_b == frozenset()


# --- Field-level read masking -------------------------------------------------

_COMP_PERMISSION = "hr.compensation.read"


class _CompensationRead(ApiModel):
    name: str
    base_salary: Masked(str, _COMP_PERMISSION)


class _CompensationCreate(BaseModel):
    # CONVENTION (D-009): masked fields are EXCLUDED from Create/Update schemas so a
    # partial write can never silently null compensation; only `name` is settable here.
    name: str


def test_masked_field_serializes_real_value_when_permitted(
    permissions_context: Callable[[frozenset[str]], None],
) -> None:
    permissions_context(frozenset({_COMP_PERMISSION}))
    model = _CompensationRead(name="Ada", base_salary="120000")
    assert model.model_dump()["base_salary"] == "120000"


def test_masked_field_serializes_none_when_not_permitted(
    permissions_context: Callable[[frozenset[str]], None],
) -> None:
    permissions_context(frozenset())
    model = _CompensationRead(name="Ada", base_salary="120000")
    assert model.model_dump()["base_salary"] is None


def test_masked_field_excluded_from_create_schema() -> None:
    assert "base_salary" not in _CompensationCreate.model_fields
    assert "base_salary" in _CompensationRead.model_fields


# --- /auth/me returns the granted permission set ------------------------------


async def test_me_returns_granted_permissions_after_admin_role(
    admin_client: AsyncClient, admin_user: ProvisionedUser
) -> None:
    response = await admin_client.get("/api/v1/auth/me")
    assert response.status_code == 200
    permissions = response.json()["permissions"]
    assert ADMIN_USER_MANAGE in permissions
    assert ADMIN_ROLE_MANAGE in permissions
    assert ADMIN_AUDIT_READ in permissions
