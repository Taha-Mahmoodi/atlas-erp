"""Delivery API tests (PLAN 7.3, D-045) — the outbound twin of the goods-receipt API tests: create a
DRAFT against a CONFIRMED order (201), list (paginated, filtered) + detail (+lines), POST over the
wire (the delivery POSTED, the order's delivered_quantity rose + status advanced, the order →
delivery → move docflow chain), RBAC (read vs manage vs post distinct, 401 unauthenticated),
idempotency on create/post, the ≤3-query list budget, tenant isolation, and the 422 envelopes for
over-delivery + order-not-confirmed.

The cross-module environment a delivery needs (GL accounts, an open period, a warehouse + bin, stock
on hand, a confirmed sales order) is scaffolded at the DB layer through the real factories under the
sales_client principal's OWN tenant (the sales principal's wire keys cover only currency/item, not
inventory stock / GL postings), then the delivery endpoints are exercised over the wire so the real
router → service → event-bus → handler path runs end to end.

Issue #53 caveat: an EXPECTED post failure from a handler-raised exception (insufficient stock) can
leave the aiosqlite connection unusable, so the 422 cases here are the ones that fail at CREATE
validation cleanly (over-delivery, order-not-confirmed); the happy post asserts success + advanced
state only.
"""

import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import QueryCounter, assert_query_budget
from tests.modules.sales.factories import (
    OrderSetup,
    SalesPrincipal,
    build_confirmed_order,
    build_order_setup,
    seed_on_hand,
)

_SALES = "/api/v1/sales"


def _idem(key: str) -> dict[str, str]:
    return {"Idempotency-Key": key}


@dataclass(frozen=True)
class DeliveryEnv:
    """The ids a delivery payload + its assertions use: the authenticated client, the principal's
    tenant setup, the confirmed order, its single line, and the source warehouse + bin."""

    client: AsyncClient
    principal: SalesPrincipal
    setup: OrderSetup
    order_id: uuid.UUID
    order_line_id: uuid.UUID
    item_id: uuid.UUID
    warehouse_id: uuid.UUID
    bin_id: uuid.UUID


async def _login(client: AsyncClient, principal: SalesPrincipal) -> str:
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
async def delivery_env(
    client: AsyncClient,
    db_session: AsyncSession,
    sales_user_factory: Callable[..., object],
) -> AsyncIterator[DeliveryEnv]:
    """A confirmed order with 10 on hand at a bin, scaffolded at the DB layer in the sales
    principal's own tenant (the wire keys cannot create stock / GL postings), then an authenticated
    client over that tenant. Yields the ids the delivery endpoints ship against (ordered qty 5)."""
    principal: SalesPrincipal = await sales_user_factory()  # type: ignore[assignment]
    setup = await build_order_setup(db_session, principal.tenant_id)
    await seed_on_hand(db_session, setup, "10")
    order = await build_confirmed_order(db_session, setup, quantity="5")

    access_token = await _login(client, principal)
    client.headers["Authorization"] = f"Bearer {access_token}"
    detail = await client.get(f"{_SALES}/orders/{order.id}")
    assert detail.status_code == 200, detail.text
    body = detail.json()
    yield DeliveryEnv(
        client=client,
        principal=principal,
        setup=setup,
        order_id=order.id,
        order_line_id=uuid.UUID(body["lines"][0]["id"]),
        item_id=setup.item_id,
        warehouse_id=setup.warehouse_id,
        bin_id=setup.bin_id,
    )


def _body(env: DeliveryEnv, *, qty: str = "3", order_line_id: uuid.UUID | None = None) -> dict:
    return {
        "sales_order_id": str(env.order_id),
        "warehouse_id": str(env.warehouse_id),
        "lines": [
            {
                "sales_order_line_id": str(order_line_id or env.order_line_id),
                "bin_id": str(env.bin_id),
                "quantity": qty,
            }
        ],
    }


# --- Create draft -------------------------------------------------------------


