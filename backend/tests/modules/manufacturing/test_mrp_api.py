"""MRP HTTP tests (PLAN 8.3, D-049): run-as-job (202 + job id → completes), the run/planned-order/
capacity reads, conversion (MAKE → production order; BUY → requisition), firm/cancel, idempotency,
RBAC, tenant isolation, pagination + query budgets.

The run is ALWAYS a background job (PERFORMANCE §3): POST returns 202 {job_id}; ``wait_for_jobs``
drives it to completion (the depreciation-job test pattern), then the run + planned orders +
capacity are read back. Drives the endpoints against the ``mrp_api`` fixture's fully-wired tenant.
"""

import uuid
from collections.abc import Callable

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.jobs import JobStatus, wait_for_jobs
from tests.conftest import QueryCounter, assert_query_budget
from tests.modules.manufacturing.conftest import MrpApi

pytestmark = pytest.mark.asyncio

_MFG = "/api/v1/manufacturing"


def _idem() -> dict[str, str]:
    return {"Idempotency-Key": str(uuid.uuid4())}


async def _run_to_completion(api: MrpApi, *, headers: dict[str, str] | None = None) -> dict:
    """POST the run (202 + job id), drive the job, return the COMPLETED job body."""
    accepted = await api.client.post(
        f"{_MFG}/mrp/runs", json={"run_date": "2026-06-01"}, headers=headers or _idem()
    )
    assert accepted.status_code == 202, accepted.text
    assert accepted.json()["status"] == JobStatus.PENDING.value
    job_id = accepted.json()["job_id"]
    await wait_for_jobs()
    job = await api.client.get(f"/api/v1/jobs/{job_id}")
    assert job.json()["status"] == JobStatus.COMPLETED.value, job.text
    return job.json()


async def _latest_run_id(api: MrpApi) -> str:
    runs = await api.client.get(f"{_MFG}/mrp/runs")
    assert runs.status_code == 200, runs.text
    return runs.json()["items"][0]["id"]


# --- run as a background job --------------------------------------------------


async def test_run_executes_as_job_and_persists_plan(mrp_api: MrpApi) -> None:
    """The run returns 202 {job_id}; the job completes; the MrpRun + planned orders exist (mirrors
    the depreciation/bank-import job test)."""
    job = await _run_to_completion(mrp_api)
    result = job["result"]
    assert result["run_number"].startswith("MRP")
    # 2 MAKE (finished + sub-assembly) + 2 BUY (raw1 + raw2).
    assert result["planned_make_count"] == 2
    assert result["planned_buy_count"] == 2

    run_id = result["run_id"]
    run = await mrp_api.client.get(f"{_MFG}/mrp/runs/{run_id}")
    assert run.status_code == 200
    assert run.json()["status"] == "COMPLETED"
    assert "capacity_loads" in run.json()

    planned = await mrp_api.client.get(f"{_MFG}/mrp/runs/{run_id}/planned-orders")
    assert planned.status_code == 200
    assert len(planned.json()["items"]) == 4


async def test_run_submit_is_idempotent(mrp_api: MrpApi) -> None:
    """A replayed Idempotency-Key returns the SAME job id (D-013)."""
    headers = _idem()
    first = await mrp_api.client.post(
        f"{_MFG}/mrp/runs", json={"run_date": "2026-06-01"}, headers=headers
    )
    second = await mrp_api.client.post(
        f"{_MFG}/mrp/runs", json={"run_date": "2026-06-01"}, headers=headers
    )
    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["job_id"] == second.json()["job_id"]
    await wait_for_jobs()


# --- planned-order reads + filters --------------------------------------------


async def test_planned_orders_filter_by_type(mrp_api: MrpApi) -> None:
    await _run_to_completion(mrp_api)
    run_id = await _latest_run_id(mrp_api)
    buys = await mrp_api.client.get(
        f"{_MFG}/mrp/runs/{run_id}/planned-orders?order_type=BUY"
    )
    assert buys.status_code == 200
    assert {row["order_type"] for row in buys.json()["items"]} == {"BUY"}
    assert len(buys.json()["items"]) == 2


async def test_capacity_report_lists_loaded_work_center(mrp_api: MrpApi) -> None:
    await _run_to_completion(mrp_api)
    run_id = await _latest_run_id(mrp_api)
    capacity = await mrp_api.client.get(f"{_MFG}/mrp/runs/{run_id}/capacity")
    assert capacity.status_code == 200
    loads = capacity.json()
    assert len(loads) == 1
    assert loads[0]["work_center_id"] == str(mrp_api.setup.work_center_id)
    assert loads[0]["is_overloaded"] is False  # 160 min << 14400 available


# --- conversion ---------------------------------------------------------------


