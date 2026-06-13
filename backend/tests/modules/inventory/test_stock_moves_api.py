"""Inventory stock HTTP layer (PLAN 5.2): warehouse/bin/move/on-hand endpoints, RBAC, pagination,
query budget, idempotency, tenant isolation, and the on-hand projection endpoint.

Data setup goes through the API itself so the tests exercise the real router -> service -> uow path
end to end. Move-creating endpoints require an Idempotency-Key header (D-013).
"""

from collections.abc import AsyncIterator, Callable

from httpx import AsyncClient, Response

from tests.conftest import assert_query_budget
from tests.modules.inventory.factories import InventoryPrincipal


async def _warehouse(client: AsyncClient, code: str = "WH-1") -> str:
    response = await client.post(
        "/api/v1/inventory/warehouses", json={"code": code, "name": "Warehouse"}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _bin(client: AsyncClient, warehouse_id: str, code: str = "A1") -> str:
    response = await client.post(
        "/api/v1/inventory/bins",
        json={"warehouse_id": warehouse_id, "code": code, "name": code},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _account(client: AsyncClient, code: str, name: str, account_type: str) -> str:
    response = await client.post(
        "/api/v1/finance/accounts",
        json={"code": code, "name": name, "account_type": account_type},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _open_year(client: AsyncClient) -> None:
    """Seed the 2026 fiscal year (12 OPEN periods) so a valued move's COGS journal can post."""
    response = await client.post(
        "/api/v1/finance/fiscal-years",
        json={"code": "2026", "name": "FY2026", "start_date": "2026-01-01"},
    )
    assert response.status_code == 201, response.text


async def _stocked_item(client: AsyncClient) -> str:
    """A STOCKED item whose category wires the three GL accounts (the costing precondition, PLAN
    5.3) AND an open fiscal year, all through the API so the receipt's COGS journal can post."""
    await _open_year(client)
    uom = await client.post("/api/v1/inventory/uoms", json={"code": "EA", "name": "Each"})
    inventory_account = await _account(client, "1300", "Inventory", "ASSET")
    cogs_account = await _account(client, "5000", "COGS", "EXPENSE")
    price_diff_account = await _account(client, "5900", "Price difference", "EXPENSE")
    cat = await client.post(
        "/api/v1/inventory/item-categories",
        json={
            "code": "C1",
            "name": "Cat",
            "inventory_account_id": inventory_account,
            "cogs_account_id": cogs_account,
            "price_difference_account_id": price_diff_account,
        },
    )
    assert cat.status_code == 201, cat.text
    item = await client.post(
        "/api/v1/inventory/items",
        json={
            "item_code": "ITEM-1",
            "name": "Item",
            "item_type": "STOCKED",
            "category_id": cat.json()["id"],
            "base_uom_id": uom.json()["id"],
        },
    )
    assert item.status_code == 201, item.text
    return item.json()["id"]


async def _receipt(
    client: AsyncClient,
    item_id: str,
    bin_id: str,
    qty: str,
    *,
    key: str,
    unit_cost: str = "2.00",
) -> Response:
    response = await client.post(
        "/api/v1/inventory/stock-moves",
        json={
            "move_type": "RECEIPT",
            "item_id": item_id,
            "quantity": qty,
            "to_bin_id": bin_id,
            "unit_cost": unit_cost,
        },
        headers={"Idempotency-Key": key},
    )
    return response


async def test_warehouse_bin_crud_round_trip(inventory_client: AsyncClient) -> None:
    warehouse_id = await _warehouse(inventory_client)
    bin_id = await _bin(inventory_client, warehouse_id)
    got = await inventory_client.get(f"/api/v1/inventory/bins/{bin_id}")
    assert got.status_code == 200
    assert got.json()["warehouse_id"] == warehouse_id
    # PATCH deactivates the warehouse (soft-delete).
    patched = await inventory_client.patch(
        f"/api/v1/inventory/warehouses/{warehouse_id}", json={"is_active": False}
    )
    assert patched.status_code == 200
    assert patched.json()["is_active"] is False


async def test_receipt_then_on_hand_projection(inventory_client: AsyncClient) -> None:
    warehouse_id = await _warehouse(inventory_client)
    bin_id = await _bin(inventory_client, warehouse_id)
    item_id = await _stocked_item(inventory_client)
    receipt = await _receipt(inventory_client, item_id, bin_id, "12", key="r1")
    assert receipt.status_code == 201, receipt.text
    assert receipt.json()["move_number"].startswith("STK-")

    on_hand = await inventory_client.get(
        f"/api/v1/inventory/stock-on-hand?item_id={item_id}"
    )
    assert on_hand.status_code == 200
    rows = on_hand.json()["items"]
    assert len(rows) == 1
    assert rows[0]["bin_id"] == bin_id
    assert rows[0]["on_hand_qty"] == "12.000000"


async def test_issue_beyond_on_hand_returns_422(inventory_client: AsyncClient) -> None:
    warehouse_id = await _warehouse(inventory_client)
    bin_id = await _bin(inventory_client, warehouse_id)
    item_id = await _stocked_item(inventory_client)
    await _receipt(inventory_client, item_id, bin_id, "3", key="r1")
    response = await inventory_client.post(
        "/api/v1/inventory/stock-moves",
        json={
            "move_type": "ISSUE",
            "item_id": item_id,
            "quantity": "5",
            "from_bin_id": bin_id,
        },
        headers={"Idempotency-Key": "i1"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "inventory.insufficient_stock"


async def test_reverse_move_endpoint_restores_on_hand(
    inventory_client: AsyncClient,
) -> None:
    warehouse_id = await _warehouse(inventory_client)
    bin_id = await _bin(inventory_client, warehouse_id)
    item_id = await _stocked_item(inventory_client)
    await _receipt(inventory_client, item_id, bin_id, "10", key="r1")
    issue = await inventory_client.post(
        "/api/v1/inventory/stock-moves",
        json={
            "move_type": "ISSUE",
            "item_id": item_id,
            "quantity": "4",
            "from_bin_id": bin_id,
        },
        headers={"Idempotency-Key": "i1"},
    )
    move_id = issue.json()["id"]
    reverse = await inventory_client.post(
        f"/api/v1/inventory/stock-moves/{move_id}/reverse",
        headers={"Idempotency-Key": "rev1"},
    )
    assert reverse.status_code == 201, reverse.text
    assert reverse.json()["move_type"] == "RECEIPT"

    on_hand = await inventory_client.get(
        f"/api/v1/inventory/stock-on-hand?item_id={item_id}"
    )
    assert on_hand.json()["items"][0]["on_hand_qty"] == "10.000000"


async def test_create_move_is_idempotent(inventory_client: AsyncClient) -> None:
    warehouse_id = await _warehouse(inventory_client)
    bin_id = await _bin(inventory_client, warehouse_id)
    item_id = await _stocked_item(inventory_client)
    first = await _receipt(inventory_client, item_id, bin_id, "5", key="same-key")
    assert first.status_code == 201
    replay = await _receipt(inventory_client, item_id, bin_id, "5", key="same-key")
    assert replay.status_code == 201
    assert replay.headers.get("Idempotency-Replayed") == "true"
    # Same move id returned; on-hand reflects ONE receipt, not two.
    assert replay.json()["id"] == first.json()["id"]
    on_hand = await inventory_client.get(
        f"/api/v1/inventory/stock-on-hand?item_id={item_id}"
    )
    assert on_hand.json()["items"][0]["on_hand_qty"] == "5.000000"


async def test_create_move_requires_idempotency_key(inventory_client: AsyncClient) -> None:
    warehouse_id = await _warehouse(inventory_client)
    bin_id = await _bin(inventory_client, warehouse_id)
    item_id = await _stocked_item(inventory_client)
    response = await inventory_client.post(
        "/api/v1/inventory/stock-moves",
        json={
            "move_type": "RECEIPT",
            "item_id": item_id,
            "quantity": "1",
            "to_bin_id": bin_id,
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "idempotency.key_required"


async def test_move_ledger_filtered_by_type(inventory_client: AsyncClient) -> None:
    warehouse_id = await _warehouse(inventory_client)
    bin_id = await _bin(inventory_client, warehouse_id)
    item_id = await _stocked_item(inventory_client)
    await _receipt(inventory_client, item_id, bin_id, "10", key="r1")
    await inventory_client.post(
        "/api/v1/inventory/stock-moves",
        json={
            "move_type": "ISSUE",
            "item_id": item_id,
            "quantity": "2",
            "from_bin_id": bin_id,
        },
        headers={"Idempotency-Key": "i1"},
    )
    receipts = await inventory_client.get(
        "/api/v1/inventory/stock-moves?move_type=RECEIPT"
    )
    assert receipts.status_code == 200
    assert {m["move_type"] for m in receipts.json()["items"]} == {"RECEIPT"}


async def test_rbac_read_only_principal_cannot_create_move(
    inventory_client: AsyncClient,
    inventory_user_factory: Callable[..., AsyncIterator[InventoryPrincipal]],
    client: AsyncClient,
) -> None:
    """A principal with only move.read (no move.create) gets 403 on POST /stock-moves."""
    warehouse_id = await _warehouse(inventory_client)
    bin_id = await _bin(inventory_client, warehouse_id)
    item_id = await _stocked_item(inventory_client)
    await _receipt(inventory_client, item_id, bin_id, "5", key="r1")

    reader = await inventory_user_factory(
        slug="inv-reader",
        email="reader@inv.test",
        keys=("inventory.move.read",),
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": reader.tenant_slug,
            "email": reader.email,
            "password": reader.password,
        },
    )
    token = login.json()["access_token"]
    response = await client.post(
        "/api/v1/inventory/stock-moves",
        json={
            "move_type": "RECEIPT",
            "item_id": item_id,
            "quantity": "1",
            "to_bin_id": bin_id,
        },
        headers={"Idempotency-Key": "x", "Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


async def test_warehouse_list_query_budget(
    inventory_client: AsyncClient, query_counter
) -> None:  # noqa: ANN001 - fixture factory typed in conftest
    await _warehouse(inventory_client, code="WH-A")
    await _warehouse(inventory_client, code="WH-B")
    await assert_query_budget(
        inventory_client, query_counter, "/api/v1/inventory/warehouses"
    )


async def test_on_hand_query_budget(
    inventory_client: AsyncClient, query_counter
) -> None:  # noqa: ANN001 - fixture factory typed in conftest
    warehouse_id = await _warehouse(inventory_client)
    bin_id = await _bin(inventory_client, warehouse_id)
    item_id = await _stocked_item(inventory_client)
    await _receipt(inventory_client, item_id, bin_id, "5", key="r1")
    await assert_query_budget(
        inventory_client, query_counter, "/api/v1/inventory/stock-on-hand"
    )


async def test_tenant_isolation_on_hand(
    inventory_client: AsyncClient, inventory_client_b: AsyncClient
) -> None:
    """Tenant B never sees tenant A's stock or moves."""
    warehouse_id = await _warehouse(inventory_client)
    bin_id = await _bin(inventory_client, warehouse_id)
    item_id = await _stocked_item(inventory_client)
    await _receipt(inventory_client, item_id, bin_id, "9", key="r1")

    a_on_hand = await inventory_client.get("/api/v1/inventory/stock-on-hand")
    assert len(a_on_hand.json()["items"]) == 1
    b_on_hand = await inventory_client_b.get("/api/v1/inventory/stock-on-hand")
    assert b_on_hand.json()["items"] == []
    b_moves = await inventory_client_b.get("/api/v1/inventory/stock-moves")
    assert b_moves.json()["items"] == []
