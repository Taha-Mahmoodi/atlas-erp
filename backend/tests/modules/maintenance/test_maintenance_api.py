"""Maintenance HTTP behaviour (PLAN 9.2, D-051): equipment / order / plan endpoints over the wire,
RBAC (read vs manage vs complete vs plan.run), pagination, the ≤3-query list budgets (PERFORMANCE
§6), the conditional-GET ETag on the equipment + plan reference lists, tenant isolation, the
run-preventive endpoint, and idempotency on the order create + complete.

Driven against a real bearer-token client whose tenant has a seeded cost centre + ACTIVE equipment.
"""

import uuid
from collections.abc import Callable
from datetime import date, timedelta
from decimal import Decimal

from httpx import AsyncClient

from tests.conftest import QueryCounter, assert_query_budget
from tests.modules.maintenance.conftest import MaintenanceApi, MaintenancePrincipal

_MNT = "/api/v1/maintenance"


# --- Equipment endpoints ------------------------------------------------------


async def test_create_and_get_equipment(maintenance_client: AsyncClient) -> None:
    create = await maintenance_client.post(
        f"{_MNT}/equipment",
        json={"code": "EQ-API", "name": "Conveyor", "location": "Line 1"},
    )
    assert create.status_code == 201, create.text
    equipment_id = create.json()["id"]
    got = await maintenance_client.get(f"{_MNT}/equipment/{equipment_id}")
    assert got.status_code == 200
    assert got.json()["code"] == "EQ-API"
    assert got.json()["status"] == "ACTIVE"


async def test_list_equipment_filters_by_status(maintenance_api: MaintenanceApi) -> None:
    """The seeded ACTIVE equipment shows under an ACTIVE filter and is excluded by a RETIRED one."""
    active = await maintenance_api.client.get(
        f"{_MNT}/equipment", params={"status": "ACTIVE"}
    )
    assert active.status_code == 200
    assert len(active.json()["items"]) == 1
    retired = await maintenance_api.client.get(
        f"{_MNT}/equipment", params={"status": "RETIRED"}
    )
    assert retired.json()["items"] == []


# --- Maintenance-order endpoints ----------------------------------------------


async def test_order_lifecycle_over_the_wire(maintenance_api: MaintenanceApi) -> None:
    """Create (DRAFT) → schedule → start → complete with actual_cost, all over the wire."""
    setup = maintenance_api.setup
    create = await maintenance_api.client.post(
        f"{_MNT}/maintenance-orders",
        json={"equipment_id": str(setup.equipment_id), "description": "Repair motor"},
        headers={"Idempotency-Key": uuid.uuid4().hex},
    )
    assert create.status_code == 201, create.text
    order = create.json()
    assert order["status"] == "DRAFT"
    assert order["order_number"].startswith("MNT")
    order_id = order["id"]

    sched = await maintenance_api.client.post(
        f"{_MNT}/maintenance-orders/{order_id}/schedule",
        json={"scheduled_date": "2026-07-15"},
    )
    assert sched.status_code == 200
    assert sched.json()["status"] == "SCHEDULED"

    started = await maintenance_api.client.post(
        f"{_MNT}/maintenance-orders/{order_id}/start"
    )
    assert started.json()["status"] == "IN_PROGRESS"

    completed = await maintenance_api.client.post(
        f"{_MNT}/maintenance-orders/{order_id}/complete",
        json={"actual_cost": "99.99", "completed_date": "2026-07-16"},
        headers={"Idempotency-Key": uuid.uuid4().hex},
    )
    assert completed.status_code == 200
    body = completed.json()
    assert body["status"] == "COMPLETED"
    assert Decimal(body["actual_cost"]) == Decimal("99.99")  # MoneyType serialises at scale-6


