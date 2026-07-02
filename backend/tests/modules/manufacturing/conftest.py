"""Manufacturing test fixtures (STRUCTURE §6): a tenant with EA UoM + a parent/component item ready
to author BOMs/routings, plus bearer-token clients holding manufacturing permissions.

The data builders live in tests/modules/manufacturing/factories.py (STRUCTURE §8.4); this conftest
keeps only the thin pytest fixtures wrapping them. Factories go through the REAL service layer under
the tenant context (D-025). The manufacturing-permissioned clients provision a user, sync the
catalog, and grant a role carrying the manufacturing keys — the inventory_client pattern with
manufacturing.* instead of inventory.*.
"""

import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from functools import partial

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import register_event_handlers
from tests.modules.manufacturing.factories import (
    ManufacturingPrincipal,
    ManufacturingSetup,
    build_manufacturing_setup,
    create_mfg_principal,
)
from tests.modules.manufacturing.mrp_factories import MrpSetup, build_mrp_setup
from tests.modules.manufacturing.production_factories import (
    ProductionOrderSetup,
    build_production_order_setup,
)

__all__ = ["ManufacturingPrincipal", "ManufacturingSetup", "MrpSetup", "ProductionOrderSetup"]


@pytest.fixture(autouse=True)
def _register_event_handlers(clear_event_subscriptions: Callable[[], None]) -> None:
    """Register the cross-module handlers for every manufacturing test (PLAN 8.2, D-048): the
    production-order → inventory component-issue/finished-receipt bridges, the inventory → finance
    WIP-journal handler, and the finance WIP-variance handler — so an issue/finish posted through
    the SERVICE layer (not the HTTP app, which registers handlers in its factory) creates the stock
    moves + WIP journals. Depends on the global ``clear_event_subscriptions`` so it runs AFTER the
    per-test reset; idempotent (``register_event_handlers`` de-duplicates)."""
    register_event_handlers()


@pytest.fixture
async def manufacturing_setup(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> ManufacturingSetup:
    """An EA UoM, a category, and a parent + component item in tenant A, ready to author masters."""
    return await build_manufacturing_setup(db_session, tenant_a)


@pytest.fixture
async def production_order_setup(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> ProductionOrderSetup:
    """A tenant fully wired for the production-order flow (PLAN 8.2): items + GL accounts + open
    period + warehouse/bins + WIP/variance defaults + component on-hand + an ACTIVE BOM."""
    return await build_production_order_setup(db_session, tenant_a)


# --- Manufacturing-permissioned HTTP clients ----------------------------------


@pytest.fixture
def mfg_user_factory(
    db_session: AsyncSession,
) -> Callable[..., "AsyncIterator[ManufacturingPrincipal]"]:
    """Provision a tenant + user and grant a role with the manufacturing permission keys through the
    real services (D-025). ``keys`` lets a test request a narrower grant (the 403 RBAC tests)."""
    return partial(create_mfg_principal, db_session)


async def _login(client: AsyncClient, principal: ManufacturingPrincipal) -> str:
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
async def mfg_client(
    client: AsyncClient,
    mfg_user_factory: Callable[..., AsyncIterator[ManufacturingPrincipal]],
) -> AsyncIterator[AsyncClient]:
    """A real bearer-token client whose principal holds all manufacturing permissions."""
    principal = await mfg_user_factory()
    access_token = await _login(client, principal)
    client.headers["Authorization"] = f"Bearer {access_token}"
    yield client


@dataclass(frozen=True)
class ProductionApi:
    """A logged-in full-rights client plus a ProductionOrderSetup seeded in THAT client's tenant —
    so the production-order endpoints can be driven over the wire against a fully-wired tenant."""

    client: AsyncClient
    setup: ProductionOrderSetup


@pytest.fixture
async def production_api(
    client: AsyncClient,
    db_session: AsyncSession,
    mfg_user_factory: Callable[..., AsyncIterator[ManufacturingPrincipal]],
) -> AsyncIterator[ProductionApi]:
    """A bearer-token client whose principal holds all manufacturing keys, with the full
    production-order setup (items + GL accounts + open period + warehouse/bins + WIP/variance
    defaults + component on-hand + an ACTIVE BOM) seeded in that principal's tenant (PLAN 8.2)."""
    principal = await mfg_user_factory()
    setup = await build_production_order_setup(db_session, principal.tenant_id)
    access_token = await _login(client, principal)
    client.headers["Authorization"] = f"Bearer {access_token}"
    yield ProductionApi(client=client, setup=setup)


@dataclass(frozen=True)
class MrpApi:
    """A logged-in full-rights client plus an MrpSetup seeded in THAT client's tenant — so the MRP
    endpoints (run as a job, planned-order reads + conversions, capacity) can be driven over the
    wire against a tenant with real demand + a multi-level BOM."""

    client: AsyncClient
    setup: MrpSetup


@pytest.fixture
async def mrp_api(
    client: AsyncClient,
    db_session: AsyncSession,
    mfg_user_factory: Callable[..., AsyncIterator[ManufacturingPrincipal]],
) -> AsyncIterator[MrpApi]:
    """A bearer-token client whose principal holds all manufacturing keys, with the full MRP setup
    (a confirmed undelivered sales order, a multi-level BOM, a routing, a vendor) seeded in that
    principal's tenant (PLAN 8.3)."""
    principal = await mfg_user_factory()
    setup = await build_mrp_setup(db_session, principal.tenant_id)
    access_token = await _login(client, principal)
    client.headers["Authorization"] = f"Bearer {access_token}"
    yield MrpApi(client=client, setup=setup)


@pytest.fixture
async def mfg_principal_b(
    mfg_user_factory: Callable[..., AsyncIterator[ManufacturingPrincipal]],
) -> ManufacturingPrincipal:
    """A SECOND manufacturing principal in its own tenant — used by the cross-tenant tests to prove
    one tenant's masters can't be seen (or invalidate an ETag) for another tenant."""
    return await mfg_user_factory(slug="mfg-beta", email="ops@mfg-beta.test")


@pytest.fixture
async def mfg_client_b(
    client: AsyncClient, mfg_principal_b: ManufacturingPrincipal
) -> AsyncIterator[AsyncClient]:
    """A bearer-token client for the second manufacturing tenant. Built on a SEPARATE httpx client
    so its Authorization header never clobbers the primary ``mfg_client``."""
    transport = client._transport  # the per-test ASGI transport bound to this test's app
    async with AsyncClient(transport=transport, base_url="https://test") as client_b:
        access_token = await _login(client_b, mfg_principal_b)
        client_b.headers["Authorization"] = f"Bearer {access_token}"
        yield client_b
