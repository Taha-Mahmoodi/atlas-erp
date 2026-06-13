"""Inventory test fixtures (STRUCTURE §6): a tenant with EA/BOX UoMs and a costing category,
plus bearer-token clients holding inventory permissions.

The data builders live in tests/modules/inventory/factories.py (STRUCTURE §8.4); this conftest
keeps only the thin pytest fixtures wrapping them. Factories go through the REAL service layer
under the tenant context (D-025), so tenancy stamping and audit fire exactly as in production.
The inventory-permissioned clients provision a user, sync the catalog, and grant a role carrying
the inventory keys — mirroring the finance_client pattern with inventory.* instead of finance.*.
"""

import uuid
from collections.abc import AsyncIterator, Callable
from functools import partial

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.modules.inventory.factories import (
    InventoryPrincipal,
    InventorySetup,
    StockSetup,
    build_inventory_setup,
    build_stock_setup,
    create_inventory_principal,
)

__all__ = ["InventoryPrincipal", "InventorySetup", "StockSetup"]


@pytest.fixture
async def inventory_setup(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> InventorySetup:
    """EA + BOX units and a MOVING_AVERAGE raw-materials category in tenant A (PLAN 5.1)."""
    return await build_inventory_setup(db_session, tenant_a)


@pytest.fixture
async def stock_setup(db_session: AsyncSession, tenant_a: uuid.UUID) -> StockSetup:
    """A STOCKED item + warehouse + two bins in tenant A, ready to post moves (PLAN 5.2)."""
    return await build_stock_setup(db_session, tenant_a)


# --- Inventory-permissioned HTTP clients --------------------------------------


@pytest.fixture
def inventory_user_factory(
    db_session: AsyncSession,
) -> Callable[..., "AsyncIterator[InventoryPrincipal]"]:
    """Provision a tenant + user and grant a role with the inventory permission keys, through the
    real services (D-025). ``keys`` lets a test request a narrower grant (the 403 RBAC tests)."""
    return partial(create_inventory_principal, db_session)


async def _login(client: AsyncClient, principal: InventoryPrincipal) -> str:
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
async def inventory_client(
    client: AsyncClient,
    inventory_user_factory: Callable[..., AsyncIterator[InventoryPrincipal]],
) -> AsyncIterator[AsyncClient]:
    """A real bearer-token client whose principal holds all inventory permissions."""
    principal = await inventory_user_factory()
    access_token = await _login(client, principal)
    client.headers["Authorization"] = f"Bearer {access_token}"
    yield client


@pytest.fixture
async def inventory_principal_b(
    inventory_user_factory: Callable[..., AsyncIterator[InventoryPrincipal]],
) -> InventoryPrincipal:
    """A SECOND inventory principal in its own tenant — used by the cross-tenant tests to prove one
    tenant's items can't be seen (or invalidate an ETag) for another tenant."""
    return await inventory_user_factory(slug="inv-beta", email="ops@inv-beta.test")


@pytest.fixture
async def inventory_client_b(
    client: AsyncClient, inventory_principal_b: InventoryPrincipal
) -> AsyncIterator[AsyncClient]:
    """A bearer-token client for the second inventory tenant. Built on a SEPARATE httpx client so
    its Authorization header never clobbers the primary ``inventory_client``."""
    transport = client._transport  # the per-test ASGI transport bound to this test's app
    async with AsyncClient(transport=transport, base_url="https://test") as client_b:
        access_token = await _login(client_b, inventory_principal_b)
        client_b.headers["Authorization"] = f"Bearer {access_token}"
        yield client_b
