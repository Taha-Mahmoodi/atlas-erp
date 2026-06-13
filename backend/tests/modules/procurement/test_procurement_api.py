"""Procurement P2P document API tests (PLAN 6.2): the requisition → RFQ → PO chain over the wire,
RBAC (manage vs approve distinct), pagination + query budget (≤3), idempotency on create/convert/
approve, tenant isolation, and the docflow chain endpoint showing requisition→rfq→po.

Cross-module setup goes through the API itself (a currency via finance, a UoM/category/item via
inventory) so the tests exercise the real router → service → uow path end to end.
"""

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient

from tests.conftest import assert_query_budget

_PROC = "/api/v1/procurement"


async def _seed_currency(client: AsyncClient, code: str = "USD") -> None:
    response = await client.post("/api/v1/finance/currencies", json={"code": code, "name": code})
    assert response.status_code == 201, response.text


async def _seed_item(client: AsyncClient, *, item_code: str = "ITEM-1") -> tuple[str, str]:
    """Create a UoM + category + item over the wire; return (item_id, uom_id)."""
    uom = await client.post("/api/v1/inventory/uoms", json={"code": "EA", "name": "Each"})
    assert uom.status_code == 201, uom.text
    category = await client.post(
        "/api/v1/inventory/item-categories", json={"code": "CAT-1", "name": "Category"}
    )
    assert category.status_code == 201, category.text
    item = await client.post(
        "/api/v1/inventory/items",
        json={
            "item_code": item_code,
            "name": "An item",
            "item_type": "STOCKED",
            "category_id": category.json()["id"],
            "base_uom_id": uom.json()["id"],
        },
    )
    assert item.status_code == 201, item.text
    return item.json()["id"], uom.json()["id"]


async def _create_active_vendor_with_item(
    client: AsyncClient, item_id: str, *, vendor_code: str = "V-1"
) -> str:
    vendor = await client.post(
        f"{_PROC}/vendors",
        json={"vendor_code": vendor_code, "name": "Acme", "default_currency_code": "USD"},
    )
    assert vendor.status_code == 201, vendor.text
    vendor_id = vendor.json()["id"]
    approved = await client.post(
        f"{_PROC}/vendors/{vendor_id}/approved-items", json={"item_id": item_id}
    )
    assert approved.status_code == 201, approved.text
    return vendor_id


def _idem(key: str) -> dict[str, str]:
    return {"Idempotency-Key": key}


# --- The full requisition → RFQ → PO chain + docflow ---------------------------


async def test_full_chain_and_docflow(procurement_client: AsyncClient) -> None:
    """Create a requisition, submit (auto-approve, no rule), convert to RFQ, send + quote, convert
    the RFQ to a PO, then assert the docflow chain endpoint shows all three documents linked."""
    await _seed_currency(procurement_client)
    item_id, uom_id = await _seed_item(procurement_client)
    vendor_id = await _create_active_vendor_with_item(procurement_client, item_id)

    req = await procurement_client.post(
        f"{_PROC}/requisitions",
        headers=_idem("req-1"),
        json={
            "lines": [
                {"item_id": item_id, "quantity": "5", "uom_id": uom_id, "currency_code": "USD"}
            ]
        },
    )
    assert req.status_code == 201, req.text
    req_id = req.json()["id"]
    req_document_id = req.json()["document_id"]

    submitted = await procurement_client.post(
        f"{_PROC}/requisitions/{req_id}/submit", headers=_idem("sub-1")
    )
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "APPROVED"

    rfq = await procurement_client.post(
        f"{_PROC}/requisitions/{req_id}/convert-to-rfq",
        headers=_idem("torfq-1"),
        json={"vendor_id": vendor_id},
    )
    assert rfq.status_code == 201, rfq.text
    rfq_id = rfq.json()["id"]
    rfq_line_id = rfq.json()["lines"][0]["id"]

    await procurement_client.post(f"{_PROC}/rfqs/{rfq_id}/send", headers=_idem("send-1"))
    quoted = await procurement_client.post(
        f"{_PROC}/rfqs/{rfq_id}/record-quote",
        headers=_idem("quote-1"),
        json={"quotes": [{"line_id": rfq_line_id, "quoted_unit_cost": "8"}]},
    )
    assert quoted.status_code == 200
    assert quoted.json()["status"] == "QUOTED"

    po = await procurement_client.post(
        f"{_PROC}/rfqs/{rfq_id}/convert-to-po", headers=_idem("topo-1"), json={}
    )
    assert po.status_code == 201, po.text
    assert Decimal(po.json()["total_amount"]) == Decimal("40")  # 5 × 8

    # The docflow chain for the requisition shows all three documents (requisition→rfq→po).
    chain = await procurement_client.get(f"/api/v1/documents/{req_document_id}/chain")
    assert chain.status_code == 200, chain.text
    doc_types = {node["doc_type"] for node in chain.json()["nodes"]}
    assert "procurement.requisition" in doc_types
    assert "procurement.rfq" in doc_types
    assert "procurement.purchase_order" in doc_types


