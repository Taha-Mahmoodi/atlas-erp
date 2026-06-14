"""Quality test fixtures (STRUCTURE §6): an inspection-lot setup (a posted, flagged goods receipt
that auto-created an OPEN lot) + bearer-token clients holding quality permissions.

The data builders live in tests/modules/quality/factories.py (STRUCTURE §8.4); this conftest keeps
only the thin pytest fixtures wrapping them. Factories go through the REAL service layer under the
tenant context (D-025). The autouse handler-registration fixture wires the cross-module handlers so
a
flagged GR posted through the SERVICE layer creates an inspection lot, and a reject decision moves
the
rejected stock — exactly as in production.
"""

import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from functools import partial

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import register_event_handlers
from tests.modules.quality.factories import (
    InspectionLotSetup,
    QualityPrincipal,
    build_inspection_lot_setup,
    create_quality_principal,
)

__all__ = ["InspectionLotSetup", "QualityPrincipal"]


@pytest.fixture(autouse=True)
def _register_event_handlers(clear_event_subscriptions: Callable[[], None]) -> None:
    """Register the cross-module handlers for every quality test (PLAN 9.1, D-050): the
    procurement→inventory GR move bridge, the procurement→quality inspection-lot bridge, the
    inventory→finance journal handler, and the quality→inventory disposition bridge — so a flagged
    GR
    posted through the SERVICE layer (not the HTTP app, which registers handlers in its factory)
    creates the inspection lot, and a reject decision moves the rejected stock + posts the
    write-off.
    Depends on the global ``clear_event_subscriptions`` so it runs AFTER the per-test reset;
    idempotent (``register_event_handlers`` de-duplicates)."""
    register_event_handlers()


@pytest.fixture
async def inspection_lot_setup(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> InspectionLotSetup:
    """A tenant with a posted, inspection-flagged goods receipt that auto-created an OPEN inspection
    lot (PLAN 9.1), ready to decide / cancel."""
    return await build_inspection_lot_setup(db_session, tenant_a)


# --- Quality-permissioned HTTP clients ----------------------------------------


@pytest.fixture
def quality_user_factory(
    db_session: AsyncSession,
) -> Callable[..., "AsyncIterator[QualityPrincipal]"]:
    """Provision a tenant + user and grant a role with the quality permission keys through the real
    services (D-025). ``keys`` lets a test request a narrower grant (the 403 RBAC tests)."""
    return partial(create_quality_principal, db_session)


async def _login(client: AsyncClient, principal: QualityPrincipal) -> str:
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
async def quality_client(
    client: AsyncClient,
    quality_user_factory: Callable[..., AsyncIterator[QualityPrincipal]],
) -> AsyncIterator[AsyncClient]:
    """A real bearer-token client whose principal holds all quality permissions."""
    principal = await quality_user_factory()
    access_token = await _login(client, principal)
    client.headers["Authorization"] = f"Bearer {access_token}"
    yield client


@dataclass(frozen=True)
class QualityApi:
    """A logged-in full-rights client plus an InspectionLotSetup seeded in THAT client's tenant — so
    the inspection-lot endpoints can be driven over the wire against a tenant with a real OPEN
    lot."""

    client: AsyncClient
    setup: InspectionLotSetup


@pytest.fixture
async def quality_api(
    client: AsyncClient,
    db_session: AsyncSession,
    quality_user_factory: Callable[..., AsyncIterator[QualityPrincipal]],
) -> AsyncIterator[QualityApi]:
    """A bearer-token client whose principal holds all quality keys, with the inspection-lot setup
    (a posted, flagged goods receipt → an OPEN lot) seeded in that principal's tenant (PLAN 9.1)."""
    principal = await quality_user_factory()
    setup = await build_inspection_lot_setup(db_session, principal.tenant_id)
    access_token = await _login(client, principal)
    client.headers["Authorization"] = f"Bearer {access_token}"
    yield QualityApi(client=client, setup=setup)


@pytest.fixture
async def quality_principal_b(
    quality_user_factory: Callable[..., AsyncIterator[QualityPrincipal]],
) -> QualityPrincipal:
    """A SECOND quality principal in its own tenant — used by the cross-tenant tests to prove one
    tenant's inspection lots can't be seen by another tenant."""
    return await quality_user_factory(slug="qm-beta", email="qa@qm-beta.test")


@pytest.fixture
async def quality_client_b(
    client: AsyncClient, quality_principal_b: QualityPrincipal
) -> AsyncIterator[AsyncClient]:
    """A bearer-token client for the second quality tenant. Built on a SEPARATE httpx client so its
    Authorization header never clobbers the primary ``quality_client``."""
    transport = client._transport  # the per-test ASGI transport bound to this test's app
    async with AsyncClient(transport=transport, base_url="https://test") as client_b:
        access_token = await _login(client_b, quality_principal_b)
        client_b.headers["Authorization"] = f"Bearer {access_token}"
        yield client_b
