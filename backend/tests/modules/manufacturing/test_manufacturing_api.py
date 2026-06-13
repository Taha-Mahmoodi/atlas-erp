"""Manufacturing HTTP tests (PLAN 8.1): work-centre / BOM / routing endpoints over the wire, the
nested component/operation sub-resources, the activate/deactivate actions, RBAC (read vs manage),
pagination, the ≤3 query budget, the conditional-GET ETag on the reference lists, and tenant
isolation.

Cross-module scaffolding (a UoM + category + items) goes through the API itself — the full-rights
principal carries the inventory setup keys — so the tests exercise the real router → service → uow
path and the D-029 opaque-id reads end to end.
"""

from collections.abc import Callable

from httpx import AsyncClient

from tests.conftest import QueryCounter, assert_query_budget

_MFG = "/api/v1/manufacturing"


async def _seed_scaffold(client: AsyncClient) -> tuple[str, str]:
    """Create a shared UoM + category over the wire; return (uom_id, category_id)."""
    uom = await client.post("/api/v1/inventory/uoms", json={"code": "EA", "name": "Each"})
    assert uom.status_code == 201, uom.text
    category = await client.post(
        "/api/v1/inventory/item-categories", json={"code": "CAT-1", "name": "Cat"}
    )
    assert category.status_code == 201, category.text
    return uom.json()["id"], category.json()["id"]


async def _seed_item(
    client: AsyncClient, *, item_code: str, uom_id: str, category_id: str
) -> str:
    """Create one inventory item over the wire; return its id."""
    item = await client.post(
        "/api/v1/inventory/items",
        json={
            "item_code": item_code,
            "name": "An item",
            "item_type": "STOCKED",
            "category_id": category_id,
            "base_uom_id": uom_id,
        },
    )
    assert item.status_code == 201, item.text
    return item.json()["id"]


async def _seed_parent_and_component(client: AsyncClient) -> tuple[str, str, str]:
    """Parent + component items sharing one UoM; return (parent_id, component_id, uom_id)."""
    uom_id, category_id = await _seed_scaffold(client)
    parent_id = await _seed_item(
        client, item_code="FG-API", uom_id=uom_id, category_id=category_id
    )
    component_id = await _seed_item(
        client, item_code="RM-API", uom_id=uom_id, category_id=category_id
    )
    return parent_id, component_id, uom_id


# --- Work centres -------------------------------------------------------------


async def test_work_center_crud(mfg_client: AsyncClient) -> None:
    created = await mfg_client.post(
        f"{_MFG}/work-centers",
        json={"code": "WC-1", "name": "Line 1", "capacity_hours_per_day": "8"},
    )
    assert created.status_code == 201, created.text
    wc_id = created.json()["id"]
    assert created.json()["capacity_hours_per_day"] == "8.000000"

    fetched = await mfg_client.get(f"{_MFG}/work-centers/{wc_id}")
    assert fetched.status_code == 200

    patched = await mfg_client.patch(
        f"{_MFG}/work-centers/{wc_id}", json={"name": "Line 1 renamed"}
    )
    assert patched.status_code == 200
    assert patched.json()["name"] == "Line 1 renamed"


async def test_bom_lifecycle_over_the_wire(mfg_client: AsyncClient) -> None:
    parent_id, component_id, uom_id = await _seed_parent_and_component(mfg_client)
    bom = await mfg_client.post(
        f"{_MFG}/boms",
        json={"item_id": parent_id, "version": "1", "name": "BOM 1", "uom_id": uom_id},
    )
    assert bom.status_code == 201, bom.text
    bom_id = bom.json()["id"]
    assert bom.json()["status"] == "DRAFT"

    # activation requires a component
    no_comp = await mfg_client.post(f"{_MFG}/boms/{bom_id}/activate")
    assert no_comp.status_code == 422
    assert no_comp.json()["error"]["code"] == "manufacturing.bom_no_components"

    comp = await mfg_client.post(
        f"{_MFG}/boms/{bom_id}/components",
        json={"component_item_id": component_id, "uom_id": uom_id, "quantity_per": "2"},
    )
    assert comp.status_code == 201, comp.text

    listed = await mfg_client.get(f"{_MFG}/boms/{bom_id}/components")
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    activated = await mfg_client.post(f"{_MFG}/boms/{bom_id}/activate")
    assert activated.status_code == 200
    assert activated.json()["status"] == "ACTIVE"
    assert activated.json()["is_default"] is True

    # frozen once active
    frozen = await mfg_client.post(
        f"{_MFG}/boms/{bom_id}/components",
        json={"component_item_id": component_id, "uom_id": uom_id, "quantity_per": "1"},
    )
    assert frozen.status_code == 409


