"""Invoice-match HTTP surface (PLAN 6.4, D-042): RBAC (manage vs post), idempotency, pagination +
query budget, tenant isolation, and the reorder-scan endpoint.

These hit the real ASGI app (which registers the cross-module handlers in its factory), so a POSTed
match creates + posts its AP bill through the wire exactly as in production.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import tenant_context
from tests.modules.procurement.factories import build_invoice_match_setup


async def _principal_tenant(procurement_client: AsyncClient) -> uuid.UUID:
    me = await procurement_client.get("/api/v1/auth/me")
    return uuid.UUID(me.json()["tenant_id"])


async def test_create_and_post_match_over_the_wire(
    procurement_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Create a match then post it: the response carries the MATCH number and POSTED status."""
    tenant_id = await _principal_tenant(procurement_client)
    with tenant_context(tenant_id):
        setup = await build_invoice_match_setup(db_session, tenant_id)

    create = await procurement_client.post(
        "/api/v1/procurement/invoice-matches",
        json={
            "purchase_order_id": str(setup.po_id),
            "vendor_invoice_ref": "VINV-9",
            "lines": [
                {
                    "purchase_order_line_id": str(setup.po_line_id),
                    "matched_quantity": "10",
                    "unit_price": "5",
                }
            ],
        },
        headers={"Idempotency-Key": uuid.uuid4().hex},
    )
    assert create.status_code == 201, create.text
    match_id = create.json()["id"]
    assert create.json()["status"] == "MATCHED"

    post = await procurement_client.post(
        f"/api/v1/procurement/invoice-matches/{match_id}/post",
        headers={"Idempotency-Key": uuid.uuid4().hex},
    )
    assert post.status_code == 200, post.text
    assert post.json()["status"] == "POSTED"


async def test_post_requires_post_permission(
    client: AsyncClient,
    procurement_user_factory,
    db_session: AsyncSession,
) -> None:
    """A principal with manage but not the post key gets 403 on /post (RBAC manage vs post)."""
    principal = await procurement_user_factory(
        slug="proc-noPost",
        email="nopost@proc.test",
        keys=(
            "procurement.invoice_match.read",
            "procurement.invoice_match.manage",
            "finance.account.manage",
            "finance.period.manage",
            "finance.fx.manage",
            "inventory.uom.manage",
            "inventory.category.manage",
            "inventory.item.manage",
            "inventory.warehouse.manage",
            "inventory.bin.manage",
            "procurement.vendor.manage",
            "procurement.po.manage",
            "procurement.goods_receipt.manage",
            "procurement.goods_receipt.post",
        ),
    )
    with tenant_context(principal.tenant_id):
        setup = await build_invoice_match_setup(db_session, principal.tenant_id)

    login = await client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": principal.tenant_slug,
            "email": principal.email,
            "password": principal.password,
        },
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    create = await client.post(
        "/api/v1/procurement/invoice-matches",
        json={
            "purchase_order_id": str(setup.po_id),
            "lines": [
                {
                    "purchase_order_line_id": str(setup.po_line_id),
                    "matched_quantity": "10",
                    "unit_price": "5",
                }
            ],
        },
        headers={**headers, "Idempotency-Key": uuid.uuid4().hex},
    )
    assert create.status_code == 201, create.text
    match_id = create.json()["id"]

    post = await client.post(
        f"/api/v1/procurement/invoice-matches/{match_id}/post",
        headers={**headers, "Idempotency-Key": uuid.uuid4().hex},
    )
    assert post.status_code == 403


async def test_list_matches_paginated_within_query_budget(
    procurement_client: AsyncClient, db_session: AsyncSession, query_counter
) -> None:
    """The match list is paginated and runs within the PERFORMANCE §6 query budget (≤3)."""
    tenant_id = await _principal_tenant(procurement_client)
    with tenant_context(tenant_id):
        setup = await build_invoice_match_setup(db_session, tenant_id)
    await procurement_client.post(
        "/api/v1/procurement/invoice-matches",
        json={
            "purchase_order_id": str(setup.po_id),
            "lines": [
                {
                    "purchase_order_line_id": str(setup.po_line_id),
                    "matched_quantity": "10",
                    "unit_price": "5",
                }
            ],
        },
        headers={"Idempotency-Key": uuid.uuid4().hex},
    )
    with query_counter() as qc:
        page = await procurement_client.get("/api/v1/procurement/invoice-matches?limit=50")
    assert page.status_code == 200
    assert "items" in page.json()
    assert qc.count <= 3


async def test_reorder_scan_endpoint_returns_nothing_to_reorder(
    procurement_client: AsyncClient,
) -> None:
    """With no below-reorder items, the reorder-scan endpoint returns 200 with a null body."""
    resp = await procurement_client.post(
        "/api/v1/procurement/reorder-scan",
        headers={"Idempotency-Key": uuid.uuid4().hex},
    )
    assert resp.status_code == 200
    assert resp.json() is None


async def test_match_tenant_isolation(
    procurement_client: AsyncClient,
    procurement_client_b: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Tenant B cannot see tenant A's match (tenant isolation)."""
    tenant_a = await _principal_tenant(procurement_client)
    with tenant_context(tenant_a):
        setup = await build_invoice_match_setup(db_session, tenant_a)
    create = await procurement_client.post(
        "/api/v1/procurement/invoice-matches",
        json={
            "purchase_order_id": str(setup.po_id),
            "lines": [
                {
                    "purchase_order_line_id": str(setup.po_line_id),
                    "matched_quantity": "10",
                    "unit_price": "5",
                }
            ],
        },
        headers={"Idempotency-Key": uuid.uuid4().hex},
    )
    match_id = create.json()["id"]
    cross = await procurement_client_b.get(f"/api/v1/procurement/invoice-matches/{match_id}")
    assert cross.status_code == 404


@pytest.mark.parametrize("missing", ["procurement.invoice_match.read"])
async def test_list_requires_read(
    client: AsyncClient, procurement_user_factory, missing: str
) -> None:
    """Listing matches needs the read key — a principal without it gets 403."""
    principal = await procurement_user_factory(
        slug="proc-noread", email="noread@proc.test", keys=("procurement.vendor.read",)
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": principal.tenant_slug,
            "email": principal.email,
            "password": principal.password,
        },
    )
    token = login.json()["access_token"]
    resp = await client.get(
        "/api/v1/procurement/invoice-matches",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