async def test_convert_make_planned_order_to_production_order(mrp_api: MrpApi) -> None:
    """Converting a MAKE planned order over the wire creates a real production order."""
    await _run_to_completion(mrp_api)
    run_id = await _latest_run_id(mrp_api)
    planned = (
        await mrp_api.client.get(f"{_MFG}/mrp/runs/{run_id}/planned-orders?order_type=MAKE")
    ).json()["items"]
    make_order = next(p for p in planned if p["item_id"] == str(mrp_api.setup.finished_item_id))

    resp = await mrp_api.client.post(
        f"{_MFG}/planned-orders/{make_order['id']}/convert",
        json={"warehouse_id": str(mrp_api.setup.warehouse_id)},
        headers=_idem(),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "CONVERTED"
    assert resp.json()["converted_document_id"] is not None

    # A production order now exists for the finished item.
    orders = await mrp_api.client.get(f"{_MFG}/production-orders")
    assert any(
        o["item_id"] == str(mrp_api.setup.finished_item_id) for o in orders.json()["items"]
    )


async def test_convert_buy_planned_order_to_requisition(
    mrp_api: MrpApi, db_session: "AsyncSession"
) -> None:
    """Converting a BUY planned order creates a procurement requisition via the event bus. The mfg
    principal holds no procurement permission, so the requisition is verified by a direct DB read
    (the cross-module write landed in the same transaction)."""
    from sqlalchemy import func, select

    from app.core.tenancy import tenant_context
    from app.modules.procurement.models import PurchaseRequisition

    await _run_to_completion(mrp_api)
    run_id = await _latest_run_id(mrp_api)
    buys = (
        await mrp_api.client.get(f"{_MFG}/mrp/runs/{run_id}/planned-orders?order_type=BUY")
    ).json()["items"]
    buy_order = buys[0]

    resp = await mrp_api.client.post(
        f"{_MFG}/planned-orders/{buy_order['id']}/convert", json={}, headers=_idem()
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "CONVERTED"
    with tenant_context(mrp_api.setup.tenant_id):
        req_count = (
            await db_session.execute(
                select(func.count()).select_from(PurchaseRequisition).where(
                    PurchaseRequisition.tenant_id == mrp_api.setup.tenant_id
                )
            )
        ).scalar_one()
    assert req_count == 1


async def test_firm_and_cancel_planned_order(mrp_api: MrpApi) -> None:
    await _run_to_completion(mrp_api)
    run_id = await _latest_run_id(mrp_api)
    planned = (
        await mrp_api.client.get(f"{_MFG}/mrp/runs/{run_id}/planned-orders")
    ).json()["items"]
    firmed_id = planned[0]["id"]
    cancelled_id = planned[1]["id"]

    firm = await mrp_api.client.post(f"{_MFG}/planned-orders/{firmed_id}/firm")
    assert firm.status_code == 200
    assert firm.json()["status"] == "FIRMED"

    cancel = await mrp_api.client.post(f"{_MFG}/planned-orders/{cancelled_id}/cancel")
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "CANCELLED"


# --- RBAC ---------------------------------------------------------------------


async def test_run_requires_run_permission(
    client: AsyncClient, mfg_user_factory: Callable[..., object]
) -> None:
    """A principal with mrp.read but not mrp.run cannot run MRP (403)."""
    principal = await mfg_user_factory(
        slug="mfg-norun",
        email="norun@mfg.test",
        keys=("manufacturing.mrp.read", "manufacturing.planned_order.read"),
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
        f"{_MFG}/mrp/runs", json={"run_date": "2026-06-01"}, headers=_idem()
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "rbac.permission_denied"


async def test_convert_requires_manage_permission(
    client: AsyncClient, mfg_user_factory: Callable[..., object]
) -> None:
    """mrp.read does NOT grant planned_order.manage — convert is 403 for a read-only principal."""
    principal = await mfg_user_factory(
        slug="mfg-readonly",
        email="ro@mfg.test",
        keys=("manufacturing.mrp.read", "manufacturing.planned_order.read"),
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
        f"{_MFG}/planned-orders/{uuid.uuid4()}/convert", json={}, headers=_idem()
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "rbac.permission_denied"


# --- isolation + pagination budgets ------------------------------------------


async def test_other_tenant_cannot_read_run(
    mrp_api: MrpApi, mfg_client_b: AsyncClient
) -> None:
    await _run_to_completion(mrp_api)
    run_id = await _latest_run_id(mrp_api)
    resp = await mfg_client_b.get(f"{_MFG}/mrp/runs/{run_id}")
    assert resp.status_code == 404


async def test_list_runs_query_budget(
    mrp_api: MrpApi, query_counter: Callable[[], QueryCounter]
) -> None:
    await _run_to_completion(mrp_api)
    await assert_query_budget(mrp_api.client, query_counter, f"{_MFG}/mrp/runs", budget=3)


async def test_planned_orders_query_budget(
    mrp_api: MrpApi, query_counter: Callable[[], QueryCounter]
) -> None:
    await _run_to_completion(mrp_api)
    run_id = await _latest_run_id(mrp_api)
    # The nested list does a run 404-guard read (1) + the auth load (1) + the page select (1) = 3.
    await assert_query_budget(
        mrp_api.client, query_counter, f"{_MFG}/mrp/runs/{run_id}/planned-orders", budget=3
    )
