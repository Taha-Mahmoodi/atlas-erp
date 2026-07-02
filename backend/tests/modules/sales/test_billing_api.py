"""Billing API tests (PLAN 7.4, D-046) — the AR mirror of the delivery API tests: create a DRAFT
against a delivered order (201), list (paginated, filtered) + detail (+lines), POST over the wire
(the
billing POSTED, the AR customer invoice created, the order's invoiced_quantity rose + status
advanced, the order → billing → invoice docflow chain), RBAC (read vs manage vs post distinct, 401),
idempotency on create/post, the ≤3-query list budget, tenant isolation, and the 422 envelope for
over-billing.

The cross-module environment (GL accounts + AR posting defaults, an open period, a delivered order)
is scaffolded at the DB layer through the real factories under the sales_client principal's OWN
tenant, then the billing endpoints are exercised over the wire so the real router → service →
event-bus → finance-handler path runs end to end. Per issue #53 the 422 case fails at CREATE
validation cleanly (over-billing); the happy post asserts success + advanced state only.
"""

import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import QueryCounter, assert_query_budget
from tests.modules.sales.factories import (
    BillingSetup,
    SalesPrincipal,
    build_billing_setup,
    build_delivered_order,
)

_SALES = "/api/v1/sales"


def _idem(key: str) -> dict[str, str]:
    return {"Idempotency-Key": key}


@dataclass(frozen=True)
class BillingEnv:
    client: AsyncClient
    principal: SalesPrincipal
    setup: BillingSetup
    order_id: uuid.UUID
    order_line_id: uuid.UUID


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
async def billing_env(
    client: AsyncClient,
    db_session: AsyncSession,
    sales_user_factory: Callable[..., object],
) -> AsyncIterator[BillingEnv]:
    """A fully-delivered order (5 delivered) with the AR posting defaults wired, scaffolded at the
    DB
    layer in the sales principal's own tenant, then an authenticated client over that tenant."""
    principal: SalesPrincipal = await sales_user_factory()  # type: ignore[assignment]
    setup = await build_billing_setup(db_session, principal.tenant_id)
    order = await build_delivered_order(db_session, setup, quantity="5")

    access_token = await _login(client, principal)
    client.headers["Authorization"] = f"Bearer {access_token}"
    detail = await client.get(f"{_SALES}/orders/{order.id}")
    assert detail.status_code == 200, detail.text
    yield BillingEnv(
        client=client,
        principal=principal,
        setup=setup,
        order_id=order.id,
        order_line_id=uuid.UUID(detail.json()["lines"][0]["id"]),
    )


def _body(env: BillingEnv, *, qty: str = "3") -> dict:
    return {
        "sales_order_id": str(env.order_id),
        "lines": [{"sales_order_line_id": str(env.order_line_id), "quantity": qty}],
    }


# --- Create draft -------------------------------------------------------------