async def test_order_against_inactive_equipment_422(maintenance_api: MaintenanceApi) -> None:
    """Creating an order against retired equipment is a 422 over the wire."""
    setup = maintenance_api.setup
    # Retire the equipment first.
    await maintenance_api.client.patch(
        f"{_MNT}/equipment/{setup.equipment_id}", json={"status": "RETIRED"}
    )
    resp = await maintenance_api.client.post(
        f"{_MNT}/maintenance-orders",
        json={"equipment_id": str(setup.equipment_id), "description": "x"},
        headers={"Idempotency-Key": uuid.uuid4().hex},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "maintenance.equipment_not_active"


async def test_order_create_idempotent(maintenance_api: MaintenanceApi) -> None:
    """Replaying create with the same Idempotency-Key returns the captured response (D-013)."""
    setup = maintenance_api.setup
    key = uuid.uuid4().hex
    body = {"equipment_id": str(setup.equipment_id), "description": "Once"}
    first = await maintenance_api.client.post(
        f"{_MNT}/maintenance-orders", json=body, headers={"Idempotency-Key": key}
    )
    assert first.status_code == 201, first.text
    replay = await maintenance_api.client.post(
        f"{_MNT}/maintenance-orders", json=body, headers={"Idempotency-Key": key}
    )
    assert replay.status_code in (200, 201)
    assert replay.json()["order_number"] == first.json()["order_number"]


# --- Plan endpoints + run -----------------------------------------------------


async def test_plan_crud_and_run_preventive(maintenance_api: MaintenanceApi) -> None:
    """Create a due plan, then the run-preventive endpoint generates one order and advances it."""
    setup = maintenance_api.setup
    start = (date.today() - timedelta(days=2)).isoformat()
    create = await maintenance_api.client.post(
        f"{_MNT}/maintenance-plans",
        json={
            "code": "MP-API",
            "name": "Daily check",
            "equipment_id": str(setup.equipment_id),
            "interval_value": 1,
            "interval_unit": "DAYS",
            "task_description": "Inspect",
            "start_date": start,
        },
    )
    assert create.status_code == 201, create.text

    run = await maintenance_api.client.post(
        f"{_MNT}/maintenance-plans/run-preventive",
        headers={"Idempotency-Key": uuid.uuid4().hex},
    )
    assert run.status_code == 200, run.text
    result = run.json()
    assert result["plans_due"] == 1
    assert len(result["orders_generated"]) == 1
    assert result["orders_generated"][0]["order_type"] == "PREVENTIVE"


async def test_run_preventive_with_as_of(maintenance_api: MaintenanceApi) -> None:
    """The run honours an explicit ?as_of= and is naturally idempotent on a second call."""
    setup = maintenance_api.setup
    await maintenance_api.client.post(
        f"{_MNT}/maintenance-plans",
        json={
            "code": "MP-ASOF",
            "name": "Monthly",
            "equipment_id": str(setup.equipment_id),
            "interval_value": 1,
            "interval_unit": "MONTHS",
            "task_description": "Service",
            "start_date": "2026-01-01",
        },
    )
    first = await maintenance_api.client.post(
        f"{_MNT}/maintenance-plans/run-preventive",
        params={"as_of": "2026-02-01"},
        headers={"Idempotency-Key": uuid.uuid4().hex},
    )
    assert first.json()["plans_due"] == 1
    second = await maintenance_api.client.post(
        f"{_MNT}/maintenance-plans/run-preventive",
        params={"as_of": "2026-02-01"},
        headers={"Idempotency-Key": uuid.uuid4().hex},
    )
    assert second.json()["plans_due"] == 0  # naturally idempotent


# --- RBAC ---------------------------------------------------------------------


async def _login_with(
    client: AsyncClient,
    factory: Callable[..., object],
    keys: tuple[str, ...],
) -> MaintenancePrincipal:
    principal: MaintenancePrincipal = await factory(keys=keys)
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": principal.tenant_slug,
            "email": principal.email,
            "password": principal.password,
        },
    )
    client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
    return principal


async def test_read_requires_permission(
    client: AsyncClient, maintenance_user_factory: Callable[..., object]
) -> None:
    """A principal without maintenance.equipment.read cannot list equipment (403)."""
    await _login_with(client, maintenance_user_factory, keys=())
    resp = await client.get(f"{_MNT}/equipment")
    assert resp.status_code == 403


