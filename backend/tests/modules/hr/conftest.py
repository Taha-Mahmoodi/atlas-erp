"""HR test fixtures (STRUCTURE §6): a tenant with a cost centre + a root department ready to author
positions and employees, plus bearer-token clients holding hr permissions (full, and narrowed grants
for the masking / RBAC tests).

The data builders live in tests/modules/hr/factories.py (STRUCTURE §8.4); this conftest keeps only
the thin pytest fixtures wrapping them. Factories go through the REAL service layer under the tenant
context (D-025). The hr-permissioned clients provision a user, sync the catalog, and grant a role
carrying the requested hr keys — the maintenance_client pattern with hr.* instead of maintenance.*.
"""

import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from functools import partial

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import register_event_handlers
from tests.modules.hr.factories import (
    HrPrincipal,
    HrSetup,
    build_hr_setup,
    create_hr_principal,
)

__all__ = ["HrApi", "HrPrincipal", "HrSetup"]


@pytest.fixture(autouse=True)
def _register_event_handlers(clear_event_subscriptions: Callable[[], None]) -> None:
    """Register the cross-module handlers for every hr test. HR publishes / subscribes to NO
    cross-module event in v1 (D-052), but the shared app factory registers ALL module handlers, so
    this keeps the test environment identical to production and idempotent
    (``register_event_handlers`` de-duplicates). Depends on the global ``clear_event_subscriptions``
    so it runs AFTER the per-test reset."""
    register_event_handlers()


@pytest.fixture
async def hr_setup(db_session: AsyncSession, tenant_a: uuid.UUID) -> HrSetup:
    """A cost centre + a root department in tenant A, ready to author positions and employees."""
    return await build_hr_setup(db_session, tenant_a)


# --- HR-permissioned HTTP clients ---------------------------------------------


@pytest.fixture
def hr_user_factory(
    db_session: AsyncSession,
) -> Callable[..., "AsyncIterator[HrPrincipal]"]:
    """Provision a tenant + user and grant a role with the hr permission keys through the real
    services (D-025). ``keys`` lets a test request a narrower grant (the masking / 403 RBAC
    tests)."""
    return partial(create_hr_principal, db_session)


async def _login(client: AsyncClient, principal: HrPrincipal) -> str:
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
async def hr_client(
    client: AsyncClient,
    hr_user_factory: Callable[..., AsyncIterator[HrPrincipal]],
) -> AsyncIterator[AsyncClient]:
    """A real bearer-token client whose principal holds all hr permissions (incl.
    read_compensation)."""
    principal = await hr_user_factory()
    access_token = await _login(client, principal)
    client.headers["Authorization"] = f"Bearer {access_token}"
    yield client


@dataclass(frozen=True)
class HrApi:
    """A logged-in full-rights client plus an HrSetup seeded in THAT client's tenant — so the hr
    endpoints can be driven over the wire against a tenant with a real cost centre + department."""

    client: AsyncClient
    setup: HrSetup


@pytest.fixture
async def hr_api(
    client: AsyncClient,
    db_session: AsyncSession,
    hr_user_factory: Callable[..., AsyncIterator[HrPrincipal]],
) -> AsyncIterator[HrApi]:
    """A bearer-token client whose principal holds all hr keys, with the hr setup (a cost centre + a
    root department) seeded in that principal's tenant (PLAN 10.1)."""
    principal = await hr_user_factory()
    setup = await build_hr_setup(db_session, principal.tenant_id)
    access_token = await _login(client, principal)
    client.headers["Authorization"] = f"Bearer {access_token}"
    yield HrApi(client=client, setup=setup)


@pytest.fixture
async def hr_principal_b(
    hr_user_factory: Callable[..., AsyncIterator[HrPrincipal]],
) -> HrPrincipal:
    """A SECOND hr principal in its own tenant — used by the cross-tenant tests to prove one
    tenant's employees/departments can't be seen by another tenant."""
    return await hr_user_factory(slug="hr-beta", email="people@hr-beta.test")


@pytest.fixture
async def hr_client_b(
    client: AsyncClient, hr_principal_b: HrPrincipal
) -> AsyncIterator[AsyncClient]:
    """A bearer-token client for the second hr tenant. Built on a SEPARATE httpx client so its
    Authorization header never clobbers the primary ``hr_client``."""
    transport = client._transport  # the per-test ASGI transport bound to this test's app
    async with AsyncClient(transport=transport, base_url="https://test") as client_b:
        access_token = await _login(client_b, hr_principal_b)
        client_b.headers["Authorization"] = f"Bearer {access_token}"
        yield client_b
