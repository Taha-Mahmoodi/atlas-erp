"""Return (RMA) API tests (PLAN 7.4, D-046): create a DRAFT against an invoiced order (201), list
(paginated, filtered) + detail (+lines), POST over the wire (the return POSTED, stock received back
+
the AR credit note posted, the order's returned_quantity rose, the order → return → move/credit-note
docflow chain), RBAC (read vs manage vs post distinct, 401), idempotency on create/post, the
≤3-query
list budget, tenant isolation, and the 422 envelope for over-return.

The cross-module environment (GL accounts + AR posting defaults, an open period, a delivered +
billed
order) is scaffolded at the DB layer through the real factories under the sales_client principal's
OWN
tenant, then the return endpoints are exercised over the wire so the real router → service →
event-bus → handlers path runs end to end. Per issue #53 the 422 case fails at CREATE validation
cleanly (over-return); the happy post asserts success + state only.
"""

import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.sales.schemas import BillingLineCreate
from tests.conftest import QueryCounter, assert_query_budget
from tests.modules.sales.factories import (
    BillingSetup,
    SalesPrincipal,
    build_billing,
    build_billing_setup,
    build_delivered_order,
    post_billing,
)

_SALES = "/api/v1/sales"


def _idem(key: str) -> dict[str, str]:
    return {"Idempotency-Key": key}


@dataclass(frozen=True)
class ReturnEnv:
    client: AsyncClient
    principal: SalesPrincipal
    setup: BillingSetup
    order_id: uuid.UUID
    order_line_id: uuid.UUID
    bin_id: uuid.UUID
    warehouse_id: uuid.UUID


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
async def return_env(
    client: AsyncClient,
    db_session: AsyncSession,
    sales_user_factory: Callable[..., object],
) -> AsyncIterator[ReturnEnv]:
    """A delivered AND fully-billed order (5 invoiced), scaffolded at the DB layer in the sales
    principal's own tenant, then an authenticated client over that tenant — the return
    precondition."""
    principal: SalesPrincipal = await sales_user_factory()  # type: ignore[assignment]
    setup = await build_billing_setup(db_session, principal.tenant_id)
    order = await build_delivered_order(db_session, setup, quantity="5", unit_cost="4")
    # Bill the full delivered quantity so the order line is invoiced (the return cap).
    from app.core.tenancy import tenant_context
    from app.modules.sales import service

    with tenant_context(setup.order.tenant_id):
        lines = await service.get_sales_order_lines(db_session, setup.order.tenant_id, order.id)
    billing = await build_billing(
        db_session,
        setup,
        order_id=order.id,
        lines=[BillingLineCreate(sales_order_line_id=lines[0].id, quantity=Decimal(5))],
    )
    await post_billing(db_session, setup.order.tenant_id, billing.id)

    access_token = await _login(client, principal)
    client.headers["Authorization"] = f"Bearer {access_token}"
    yield ReturnEnv(
        client=client,
        principal=principal,
        setup=setup,
        order_id=order.id,
        order_line_id=lines[0].id,
        bin_id=setup.order.bin_id,
        warehouse_id=setup.order.warehouse_id,
    )


def _body(env: ReturnEnv, *, qty: str = "2") -> dict:
    return {
        "sales_order_id": str(env.order_id),
        "warehouse_id": str(env.warehouse_id),
        "lines": [
            {
                "sales_order_line_id": str(env.order_line_id),
                "bin_id": str(env.bin_id),
                "quantity": qty,
            }
        ],
    }


# --- Create draft -------------------------------------------------------------


