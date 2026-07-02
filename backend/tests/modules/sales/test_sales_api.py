"""Sales quote + order HTTP tests (PLAN 7.2): CRUD + actions over the wire, the quote→order docflow
chain, the confirm gate (credit block + release), the ATP endpoint, RBAC (manage vs confirm vs
credit_release), pagination, the query budget (≤3), idempotency, and tenant isolation.

Cross-module scaffolding goes through the API itself (a currency via finance, an item via inventory
—
the full-rights principal carries those setup keys), so the tests exercise the real router → service
→ uow path and the D-029 cross-module reads end to end. ATP never blocks, so a confirm with no
on-hand still CONFIRMS when credit is within limit; the credit block is driven by a cash-only
(credit_limit 0) customer so any order's own value exceeds the limit.
"""

from collections.abc import Callable

from httpx import AsyncClient

from tests.conftest import QueryCounter, assert_query_budget

_SALES = "/api/v1/sales"


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


async def _create_customer(
    client: AsyncClient, *, code: str = "C-1", credit_limit: str = "100000"
) -> str:
    response = await client.post(
        f"{_SALES}/customers",
        json={
            "customer_code": code,
            "name": "Acme",
            "default_currency_code": "USD",
            "credit_limit": credit_limit,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _idem(key: str) -> dict[str, str]:
    return {"Idempotency-Key": key}


async def _setup(client: AsyncClient, **customer_kwargs: str) -> tuple[str, str, str]:
    """Currency + item + customer over the wire; return (customer_id, item_id, uom_id)."""
    await _seed_currency(client)
    item_id, uom_id = await _seed_item(client)
    customer_id = await _create_customer(client, **customer_kwargs)
    return customer_id, item_id, uom_id


# --- Quote → order chain + docflow --------------------------------------------


async def test_quote_to_order_chain(sales_client: AsyncClient) -> None:
    customer_id, item_id, uom_id = await _setup(sales_client)
    quote = await sales_client.post(
        f"{_SALES}/quotes",
        headers=_idem("q-1"),
        json={
            "customer_id": customer_id,
            "lines": [
                {"item_id": item_id, "quantity": "4", "uom_id": uom_id, "unit_price": "25"}
            ],
        },
    )
    assert quote.status_code == 201, quote.text
    quote_id = quote.json()["id"]
    assert quote.json()["total_amount"] == "100.000000"
    assert quote.json()["quote_number"].startswith("QUO-")

    await sales_client.post(f"{_SALES}/quotes/{quote_id}/send", headers=_idem("send-1"))
    await sales_client.post(f"{_SALES}/quotes/{quote_id}/accept", headers=_idem("acc-1"))
    order = await sales_client.post(
        f"{_SALES}/quotes/{quote_id}/convert-to-order", headers=_idem("conv-1"), json={}
    )
    assert order.status_code == 201, order.text
    order_body = order.json()
    assert order_body["source_quote_id"] == quote_id  # the quote→order link the chain renders
    assert order_body["status"] == "DRAFT"
    assert order_body["total_amount"] == "100.000000"
    assert order_body["order_number"].startswith("SO-")
    # The quote is advanced to CONVERTED (the docflow edge is asserted in the service test).
    converted = await sales_client.get(f"{_SALES}/quotes/{quote_id}")
    assert converted.json()["status"] == "CONVERTED"


async def test_order_confirm_passes(sales_client: AsyncClient) -> None:
    customer_id, item_id, uom_id = await _setup(sales_client)
    order = await sales_client.post(
        f"{_SALES}/orders",
        headers=_idem("o-1"),
        json={
            "customer_id": customer_id,
            "lines": [
                {"item_id": item_id, "quantity": "2", "uom_id": uom_id, "unit_price": "10"}
            ],
        },
    )
    assert order.status_code == 201, order.text
    order_id = order.json()["id"]
    confirmed = await sales_client.post(
        f"{_SALES}/orders/{order_id}/confirm", headers=_idem("conf-1")
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "CONFIRMED"
    assert confirmed.json()["credit_check_status"] == "PASSED"


async def test_order_credit_block_then_release(
    sales_client: AsyncClient,
    sales_user_factory: Callable[..., object],
    client: AsyncClient,
) -> None:
    # A cash-only customer (credit_limit 0): any order's own value exceeds the limit → BLOCKED.
    customer_id, item_id, uom_id = await _setup(sales_client, code="C-CASH", credit_limit="0")
    order = await sales_client.post(
        f"{_SALES}/orders",
        headers=_idem("o-cb"),
        json={
            "customer_id": customer_id,
            "lines": [
                {"item_id": item_id, "quantity": "1", "uom_id": uom_id, "unit_price": "10"}
            ],
        },
    )
    order_id = order.json()["id"]
    blocked = await sales_client.post(
        f"{_SALES}/orders/{order_id}/confirm", headers=_idem("conf-cb")
    )
    assert blocked.status_code == 200, blocked.text
    assert blocked.json()["status"] == "CREDIT_BLOCKED"
    assert blocked.json()["credit_check_status"] == "BLOCKED"

    # A user holding only confirm (not credit_release) cannot release.
    no_release = await sales_user_factory(
        slug="sales-nr",
        email="nr@sales-nr.test",
        keys=("sales.order.read", "sales.order.confirm"),
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": no_release.tenant_slug,
            "email": no_release.email,
            "password": no_release.password,
        },
    )
    token = login.json()["access_token"]
    denied = await client.post(
        f"{_SALES}/orders/{order_id}/credit-release",
        headers={"Authorization": f"Bearer {token}", **_idem("rel-deny")},
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "rbac.permission_denied"

    # The full-rights principal (holds credit_release) releases → CONFIRMED.
    released = await sales_client.post(
        f"{_SALES}/orders/{order_id}/credit-release", headers=_idem("rel-1")
    )
    assert released.status_code == 200, released.text
    assert released.json()["status"] == "CONFIRMED"
    assert released.json()["credit_check_status"] == "RELEASED"


async def test_atp_endpoint(sales_client: AsyncClient) -> None:
    _customer_id, item_id, _uom_id = await _setup(sales_client)
    response = await sales_client.post(
        f"{_SALES}/orders/atp",
        json={"lines": [{"item_id": item_id, "quantity": "5"}]},
    )
    assert response.status_code == 200, response.text
    line = response.json()["lines"][0]
    assert line["item_id"] == item_id
    assert line["on_hand"] == "0.000000"  # no stock seeded
    assert line["atp_ok"] is False
    assert line["backordered"] is True


# --- RBAC + pagination + budget + idempotency + isolation ----------------------


async def test_confirm_requires_confirm_key(
    sales_client: AsyncClient,
    sales_user_factory: Callable[..., object],
    client: AsyncClient,
) -> None:
    """A principal holding order.manage but NOT order.confirm cannot confirm — 403."""
    customer_id, item_id, uom_id = await _setup(sales_client)
    order = await sales_client.post(
        f"{_SALES}/orders",
        headers=_idem("o-rbac"),
        json={
            "customer_id": customer_id,
            "lines": [
                {"item_id": item_id, "quantity": "1", "uom_id": uom_id, "unit_price": "10"}
            ],
        },
    )
    order_id = order.json()["id"]
    no_confirm = await sales_user_factory(
        slug="sales-nc",
        email="nc@sales-nc.test",
        keys=("sales.order.read", "sales.order.manage"),
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": no_confirm.tenant_slug,
            "email": no_confirm.email,
            "password": no_confirm.password,
        },
    )
    token = login.json()["access_token"]
    denied = await client.post(
        f"{_SALES}/orders/{order_id}/confirm",
        headers={"Authorization": f"Bearer {token}", **_idem("conf-deny")},
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "rbac.permission_denied"


async def test_order_list_query_budget(
    sales_client: AsyncClient, query_counter: Callable[[], QueryCounter]
) -> None:
    customer_id, item_id, uom_id = await _setup(sales_client)
    for n in range(3):
        await sales_client.post(
            f"{_SALES}/orders",
            headers=_idem(f"budget-{n}"),
            json={
                "customer_id": customer_id,
                "lines": [
                    {"item_id": item_id, "quantity": "1", "uom_id": uom_id, "unit_price": "10"}
                ],
            },
        )
    await assert_query_budget(sales_client, query_counter, f"{_SALES}/orders")


async def test_quotes_paginate(sales_client: AsyncClient) -> None:
    customer_id, item_id, uom_id = await _setup(sales_client)
    for n in range(3):
        await sales_client.post(
            f"{_SALES}/quotes",
            headers=_idem(f"page-{n}"),
            json={
                "customer_id": customer_id,
                "lines": [
                    {"item_id": item_id, "quantity": "1", "uom_id": uom_id, "unit_price": "10"}
                ],
            },
        )
    page = await sales_client.get(f"{_SALES}/quotes?limit=2")
    assert page.status_code == 200
    body = page.json()
    assert len(body["items"]) == 2
    assert body["next_cursor"] is not None


async def test_order_create_idempotent(sales_client: AsyncClient) -> None:
    customer_id, item_id, uom_id = await _setup(sales_client)
    payload = {
        "customer_id": customer_id,
        "lines": [{"item_id": item_id, "quantity": "1", "uom_id": uom_id, "unit_price": "10"}],
    }
    first = await sales_client.post(f"{_SALES}/orders", headers=_idem("dup"), json=payload)
    second = await sales_client.post(f"{_SALES}/orders", headers=_idem("dup"), json=payload)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]  # replay, no second order


async def test_orders_tenant_isolated(
    sales_client: AsyncClient, sales_client_b: AsyncClient
) -> None:
    customer_id, item_id, uom_id = await _setup(sales_client)
    order = await sales_client.post(
        f"{_SALES}/orders",
        headers=_idem("iso"),
        json={
            "customer_id": customer_id,
            "lines": [
                {"item_id": item_id, "quantity": "1", "uom_id": uom_id, "unit_price": "10"}
            ],
        },
    )
    a_id = order.json()["id"]
    b_list = await sales_client_b.get(f"{_SALES}/orders")
    assert b_list.json()["items"] == []
    b_get = await sales_client_b.get(f"{_SALES}/orders/{a_id}")
    assert b_get.status_code == 404
