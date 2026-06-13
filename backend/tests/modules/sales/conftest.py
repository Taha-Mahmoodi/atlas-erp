"""Sales test fixtures (STRUCTURE §6): a tenant ready to create customers + price lists (a seeded
currency + a real inventory item), plus bearer-token clients holding sales permissions.

The data builders live in tests/modules/sales/factories.py (STRUCTURE §8.4); this conftest keeps
only
the thin pytest fixtures wrapping them. Factories go through the REAL service layer under the tenant
context (D-025), so tenancy stamping and audit fire exactly as in production. The sales-permissioned
clients provision a user, sync the catalog, and grant a role carrying the sales keys (plus the
finance/inventory setup keys the cross-module API tests need) — mirroring the procurement_client
pattern with sales.* instead.
"""

import uuid
from collections.abc import AsyncIterator, Callable
from functools import partial

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.modules.sales.factories import (
    SalesPrincipal,
    SalesSetup,
    build_sales_setup,
    create_sales_principal,
)

__all__ = ["SalesPrincipal", "SalesSetup"]


@pytest.fixture
async def sales_setup(db_session: AsyncSession, tenant_a: uuid.UUID) -> SalesSetup:
    """A USD currency + a real inventory item in tenant A, ready to create customers and price-list
    items (PLAN 7.1)."""
    return await build_sales_setup(db_session, tenant_a)


# --- Sales-permissioned HTTP clients ------------------------------------------


@pytest.fixture
def sales_user_factory(
    db_session: AsyncSession,
) -> Callable[..., "AsyncIterator[SalesPrincipal]"]:
    """Provision a tenant + user and grant a role with the sales permission keys, through the real
    services (D-025). ``keys`` lets a test request a narrower grant (the 403 RBAC tests)."""
    return partial(create_sales_principal, db_session)


async def _login(client: AsyncClient, principal: SalesPrincipal) -> str:
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
async def sales_client(
    client: AsyncClient,
    sales_user_factory: Callable[..., AsyncIterator[SalesPrincipal]],
) -> AsyncIterator[AsyncClient]:
    """A real bearer-token client whose principal holds all sales permissions (plus the
    finance/inventory setup keys for cross-module API scaffolding)."""
    principal = await sales_user_factory()
    access_token = await _login(client, principal)
    client.headers["Authorization"] = f"Bearer {access_token}"
    yield client


@pytest.fixture
async def sales_principal_b(
    sales_user_factory: Callable[..., AsyncIterator[SalesPrincipal]],
) -> SalesPrincipal:
    """A SECOND sales principal in its own tenant — used by the cross-tenant tests to prove one
    tenant's customers can't be seen (or invalidate an ETag) for another tenant."""
    return await sales_user_factory(slug="sales-beta", email="rep@sales-beta.test")


@pytest.fixture
async def sales_client_b(
    client: AsyncClient, sales_principal_b: SalesPrincipal
) -> AsyncIterator[AsyncClient]:
    """A bearer-token client for the second sales tenant. Built on a SEPARATE httpx client so its
    Authorization header never clobbers the primary ``sales_client``."""
    transport = client._transport  # the per-test ASGI transport bound to this test's app
    async with AsyncClient(transport=transport, base_url="https://test") as client_b:
        access_token = await _login(client_b, sales_principal_b)
        client_b.headers["Authorization"] = f"Bearer {access_token}"
        yield client_b
