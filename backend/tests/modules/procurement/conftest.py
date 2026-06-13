"""Procurement test fixtures (STRUCTURE §6): a tenant ready to create vendors (a seeded currency +
a real inventory item), plus bearer-token clients holding procurement permissions.

The data builders live in tests/modules/procurement/factories.py (STRUCTURE §8.4); this conftest
keeps only the thin pytest fixtures wrapping them. Factories go through the REAL service layer under
the tenant context (D-025), so tenancy stamping and audit fire exactly as in production. The
procurement-permissioned clients provision a user, sync the catalog, and grant a role carrying the
procurement keys (plus the finance/inventory setup keys the cross-module API tests need) — mirroring
the finance_client / inventory_client pattern with procurement.* instead.
"""

import uuid
from collections.abc import AsyncIterator, Callable
from functools import partial

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.modules.procurement.factories import (
    ProcurementPrincipal,
    ProcurementSetup,
    build_procurement_setup,
    create_procurement_principal,
)

__all__ = ["ProcurementPrincipal", "ProcurementSetup"]


@pytest.fixture
async def procurement_setup(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> ProcurementSetup:
    """A USD currency + a STOCKED inventory item in tenant A, ready to create vendors and approve
    items (PLAN 6.1)."""
    return await build_procurement_setup(db_session, tenant_a)


# --- Procurement-permissioned HTTP clients ------------------------------------


@pytest.fixture
def procurement_user_factory(
    db_session: AsyncSession,
) -> Callable[..., "AsyncIterator[ProcurementPrincipal]"]:
    """Provision a tenant + user and grant a role with the procurement permission keys, through the
    real services (D-025). ``keys`` lets a test request a narrower grant (the 403 RBAC tests)."""
    return partial(create_procurement_principal, db_session)


async def _login(client: AsyncClient, principal: ProcurementPrincipal) -> str:
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
async def procurement_client(
    client: AsyncClient,
    procurement_user_factory: Callable[..., AsyncIterator[ProcurementPrincipal]],
) -> AsyncIterator[AsyncClient]:
    """A real bearer-token client whose principal holds all procurement permissions (plus the
    finance/inventory setup keys for cross-module API scaffolding)."""
    principal = await procurement_user_factory()
    access_token = await _login(client, principal)
    client.headers["Authorization"] = f"Bearer {access_token}"
    yield client


@pytest.fixture
async def procurement_principal_b(
    procurement_user_factory: Callable[..., AsyncIterator[ProcurementPrincipal]],
) -> ProcurementPrincipal:
    """A SECOND procurement principal in its own tenant — used by the cross-tenant tests to prove
    one tenant's vendors can't be seen (or invalidate an ETag) for another tenant."""
    return await procurement_user_factory(slug="proc-beta", email="buyer@proc-beta.test")


@pytest.fixture
async def procurement_client_b(
    client: AsyncClient, procurement_principal_b: ProcurementPrincipal
) -> AsyncIterator[AsyncClient]:
    """A bearer-token client for the second procurement tenant. Built on a SEPARATE httpx client so
    its Authorization header never clobbers the primary ``procurement_client``."""
    transport = client._transport  # the per-test ASGI transport bound to this test's app
    async with AsyncClient(transport=transport, base_url="https://test") as client_b:
        access_token = await _login(client_b, procurement_principal_b)
        client_b.headers["Authorization"] = f"Bearer {access_token}"
        yield client_b
