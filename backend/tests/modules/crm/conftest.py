"""CRM test fixtures (STRUCTURE §6): a tenant with the cross-module data CRM validates against (a
currency + an item + a customer + an employee), plus bearer-token clients holding crm permissions.

The data builders live in tests/modules/crm/factories.py (STRUCTURE §8.4); this conftest keeps only
the
thin pytest fixtures wrapping them. Factories go through the REAL service layer under the tenant
context (D-025). The crm-permissioned clients provision a user, sync the catalog, and grant a role
carrying the crm keys — the projects_client pattern with crm.* keys. The autouse
handler-registration
fixture wires the sales OpportunityConverted handler so the convert tests dispatch it (D-011/D-057).
"""

import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from functools import partial

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import register_event_handlers
from tests.modules.crm.factories import (
    CrmPrincipal,
    CrmSetup,
    build_crm_setup,
    create_crm_principal,
)

__all__ = ["CrmPrincipal", "CrmSetup"]


@pytest.fixture(autouse=True)
def _register_event_handlers(clear_event_subscriptions: Callable[[], None]) -> None:
    """Register the cross-module handlers for every crm test. CRM publishes OpportunityConverted and
    SALES' handler creates the customer + quote (D-057), so the convert tests need the handler
    wired;
    this also wires the other module handlers so the test environment matches production.
    ``register_event_handlers`` de-duplicates (idempotent). Depends on the global
    ``clear_event_subscriptions`` so it runs AFTER the per-test reset."""
    register_event_handlers()


@pytest.fixture
async def crm_setup(db_session: AsyncSession, tenant_a: uuid.UUID) -> CrmSetup:
    """A currency + an item + an existing customer + an employee in tenant A, ready to drive the CRM
    flow (leads → opportunities + lines → activities → convert)."""
    return await build_crm_setup(db_session, tenant_a)


# --- CRM-permissioned HTTP clients --------------------------------------------


@pytest.fixture
def crm_user_factory(
    db_session: AsyncSession,
) -> Callable[..., "AsyncIterator[CrmPrincipal]"]:
    """Provision a tenant + user and grant a role with the crm permission keys through the real
    services (D-025). ``keys`` lets a test request a narrower grant (the 403 RBAC tests)."""
    return partial(create_crm_principal, db_session)


async def _login(client: AsyncClient, principal: CrmPrincipal) -> str:
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
async def crm_client(
    client: AsyncClient,
    crm_user_factory: Callable[..., AsyncIterator[CrmPrincipal]],
) -> AsyncIterator[AsyncClient]:
    """A real bearer-token client whose principal holds all crm permissions."""
    principal = await crm_user_factory()
    access_token = await _login(client, principal)
    client.headers["Authorization"] = f"Bearer {access_token}"
    yield client


@dataclass(frozen=True)
class CrmApi:
    """A logged-in full-rights client plus a CrmSetup seeded in THAT client's tenant — so the crm
    endpoints can be driven over the wire against a tenant with real cross-module data."""

    client: AsyncClient
    setup: CrmSetup


@pytest.fixture
async def crm_api(
    client: AsyncClient,
    db_session: AsyncSession,
    crm_user_factory: Callable[..., AsyncIterator[CrmPrincipal]],
) -> AsyncIterator[CrmApi]:
    """A bearer-token client whose principal holds all crm keys, with the crm setup (currency + item
    +
    customer + employee) seeded in that principal's tenant (PLAN 12.1)."""
    principal = await crm_user_factory()
    setup = await build_crm_setup(db_session, principal.tenant_id)
    access_token = await _login(client, principal)
    client.headers["Authorization"] = f"Bearer {access_token}"
    yield CrmApi(client=client, setup=setup)


@pytest.fixture
async def crm_principal_b(
    crm_user_factory: Callable[..., AsyncIterator[CrmPrincipal]],
) -> CrmPrincipal:
    """A SECOND crm principal in its own tenant — the cross-tenant tests prove one tenant's
    leads/opportunities can't be seen by another."""
    return await crm_user_factory(slug="crm-beta", email="sales@crm-beta.test")


@pytest.fixture
async def crm_client_b(
    client: AsyncClient, crm_principal_b: CrmPrincipal
) -> AsyncIterator[AsyncClient]:
    """A bearer-token client for the SECOND crm principal (tenant-isolation tests). Built on a
    SEPARATE
    httpx client so its Authorization header never clobbers the primary ``crm_client`` / ``crm_api``
    (the projects_client_b precedent)."""
    transport = client._transport  # the per-test ASGI transport bound to this test's app
    async with AsyncClient(transport=transport, base_url="https://test") as client_b:
        access_token = await _login(client_b, crm_principal_b)
        client_b.headers["Authorization"] = f"Bearer {access_token}"
        yield client_b