async def test_create_return_is_draft(return_env: ReturnEnv) -> None:
    """POST /returns against an invoiced order returns 201, status DRAFT, an RMA number + lines."""
    created = await return_env.client.post(
        f"{_SALES}/returns", headers=_idem("rma-1"), json=_body(return_env)
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["status"] == "DRAFT"
    assert body["return_number"].startswith("RMA-")
    assert body["lines"][0]["unit_price"] == "10.000000"  # snapshot from the order line


async def test_get_return_returns_lines(return_env: ReturnEnv) -> None:
    created = await return_env.client.post(
        f"{_SALES}/returns", headers=_idem("rma-get"), json=_body(return_env)
    )
    return_id = created.json()["id"]
    got = await return_env.client.get(f"{_SALES}/returns/{return_id}")
    assert got.status_code == 200, got.text
    assert got.json()["lines"][0]["quantity"] == "2.000000"


async def test_over_return_returns_422(return_env: ReturnEnv) -> None:
    """Returning more than invoiced-not-returned is rejected 422 at CREATE."""
    resp = await return_env.client.post(
        f"{_SALES}/returns", headers=_idem("rma-over"), json=_body(return_env, qty="6")
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "sales.over_return"


# --- Post: the happy chain ----------------------------------------------------


async def test_post_receives_stock_and_credits_links_chain(return_env: ReturnEnv) -> None:
    """POST /returns/{id}/post → 200 POSTED; the order's returned_quantity rose; the credit note
    exists
    (a CN- finance customer invoice); the order → return ('returned_by'), return → move
    ('received_by')
    + return → credit note ('credited_by') docflow."""
    created = await return_env.client.post(
        f"{_SALES}/returns", headers=_idem("rma-post"), json=_body(return_env, qty="2")
    )
    return_id = created.json()["id"]
    return_doc_id = created.json()["document_id"]

    posted = await return_env.client.post(
        f"{_SALES}/returns/{return_id}/post", headers=_idem("rma-post-act")
    )
    assert posted.status_code == 200, posted.text
    assert posted.json()["status"] == "POSTED"

    order = await return_env.client.get(f"{_SALES}/orders/{return_env.order_id}")
    assert order.json()["lines"][0]["returned_quantity"] == "2.000000"

    # The AR credit note exists over the wire (a CN- finance customer invoice).
    invoices = await return_env.client.get("/api/v1/finance/customer-invoices")
    assert invoices.status_code == 200, invoices.text
    assert any(
        (inv["invoice_number"] or "").startswith("CN-") for inv in invoices.json()["items"]
    )

    # The return's connected chain spans order → return ('returned_by'), return → move
    # ('received_by') and return → credit note ('credited_by').
    chain = await return_env.client.get(f"/api/v1/documents/{return_doc_id}/chain")
    link_types = {edge["link_type"] for edge in chain.json()["edges"]}
    assert "received_by" in link_types
    assert "credited_by" in link_types
    assert "returned_by" in link_types


# --- Idempotency --------------------------------------------------------------


async def test_create_is_idempotent(return_env: ReturnEnv) -> None:
    first = await return_env.client.post(
        f"{_SALES}/returns", headers=_idem("rma-idem"), json=_body(return_env)
    )
    second = await return_env.client.post(
        f"{_SALES}/returns", headers=_idem("rma-idem"), json=_body(return_env)
    )
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["id"] == second.json()["id"]


async def test_post_is_idempotent(return_env: ReturnEnv) -> None:
    created = await return_env.client.post(
        f"{_SALES}/returns", headers=_idem("rma-pidem"), json=_body(return_env, qty="2")
    )
    return_id = created.json()["id"]
    first = await return_env.client.post(
        f"{_SALES}/returns/{return_id}/post", headers=_idem("rma-pidem-act")
    )
    second = await return_env.client.post(
        f"{_SALES}/returns/{return_id}/post", headers=_idem("rma-pidem-act")
    )
    assert first.status_code == 200 and second.status_code == 200
    order = await return_env.client.get(f"{_SALES}/orders/{return_env.order_id}")
    assert order.json()["lines"][0]["returned_quantity"] == "2.000000"  # returned once


# --- List: pagination + filter + budget ---------------------------------------


async def test_list_paginates_and_filters(return_env: ReturnEnv) -> None:
    for n in range(3):
        await return_env.client.post(
            f"{_SALES}/returns", headers=_idem(f"rma-page-{n}"), json=_body(return_env, qty="1")
        )
    page = await return_env.client.get(f"{_SALES}/returns", params={"limit": 2})
    assert page.status_code == 200, page.text
    assert len(page.json()["items"]) == 2
    assert page.json()["next_cursor"] is not None
    by_status = await return_env.client.get(f"{_SALES}/returns", params={"status": "DRAFT"})
    assert len(by_status.json()["items"]) == 3


async def test_list_query_budget(
    return_env: ReturnEnv, query_counter: Callable[[], QueryCounter]
) -> None:
    for n in range(3):
        await return_env.client.post(
            f"{_SALES}/returns", headers=_idem(f"rma-bud-{n}"), json=_body(return_env, qty="1")
        )
    await assert_query_budget(return_env.client, query_counter, f"{_SALES}/returns?limit=2")


# --- RBAC ---------------------------------------------------------------------


async def test_create_requires_manage(
    return_env: ReturnEnv, sales_user_factory: Callable[..., object]
) -> None:
    principal = await sales_user_factory(
        slug="rma-noManage", email="nomanage@rma.test", keys=("sales.return.read",)
    )
    transport = return_env.client._transport
    async with AsyncClient(transport=transport, base_url="https://test") as client2:
        token = await _login(client2, principal)  # type: ignore[arg-type]
        client2.headers["Authorization"] = f"Bearer {token}"
        resp = await client2.post(
            f"{_SALES}/returns", headers=_idem("rma-rbac-c"), json=_body(return_env)
        )
    assert resp.status_code == 403, resp.text


async def test_post_requires_post_key(
    return_env: ReturnEnv, sales_user_factory: Callable[..., object]
) -> None:
    created = await return_env.client.post(
        f"{_SALES}/returns", headers=_idem("rma-rbac-p"), json=_body(return_env)
    )
    return_id = created.json()["id"]
    principal = await sales_user_factory(
        slug="rma-noPost",
        email="nopost@rma.test",
        keys=("sales.return.read", "sales.return.manage"),
    )
    transport = return_env.client._transport
    async with AsyncClient(transport=transport, base_url="https://test") as client2:
        token = await _login(client2, principal)  # type: ignore[arg-type]
        client2.headers["Authorization"] = f"Bearer {token}"
        resp = await client2.post(
            f"{_SALES}/returns/{return_id}/post", headers=_idem("rma-rbac-p-act")
        )
    assert resp.status_code == 403, resp.text


async def test_unauthenticated_is_401(return_env: ReturnEnv) -> None:
    transport = return_env.client._transport
    async with AsyncClient(transport=transport, base_url="https://test") as anon:
        resp = await anon.get(f"{_SALES}/returns")
    assert resp.status_code == 401, resp.text


# --- Tenant isolation ---------------------------------------------------------


async def test_tenant_isolation(
    return_env: ReturnEnv,
    app,
    sales_user_factory: Callable[..., object],
) -> None:
    """Tenant B cannot read (404) or post (404) tenant A's return."""
    created = await return_env.client.post(
        f"{_SALES}/returns", headers=_idem("rma-iso"), json=_body(return_env)
    )
    return_id = created.json()["id"]
    principal_b = await sales_user_factory(slug="rma-isob", email="rep@rmaisob.test")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as client_b:
        token = await _login(client_b, principal_b)  # type: ignore[arg-type]
        client_b.headers["Authorization"] = f"Bearer {token}"
        get_b = await client_b.get(f"{_SALES}/returns/{return_id}")
        post_b = await client_b.post(
            f"{_SALES}/returns/{return_id}/post", headers=_idem("rma-iso-post")
        )
    assert get_b.status_code == 404, get_b.text
    assert post_b.status_code == 404, post_b.text
