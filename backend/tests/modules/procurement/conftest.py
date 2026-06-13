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

from app.main import register_event_handlers
from tests.modules.procurement.factories import (
    GoodsReceiptSetup,
    InvoiceMatchSetup,
    ProcurementPrincipal,
    ProcurementSetup,
    build_goods_receipt_setup,
    build_invoice_match_setup,
    build_procurement_setup,
    create_procurement_principal,
)

__all__ = [
    "GoodsReceiptSetup",
    "InvoiceMatchSetup",
    "ProcurementPrincipal",
    "ProcurementSetup",
]


@pytest.fixture(autouse=True)
def _register_event_handlers(clear_event_subscriptions: Callable[[], None]) -> None:
    """Register the cross-module handlers for every procurement test (PLAN 6.3, D-041): the
    procurement→inventory goods-receipt bridge AND the inventory→finance COGS handler, so a GR
    posted through the SERVICE layer (not the HTTP app, which registers handlers in its factory)
    creates the stock moves + GR/IR journals. Depends on the global ``clear_event_subscriptions`` so
    it runs AFTER the per-test reset; idempotent (``register_event_handlers`` de-duplicates)."""
    register_event_handlers()


@pytest.fixture
async def procurement_setup(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> ProcurementSetup:
    """A USD currency + a STOCKED inventory item in tenant A, ready to create vendors and approve
    items (PLAN 6.1)."""
    return await build_procurement_setup(db_session, tenant_a)


@pytest.fixture
async def goods_receipt_setup(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> GoodsReceiptSetup:
    """A SENT PO (10 @ 5 USD) for a STOCKED item, the GL accounts wired, an open period, a warehouse
    + bin, and the GR/IR clearing posting default mapped — ready to create + post a goods receipt
    (PLAN 6.3)."""
    return await build_goods_receipt_setup(db_session, tenant_a)


@pytest.fixture
async def invoice_match_setup(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> InvoiceMatchSetup:
    """A RECEIVED PO (10 @ 5 USD, a GR posted so received_quantity = 10), with the GR/IR + PPV +
    AP-control posting defaults mapped — ready to create + post a 3-way match (PLAN 6.4)."""
    return await build_invoice_match_setup(db_session, tenant_a)


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