async def test_self_component_rejected_over_the_wire(mfg_client: AsyncClient) -> None:
    parent_id, _component_id, uom_id = await _seed_parent_and_component(mfg_client)
    bom = await mfg_client.post(
        f"{_MFG}/boms",
        json={"item_id": parent_id, "version": "1", "name": "BOM", "uom_id": uom_id},
    )
    bom_id = bom.json()["id"]
    response = await mfg_client.post(
        f"{_MFG}/boms/{bom_id}/components",
        json={"component_item_id": parent_id, "uom_id": uom_id, "quantity_per": "1"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "manufacturing.bom_self_component"


async def test_routing_lifecycle_over_the_wire(mfg_client: AsyncClient) -> None:
    parent_id, _component_id, _uom_id = await _seed_parent_and_component(mfg_client)
    wc = await mfg_client.post(
        f"{_MFG}/work-centers", json={"code": "WC-R", "name": "WC"}
    )
    wc_id = wc.json()["id"]
    routing = await mfg_client.post(
        f"{_MFG}/routings", json={"item_id": parent_id, "version": "1", "name": "R1"}
    )
    assert routing.status_code == 201, routing.text
    routing_id = routing.json()["id"]

    op = await mfg_client.post(
        f"{_MFG}/routings/{routing_id}/operations",
        json={
            "work_center_id": wc_id,
            "setup_time_minutes": "30",
            "run_time_minutes_per_unit": "5",
        },
    )
    assert op.status_code == 201, op.text
    assert op.json()["operation_number"] == 10

    activated = await mfg_client.post(f"{_MFG}/routings/{routing_id}/activate")
    assert activated.status_code == 200
    assert activated.json()["status"] == "ACTIVE"

    deactivated = await mfg_client.post(f"{_MFG}/routings/{routing_id}/deactivate")
    assert deactivated.status_code == 200
    assert deactivated.json()["status"] == "INACTIVE"


# --- RBAC ---------------------------------------------------------------------


async def test_manage_requires_permission(
    client: AsyncClient, mfg_user_factory: Callable[..., object]
) -> None:
    """A read-only principal can list but not create a work centre (403)."""
    principal = await mfg_user_factory(
        slug="mfg-ro", email="ro@mfg.test", keys=("manufacturing.workcenter.read",)
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": principal.tenant_slug,
            "email": principal.email,
            "password": principal.password,
        },
    )
    client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"

    listed = await client.get(f"{_MFG}/work-centers")
    assert listed.status_code == 200

    created = await client.post(f"{_MFG}/work-centers", json={"code": "X", "name": "X"})
    assert created.status_code == 403
    assert created.json()["error"]["code"] == "rbac.permission_denied"


# --- Pagination + budget + ETag ----------------------------------------------


async def test_work_center_list_paginates_and_budget(
    mfg_client: AsyncClient, query_counter: Callable[[], QueryCounter]
) -> None:
    for i in range(3):
        response = await mfg_client.post(
            f"{_MFG}/work-centers", json={"code": f"WC-{i}", "name": f"WC {i}"}
        )
        assert response.status_code == 201

    page = await mfg_client.get(f"{_MFG}/work-centers?limit=2")
    assert page.status_code == 200
    body = page.json()
    assert len(body["items"]) == 2
    assert body["next_cursor"] is not None

    await assert_query_budget(mfg_client, query_counter, f"{_MFG}/work-centers", budget=3)


async def test_bom_list_query_budget(
    mfg_client: AsyncClient, query_counter: Callable[[], QueryCounter]
) -> None:
    parent_id, _component_id, uom_id = await _seed_parent_and_component(mfg_client)
    for v in ("1", "2", "3"):
        response = await mfg_client.post(
            f"{_MFG}/boms",
            json={"item_id": parent_id, "version": v, "name": f"BOM {v}", "uom_id": uom_id},
        )
        assert response.status_code == 201
    await assert_query_budget(mfg_client, query_counter, f"{_MFG}/boms", budget=3)


async def test_work_center_list_etag(mfg_client: AsyncClient) -> None:
    await mfg_client.post(f"{_MFG}/work-centers", json={"code": "WC-E", "name": "WC"})
    first = await mfg_client.get(f"{_MFG}/work-centers")
    assert first.status_code == 200
    etag = first.headers.get("etag")
    assert etag is not None
    cached = await mfg_client.get(f"{_MFG}/work-centers", headers={"If-None-Match": etag})
    assert cached.status_code == 304


# --- Tenant isolation ---------------------------------------------------------


async def test_tenant_isolation(
    mfg_client: AsyncClient, mfg_client_b: AsyncClient
) -> None:
    """A work centre created in tenant A is invisible to tenant B."""
    created = await mfg_client.post(
        f"{_MFG}/work-centers", json={"code": "WC-A", "name": "A only"}
    )
    wc_id = created.json()["id"]

    b_get = await mfg_client_b.get(f"{_MFG}/work-centers/{wc_id}")
    assert b_get.status_code == 404

    b_list = await mfg_client_b.get(f"{_MFG}/work-centers")
    assert all(item["id"] != wc_id for item in b_list.json()["items"])
