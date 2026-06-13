"""Sales customer + customer-group HTTP tests (PLAN 7.1): CRUD over the wire, RBAC, pagination, the
query budget (≤3), ETag on the customer + group lists, and tenant isolation.

Cross-module setup goes through the API itself: a currency is created via the finance endpoint (the
customer's default_currency_code validates against it) — so the tests exercise the real router ->
service -> uow path and the D-029 cross-module read end to end. The full-rights principal carries
the
finance setup key for exactly this scaffolding.
"""

from collections.abc import Callable

from httpx import AsyncClient

from tests.conftest import QueryCounter, assert_query_budget

_CUSTOMERS_URL = "/api/v1/sales/customers"
_GROUPS_URL = "/api/v1/sales/customer-groups"


async def _seed_currency(client: AsyncClient, code: str = "USD") -> None:
    response = await client.post(
        "/api/v1/finance/currencies", json={"code": code, "name": code}
    )
    assert response.status_code == 201, response.text


async def _create_customer(
    client: AsyncClient, *, customer_code: str = "C-001", currency: str = "USD"
) -> str:
    response = await client.post(
        _CUSTOMERS_URL,
        json={
            "customer_code": customer_code,
            "name": "Acme",
            "default_currency_code": currency,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


# --- CRUD round-trip -----------------------------------------------------------


async def test_customer_crud_round_trip(sales_client: AsyncClient) -> None:
    await _seed_currency(sales_client)
    customer_id = await _create_customer(sales_client)

    got = await sales_client.get(f"{_CUSTOMERS_URL}/{customer_id}")
    assert got.status_code == 200
    body = got.json()
    assert body["customer_code"] == "C-001"
    assert body["status"] == "ACTIVE"
    assert body["payment_terms_days"] == 30
    # MoneyType serializes at scale 6; 0 = cash-only default (D-043).
    assert body["credit_limit"] == "0.000000"

    patched = await sales_client.patch(
        f"{_CUSTOMERS_URL}/{customer_id}",
        json={"status": "BLOCKED", "credit_limit": "5000"},
    )
    assert patched.status_code == 200
    assert patched.json()["status"] == "BLOCKED"
    assert patched.json()["credit_limit"] == "5000.000000"


async def test_customer_group_crud_and_membership(sales_client: AsyncClient) -> None:
    await _seed_currency(sales_client)
    group = await sales_client.post(_GROUPS_URL, json={"code": "GRP-1", "name": "Wholesale"})
    assert group.status_code == 201, group.text
    group_id = group.json()["id"]

    created = await sales_client.post(
        _CUSTOMERS_URL,
        json={
            "customer_code": "C-001",
            "name": "Acme",
            "default_currency_code": "USD",
            "customer_group_id": group_id,
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["customer_group_id"] == group_id


async def test_unknown_currency_rejected(sales_client: AsyncClient) -> None:
    response = await sales_client.post(
        _CUSTOMERS_URL,
        json={"customer_code": "C-1", "name": "x", "default_currency_code": "EUR"},
    )
    assert response.status_code == 422, response.text


async def test_negative_credit_limit_rejected(sales_client: AsyncClient) -> None:
    await _seed_currency(sales_client)
    response = await sales_client.post(
        _CUSTOMERS_URL,
        json={
            "customer_code": "C-1",
            "name": "x",
            "default_currency_code": "USD",
            "credit_limit": "-1",
        },
    )
    assert response.status_code == 422, response.text


# --- Performance: query budget + ETag ------------------------------------------


async def test_customer_list_query_budget(
    sales_client: AsyncClient,
    query_counter: Callable[[], QueryCounter],
) -> None:
    await _seed_currency(sales_client)
    await _create_customer(sales_client)
    await assert_query_budget(sales_client, query_counter, _CUSTOMERS_URL)


async def test_customer_list_returns_etag_and_304(sales_client: AsyncClient) -> None:
    await _seed_currency(sales_client)
    await _create_customer(sales_client)
    first = await sales_client.get(_CUSTOMERS_URL)
    assert first.status_code == 200, first.text
    etag = first.headers["ETag"]
    again = await sales_client.get(_CUSTOMERS_URL, headers={"If-None-Match": etag})
    assert again.status_code == 304


async def test_group_list_returns_etag_and_304(sales_client: AsyncClient) -> None:
    await sales_client.post(_GROUPS_URL, json={"code": "GRP-1", "name": "Wholesale"})
    first = await sales_client.get(_GROUPS_URL)
    assert first.status_code == 200, first.text
    etag = first.headers["ETag"]
    again = await sales_client.get(_GROUPS_URL, headers={"If-None-Match": etag})
    assert again.status_code == 304


async def test_etag_invalidated_by_write(sales_client: AsyncClient) -> None:
    await _seed_currency(sales_client)
    await _create_customer(sales_client, customer_code="C-001")
    first = await sales_client.get(_CUSTOMERS_URL)
    etag = first.headers["ETag"]
    await _create_customer(sales_client, customer_code="C-002")
    after = await sales_client.get(_CUSTOMERS_URL, headers={"If-None-Match": etag})
    assert after.status_code == 200


async def test_status_filter(sales_client: AsyncClient) -> None:
    await _seed_currency(sales_client)
    c1 = await _create_customer(sales_client, customer_code="C-001")
    await sales_client.patch(f"{_CUSTOMERS_URL}/{c1}", json={"status": "BLOCKED"})
    await _create_customer(sales_client, customer_code="C-002")
    listed = await sales_client.get(f"{_CUSTOMERS_URL}?status=BLOCKED")
    assert listed.status_code == 200
    codes = [c["customer_code"] for c in listed.json()["items"]]
    assert codes == ["C-001"]


# --- RBAC + isolation ----------------------------------------------------------


async def test_read_key_cannot_write(
    sales_client: AsyncClient,
    sales_user_factory: Callable[..., object],
    client: AsyncClient,
) -> None:
    """A principal holding only the READ key cannot create — 403 permission_denied."""
    read_only = await sales_user_factory(
        slug="sales-ro", email="ro@sales-ro.test", keys=("sales.customer.read",)
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
        _CUSTOMERS_URL,
        json={"customer_code": "C-1", "name": "x", "default_currency_code": "USD"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "rbac.permission_denied"


async def test_unauthenticated_rejected(client: AsyncClient) -> None:
    response = await client.get(_CUSTOMERS_URL)
    assert response.status_code == 401


async def test_customers_are_tenant_isolated(
    sales_client: AsyncClient, sales_client_b: AsyncClient
) -> None:
    """Tenant B never sees tenant A's customers, and A's customer id 404s for B (D-007)."""
    await _seed_currency(sales_client)
    a_id = await _create_customer(sales_client)

    b_list = await sales_client_b.get(_CUSTOMERS_URL)
    assert b_list.status_code == 200
    assert b_list.json()["items"] == []

    b_get = await sales_client_b.get(f"{_CUSTOMERS_URL}/{a_id}")
    assert b_get.status_code == 404


async def test_cross_tenant_write_does_not_invalidate_etag(
    sales_client: AsyncClient, sales_client_b: AsyncClient
) -> None:
    """A write in tenant B must NOT invalidate tenant A's collection ETag (validator
    tenant-scoped)."""
    await _seed_currency(sales_client)
    await _create_customer(sales_client)
    a_first = await sales_client.get(_CUSTOMERS_URL)
    a_etag = a_first.headers["ETag"]

    await _seed_currency(sales_client_b)
    response = await sales_client_b.post(
        _CUSTOMERS_URL,
        json={"customer_code": "B-1", "name": "B", "default_currency_code": "USD"},
    )
    assert response.status_code == 201, response.text

    a_again = await sales_client.get(_CUSTOMERS_URL, headers={"If-None-Match": a_etag})
    assert a_again.status_code == 304
