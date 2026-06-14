"""Maintenance test fixtures (STRUCTURE §6): a tenant with a cost centre + ACTIVE equipment ready to
raise corrective orders / author plans, plus bearer-token clients holding maintenance permissions.

The data builders live in tests/modules/maintenance/factories.py (STRUCTURE §8.4); this conftest
keeps only the thin pytest fixtures wrapping them. Factories go through the REAL service layer under
the tenant context (D-025). The maintenance-permissioned clients provision a user, sync the catalog,
and grant a role carrying the maintenance keys — the manufacturing_client pattern with maintenance.*
instead of manufacturing.*.
"""

import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from functools import partial

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import register_event_handlers
from tests.modules.maintenance.factories import (
    MaintenancePrincipal,
    MaintenanceSetup,
    build_maintenance_setup,
    create_maintenance_principal,
)

__all__ = ["MaintenancePrincipal", "MaintenanceSetup"]


@pytest.fixture(autouse=True)
def _register_event_handlers(clear_event_subscriptions: Callable[[], None]) -> None:
    """Register the cross-module handlers for every maintenance test. Maintenance publishes /
    subscribes to NO cross-module event in v1 (record-only completion, D-051), but the shared app
    factory registers ALL module handlers, so this keeps the test environment identical to
    production and idempotent (``register_event_handlers`` de-duplicates). Depends on the global
    ``clear_event_subscriptions`` so it runs AFTER the per-test reset."""
    register_event_handlers()


@pytest.fixture
async def maintenance_setup(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> MaintenanceSetup:
    """A cost centre + a piece of ACTIVE equipment in tenant A, ready to raise corrective orders and
    author plans."""
    return await build_maintenance_setup(db_session, tenant_a)


# --- Maintenance-permissioned HTTP clients ------------------------------------


@pytest.fixture
def maintenance_user_factory(
    db_session: AsyncSession,
) -> Callable[..., "AsyncIterator[MaintenancePrincipal]"]:
    """Provision a tenant + user and grant a role with the maintenance permission keys through the
    real services (D-025). ``keys`` lets a test request a narrower grant (the 403 RBAC tests)."""
    return partial(create_maintenance_principal, db_session)


async def _login(client: AsyncClient, principal: MaintenancePrincipal) -> str:
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


@pytest.fixture
async def maintenance_client(
    client: AsyncClient,
    maintenance_user_factory: Callable[..., AsyncIterator[MaintenancePrincipal]],
) -> AsyncIterator[AsyncClient]:
    """A real bearer-token client whose principal holds all maintenance permissions."""
    principal = await maintenance_user_factory()
    access_token = await _login(client, principal)
    client.headers["Authorization"] = f"Bearer {access_token}"
    yield client


@dataclass(frozen=True)
class MaintenanceApi:
    """A logged-in full-rights client plus a MaintenanceSetup seeded in THAT client's tenant — so
    the maintenance endpoints can be driven over the wire against a tenant with real equipment."""

    client: AsyncClient
    setup: MaintenanceSetup


@pytest.fixture
async def maintenance_api(
    client: AsyncClient,
    db_session: AsyncSession,
    maintenance_user_factory: Callable[..., AsyncIterator[MaintenancePrincipal]],
) -> AsyncIterator[MaintenanceApi]:
    """A bearer-token client whose principal holds all maintenance keys, with the maintenance setup
    (a cost centre + ACTIVE equipment) seeded in that principal's tenant (PLAN 9.2)."""
    principal = await maintenance_user_factory()
    setup = await build_maintenance_setup(db_session, principal.tenant_id)
    access_token = await _login(client, principal)
    client.headers["Authorization"] = f"Bearer {access_token}"
    yield MaintenanceApi(client=client, setup=setup)


@pytest.fixture
async def maintenance_principal_b(
    maintenance_user_factory: Callable[..., AsyncIterator[MaintenancePrincipal]],
) -> MaintenancePrincipal:
    """A SECOND maintenance principal in its own tenant — used by the cross-tenant tests to prove
    one tenant's equipment/orders can't be seen by another tenant."""
    return await maintenance_user_factory(slug="pm-beta", email="ops@pm-beta.test")


@pytest.fixture
async def maintenance_client_b(
    client: AsyncClient, maintenance_principal_b: MaintenancePrincipal
) -> AsyncIterator[AsyncClient]:
    """A bearer-token client for the second maintenance tenant. Built on a SEPARATE httpx client so
    its Authorization header never clobbers the primary ``maintenance_client``."""
    transport = client._transport  # the per-test ASGI transport bound to this test's app
    async with AsyncClient(transport=transport, base_url="https://test") as client_b:
        access_token = await _login(client_b, maintenance_principal_b)
        client_b.headers["Authorization"] = f"Bearer {access_token}"
        yield client_b
