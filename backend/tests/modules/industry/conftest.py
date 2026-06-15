"""Industry test fixtures (STRUCTURE §6): an industry-permissioned principal factory + bearer-token
clients, plus the autouse handler-registration fixture so the finance/inventory/procurement
provisioning handlers fire when a template is applied (D-011/D-060).

Factories go through the REAL admin service under system_context (D-025). The apply path runs the
cross-module handlers, so every industry test registers them via register_event_handlers
(idempotent; runs after the global per-test clear_subscriptions reset).
"""

import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from functools import partial

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import sync_permission_catalog
from app.core.tenancy import system_context
from app.main import register_event_handlers
from app.modules.admin.service import (
    assign_role,
    create_role,
    provision_tenant,
    provision_user,
)
from app.modules.industry.constants import (
    INDUSTRY_TEMPLATE_APPLY,
    INDUSTRY_TEMPLATE_READ,
)

_INDUSTRY_KEYS = (INDUSTRY_TEMPLATE_READ, INDUSTRY_TEMPLATE_APPLY)


@dataclass(frozen=True)
class IndustryPrincipal:
    tenant_id: uuid.UUID
    tenant_slug: str
    user_id: uuid.UUID
    email: str
    password: str


@pytest.fixture(autouse=True)
def _register_event_handlers(clear_event_subscriptions: Callable[[], None]) -> None:
    """Wire the cross-module handlers for every industry test so an apply dispatches the
    finance/inventory/procurement provisioning handlers (D-060). Idempotent; depends on the global
    clear_event_subscriptions so it runs AFTER the per-test reset (D-011/D-025)."""
    register_event_handlers()


async def create_industry_principal(
    session: AsyncSession,
    slug: str = "ind-acme",
    email: str = "owner@ind-acme.test",
    password: str = "correct-horse-battery",
    keys: tuple[str, ...] = _INDUSTRY_KEYS,
) -> IndustryPrincipal:
    """Provision a tenant + user and grant a role with the industry keys through the real services
    (D-025); ``keys`` narrows the grant for the 403 RBAC tests."""
    tenant = await provision_tenant(session, slug=slug, name=slug.title())
    user = await provision_user(session, tenant.id, email=email, password=password)
    with system_context():
        await sync_permission_catalog(session)
    role = await create_role(session, tenant.id, "Industry", keys, is_system=True)
    await assign_role(session, tenant.id, user.id, role.id, user.token_version)
    await session.commit()
    return IndustryPrincipal(
        tenant_id=tenant.id,
        tenant_slug=slug,
        user_id=user.id,
        email=email,
        password=password,
    )


@pytest.fixture
def industry_user_factory(
    db_session: AsyncSession,
) -> Callable[..., "AsyncIterator[IndustryPrincipal]"]:
    return partial(create_industry_principal, db_session)


async def _login(client: AsyncClient, principal: IndustryPrincipal) -> str:
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


@dataclass(frozen=True)
class IndustryApi:
    client: AsyncClient
    principal: IndustryPrincipal


@pytest.fixture
async def industry_api(
    client: AsyncClient,
    industry_user_factory: Callable[..., AsyncIterator[IndustryPrincipal]],
) -> AsyncIterator[IndustryApi]:
    """A bearer-token client whose principal holds both industry keys."""
    principal = await industry_user_factory()
    access_token = await _login(client, principal)
    client.headers["Authorization"] = f"Bearer {access_token}"
    yield IndustryApi(client=client, principal=principal)
