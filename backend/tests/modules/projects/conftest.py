"""Projects test fixtures (STRUCTURE §6): a tenant with a cost centre + customer + COA + a project
ready to author WBS elements and post WBS-tagged journal entries, plus bearer-token clients holding
projects permissions.

The data builders live in tests/modules/projects/factories.py (STRUCTURE §8.4); this conftest keeps
only the thin pytest fixtures wrapping them. Factories go through the REAL service layer under the
tenant context (D-025). The projects-permissioned clients provision a user, sync the catalog, and
grant a role carrying the projects keys — the maintenance_client pattern with projects.* keys.
"""

import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from functools import partial

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import register_event_handlers
from tests.modules.projects.factories import (
    ProjectsPrincipal,
    ProjectsSetup,
    build_projects_setup,
    create_projects_principal,
)

__all__ = ["ProjectsPrincipal", "ProjectsSetup"]


@pytest.fixture(autouse=True)
def _register_event_handlers(clear_event_subscriptions: Callable[[], None]) -> None:
    """Register the cross-module handlers for every projects test. Projects publishes / subscribes
    to NO cross-module event (masters + a read report, D-056), but the shared app factory registers
    module handlers, so this keeps the test environment identical to production and idempotent
    (``register_event_handlers`` de-duplicates). It also wires finance's stock/payroll handlers the
    journal/timesheet builders may touch. Depends on the global ``clear_event_subscriptions`` so it
    runs AFTER the per-test reset."""
    register_event_handlers()


@pytest.fixture
async def projects_setup(db_session: AsyncSession, tenant_a: uuid.UUID) -> ProjectsSetup:
    """A cost centre + customer + COA + a project in tenant A, ready to author WBS elements and post
    WBS-tagged journal entries for the cost report."""
    return await build_projects_setup(db_session, tenant_a)


# --- Projects-permissioned HTTP clients ---------------------------------------


@pytest.fixture
def projects_user_factory(
    db_session: AsyncSession,
) -> Callable[..., "AsyncIterator[ProjectsPrincipal]"]:
    """Provision a tenant + user and grant a role with the projects permission keys through the real
    services (D-025). ``keys`` lets a test request a narrower grant (the 403 RBAC tests)."""
    return partial(create_projects_principal, db_session)


async def _login(client: AsyncClient, principal: ProjectsPrincipal) -> str:
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
async def projects_client(
    client: AsyncClient,
    projects_user_factory: Callable[..., AsyncIterator[ProjectsPrincipal]],
) -> AsyncIterator[AsyncClient]:
    """A real bearer-token client whose principal holds all projects permissions."""
    principal = await projects_user_factory()
    access_token = await _login(client, principal)
    client.headers["Authorization"] = f"Bearer {access_token}"
    yield client


@dataclass(frozen=True)
class ProjectsApi:
    """A logged-in full-rights client plus a ProjectsSetup seeded in THAT client's tenant — so the
    projects endpoints can be driven over the wire against a tenant with a real project."""

    client: AsyncClient
    setup: ProjectsSetup


@pytest.fixture
async def projects_api(
    client: AsyncClient,
    db_session: AsyncSession,
    projects_user_factory: Callable[..., AsyncIterator[ProjectsPrincipal]],
) -> AsyncIterator[ProjectsApi]:
    """A bearer-token client whose principal holds all projects keys, with the projects setup (a
    cost centre + customer + COA + a project) seeded in that principal's tenant (PLAN 11.1)."""
    principal = await projects_user_factory()
    setup = await build_projects_setup(db_session, principal.tenant_id)
    access_token = await _login(client, principal)
    client.headers["Authorization"] = f"Bearer {access_token}"
    yield ProjectsApi(client=client, setup=setup)


@pytest.fixture
async def projects_principal_b(
    projects_user_factory: Callable[..., AsyncIterator[ProjectsPrincipal]],
) -> ProjectsPrincipal:
    """A SECOND projects principal in its own tenant — used by the cross-tenant tests to prove one
    tenant's projects/WBS can't be seen by another tenant."""
    return await projects_user_factory(slug="ps-beta", email="pm@ps-beta.test")


@pytest.fixture
async def projects_client_b(
    client: AsyncClient, projects_principal_b: ProjectsPrincipal
) -> AsyncIterator[AsyncClient]:
    """A bearer-token client for the second projects tenant. Built on a SEPARATE httpx client so its
    Authorization header never clobbers the primary ``projects_client``."""
    transport = client._transport  # the per-test ASGI transport bound to this test's app
    async with AsyncClient(transport=transport, base_url="https://test") as client_b:
        access_token = await _login(client_b, projects_principal_b)
        client_b.headers["Authorization"] = f"Bearer {access_token}"
        yield client_b
