"""Sales pricing HTTP tests (PLAN 7.1): price-list + price-list-item CRUD, the price-quote endpoint,
RBAC, the query budget (≤3), ETag on the price-list list, and tenant isolation.

Cross-module setup goes through the API itself: a currency via finance, an item via inventory (a
price-list item points at it; the price-quote resolves a customer's currency against it).
"""

from collections.abc import Callable

from httpx import AsyncClient

from tests.conftest import QueryCounter, assert_query_budget

_PRICE_LISTS_URL = "/api/v1/sales/price-lists"
_CUSTOMERS_URL = "/api/v1/sales/customers"
_QUOTE_URL = "/api/v1/sales/price-quote"


async def _seed_currency(client: AsyncClient, code: str = "USD") -> None:
    response = await client.post("/api/v1/finance/currencies", json={"code": code, "name": code})
    assert response.status_code == 201, response.text


async def _seed_item(client: AsyncClient, *, item_code: str = "ITEM-1") -> str:
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
    return item.json()["id"]


async def _create_price_list(client: AsyncClient, *, code: str = "PL-1") -> str:
    response = await client.post(
        _PRICE_LISTS_URL,
        json={
            "code": code,
            "name": "Standard",
            "currency_code": "USD",
            "valid_from": "2026-01-01",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _create_customer(client: AsyncClient, *, customer_code: str = "C-001") -> str:
    response = await client.post(
        _CUSTOMERS_URL,
        json={"customer_code": customer_code, "name": "Acme", "default_currency_code": "USD"},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


# --- CRUD round-trip -----------------------------------------------------------


async def test_price_list_crud_round_trip(sales_client: AsyncClient) -> None:
    await _seed_currency(sales_client)
    pl_id = await _create_price_list(sales_client)
    got = await sales_client.get(f"{_PRICE_LISTS_URL}/{pl_id}")
    assert got.status_code == 200
    assert got.json()["status"] == "ACTIVE"
    assert got.json()["priority"] == 0

    patched = await sales_client.patch(
        f"{_PRICE_LISTS_URL}/{pl_id}", json={"status": "INACTIVE", "priority": 3}
    )
    assert patched.status_code == 200
    assert patched.json()["status"] == "INACTIVE"
    assert patched.json()["priority"] == 3


async def test_price_list_items_crud(sales_client: AsyncClient) -> None:
    await _seed_currency(sales_client)
    item_id = await _seed_item(sales_client)
    pl_id = await _create_price_list(sales_client)
    items_url = f"{_PRICE_LISTS_URL}/{pl_id}/items"

    created = await sales_client.post(
        items_url, json={"item_id": item_id, "unit_price": "12.50", "min_quantity": "5"}
    )
    assert created.status_code == 201, created.text
    assert created.json()["unit_price"] == "12.500000"

    listed = await sales_client.get(items_url)
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    deleted = await sales_client.delete(f"{items_url}/{item_id}")
    assert deleted.status_code == 204
    assert (await sales_client.get(items_url)).json() == []


async def test_price_list_item_unknown_item_rejected(sales_client: AsyncClient) -> None:
    import uuid

    await _seed_currency(sales_client)
    pl_id = await _create_price_list(sales_client)
    response = await sales_client.post(
        f"{_PRICE_LISTS_URL}/{pl_id}/items",
        json={"item_id": str(uuid.uuid4()), "unit_price": "5"},
    )
    assert response.status_code == 422, response.text


# --- The price-quote endpoint --------------------------------------------------


async def test_price_quote_resolves(sales_client: AsyncClient) -> None:
    await _seed_currency(sales_client)
    item_id = await _seed_item(sales_client)
    customer_id = await _create_customer(sales_client)
    pl_id = await _create_price_list(sales_client)
    await sales_client.post(
        f"{_PRICE_LISTS_URL}/{pl_id}/items", json={"item_id": item_id, "unit_price": "10"}
    )

    response = await sales_client.get(
        _QUOTE_URL,
        params={
            "item_id": item_id,
            "customer_id": customer_id,
            "quantity": "1",
            "date": "2026-06-15",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["matched"] is True
    assert body["unit_price"] == "10.000000"
    assert body["price_list_id"] == pl_id
    assert body["currency_code"] == "USD"


async def test_price_quote_no_match(sales_client: AsyncClient) -> None:
    await _seed_currency(sales_client)
    item_id = await _seed_item(sales_client)
    customer_id = await _create_customer(sales_client)
    response = await sales_client.get(
        _QUOTE_URL,
        params={"item_id": item_id, "customer_id": customer_id, "quantity": "1"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["matched"] is False
    assert body["unit_price"] is None


async def test_price_quote_unknown_customer_404(sales_client: AsyncClient) -> None:
    import uuid

    await _seed_currency(sales_client)
    item_id = await _seed_item(sales_client)
    response = await sales_client.get(
        _QUOTE_URL,
        params={"item_id": item_id, "customer_id": str(uuid.uuid4()), "quantity": "1"},
    )
    assert response.status_code == 404, response.text


# --- Performance: query budget + ETag ------------------------------------------


async def test_price_list_query_budget(
    sales_client: AsyncClient,
    query_counter: Callable[[], QueryCounter],
) -> None:
    await _seed_currency(sales_client)
    await _create_price_list(sales_client)
    await assert_query_budget(sales_client, query_counter, _PRICE_LISTS_URL)


async def test_price_list_returns_etag_and_304(sales_client: AsyncClient) -> None:
    await _seed_currency(sales_client)
    await _create_price_list(sales_client)
    first = await sales_client.get(_PRICE_LISTS_URL)
    assert first.status_code == 200, first.text
    etag = first.headers["ETag"]
    again = await sales_client.get(_PRICE_LISTS_URL, headers={"If-None-Match": etag})
    assert again.status_code == 304


# --- RBAC + isolation ----------------------------------------------------------


async def test_read_key_cannot_write(
    sales_user_factory: Callable[..., object],
    client: AsyncClient,
) -> None:
    """A principal holding only the pricelist READ key cannot create — 403 permission_denied."""
    read_only = await sales_user_factory(
        slug="sales-plro", email="ro@sales-plro.test", keys=("sales.pricelist.read",)
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": read_only.tenant_slug,
            "email": read_only.email,
            "password": read_only.password,
        },
    )
    token = login.json()["access_token"]
    response = await client.post(
        _PRICE_LISTS_URL,
        json={"code": "PL-1", "name": "x", "currency_code": "USD", "valid_from": "2026-01-01"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "rbac.permission_denied"


async def test_price_lists_are_tenant_isolated(
    sales_client: AsyncClient, sales_client_b: AsyncClient
) -> None:
    """Tenant B never sees tenant A's price lists, and A's list id 404s for B (D-007)."""
    await _seed_currency(sales_client)
    a_id = await _create_price_list(sales_client)

    b_list = await sales_client_b.get(_PRICE_LISTS_URL)
    assert b_list.status_code == 200
    assert b_list.json()["items"] == []

    b_get = await sales_client_b.get(f"{_PRICE_LISTS_URL}/{a_id}")
    assert b_get.status_code == 404