async def test_create_billing_is_draft(billing_env: BillingEnv) -> None:
    """POST /billings against a delivered order returns 201, status DRAFT, a BIL number + lines."""
    created = await billing_env.client.post(
        f"{_SALES}/billings", headers=_idem("bil-1"), json=_body(billing_env)
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["status"] == "DRAFT"
    assert body["billing_number"].startswith("BIL-")
    assert body["sales_order_id"] == str(billing_env.order_id)
    assert body["lines"][0]["unit_price"] == "10.000000"  # snapshot from the order line


async def test_get_billing_returns_lines(billing_env: BillingEnv) -> None:
    created = await billing_env.client.post(
        f"{_SALES}/billings", headers=_idem("bil-get"), json=_body(billing_env)
    )
    billing_id = created.json()["id"]
    got = await billing_env.client.get(f"{_SALES}/billings/{billing_id}")
    assert got.status_code == 200, got.text
    assert got.json()["lines"][0]["quantity"] == "3.000000"


async def test_over_billing_returns_422(billing_env: BillingEnv) -> None:
    """Billing more than delivered-not-invoiced is rejected 422 at CREATE."""
    resp = await billing_env.client.post(
        f"{_SALES}/billings", headers=_idem("bil-over"), json=_body(billing_env, qty="6")
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "sales.over_billing"


# --- Post: the happy chain ----------------------------------------------------


async def test_post_creates_invoice_and_links_chain(billing_env: BillingEnv) -> None:
    """POST /billings/{id}/post → 200 POSTED; the order's invoiced_quantity rose; the AR invoice
    exists
    (a finance customer invoice); the order → billing ('billed_by') + billing → invoice docflow."""
    created = await billing_env.client.post(
        f"{_SALES}/billings", headers=_idem("bil-post"), json=_body(billing_env, qty="3")
    )
    billing_id = created.json()["id"]
    billing_doc_id = created.json()["document_id"]

    posted = await billing_env.client.post(
        f"{_SALES}/billings/{billing_id}/post", headers=_idem("bil-post-act")
    )
    assert posted.status_code == 200, posted.text
    assert posted.json()["status"] == "POSTED"

    order = await billing_env.client.get(f"{_SALES}/orders/{billing_env.order_id}")
    assert order.json()["lines"][0]["invoiced_quantity"] == "3.000000"

    # The AR customer invoice exists over the wire (a POSTED finance customer invoice).
    invoices = await billing_env.client.get("/api/v1/finance/customer-invoices")
    assert invoices.status_code == 200, invoices.text
    assert any(inv["status"] == "POSTED" for inv in invoices.json()["items"])

    # The billing's connected chain spans order → billing ('billed_by') → invoice
    # ('invoiced_by_invoice').
    chain = await billing_env.client.get(f"/api/v1/documents/{billing_doc_id}/chain")
    link_types = {edge["link_type"] for edge in chain.json()["edges"]}
    assert "invoiced_by_invoice" in link_types
    assert "billed_by" in link_types


async def test_full_billing_closes_order(billing_env: BillingEnv) -> None:
    """Billing the whole delivered quantity (5 of 5) posts and advances the order to CLOSED."""
    created = await billing_env.client.post(
        f"{_SALES}/billings", headers=_idem("bil-full"), json=_body(billing_env, qty="5")
    )
    billing_id = created.json()["id"]
    posted = await billing_env.client.post(
        f"{_SALES}/billings/{billing_id}/post", headers=_idem("bil-full-act")
    )
    assert posted.status_code == 200, posted.text
    order = await billing_env.client.get(f"{_SALES}/orders/{billing_env.order_id}")
    assert order.json()["status"] == "CLOSED"


# --- Idempotency --------------------------------------------------------------


async def test_create_is_idempotent(billing_env: BillingEnv) -> None:
    first = await billing_env.client.post(
        f"{_SALES}/billings", headers=_idem("bil-idem"), json=_body(billing_env)
    )
    second = await billing_env.client.post(
        f"{_SALES}/billings", headers=_idem("bil-idem"), json=_body(billing_env)
    )
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["id"] == second.json()["id"]


async def test_post_is_idempotent(billing_env: BillingEnv) -> None:
    created = await billing_env.client.post(
        f"{_SALES}/billings", headers=_idem("bil-pidem"), json=_body(billing_env, qty="3")
    )
    billing_id = created.json()["id"]
    first = await billing_env.client.post(
        f"{_SALES}/billings/{billing_id}/post", headers=_idem("bil-pidem-act")
    )
    second = await billing_env.client.post(
        f"{_SALES}/billings/{billing_id}/post", headers=_idem("bil-pidem-act")
    )
    assert first.status_code == 200 and second.status_code == 200
    order = await billing_env.client.get(f"{_SALES}/orders/{billing_env.order_id}")
    assert order.json()["lines"][0]["invoiced_quantity"] == "3.000000"  # billed once


# --- List: pagination + filter + budget ---------------------------------------


async def test_list_paginates_and_filters(billing_env: BillingEnv) -> None:
    for n in range(3):
        await billing_env.client.post(
            f"{_SALES}/billings", headers=_idem(f"bil-page-{n}"), json=_body(billing_env, qty="1")
        )
    page = await billing_env.client.get(f"{_SALES}/billings", params={"limit": 2})
    assert page.status_code == 200, page.text
    assert len(page.json()["items"]) == 2
    assert page.json()["next_cursor"] is not None
    by_status = await billing_env.client.get(f"{_SALES}/billings", params={"status": "DRAFT"})
    assert len(by_status.json()["items"]) == 3


async def test_list_query_budget(
    billing_env: BillingEnv, query_counter: Callable[[], QueryCounter]
) -> None:
    for n in range(3):
        await billing_env.client.post(
            f"{_SALES}/billings", headers=_idem(f"bil-bud-{n}"), json=_body(billing_env, qty="1")
        )
    await assert_query_budget(billing_env.client, query_counter, f"{_SALES}/billings?limit=2")


# --- RBAC ---------------------------------------------------------------------


async def test_create_requires_manage(
    billing_env: BillingEnv, sales_user_factory: Callable[..., object]
) -> None:
    principal = await sales_user_factory(
        slug="bil-noManage", email="nomanage@bil.test", keys=("sales.billing.read",)
    )
    transport = billing_env.client._transport
    async with AsyncClient(transport=transport, base_url="https://test") as client2:
        token = await _login(client2, principal)  # type: ignore[arg-type]
        client2.headers["Authorization"] = f"Bearer {token}"
        resp = await client2.post(
            f"{_SALES}/billings", headers=_idem("bil-rbac-c"), json=_body(billing_env)
        )
    assert resp.status_code == 403, resp.text
    assert resp.json()["error"]["code"] == "rbac.permission_denied"


async def test_post_requires_post_key(
    billing_env: BillingEnv, sales_user_factory: Callable[..., object]
) -> None:
    created = await billing_env.client.post(
        f"{_SALES}/billings", headers=_idem("bil-rbac-p"), json=_body(billing_env)
    )
    billing_id = created.json()["id"]
    principal = await sales_user_factory(
        slug="bil-noPost",
        email="nopost@bil.test",
        keys=("sales.billing.read", "sales.billing.manage"),
    )
    transport = billing_env.client._transport
    async with AsyncClient(transport=transport, base_url="https://test") as client2:
        token = await _login(client2, principal)  # type: ignore[arg-type]
        client2.headers["Authorization"] = f"Bearer {token}"
        resp = await client2.post(
            f"{_SALES}/billings/{billing_id}/post", headers=_idem("bil-rbac-p-act")
        )
    assert resp.status_code == 403, resp.text


async def test_unauthenticated_is_401(billing_env: BillingEnv) -> None:
    transport = billing_env.client._transport
    async with AsyncClient(transport=transport, base_url="https://test") as anon:
        resp = await anon.get(f"{_SALES}/billings")
    assert resp.status_code == 401, resp.text


# --- Tenant isolation ---------------------------------------------------------


async def test_tenant_isolation(
    billing_env: BillingEnv,
    app,
    sales_user_factory: Callable[..., object],
) -> None:
    """Tenant B cannot read (404) or post (404) tenant A's billing."""
    created = await billing_env.client.post(
        f"{_SALES}/billings", headers=_idem("bil-iso"), json=_body(billing_env)
    )
    billing_id = created.json()["id"]
    principal_b = await sales_user_factory(slug="bil-isob", email="rep@bilisob.test")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as client_b:
        token = await _login(client_b, principal_b)  # type: ignore[arg-type]
        client_b.headers["Authorization"] = f"Bearer {token}"
        get_b = await client_b.get(f"{_SALES}/billings/{billing_id}")
        post_b = await client_b.post(
            f"{_SALES}/billings/{billing_id}/post", headers=_idem("bil-iso-post")
        )
    assert get_b.status_code == 404, get_b.text
    assert post_b.status_code == 404, post_b.text
