"""Timesheet HTTP behaviour (PLAN 10.3, D-054): the timesheet + nested time-entry endpoints, the
submit → approve / reject / cancel flow, RBAC (manage vs approve), pagination, the ≤3-query list
budgets (PERFORMANCE §6), the allocation report, and tenant isolation.

Driven against a real bearer-token client whose tenant has a seeded cost centre + department.
"""

import uuid
from collections.abc import Callable

from httpx import AsyncClient

from app.modules.hr.constants import HR_TIMESHEET_MANAGE, HR_TIMESHEET_READ
from tests.conftest import QueryCounter, assert_query_budget
from tests.modules.hr.conftest import HrApi, HrPrincipal

_HR = "/api/v1/hr"


def _idem() -> dict[str, str]:
    """A fresh Idempotency-Key header (D-013): create/submit/approve/reject endpoints need one."""
    return {"Idempotency-Key": uuid.uuid4().hex}


async def _make_employee(client: AsyncClient, code: str = "EMP-TS") -> str:
    resp = await client.post(
        f"{_HR}/employees",
        json={
            "employee_code": code,
            "first_name": "Ada",
            "last_name": "Lovelace",
            "hire_date": "2021-01-01",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _make_timesheet(
    client: AsyncClient,
    employee_id: str,
    *,
    period_start: str = "2026-06-01",
    period_end: str = "2026-06-30",
) -> str:
    resp = await client.post(
        f"{_HR}/timesheets",
        json={
            "employee_id": employee_id,
            "period_start": period_start,
            "period_end": period_end,
        },
        headers=_idem(),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _add_entry(client: AsyncClient, timesheet_id: str, **body) -> dict:
    payload = {"entry_date": "2026-06-02", "hours": "8"}
    payload.update(body)
    resp = await client.post(
        f"{_HR}/timesheets/{timesheet_id}/time-entries", json=payload
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# --- CRUD + entries -----------------------------------------------------------


async def test_create_and_get_timesheet(hr_api: HrApi) -> None:
    emp_id = await _make_employee(hr_api.client)
    ts_id = await _make_timesheet(hr_api.client, emp_id)
    got = await hr_api.client.get(f"{_HR}/timesheets/{ts_id}")
    assert got.status_code == 200
    assert got.json()["timesheet_number"].startswith("TS-")
    assert got.json()["status"] == "DRAFT"


async def test_entries_maintain_total_hours(hr_api: HrApi) -> None:
    emp_id = await _make_employee(hr_api.client, code="EMP-TOT")
    ts_id = await _make_timesheet(hr_api.client, emp_id)
    await _add_entry(hr_api.client, ts_id, hours="8")
    await _add_entry(hr_api.client, ts_id, entry_date="2026-06-03", hours="4.5")
    got = await hr_api.client.get(f"{_HR}/timesheets/{ts_id}")
    assert got.json()["total_hours"] == "12.500000"
    entries = await hr_api.client.get(f"{_HR}/timesheets/{ts_id}/time-entries")
    assert len(entries.json()) == 2


async def test_entry_cost_center_validated(hr_api: HrApi) -> None:
    emp_id = await _make_employee(hr_api.client, code="EMP-CCV")
    ts_id = await _make_timesheet(hr_api.client, emp_id)
    bad = await hr_api.client.post(
        f"{_HR}/timesheets/{ts_id}/time-entries",
        json={"entry_date": "2026-06-02", "hours": "8", "cost_center_id": str(uuid.uuid4())},
    )
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "hr.cost_center_not_found"


async def test_entry_project_id_opaque_accepted(hr_api: HrApi) -> None:
    """An arbitrary project_id is stored as-is over the wire (NOT validated — projects is Phase
    11)."""
    emp_id = await _make_employee(hr_api.client, code="EMP-PRJ")
    ts_id = await _make_timesheet(hr_api.client, emp_id)
    project_id = str(uuid.uuid4())
    entry = await _add_entry(hr_api.client, ts_id, project_id=project_id)
    assert entry["project_id"] == project_id


async def test_remove_entry_lowers_total(hr_api: HrApi) -> None:
    emp_id = await _make_employee(hr_api.client, code="EMP-RM")
    ts_id = await _make_timesheet(hr_api.client, emp_id)
    entry = await _add_entry(hr_api.client, ts_id, hours="8")
    deleted = await hr_api.client.delete(
        f"{_HR}/timesheets/{ts_id}/time-entries/{entry['id']}"
    )
    assert deleted.status_code == 204
    got = await hr_api.client.get(f"{_HR}/timesheets/{ts_id}")
    assert got.json()["total_hours"] == "0.000000"


# --- Lifecycle ----------------------------------------------------------------


async def test_submit_approve_flow(hr_api: HrApi) -> None:
    emp_id = await _make_employee(hr_api.client, code="EMP-FLOW")
    ts_id = await _make_timesheet(hr_api.client, emp_id)
    await _add_entry(hr_api.client, ts_id)
    submitted = await hr_api.client.post(
        f"{_HR}/timesheets/{ts_id}/submit", headers=_idem()
    )
    assert submitted.json()["status"] == "SUBMITTED"
    approved = await hr_api.client.post(
        f"{_HR}/timesheets/{ts_id}/approve", json={}, headers=_idem()
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"
    assert approved.json()["approved_by"] is not None


async def test_reject_flow(hr_api: HrApi) -> None:
    emp_id = await _make_employee(hr_api.client, code="EMP-REJ")
    ts_id = await _make_timesheet(hr_api.client, emp_id)
    await hr_api.client.post(f"{_HR}/timesheets/{ts_id}/submit", headers=_idem())
    rejected = await hr_api.client.post(
        f"{_HR}/timesheets/{ts_id}/reject", json={"notes": "redo"}, headers=_idem()
    )
    assert rejected.json()["status"] == "REJECTED"


async def test_cancel_reopens_to_draft(hr_api: HrApi) -> None:
    emp_id = await _make_employee(hr_api.client, code="EMP-CAN")
    ts_id = await _make_timesheet(hr_api.client, emp_id)
    await hr_api.client.post(f"{_HR}/timesheets/{ts_id}/submit", headers=_idem())
    reopened = await hr_api.client.post(f"{_HR}/timesheets/{ts_id}/cancel")
    assert reopened.json()["status"] == "DRAFT"


# --- Allocation report --------------------------------------------------------


async def test_allocation_report_by_cost_center(hr_api: HrApi) -> None:
    emp_id = await _make_employee(hr_api.client, code="EMP-ALC")
    ts_id = await _make_timesheet(hr_api.client, emp_id)
    cc = str(hr_api.setup.cost_center_id)
    await _add_entry(hr_api.client, ts_id, hours="8", cost_center_id=cc)
    await _add_entry(hr_api.client, ts_id, entry_date="2026-06-03", hours="4", cost_center_id=cc)
    await hr_api.client.post(f"{_HR}/timesheets/{ts_id}/submit", headers=_idem())
    await hr_api.client.post(f"{_HR}/timesheets/{ts_id}/approve", json={}, headers=_idem())
    report = await hr_api.client.get(
        f"{_HR}/timesheets/allocation",
        params={"by": "cost_center", "from": "2026-06-01", "to": "2026-06-30"},
    )
    assert report.status_code == 200, report.text
    rows = {r["dimension_id"]: r["hours"] for r in report.json()["rows"]}
    assert rows[cc] == "12.000000"


async def test_allocation_report_by_project(hr_api: HrApi) -> None:
    emp_id = await _make_employee(hr_api.client, code="EMP-ALP")
    ts_id = await _make_timesheet(hr_api.client, emp_id)
    proj = str(uuid.uuid4())
    await _add_entry(hr_api.client, ts_id, hours="6", project_id=proj)
    await hr_api.client.post(f"{_HR}/timesheets/{ts_id}/submit", headers=_idem())
    await hr_api.client.post(f"{_HR}/timesheets/{ts_id}/approve", json={}, headers=_idem())
    report = await hr_api.client.get(
        f"{_HR}/timesheets/allocation",
        params={"by": "project", "from": "2026-06-01", "to": "2026-06-30"},
    )
    rows = {r["dimension_id"]: r["hours"] for r in report.json()["rows"]}
    assert rows[proj] == "6.000000"


# --- Pagination + budget ------------------------------------------------------


async def test_timesheet_list_paginated_and_budget(
    hr_api: HrApi, query_counter: Callable[[], QueryCounter]
) -> None:
    emp_id = await _make_employee(hr_api.client, code="EMP-PAGE")
    for month in range(1, 4):
        await _make_timesheet(
            hr_api.client,
            emp_id,
            period_start=f"2026-0{month}-01",
            period_end=f"2026-0{month}-28",
        )
    page = await hr_api.client.get(f"{_HR}/timesheets", params={"limit": 2})
    assert page.status_code == 200
    assert len(page.json()["items"]) == 2
    assert page.json()["next_cursor"] is not None
    await assert_query_budget(hr_api.client, query_counter, f"{_HR}/timesheets")


async def test_timesheet_list_filters_by_status(hr_api: HrApi) -> None:
    emp_id = await _make_employee(hr_api.client, code="EMP-FST")
    draft = await _make_timesheet(
        hr_api.client, emp_id, period_start="2026-01-01", period_end="2026-01-31"
    )
    submitted = await _make_timesheet(
        hr_api.client, emp_id, period_start="2026-02-01", period_end="2026-02-28"
    )
    await hr_api.client.post(f"{_HR}/timesheets/{submitted}/submit", headers=_idem())
    filtered = await hr_api.client.get(f"{_HR}/timesheets", params={"status": "DRAFT"})
    ids = {t["id"] for t in filtered.json()["items"]}
    assert draft in ids
    assert submitted not in ids


# --- RBAC ---------------------------------------------------------------------


async def test_manage_holder_cannot_approve(
    client: AsyncClient,
    db_session,  # noqa: ANN001 - fixture
    hr_user_factory: Callable[..., "object"],
) -> None:
    """A principal holding ``hr.timesheet.manage`` (but not ``.approve``) can create/submit but is
    403 on approve — the distinct approval authority (D-054)."""
    from tests.modules.hr.factories import build_employee, build_timesheet

    principal: HrPrincipal = await hr_user_factory(
        slug="hr-tsmgr",
        email="tsmgr@hr.test",
        keys=(HR_TIMESHEET_READ, HR_TIMESHEET_MANAGE),
    )
    employee = await build_employee(db_session, principal.tenant_id, employee_code="EMP-RBAC")
    timesheet = await build_timesheet(
        db_session, principal.tenant_id, employee_id=employee.id
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": principal.tenant_slug,
            "email": principal.email,
            "password": principal.password,
        },
    )
    token = login.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    await client.post(f"{_HR}/timesheets/{timesheet.id}/submit", headers=_idem())
    denied = await client.post(
        f"{_HR}/timesheets/{timesheet.id}/approve", json={}, headers=_idem()
    )
    assert denied.status_code == 403


async def test_read_only_cannot_create(
    client: AsyncClient,
    hr_user_factory: Callable[..., "object"],
) -> None:
    """A read-only principal (``hr.timesheet.read`` only) is 403 on create."""
    principal: HrPrincipal = await hr_user_factory(
        slug="hr-tsro", email="tsro@hr.test", keys=(HR_TIMESHEET_READ,)
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": principal.tenant_slug,
            "email": principal.email,
            "password": principal.password,
        },
    )
    token = login.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    denied = await client.post(
        f"{_HR}/timesheets",
        json={
            "employee_id": str(uuid.uuid4()),
            "period_start": "2026-06-01",
            "period_end": "2026-06-30",
        },
        headers=_idem(),
    )
    assert denied.status_code == 403


# --- Tenant isolation ---------------------------------------------------------


async def test_tenant_isolation(hr_api: HrApi, hr_client_b: AsyncClient) -> None:
    """Tenant B cannot read tenant A's timesheet (D-007)."""
    emp_id = await _make_employee(hr_api.client, code="EMP-ISO")
    ts_id = await _make_timesheet(hr_api.client, emp_id)
    cross = await hr_client_b.get(f"{_HR}/timesheets/{ts_id}")
    assert cross.status_code == 404
