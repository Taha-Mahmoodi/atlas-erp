"""Inventory HTTP layer (PLAN 5.1): CRUD endpoints, RBAC, pagination, query budget (≤3), ETag on
the reference lists, and tenant isolation.

The data setup goes through the API itself (creating a UoM + category first) so the tests exercise
the real router -> service -> uow path end to end.
"""


import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import API_KEY_PREFIX, mint_api_key
from app.core.models import ApiKey
from app.core.tenancy import tenant_context
from tests.conftest import assert_query_budget
from tests.modules.inventory.factories import InventoryPrincipal

_REFERENCE_ENDPOINTS = (
    "/api/v1/inventory/item-categories",
    "/api/v1/inventory/uoms",
    "/api/v1/inventory/items",
)


async def _create_uom(client: AsyncClient, code: str = "EA") -> str:
    response = await client.post("/api/v1/inventory/uoms", json={"code": code, "name": code})
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _create_category(client: AsyncClient, code: str = "CAT-1") -> str:
    response = await client.post(
        "/api/v1/inventory/item-categories", json={"code": code, "name": "Category"}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _create_item(
    client: AsyncClient, category_id: str, base_uom_id: str, *, item_code: str = "ITEM-1"
) -> str:
    response = await client.post(
        "/api/v1/inventory/items",
        json={
            "item_code": item_code,
            "name": "An item",
            "item_type": "STOCKED",
            "category_id": category_id,
            "base_uom_id": base_uom_id,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def test_item_crud_round_trip(inventory_client: AsyncClient) -> None:
    """Create a UoM + category + item, read it back, and PATCH a field over the wire."""
    uom_id = await _create_uom(inventory_client)
    category_id = await _create_category(inventory_client)
    item_id = await _create_item(inventory_client, category_id, uom_id)

    got = await inventory_client.get(f"/api/v1/inventory/items/{item_id}")
    assert got.status_code == 200
    body = got.json()
    assert body["item_code"] == "ITEM-1"
    # costing_method defaulted from the category (MOVING_AVERAGE) and serialized as its string.
    assert body["costing_method"] == "MOVING_AVERAGE"

    patched = await inventory_client.patch(
        f"/api/v1/inventory/items/{item_id}", json={"name": "Renamed"}
    )
    assert patched.status_code == 200
    assert patched.json()["name"] == "Renamed"


async def test_nested_uom_conversion_endpoints(inventory_client: AsyncClient) -> None:
    """POST/GET /items/{id}/uom-conversions add and list an alternate UoM."""
    ea_id = await _create_uom(inventory_client, "EA")
    box_id = await _create_uom(inventory_client, "BOX")
    category_id = await _create_category(inventory_client)
    item_id = await _create_item(inventory_client, category_id, ea_id)

    created = await inventory_client.post(
        f"/api/v1/inventory/items/{item_id}/uom-conversions",
        json={"alt_uom_id": box_id, "factor_to_base": "12"},
    )
    assert created.status_code == 201, created.text
    assert created.json()["factor_to_base"] == "12.000000"

    listed = await inventory_client.get(f"/api/v1/inventory/items/{item_id}/uom-conversions")
    assert listed.status_code == 200
    assert len(listed.json()) == 1


async def test_items_filtered_list(inventory_client: AsyncClient) -> None:
    """The items list filters by type — only matching rows come back."""
    ea_id = await _create_uom(inventory_client)
    category_id = await _create_category(inventory_client)
    await _create_item(inventory_client, category_id, ea_id, item_code="STK-1")
    service_item = await inventory_client.post(
        "/api/v1/inventory/items",
        json={
            "item_code": "SVC-1",
            "name": "Service",
            "item_type": "SERVICE",
            "category_id": category_id,
            "base_uom_id": ea_id,
        },
    )
    assert service_item.status_code == 201

    response = await inventory_client.get("/api/v1/inventory/items?item_type=SERVICE")
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["item_code"] == "SVC-1"


@pytest.mark.parametrize("url", _REFERENCE_ENDPOINTS)
async def test_list_query_budget(
    inventory_client: AsyncClient,
    query_counter,  # noqa: ANN001 - fixture factory typed in conftest
    url: str,
) -> None:
    """Every list endpoint stays within the PERFORMANCE §2 N+1 budget (≤3 on the warm path)."""
    await assert_query_budget(inventory_client, query_counter, url)


async def test_reference_lists_return_etag_and_304(inventory_client: AsyncClient) -> None:
    """Each reference list returns 200 + ETag; an If-None-Match re-GET returns 304, empty body."""
    for url in _REFERENCE_ENDPOINTS:
        first = await inventory_client.get(url)
        assert first.status_code == 200, first.text
        etag = first.headers.get("etag")
        assert etag is not None and etag.startswith('W/"'), first.headers
        again = await inventory_client.get(url, headers={"If-None-Match": etag})
        assert again.status_code == 304, f"{url}: {again.text}"
        assert again.content == b""


async def test_creating_item_invalidates_items_etag(inventory_client: AsyncClient) -> None:
    ea_id = await _create_uom(inventory_client)
    category_id = await _create_category(inventory_client)
    url = "/api/v1/inventory/items"
    first = await inventory_client.get(url)
    etag = first.headers["etag"]
    await _create_item(inventory_client, category_id, ea_id)
    after = await inventory_client.get(url, headers={"If-None-Match": etag})
    assert after.status_code == 200
    assert after.headers["etag"] != etag


async def test_304_path_is_cheaper_than_200(
    inventory_client: AsyncClient, query_counter
) -> None:  # noqa: ANN001
    """The 304 path skips the page query — it runs strictly fewer statements than the 200 path."""
    url = "/api/v1/inventory/items"
    first = await inventory_client.get(url)  # warm the RBAC cache + get the tag
    etag = first.headers["etag"]
    with query_counter() as qc_200:
        await inventory_client.get(url)
    with query_counter() as qc_304:
        not_modified = await inventory_client.get(url, headers={"If-None-Match": etag})
    assert not_modified.status_code == 304
    assert qc_304.count < qc_200.count


# --- RBAC -----------------------------------------------------------------


async def test_manage_requires_permission(
    inventory_client: AsyncClient, inventory_user_factory
) -> None:  # noqa: ANN001
    """A principal holding only the READ keys cannot create — 403 permission_denied."""
    read_only = await inventory_user_factory(
        slug="inv-ro",
        email="ro@inv-ro.test",
        keys=("inventory.item.read", "inventory.category.read", "inventory.uom.read"),
    )
    login = await inventory_client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": read_only.tenant_slug,
            "email": read_only.email,
            "password": read_only.password,
        },
    )
    token = login.json()["access_token"]
    response = await inventory_client.post(
        "/api/v1/inventory/uoms",
        json={"code": "EA", "name": "Each"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "rbac.permission_denied"


async def test_read_requires_authentication(client: AsyncClient) -> None:
    """No bearer token → 401 (the endpoints are permission-guarded)."""
    response = await client.get("/api/v1/inventory/items")
    assert response.status_code == 401


# --- Tenant isolation ---------------------------------------------------------


async def test_items_are_tenant_isolated(
    inventory_client: AsyncClient, inventory_client_b: AsyncClient
) -> None:
    """Tenant B never sees tenant A's items, and tenant A's item id 404s for tenant B (D-007)."""
    ea_id = await _create_uom(inventory_client)
    category_id = await _create_category(inventory_client)
    item_id = await _create_item(inventory_client, category_id, ea_id)

    b_list = await inventory_client_b.get("/api/v1/inventory/items")
    assert b_list.status_code == 200
    assert b_list.json()["items"] == []

    b_get = await inventory_client_b.get(f"/api/v1/inventory/items/{item_id}")
    assert b_get.status_code == 404


async def test_cross_tenant_write_does_not_invalidate_etag(
    inventory_client: AsyncClient, inventory_client_b: AsyncClient
) -> None:
    """A write in tenant B must NOT invalidate tenant A's collection ETag (the validator is
    tenant-scoped)."""
    url = "/api/v1/inventory/uoms"
    a_first = await inventory_client.get(url)
    a_etag = a_first.headers["etag"]
    # Tenant B creates a UoM.
    await inventory_client_b.post(url, json={"code": "KG", "name": "Kilogram"})
    a_again = await inventory_client.get(url, headers={"If-None-Match": a_etag})
    assert a_again.status_code == 304


async def _api_key_client(
    client: AsyncClient,
    db_session: AsyncSession,
    principal: InventoryPrincipal,
) -> AsyncClient:
    """Swap the client's bearer for a machine API key bound to the same principal, so the
    SAME endpoints can be measured under both credential shapes (spec Q1 / D-069)."""
    full, digest = mint_api_key(principal.tenant_id)
    with tenant_context(principal.tenant_id):
        db_session.add(
            ApiKey(
                user_id=principal.user_id,
                name="website",
                prefix=f"{API_KEY_PREFIX}_{principal.tenant_id.hex}",
                secret_sha256=digest,
                scopes=None,
            )
        )
        await db_session.commit()
    client.headers["Authorization"] = f"Bearer {full}"
    return client


@pytest.mark.parametrize("url", _REFERENCE_ENDPOINTS)
async def test_list_query_budget_under_api_key_auth(
    client: AsyncClient,
    db_session: AsyncSession,
    inventory_user_factory,  # noqa: ANN001 - fixture factory typed in the module conftest
    query_counter,  # noqa: ANN001 - fixture factory typed in conftest
    url: str,
) -> None:
    """PERFORMANCE §2 holds for the OTHER credential shape too (spec Q1 / D-069).

    These endpoints compute a collection ETag, so their warm path is already 3 statements
    under a JWT — auth + the ETag aggregate + the page — with zero slack. That is exactly
    where a per-request tenant lookup in the API-key branch showed up: it made every one of
    them 4, a real breach that /api/v1/admin/users (no ETag) could not see. The key now
    carries the tenant UUID, so authentication costs the same one statement a JWT costs.
    """
    principal = await inventory_user_factory()
    key_client = await _api_key_client(client, db_session, principal)

    await assert_query_budget(key_client, query_counter, url)
