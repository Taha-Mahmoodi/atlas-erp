"""Goods-receipt API tests (PLAN 6.3): create draft → post (stock + GR/IR journal) → over the wire,
plus pagination + query budget (≤3), idempotency on create/post, RBAC (manage vs post distinct),
tenant isolation, and the docflow chain showing PO → GR → stock move.

The cross-module receiving environment (GL accounts, an open period, a GR/IR posting default, a
warehouse + bin, a vendor + approved item, a SENT PO) is scaffolded over the wire so the test
exercises the real router → service → event-bus → handler path end to end.
"""


from httpx import AsyncClient

from tests.conftest import assert_query_budget

_PROC = "/api/v1/procurement"
_FIN = "/api/v1/finance"
_INV = "/api/v1/inventory"


def _idem(key: str) -> dict[str, str]:
    return {"Idempotency-Key": key}


async def _account(client: AsyncClient, code: str, name: str, account_type: str) -> str:
    resp = await client.post(
        f"{_FIN}/accounts", json={"code": code, "name": name, "account_type": account_type}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _scaffold_receiving_env(client: AsyncClient) -> dict[str, str]:
    """Build everything a goods receipt needs over the wire; return the ids the GR payload uses."""
    currency = await client.post(f"{_FIN}/currencies", json={"code": "USD", "name": "USD"})
    assert currency.status_code == 201, currency.text
    inv_acct = await _account(client, "1300", "Inventory", "ASSET")
    cogs_acct = await _account(client, "5000", "COGS", "EXPENSE")
    pd_acct = await _account(client, "5900", "Price diff", "EXPENSE")
    gr_ir_acct = await _account(client, "2150", "GR/IR clearing", "LIABILITY")

    gr_ir = await client.put(
        f"{_FIN}/posting-defaults",
        json={"purpose": "gr_ir_clearing", "account_id": gr_ir_acct},
    )
    assert gr_ir.status_code == 200, gr_ir.text
    year = await client.post(
        f"{_FIN}/fiscal-years", json={"code": "2026", "name": "FY2026", "start_date": "2026-01-01"}
    )
    assert year.status_code == 201, year.text

    uom = await client.post(f"{_INV}/uoms", json={"code": "EA", "name": "Each"})
    assert uom.status_code == 201, uom.text
    uom_id = uom.json()["id"]
    category = await client.post(
        f"{_INV}/item-categories",
        json={
            "code": "CAT-1",
            "name": "Category",
            "inventory_account_id": inv_acct,
            "cogs_account_id": cogs_acct,
            "price_difference_account_id": pd_acct,
        },
    )
    assert category.status_code == 201, category.text
    item = await client.post(
        f"{_INV}/items",
        json={
            "item_code": "ITEM-1",
            "name": "An item",
            "item_type": "STOCKED",
            "category_id": category.json()["id"],
            "base_uom_id": uom_id,
        },
    )
    assert item.status_code == 201, item.text
    item_id = item.json()["id"]

    warehouse = await client.post(f"{_INV}/warehouses", json={"code": "WH-1", "name": "Main"})
    assert warehouse.status_code == 201, warehouse.text
    bin_resp = await client.post(
        f"{_INV}/bins",
        json={"warehouse_id": warehouse.json()["id"], "code": "A1", "name": "Bin A1"},
    )
    assert bin_resp.status_code == 201, bin_resp.text

    vendor = await client.post(
        f"{_PROC}/vendors",
        json={"vendor_code": "V-1", "name": "Acme", "default_currency_code": "USD"},
    )
    assert vendor.status_code == 201, vendor.text
    vendor_id = vendor.json()["id"]
    approved = await client.post(
        f"{_PROC}/vendors/{vendor_id}/approved-items", json={"item_id": item_id}
    )
    assert approved.status_code == 201, approved.text

    po = await client.post(
        f"{_PROC}/purchase-orders",
        headers=_idem("po-1"),
        json={
            "vendor_id": vendor_id,
            "lines": [{"item_id": item_id, "quantity": "10", "uom_id": uom_id, "unit_cost": "5"}],
        },
    )
    assert po.status_code == 201, po.text
    po_id = po.json()["id"]
    po_line_id = po.json()["lines"][0]["id"]
    send = await client.post(
        f"{_PROC}/purchase-orders/{po_id}/send", headers=_idem("po-send-1")
    )
    assert send.status_code == 200, send.text
    return {
        "item_id": item_id,
        "warehouse_id": warehouse.json()["id"],
        "bin_id": bin_resp.json()["id"],
        "po_id": po_id,
        "po_line_id": po_line_id,
    }


def _gr_body(env: dict[str, str], qty: str = "4") -> dict[str, object]:
    return {
        "purchase_order_id": env["po_id"],
        "warehouse_id": env["warehouse_id"],
        "lines": [
            {
                "purchase_order_line_id": env["po_line_id"],
                "bin_id": env["bin_id"],
                "received_quantity": qty,
            }
        ],
    }


# --- Create + post over the wire ----------------------------------------------


async def test_create_and_post_goods_receipt(procurement_client: AsyncClient) -> None:
    """Create a DRAFT goods receipt then POST it: the GR becomes POSTED and the on-hand rises (the
    stock move was created via the event bus)."""
    env = await _scaffold_receiving_env(procurement_client)
    created = await procurement_client.post(
        f"{_PROC}/goods-receipts", headers=_idem("gr-1"), json=_gr_body(env)
    )
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "DRAFT"
    gr_id = created.json()["id"]

    posted = await procurement_client.post(
        f"{_PROC}/goods-receipts/{gr_id}/post", headers=_idem("gr-post-1")
    )
    assert posted.status_code == 200, posted.text
    assert posted.json()["status"] == "POSTED"
    assert posted.json()["posted_at"] is not None

    on_hand = await procurement_client.get(
        f"{_INV}/stock-on-hand", params={"item_id": env["item_id"]}
    )
    assert on_hand.status_code == 200, on_hand.text
    rows = on_hand.json()["items"]
    assert sum(float(row["on_hand_qty"]) for row in rows) == 4.0


async def test_over_receipt_returns_422(procurement_client: AsyncClient) -> None:
    """Receiving more than the open quantity is rejected 422 procurement.over_receipt."""
    env = await _scaffold_receiving_env(procurement_client)
    resp = await procurement_client.post(
        f"{_PROC}/goods-receipts", headers=_idem("gr-over"), json=_gr_body(env, qty="11")
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "procurement.over_receipt"


async def test_post_is_idempotent(procurement_client: AsyncClient) -> None:
    """Re-POSTing with the same Idempotency-Key replays the captured response, not a second post."""
    env = await _scaffold_receiving_env(procurement_client)
    created = await procurement_client.post(
        f"{_PROC}/goods-receipts", headers=_idem("gr-idem"), json=_gr_body(env)
    )
    gr_id = created.json()["id"]
    first = await procurement_client.post(
        f"{_PROC}/goods-receipts/{gr_id}/post", headers=_idem("gr-post-idem")
    )
    second = await procurement_client.post(
        f"{_PROC}/goods-receipts/{gr_id}/post", headers=_idem("gr-post-idem")
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["status"] == "POSTED"


async def test_docflow_chain_po_gr_move(procurement_client: AsyncClient) -> None:
    """The docflow chain endpoint shows the PO → GR ('received_by') → stock move ('moved_by')."""
    env = await _scaffold_receiving_env(procurement_client)
    created = await procurement_client.post(
        f"{_PROC}/goods-receipts", headers=_idem("gr-flow"), json=_gr_body(env)
    )
    gr = created.json()
    await procurement_client.post(
        f"{_PROC}/goods-receipts/{gr['id']}/post", headers=_idem("gr-flow-post")
    )
    chain = await procurement_client.get(f"/api/v1/documents/{gr['document_id']}/chain")
    assert chain.status_code == 200, chain.text
    link_types = {edge["link_type"] for edge in chain.json()["edges"]}
    assert "received_by" in link_types
    assert "moved_by" in link_types


# --- List: pagination + budget ------------------------------------------------


async def test_list_goods_receipts_paginated_within_budget(
    procurement_client: AsyncClient, query_counter
) -> None:
    """The GR list is paginated and stays within the ≤3-query budget (PERFORMANCE §6)."""
    env = await _scaffold_receiving_env(procurement_client)
    for i in range(3):
        await procurement_client.post(
            f"{_PROC}/goods-receipts", headers=_idem(f"gr-list-{i}"), json=_gr_body(env, qty="1")
        )
    resp = await procurement_client.get(f"{_PROC}/goods-receipts", params={"limit": 2})
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["items"]) == 2
    assert resp.json()["next_cursor"] is not None
    await assert_query_budget(
        procurement_client, query_counter, f"{_PROC}/goods-receipts?limit=2"
    )


async def test_list_filters_by_po(procurement_client: AsyncClient) -> None:
    """The GR list filters by purchase_order_id."""
    env = await _scaffold_receiving_env(procurement_client)
    await procurement_client.post(
        f"{_PROC}/goods-receipts", headers=_idem("gr-f1"), json=_gr_body(env, qty="2")
    )
    resp = await procurement_client.get(
        f"{_PROC}/goods-receipts", params={"purchase_order_id": env["po_id"]}
    )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["items"]) == 1


# --- RBAC ---------------------------------------------------------------------


async def test_post_requires_post_permission(
    procurement_client: AsyncClient, procurement_user_factory
) -> None:
    """The POST action needs procurement.goods_receipt.post; a manage-only principal is 403."""
    env = await _scaffold_receiving_env(procurement_client)
    created = await procurement_client.post(
        f"{_PROC}/goods-receipts", headers=_idem("gr-rbac"), json=_gr_body(env)
    )
    gr_id = created.json()["id"]

    # A principal WITHOUT the .post key (read+manage only) cannot post.
    principal = await procurement_user_factory(
        slug="proc-noPost",
        email="nopost@proc.test",
        keys=("procurement.goods_receipt.read", "procurement.goods_receipt.manage"),
    )
    transport = procurement_client._transport
    async with AsyncClient(transport=transport, base_url="https://test") as client2:
        login = await client2.post(
            "/api/v1/auth/login",
            json={
                "tenant_slug": principal.tenant_slug,
                "email": principal.email,
                "password": principal.password,
            },
        )
        token = login.json()["access_token"]
        client2.headers["Authorization"] = f"Bearer {token}"
        resp = await client2.post(
            f"{_PROC}/goods-receipts/{gr_id}/post", headers=_idem("gr-rbac-post")
        )
    assert resp.status_code == 403, resp.text


# --- Tenant isolation ---------------------------------------------------------


async def test_tenant_isolation(
    procurement_client: AsyncClient, procurement_client_b: AsyncClient
) -> None:
    """One tenant's goods receipt is invisible (404) to another tenant."""
    env = await _scaffold_receiving_env(procurement_client)
    created = await procurement_client.post(
        f"{_PROC}/goods-receipts", headers=_idem("gr-iso"), json=_gr_body(env)
    )
    gr_id = created.json()["id"]
    resp = await procurement_client_b.get(f"{_PROC}/goods-receipts/{gr_id}")
    assert resp.status_code == 404, resp.text