async def test_create_delivery_is_draft(delivery_env: DeliveryEnv) -> None:
    """POST /deliveries against a confirmed order returns 201, status DRAFT, a DN number + lines."""
    created = await delivery_env.client.post(
        f"{_SALES}/deliveries", headers=_idem("dn-1"), json=_body(delivery_env)
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["status"] == "DRAFT"
    assert body["delivery_number"].startswith("DN-")
    assert body["sales_order_id"] == str(delivery_env.order_id)
    assert len(body["lines"]) == 1
    assert body["lines"][0]["item_id"] == str(delivery_env.item_id)  # snapshot from the order line


async def test_get_delivery_returns_lines(delivery_env: DeliveryEnv) -> None:
    """GET /deliveries/{id} returns the header + its lines."""
    created = await delivery_env.client.post(
        f"{_SALES}/deliveries", headers=_idem("dn-get"), json=_body(delivery_env)
    )
    delivery_id = created.json()["id"]
    got = await delivery_env.client.get(f"{_SALES}/deliveries/{delivery_id}")
    assert got.status_code == 200, got.text
    assert got.json()["id"] == delivery_id
    assert got.json()["lines"][0]["quantity"] == "3.000000"


async def test_over_delivery_returns_422(delivery_env: DeliveryEnv) -> None:
    """Shipping more than the order line's open-to-deliver quantity is rejected 422 at CREATE."""
    resp = await delivery_env.client.post(
        f"{_SALES}/deliveries", headers=_idem("dn-over"), json=_body(delivery_env, qty="6")
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "sales.over_delivery"


async def test_order_not_confirmed_returns_422(
    delivery_env: DeliveryEnv, db_session: AsyncSession
) -> None:
    """A delivery against a DRAFT (unconfirmed) order is rejected 422 sales.order_not_confirmed."""
    from tests.modules.sales.factories import build_sales_order

    draft_order = await build_sales_order(
        db_session,
        delivery_env.setup.tenant_id,
        customer_id=delivery_env.setup.customer_id,
        item_id=delivery_env.setup.item_id,
        uom_id=delivery_env.setup.uom_id,
        quantity="5",
    )
    detail = await delivery_env.client.get(f"{_SALES}/orders/{draft_order.id}")
    line_id = detail.json()["lines"][0]["id"]
    body = {
        "sales_order_id": str(draft_order.id),
        "warehouse_id": str(delivery_env.warehouse_id),
        "lines": [
            {"sales_order_line_id": line_id, "bin_id": str(delivery_env.bin_id), "quantity": "3"}
        ],
    }
    resp = await delivery_env.client.post(
        f"{_SALES}/deliveries", headers=_idem("dn-nc"), json=body
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "sales.order_not_confirmed"


# --- Post: the happy chain ----------------------------------------------------


async def test_post_advances_order_and_links_chain(delivery_env: DeliveryEnv) -> None:
    """POST /deliveries/{id}/post → 200 POSTED; the order's delivered_quantity rose + status
    advanced to PARTIALLY_DELIVERED; the order → delivery → move docflow chain links."""
    created = await delivery_env.client.post(
        f"{_SALES}/deliveries", headers=_idem("dn-post"), json=_body(delivery_env, qty="3")
    )
    delivery_id = created.json()["id"]
    delivery_doc_id = created.json()["document_id"]

    posted = await delivery_env.client.post(
        f"{_SALES}/deliveries/{delivery_id}/post", headers=_idem("dn-post-act")
    )
    assert posted.status_code == 200, posted.text
    assert posted.json()["status"] == "POSTED"
    assert posted.json()["posted_at"] is not None

    # The order advanced + its line's delivered_quantity rose (ordered 5, delivered 3 → partial).
    order = await delivery_env.client.get(f"{_SALES}/orders/{delivery_env.order_id}")
    assert order.json()["status"] == "PARTIALLY_DELIVERED"
    assert order.json()["lines"][0]["delivered_quantity"] == "3.000000"

    # order → delivery ('delivered_by') → move ('moved_by') over the wire.
    chain = await delivery_env.client.get(f"/api/v1/documents/{delivery_doc_id}/chain")
    assert chain.status_code == 200, chain.text
    link_types = {edge["link_type"] for edge in chain.json()["edges"]}
    assert "delivered_by" in link_types
    assert "moved_by" in link_types


async def test_full_delivery_sets_order_delivered(delivery_env: DeliveryEnv) -> None:
    """Shipping the whole open quantity (5 of 5) posts and advances the order to DELIVERED."""
    created = await delivery_env.client.post(
        f"{_SALES}/deliveries", headers=_idem("dn-full"), json=_body(delivery_env, qty="5")
    )
    delivery_id = created.json()["id"]
    posted = await delivery_env.client.post(
        f"{_SALES}/deliveries/{delivery_id}/post", headers=_idem("dn-full-act")
    )
    assert posted.status_code == 200, posted.text
    order = await delivery_env.client.get(f"{_SALES}/orders/{delivery_env.order_id}")
    assert order.json()["status"] == "DELIVERED"


# --- Idempotency --------------------------------------------------------------


async def test_create_is_idempotent(delivery_env: DeliveryEnv) -> None:
    """Repeating create with the same Idempotency-Key replays the response, no second DN."""
    first = await delivery_env.client.post(
        f"{_SALES}/deliveries", headers=_idem("dn-idem"), json=_body(delivery_env)
    )
    second = await delivery_env.client.post(
        f"{_SALES}/deliveries", headers=_idem("dn-idem"), json=_body(delivery_env)
    )
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]


async def test_post_is_idempotent(delivery_env: DeliveryEnv) -> None:
    """Repeating post with the same Idempotency-Key replays the response, no double issue."""
    created = await delivery_env.client.post(
        f"{_SALES}/deliveries", headers=_idem("dn-pidem"), json=_body(delivery_env, qty="3")
    )
    delivery_id = created.json()["id"]
    first = await delivery_env.client.post(
        f"{_SALES}/deliveries/{delivery_id}/post", headers=_idem("dn-pidem-act")
    )
    second = await delivery_env.client.post(
        f"{_SALES}/deliveries/{delivery_id}/post", headers=_idem("dn-pidem-act")
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["status"] == "POSTED"
    # The order line was delivered exactly once (3), not twice.
    order = await delivery_env.client.get(f"{_SALES}/orders/{delivery_env.order_id}")
    assert order.json()["lines"][0]["delivered_quantity"] == "3.000000"


# --- List: pagination + filter + budget ---------------------------------------


async def test_list_paginates_and_filters(delivery_env: DeliveryEnv) -> None:
    """The list is keyset-paginated and filters by order + status."""
    for n in range(3):
        await delivery_env.client.post(
            f"{_SALES}/deliveries", headers=_idem(f"dn-page-{n}"), json=_body(delivery_env, qty="1")
        )
    page = await delivery_env.client.get(f"{_SALES}/deliveries", params={"limit": 2})
    assert page.status_code == 200, page.text
    assert len(page.json()["items"]) == 2
    assert page.json()["next_cursor"] is not None

    by_order = await delivery_env.client.get(
        f"{_SALES}/deliveries", params={"sales_order_id": str(delivery_env.order_id)}
    )
    assert len(by_order.json()["items"]) == 3
    by_status = await delivery_env.client.get(
        f"{_SALES}/deliveries", params={"status": "DRAFT"}
    )
    assert len(by_status.json()["items"]) == 3


async def test_list_query_budget(
    delivery_env: DeliveryEnv, query_counter: Callable[[], QueryCounter]
) -> None:
    """The delivery list stays within the ≤3-query budget (PERFORMANCE §6, warm path)."""
    for n in range(3):
        await delivery_env.client.post(
            f"{_SALES}/deliveries", headers=_idem(f"dn-bud-{n}"), json=_body(delivery_env, qty="1")
        )
    await assert_query_budget(
        delivery_env.client, query_counter, f"{_SALES}/deliveries?limit=2"
    )


# --- RBAC ---------------------------------------------------------------------


async def test_create_requires_manage(
    delivery_env: DeliveryEnv, sales_user_factory: Callable[..., object]
) -> None:
    """A principal with delivery.read but NOT delivery.manage cannot create — 403."""
    principal = await sales_user_factory(
        slug="sales-noManage",
        email="nomanage@sales.test",
        keys=("sales.delivery.read",),
    )
    transport = delivery_env.client._transport
    async with AsyncClient(transport=transport, base_url="https://test") as client2:
        token = await _login(client2, principal)  # type: ignore[arg-type]
        client2.headers["Authorization"] = f"Bearer {token}"
        resp = await client2.post(
            f"{_SALES}/deliveries", headers=_idem("dn-rbac-c"), json=_body(delivery_env)
        )
    assert resp.status_code == 403, resp.text
    assert resp.json()["error"]["code"] == "rbac.permission_denied"


async def test_post_requires_post_key(
    delivery_env: DeliveryEnv, sales_user_factory: Callable[..., object]
) -> None:
    """The POST action needs sales.delivery.post; a read+manage principal is 403."""
    created = await delivery_env.client.post(
        f"{_SALES}/deliveries", headers=_idem("dn-rbac-p"), json=_body(delivery_env)
    )
    delivery_id = created.json()["id"]
    principal = await sales_user_factory(
        slug="sales-noPost",
        email="nopost@sales.test",
        keys=("sales.delivery.read", "sales.delivery.manage"),
    )
    transport = delivery_env.client._transport
    async with AsyncClient(transport=transport, base_url="https://test") as client2:
        token = await _login(client2, principal)  # type: ignore[arg-type]
        client2.headers["Authorization"] = f"Bearer {token}"
        resp = await client2.post(
            f"{_SALES}/deliveries/{delivery_id}/post", headers=_idem("dn-rbac-p-act")
        )
    assert resp.status_code == 403, resp.text
    assert resp.json()["error"]["code"] == "rbac.permission_denied"


async def test_unauthenticated_is_401(delivery_env: DeliveryEnv) -> None:
    """No bearer token → 401 on the list endpoint."""
    transport = delivery_env.client._transport
    async with AsyncClient(transport=transport, base_url="https://test") as anon:
        resp = await anon.get(f"{_SALES}/deliveries")
    assert resp.status_code == 401, resp.text


# --- Tenant isolation ---------------------------------------------------------


async def test_tenant_isolation(
    delivery_env: DeliveryEnv,
    app,
    sales_user_factory: Callable[..., object],
) -> None:
    """Tenant B cannot read (404) or post (404) tenant A's delivery."""
    created = await delivery_env.client.post(
        f"{_SALES}/deliveries", headers=_idem("dn-iso"), json=_body(delivery_env)
    )
    delivery_id = created.json()["id"]

    principal_b = await sales_user_factory(slug="sales-isob", email="rep@isob.test")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as client_b:
        token = await _login(client_b, principal_b)  # type: ignore[arg-type]
        client_b.headers["Authorization"] = f"Bearer {token}"
        get_b = await client_b.get(f"{_SALES}/deliveries/{delivery_id}")
        post_b = await client_b.post(
            f"{_SALES}/deliveries/{delivery_id}/post", headers=_idem("dn-iso-post")
        )
    assert get_b.status_code == 404, get_b.text
    assert post_b.status_code == 404, post_b.text
