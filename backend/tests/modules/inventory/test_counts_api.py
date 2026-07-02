"""Inventory count HTTP layer (PLAN 5.4): the count lifecycle endpoints, RBAC (manage vs post),
idempotency on create + post, pagination + query budget, variance preview and the post guards.

Data setup goes through the API itself so the tests exercise the real router → service → uow path
end to end. The create + post endpoints require an Idempotency-Key header (D-013).
"""

from collections.abc import AsyncIterator, Callable

from httpx import AsyncClient

from tests.conftest import assert_query_budget
from tests.modules.inventory.factories import InventoryPrincipal


async def _account(client: AsyncClient, code: str, name: str, account_type: str) -> str:
    response = await client.post(
        "/api/v1/finance/accounts",
        json={"code": code, "name": name, "account_type": account_type},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _setup(client: AsyncClient) -> tuple[str, str, str]:
    """A warehouse + bin + a STOCKED item whose category wires the three GL accounts, plus an open
    2026 fiscal year — the count-post preconditions (a variance adjustment posts a journal). Returns
    (warehouse_id, bin_id, item_id)."""
    await client.post(
        "/api/v1/finance/fiscal-years",
        json={"code": "2026", "name": "FY2026", "start_date": "2026-01-01"},
    )
    warehouse = await client.post(
        "/api/v1/inventory/warehouses", json={"code": "WH-1", "name": "WH"}
    )
    bin_ = await client.post(
        "/api/v1/inventory/bins",
        json={"warehouse_id": warehouse.json()["id"], "code": "A1", "name": "A1"},
    )
    uom = await client.post("/api/v1/inventory/uoms", json={"code": "EA", "name": "Each"})
    inventory_account = await _account(client, "1300", "Inventory", "ASSET")
    cogs_account = await _account(client, "5000", "COGS", "EXPENSE")
    price_diff = await _account(client, "5900", "Price difference", "EXPENSE")
    cat = await client.post(
        "/api/v1/inventory/item-categories",
        json={
            "code": "C1",
            "name": "Cat",
            "inventory_account_id": inventory_account,
            "cogs_account_id": cogs_account,
            "price_difference_account_id": price_diff,
        },
    )
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
    return warehouse.json()["id"], bin_.json()["id"], item.json()["id"]


async def _receipt(
    client: AsyncClient, item_id: str, bin_id: str, qty: str, *, key: str
) -> None:
    response = await client.post(
        "/api/v1/inventory/stock-moves",
        json={
            "move_type": "RECEIPT",
            "item_id": item_id,
            "quantity": qty,
            "to_bin_id": bin_id,
            "unit_cost": "4.00",
        },
        headers={"Idempotency-Key": key},
    )
    assert response.status_code == 201, response.text


async def _create_count(client: AsyncClient, warehouse_id: str, *, key: str) -> dict:
    response = await client.post(
        "/api/v1/inventory/stock-counts",
        json={"count_type": "PHYSICAL", "warehouse_id": warehouse_id},
        headers={"Idempotency-Key": key},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _item(client: AsyncClient, code: str, category_id: str, uom_id: str) -> str:
    response = await client.post(
        "/api/v1/inventory/items",
        json={
            "item_code": code,
            "name": code,
            "item_type": "STOCKED",
            "category_id": category_id,
            "base_uom_id": uom_id,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


# --- Lifecycle ----------------------------------------------------------------


async def test_count_lifecycle_create_count_post(inventory_client: AsyncClient) -> None:
    """Create → snapshot → record counted → preview → post; on-hand ends at the counted qty."""
    warehouse_id, bin_id, item_id = await _setup(inventory_client)
    await _receipt(inventory_client, item_id, bin_id, "10", key="r1")

    count = await _create_count(inventory_client, warehouse_id, key="c1")
    assert count["status"] == "DRAFT"
    assert count["count_number"].startswith("CNT-")

    lines = await inventory_client.get(
        f"/api/v1/inventory/stock-counts/{count['id']}/lines"
    )
    assert lines.status_code == 200
    line = lines.json()["items"][0]
    assert line["system_qty"] == "10.000000"
    assert line["counted_qty"] is None

    counted = await inventory_client.post(
        f"/api/v1/inventory/stock-counts/{count['id']}/lines/{line['id']}/count",
        json={"counted_qty": "13"},
    )
    assert counted.status_code == 200
    assert counted.json()["counted_qty"] == "13.000000"

    preview = await inventory_client.get(
        f"/api/v1/inventory/stock-counts/{count['id']}/variance-preview"
    )
    assert preview.status_code == 200
    assert preview.json()["lines"]["items"][0]["variance_qty"] == "3.000000"

    posted = await inventory_client.post(
        f"/api/v1/inventory/stock-counts/{count['id']}/post",
        headers={"Idempotency-Key": "p1"},
    )
    assert posted.status_code == 200, posted.text
    assert posted.json()["status"] == "POSTED"

    on_hand = await inventory_client.get(
        f"/api/v1/inventory/stock-on-hand?item_id={item_id}"
    )
    assert on_hand.json()["items"][0]["on_hand_qty"] == "13.000000"


async def test_post_requires_all_lines_counted(inventory_client: AsyncClient) -> None:
    warehouse_id, bin_id, item_id = await _setup(inventory_client)
    await _receipt(inventory_client, item_id, bin_id, "10", key="r1")
    # A second bin with stock → two lines; only one will be counted.
    bin2 = await inventory_client.post(
        "/api/v1/inventory/bins",
        json={"warehouse_id": warehouse_id, "code": "A2", "name": "A2"},
    )
    await _receipt(inventory_client, item_id, bin2.json()["id"], "5", key="r2")

    count = await _create_count(inventory_client, warehouse_id, key="c1")
    lines = (
        await inventory_client.get(f"/api/v1/inventory/stock-counts/{count['id']}/lines")
    ).json()["items"]
    await inventory_client.post(
        f"/api/v1/inventory/stock-counts/{count['id']}/lines/{lines[0]['id']}/count",
        json={"counted_qty": "10"},
    )
    response = await inventory_client.post(
        f"/api/v1/inventory/stock-counts/{count['id']}/post",
        headers={"Idempotency-Key": "p1"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "inventory.count_lines_uncounted"


async def test_repost_is_idempotent(inventory_client: AsyncClient) -> None:
    """Re-posting with the SAME idempotency key replays the stored result; a fresh key on a POSTED
    count is rejected (no double adjustment)."""
    warehouse_id, bin_id, item_id = await _setup(inventory_client)
    await _receipt(inventory_client, item_id, bin_id, "10", key="r1")
    count = await _create_count(inventory_client, warehouse_id, key="c1")
    line = (
        await inventory_client.get(f"/api/v1/inventory/stock-counts/{count['id']}/lines")
    ).json()["items"][0]
    await inventory_client.post(
        f"/api/v1/inventory/stock-counts/{count['id']}/lines/{line['id']}/count",
        json={"counted_qty": "12"},
    )
    first = await inventory_client.post(
        f"/api/v1/inventory/stock-counts/{count['id']}/post",
        headers={"Idempotency-Key": "p1"},
    )
    assert first.status_code == 200
    # Same key → replayed identical body.
    replay = await inventory_client.post(
        f"/api/v1/inventory/stock-counts/{count['id']}/post",
        headers={"Idempotency-Key": "p1"},
    )
    assert replay.status_code == 200
    assert replay.json()["id"] == first.json()["id"]
    # A DIFFERENT key on a now-POSTED count is rejected by the service guard.
    fresh = await inventory_client.post(
        f"/api/v1/inventory/stock-counts/{count['id']}/post",
        headers={"Idempotency-Key": "p2"},
    )
    assert fresh.status_code == 409
    assert fresh.json()["error"]["code"] == "inventory.count_already_posted"
    # On-hand stayed at the single posted result (12), no double adjustment.
    on_hand = await inventory_client.get(
        f"/api/v1/inventory/stock-on-hand?item_id={item_id}"
    )
    assert on_hand.json()["items"][0]["on_hand_qty"] == "12.000000"


async def test_create_is_idempotent(inventory_client: AsyncClient) -> None:
    warehouse_id, bin_id, item_id = await _setup(inventory_client)
    await _receipt(inventory_client, item_id, bin_id, "10", key="r1")
    first = await _create_count(inventory_client, warehouse_id, key="c1")
    replay = await inventory_client.post(
        "/api/v1/inventory/stock-counts",
        json={"count_type": "PHYSICAL", "warehouse_id": warehouse_id},
        headers={"Idempotency-Key": "c1"},
    )
    assert replay.status_code == 201
    assert replay.json()["id"] == first["id"]


async def test_cancel_count(inventory_client: AsyncClient) -> None:
    warehouse_id, bin_id, item_id = await _setup(inventory_client)
    await _receipt(inventory_client, item_id, bin_id, "10", key="r1")
    count = await _create_count(inventory_client, warehouse_id, key="c1")
    response = await inventory_client.post(
        f"/api/v1/inventory/stock-counts/{count['id']}/cancel"
    )
    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"


# --- RBAC ---------------------------------------------------------------------


async def test_rbac_manage_principal_cannot_post(
    inventory_client: AsyncClient,
    inventory_user_factory: Callable[..., AsyncIterator[InventoryPrincipal]],
    client: AsyncClient,
) -> None:
    """A principal with count.manage + count.read (no count.post) can create/count but gets 403 on
    POST /post — posting is the privileged action."""
    warehouse_id, bin_id, item_id = await _setup(inventory_client)
    await _receipt(inventory_client, item_id, bin_id, "10", key="r1")
    count = await _create_count(inventory_client, warehouse_id, key="c1")
    line = (
        await inventory_client.get(f"/api/v1/inventory/stock-counts/{count['id']}/lines")
    ).json()["items"][0]
    await inventory_client.post(
        f"/api/v1/inventory/stock-counts/{count['id']}/lines/{line['id']}/count",
        json={"counted_qty": "12"},
    )

    manager = await inventory_user_factory(
        slug="inv-mgr",
        email="mgr@inv.test",
        keys=("inventory.count.read", "inventory.count.manage"),
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": manager.tenant_slug,
            "email": manager.email,
            "password": manager.password,
        },
    )
    token = login.json()["access_token"]
    response = await client.post(
        f"/api/v1/inventory/stock-counts/{count['id']}/post",
        headers={"Idempotency-Key": "p1", "Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


async def test_rbac_read_only_cannot_create(
    inventory_client: AsyncClient,
    inventory_user_factory: Callable[..., AsyncIterator[InventoryPrincipal]],
    client: AsyncClient,
) -> None:
    warehouse_id, _bin_id, _item_id = await _setup(inventory_client)
    reader = await inventory_user_factory(
        slug="inv-rdr", email="rdr@inv.test", keys=("inventory.count.read",)
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
        "/api/v1/inventory/stock-counts",
        json={"count_type": "PHYSICAL", "warehouse_id": warehouse_id},
        headers={"Idempotency-Key": "c1", "Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


# --- Tenant isolation + pagination + query budget -----------------------------


async def test_counts_list_is_tenant_isolated(
    inventory_client: AsyncClient, inventory_client_b: AsyncClient
) -> None:
    warehouse_id, bin_id, item_id = await _setup(inventory_client)
    await _receipt(inventory_client, item_id, bin_id, "10", key="r1")
    await _create_count(inventory_client, warehouse_id, key="c1")
    # Tenant B sees none of tenant A's counts.
    other = await inventory_client_b.get("/api/v1/inventory/stock-counts")
    assert other.status_code == 200
    assert other.json()["items"] == []


async def test_counts_list_query_budget(
    inventory_client: AsyncClient, query_counter
) -> None:  # noqa: ANN001 - fixture factory typed in conftest
    warehouse_id, bin_id, item_id = await _setup(inventory_client)
    await _receipt(inventory_client, item_id, bin_id, "10", key="r1")
    await _create_count(inventory_client, warehouse_id, key="c1")
    await _create_count(inventory_client, warehouse_id, key="c2")
    await assert_query_budget(
        inventory_client, query_counter, "/api/v1/inventory/stock-counts"
    )


async def test_variance_preview_query_budget_is_constant(
    inventory_client: AsyncClient, query_counter
) -> None:
    """Regression for #78: the preview used to issue 2-3 queries PER LINE. With several lines the
    warm-path budget stays constant: user + count header + all-lines slim read + bulk quants +
    valuations + FIFO layers + page select."""
    warehouse_id, bin_id, item_id = await _setup(inventory_client)
    await _receipt(inventory_client, item_id, bin_id, "10", key="r1")
    # Two more stocked items so the PHYSICAL count snapshots 3 lines.
    cat = await inventory_client.get("/api/v1/inventory/item-categories")
    category_id = cat.json()["items"][0]["id"]
    uoms = await inventory_client.get("/api/v1/inventory/uoms")
    uom_id = uoms.json()["items"][0]["id"]
    for index in (2, 3):
        extra = await _item(inventory_client, f"ITEM-{index}", category_id, uom_id)
        await _receipt(inventory_client, extra, bin_id, "5", key=f"r{index}")
    count = await _create_count(inventory_client, warehouse_id, key="cqb")
    await assert_query_budget(
        query_counter=query_counter,
        client=inventory_client,
        url=f"/api/v1/inventory/stock-counts/{count['id']}/variance-preview",
        budget=7,
    )