# --- RBAC: manage vs approve distinct ------------------------------------------


async def test_approve_requires_approve_permission(
    procurement_client: AsyncClient,
    procurement_user_factory,
    client: AsyncClient,
) -> None:
    """A principal with only requisition.manage (no .approve) is 403 on the decision endpoint."""
    await _seed_currency(procurement_client)
    item_id, uom_id = await _seed_item(procurement_client)
    # Rule forces SUBMITTED (awaiting approval) so the decision endpoint is reachable.
    await procurement_client.post(
        f"{_PROC}/approval-rules",
        json={"document_type": "REQUISITION", "threshold_amount": "0", "currency_code": "USD"},
    )
    req = await procurement_client.post(
        f"{_PROC}/requisitions",
        headers=_idem("rbac-req"),
        json={
            "lines": [
                {
                    "item_id": item_id,
                    "quantity": "1",
                    "uom_id": uom_id,
                    "currency_code": "USD",
                    "estimated_unit_cost": "1",
                }
            ]
        },
    )
    req_id = req.json()["id"]
    await procurement_client.post(
        f"{_PROC}/requisitions/{req_id}/submit", headers=_idem("rbac-sub")
    )

    # A narrower principal: requisition.manage but NOT requisition.approve.
    principal = await procurement_user_factory(
        slug="proc-narrow",
        email="narrow@proc.test",
        keys=("procurement.requisition.manage",),
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
    # The decision call is in the FULL-rights tenant, so use that req_id but the narrow token in its
    # OWN tenant would 404; instead assert the narrow principal is forbidden on the route guard by
    # calling within the full tenant's client headers swapped — simplest: a fresh request with the
    # narrow token against the full tenant's resource yields 404 (cross-tenant) OR 403 (guard). The
    # guard runs before the lookup, so a missing .approve key is 403 regardless of tenant.
    forbidden = await client.post(
        f"{_PROC}/requisitions/{req_id}/decision",
        headers={"Authorization": f"Bearer {token}", **_idem("rbac-dec")},
        json={"decision": "APPROVED"},
    )
    assert forbidden.status_code == 403, forbidden.text


# --- Pagination + query budget -------------------------------------------------


async def test_list_endpoints_query_budget(
    procurement_client: AsyncClient, query_counter
) -> None:
    """The three list endpoints stay within the ≤3 query budget (PERFORMANCE §2)."""
    await _seed_currency(procurement_client)
    item_id, uom_id = await _seed_item(procurement_client)
    await _create_active_vendor_with_item(procurement_client, item_id)
    await procurement_client.post(
        f"{_PROC}/requisitions",
        headers=_idem("budget-req"),
        json={
            "lines": [
                {"item_id": item_id, "quantity": "1", "uom_id": uom_id, "currency_code": "USD"}
            ]
        },
    )
    for url in (
        f"{_PROC}/requisitions",
        f"{_PROC}/rfqs",
        f"{_PROC}/purchase-orders",
    ):
        await assert_query_budget(procurement_client, query_counter, url)


# --- Idempotency on create -----------------------------------------------------


async def test_create_idempotent_replays(procurement_client: AsyncClient) -> None:
    """Re-POSTing a requisition with the same Idempotency-Key replays the stored response (no second
    document)."""
    await _seed_currency(procurement_client)
    item_id, uom_id = await _seed_item(procurement_client)
    body = {
        "lines": [
            {"item_id": item_id, "quantity": "1", "uom_id": uom_id, "currency_code": "USD"}
        ]
    }
    first = await procurement_client.post(
        f"{_PROC}/requisitions", headers=_idem("dup-1"), json=body
    )
    assert first.status_code == 201
    second = await procurement_client.post(
        f"{_PROC}/requisitions", headers=_idem("dup-1"), json=body
    )
    assert second.status_code == 201
    assert second.json()["id"] == first.json()["id"]
    assert second.headers.get("Idempotency-Replayed") == "true"

    listed = await procurement_client.get(f"{_PROC}/requisitions")
    assert len(listed.json()["items"]) == 1


# --- Tenant isolation ----------------------------------------------------------


async def test_tenant_isolation(
    procurement_client: AsyncClient, procurement_client_b: AsyncClient
) -> None:
    """Tenant A's requisition is invisible to tenant B."""
    await _seed_currency(procurement_client)
    item_id, uom_id = await _seed_item(procurement_client)
    req = await procurement_client.post(
        f"{_PROC}/requisitions",
        headers=_idem("iso-1"),
        json={
            "lines": [
                {"item_id": item_id, "quantity": "1", "uom_id": uom_id, "currency_code": "USD"}
            ]
        },
    )
    req_id = req.json()["id"]
    # Tenant B cannot read it (404) and its own list is empty.
    cross = await procurement_client_b.get(f"{_PROC}/requisitions/{req_id}")
    assert cross.status_code == 404
    listed_b = await procurement_client_b.get(f"{_PROC}/requisitions")
    assert listed_b.json()["items"] == []


# --- Approval gating on send over the wire -------------------------------------


async def test_po_send_gated_then_approved(procurement_client: AsyncClient) -> None:
    """A PO above the PURCHASE_ORDER threshold goes PENDING_APPROVAL on send; the approve endpoint
    clears it; then it can be sent."""
    await _seed_currency(procurement_client)
    item_id, uom_id = await _seed_item(procurement_client)
    vendor_id = await _create_active_vendor_with_item(procurement_client, item_id)
    await procurement_client.post(
        f"{_PROC}/approval-rules",
        json={"document_type": "PURCHASE_ORDER", "threshold_amount": "10", "currency_code": "USD"},
    )
    po = await procurement_client.post(
        f"{_PROC}/purchase-orders",
        headers=_idem("po-1"),
        json={
            "vendor_id": vendor_id,
            "lines": [
                {"item_id": item_id, "quantity": "5", "uom_id": uom_id, "unit_cost": "5"}
            ],
        },
    )
    assert po.status_code == 201, po.text
    po_id = po.json()["id"]

    sent = await procurement_client.post(
        f"{_PROC}/purchase-orders/{po_id}/send", headers=_idem("po-send-1")
    )
    assert sent.json()["status"] == "PENDING_APPROVAL"

    approved = await procurement_client.post(
        f"{_PROC}/purchase-orders/{po_id}/decision",
        headers=_idem("po-dec-1"),
        json={"decision": "APPROVED"},
    )
    assert approved.json()["status"] == "APPROVED"
    assert approved.json()["approved_by"] is not None

    final = await procurement_client.post(
        f"{_PROC}/purchase-orders/{po_id}/send", headers=_idem("po-send-2")
    )
    assert final.json()["status"] == "SENT"


@pytest.mark.parametrize("missing_key", ["procurement.po.manage"])
async def test_po_create_requires_manage(
    procurement_user_factory, client: AsyncClient, missing_key: str
) -> None:
    """A principal without procurement.po.manage is 403 on PO create."""
    principal = await procurement_user_factory(
        slug="proc-noman",
        email="noman@proc.test",
        keys=("procurement.po.read",),
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
    response = await client.post(
        f"{_PROC}/purchase-orders",
        headers={"Authorization": f"Bearer {token}", **_idem("noman-1")},
        json={"vendor_id": str(uuid.uuid4()), "lines": []},
    )
    assert response.status_code == 403, response.text
