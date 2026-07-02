"""Procurement HTTP layer (PLAN 6.1): vendor + approved-item endpoints, RBAC, pagination, the
query budget (≤3), ETag on the vendor list, and tenant isolation.

Cross-module setup goes through the API itself: a currency is created via the finance endpoint
(the vendor's default_currency_code validates against it) and an item via the inventory endpoints
(an approved item points at it) — so the tests exercise the real router -> service -> uow path and
the D-029 cross-module reads end to end. The full-rights principal carries the finance/inventory
setup keys for exactly this scaffolding.
"""

import uuid

import pytest
from httpx import AsyncClient

from tests.conftest import assert_query_budget

_VENDORS_URL = "/api/v1/procurement/vendors"


async def _seed_currency(client: AsyncClient, code: str = "USD") -> None:
    response = await client.post(
        "/api/v1/finance/currencies", json={"code": code, "name": code}
    )
    assert response.status_code == 201, response.text


async def _seed_item(client: AsyncClient, *, item_code: str = "ITEM-1") -> str:
    """Create a UoM + category + item over the wire, returning the item id."""
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


async def _create_vendor(
    client: AsyncClient, *, vendor_code: str = "V-001", currency: str = "USD"
) -> str:
    response = await client.post(
        _VENDORS_URL,
        json={"vendor_code": vendor_code, "name": "Acme", "default_currency_code": currency},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


# --- CRUD round-trip -----------------------------------------------------------


async def test_vendor_crud_round_trip(procurement_client: AsyncClient) -> None:
    """Create a currency + vendor, read it back, and PATCH status over the wire."""
    await _seed_currency(procurement_client)
    vendor_id = await _create_vendor(procurement_client)

    got = await procurement_client.get(f"{_VENDORS_URL}/{vendor_id}")
    assert got.status_code == 200
    body = got.json()
    assert body["vendor_code"] == "V-001"
    assert body["status"] == "ACTIVE"
    assert body["payment_terms_days"] == 30

    patched = await procurement_client.patch(
        f"{_VENDORS_URL}/{vendor_id}", json={"status": "BLOCKED", "payment_terms_days": 14}
    )
    assert patched.status_code == 200
    assert patched.json()["status"] == "BLOCKED"
    assert patched.json()["payment_terms_days"] == 14


async def test_create_vendor_unknown_currency_422(procurement_client: AsyncClient) -> None:
    """A vendor whose currency is not in finance is rejected with the cross-module error code."""
    response = await procurement_client.post(
        _VENDORS_URL,
        json={"vendor_code": "V-EUR", "name": "Euro", "default_currency_code": "EUR"},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "procurement.currency_not_found"


async def test_vendor_list_filtered_by_status(procurement_client: AsyncClient) -> None:
    """The vendor list filters by status — only matching rows come back."""
    await _seed_currency(procurement_client)
    await _create_vendor(procurement_client, vendor_code="V-A")
    blocked_id = await _create_vendor(procurement_client, vendor_code="V-B")
    await procurement_client.patch(
        f"{_VENDORS_URL}/{blocked_id}", json={"status": "BLOCKED"}
    )

    response = await procurement_client.get(f"{_VENDORS_URL}?status=BLOCKED")
    assert response.status_code == 200
    vendors = response.json()["items"]
    assert len(vendors) == 1
    assert vendors[0]["vendor_code"] == "V-B"


# --- Approved items (nested) ---------------------------------------------------


async def test_approved_item_endpoints(procurement_client: AsyncClient) -> None:
    """POST/GET/DELETE the nested approved-items resource."""
    await _seed_currency(procurement_client)
    item_id = await _seed_item(procurement_client)
    vendor_id = await _create_vendor(procurement_client)

    created = await procurement_client.post(
        f"{_VENDORS_URL}/{vendor_id}/approved-items",
        json={"item_id": item_id, "vendor_item_code": "SUP-9"},
    )
    assert created.status_code == 201, created.text
    assert created.json()["vendor_item_code"] == "SUP-9"

    listed = await procurement_client.get(f"{_VENDORS_URL}/{vendor_id}/approved-items")
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    deleted = await procurement_client.delete(
        f"{_VENDORS_URL}/{vendor_id}/approved-items/{item_id}"
    )
    assert deleted.status_code == 204
    after = await procurement_client.get(f"{_VENDORS_URL}/{vendor_id}/approved-items")
    assert after.json() == []


async def test_approve_unknown_item_422(procurement_client: AsyncClient) -> None:
    await _seed_currency(procurement_client)
    vendor_id = await _create_vendor(procurement_client)
    response = await procurement_client.post(
        f"{_VENDORS_URL}/{vendor_id}/approved-items",
        json={"item_id": str(uuid.uuid4())},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "procurement.item_not_found"


# --- Performance: query budget + ETag ------------------------------------------


async def test_vendor_list_query_budget(
    procurement_client: AsyncClient,
    query_counter,  # noqa: ANN001 - fixture factory typed in conftest
) -> None:
    """The vendor list stays within the PERFORMANCE §2 N+1 budget (≤3 on the warm path)."""
    await assert_query_budget(procurement_client, query_counter, _VENDORS_URL)


async def test_vendor_list_returns_etag_and_304(procurement_client: AsyncClient) -> None:
    """The vendor reference list returns 200 + ETag; an If-None-Match re-GET returns 304."""
    first = await procurement_client.get(_VENDORS_URL)
    assert first.status_code == 200, first.text
    etag = first.headers.get("etag")
    assert etag is not None and etag.startswith('W/"'), first.headers
    again = await procurement_client.get(_VENDORS_URL, headers={"If-None-Match": etag})
    assert again.status_code == 304
    assert again.content == b""


async def test_creating_vendor_invalidates_etag(procurement_client: AsyncClient) -> None:
    await _seed_currency(procurement_client)
    first = await procurement_client.get(_VENDORS_URL)
    etag = first.headers["etag"]
    await _create_vendor(procurement_client)
    after = await procurement_client.get(_VENDORS_URL, headers={"If-None-Match": etag})
    assert after.status_code == 200
    assert after.headers["etag"] != etag


# --- RBAC ----------------------------------------------------------------------


async def test_manage_requires_permission(
    procurement_client: AsyncClient, procurement_user_factory
) -> None:  # noqa: ANN001
    """A principal holding only the READ key cannot create — 403 permission_denied."""
    read_only = await procurement_user_factory(
        slug="proc-ro",
        email="ro@proc-ro.test",
        keys=("procurement.vendor.read",),
    )
    login = await procurement_client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": read_only.tenant_slug,
            "email": read_only.email,
            "password": read_only.password,
        },
    )
    token = login.json()["access_token"]
    response = await procurement_client.post(
        _VENDORS_URL,
        json={"vendor_code": "V-X", "name": "X", "default_currency_code": "USD"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "rbac.permission_denied"


async def test_read_requires_authentication(client: AsyncClient) -> None:
    """No bearer token → 401 (the endpoints are permission-guarded)."""
    response = await client.get(_VENDORS_URL)
    assert response.status_code == 401


# --- Tenant isolation ----------------------------------------------------------


async def test_vendors_are_tenant_isolated(
    procurement_client: AsyncClient, procurement_client_b: AsyncClient
) -> None:
    """Tenant B never sees tenant A's vendors, and A's vendor id 404s for B (D-007)."""
    await _seed_currency(procurement_client)
    vendor_id = await _create_vendor(procurement_client)

    b_list = await procurement_client_b.get(_VENDORS_URL)
    assert b_list.status_code == 200
    assert b_list.json()["items"] == []

    b_get = await procurement_client_b.get(f"{_VENDORS_URL}/{vendor_id}")
    assert b_get.status_code == 404


async def test_cross_tenant_write_does_not_invalidate_etag(
    procurement_client: AsyncClient, procurement_client_b: AsyncClient
) -> None:
    """A write in tenant B must NOT invalidate tenant A's collection ETag (validator is
    tenant-scoped)."""
    a_first = await procurement_client.get(_VENDORS_URL)
    a_etag = a_first.headers["etag"]
    await _seed_currency(procurement_client_b)
    await _create_vendor(procurement_client_b, vendor_code="B-1")
    a_again = await procurement_client.get(_VENDORS_URL, headers={"If-None-Match": a_etag})
    assert a_again.status_code == 304


@pytest.mark.parametrize("payment_terms_days", [0, 30, 365])
async def test_payment_terms_accepts_non_negative(
    procurement_client: AsyncClient, payment_terms_days: int
) -> None:
    """payment_terms_days >= 0 is accepted (0 = due on receipt)."""
    await _seed_currency(procurement_client)
    response = await procurement_client.post(
        _VENDORS_URL,
        json={
            "vendor_code": f"V-{payment_terms_days}",
            "name": "Terms",
            "default_currency_code": "USD",
            "payment_terms_days": payment_terms_days,
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["payment_terms_days"] == payment_terms_days