async def test_complete_requires_complete_permission(
    client: AsyncClient,
    db_session,
    maintenance_user_factory: Callable[..., object],
) -> None:
    """A principal with order.manage but NOT order.complete cannot complete an order (403) — the
    distinct authority (D-051)."""
    from tests.modules.maintenance.factories import (
        build_corrective_order,
        build_maintenance_setup,
    )

    principal: MaintenancePrincipal = await maintenance_user_factory(
        keys=("maintenance.order.read", "maintenance.order.manage")
    )
    setup = await build_maintenance_setup(db_session, principal.tenant_id)
    order = await build_corrective_order(
        db_session,
        principal.tenant_id,
        equipment_id=setup.equipment_id,
        scheduled_date=date(2026, 5, 1),
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
    resp = await client.post(
        f"{_MNT}/maintenance-orders/{order.id}/complete",
        json={"actual_cost": "10"},
        headers={"Idempotency-Key": uuid.uuid4().hex},
    )
    assert resp.status_code == 403


async def test_run_requires_run_permission(
    client: AsyncClient, maintenance_user_factory: Callable[..., object]
) -> None:
    """A principal with plan.read+manage but NOT plan.run cannot run the generator (403)."""
    await _login_with(
        client,
        maintenance_user_factory,
        keys=("maintenance.plan.read", "maintenance.plan.manage"),
    )
    resp = await client.post(
        f"{_MNT}/maintenance-plans/run-preventive",
        headers={"Idempotency-Key": uuid.uuid4().hex},
    )
    assert resp.status_code == 403


# --- Tenant isolation ---------------------------------------------------------


async def test_tenant_isolation(
    maintenance_api: MaintenanceApi, maintenance_client_b: AsyncClient
) -> None:
    """Tenant B cannot see (or read) tenant A's equipment."""
    equipment_id = maintenance_api.setup.equipment_id
    list_resp = await maintenance_client_b.get(f"{_MNT}/equipment")
    assert list_resp.status_code == 200
    assert list_resp.json()["items"] == []
    get_resp = await maintenance_client_b.get(f"{_MNT}/equipment/{equipment_id}")
    assert get_resp.status_code == 404


# --- ETag + performance -------------------------------------------------------


async def test_equipment_list_etag(maintenance_api: MaintenanceApi) -> None:
    """The equipment list returns a weak ETag; a matching If-None-Match yields 304 (D-035)."""
    first = await maintenance_api.client.get(f"{_MNT}/equipment")
    etag = first.headers.get("etag")
    assert etag is not None
    cached = await maintenance_api.client.get(
        f"{_MNT}/equipment", headers={"If-None-Match": etag}
    )
    assert cached.status_code == 304


async def test_plan_list_etag(maintenance_api: MaintenanceApi) -> None:
    """The plan list returns a weak ETag; a matching If-None-Match yields 304 (D-035)."""
    first = await maintenance_api.client.get(f"{_MNT}/maintenance-plans")
    etag = first.headers.get("etag")
    assert etag is not None
    cached = await maintenance_api.client.get(
        f"{_MNT}/maintenance-plans", headers={"If-None-Match": etag}
    )
    assert cached.status_code == 304


async def test_equipment_list_query_budget(
    maintenance_api: MaintenanceApi,
    query_counter: Callable[[], QueryCounter],
) -> None:
    await assert_query_budget(
        maintenance_api.client, query_counter, f"{_MNT}/equipment", budget=3
    )


async def test_order_list_query_budget(
    maintenance_api: MaintenanceApi,
    query_counter: Callable[[], QueryCounter],
) -> None:
    await assert_query_budget(
        maintenance_api.client, query_counter, f"{_MNT}/maintenance-orders", budget=3
    )


async def test_plan_list_query_budget(
    maintenance_api: MaintenanceApi,
    query_counter: Callable[[], QueryCounter],
) -> None:
    await assert_query_budget(
        maintenance_api.client, query_counter, f"{_MNT}/maintenance-plans", budget=3
    )
