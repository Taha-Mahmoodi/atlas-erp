"""Leave HTTP behaviour (PLAN 10.2, D-053): leave-type / balance / request endpoints over the wire,
the request approval flow (submit → approve decrements balance / reject / cancel restores), RBAC
(leave_type read vs manage, leave request vs approve), pagination, the ≤3-query list budgets
(PERFORMANCE §6), the conditional-GET ETag on the leave-type reference list, and tenant isolation.

Driven against a real bearer-token client whose tenant has a seeded cost centre + department.
"""

import uuid
from collections.abc import Callable
from decimal import Decimal

from httpx import AsyncClient

from app.modules.hr.constants import (
    HR_LEAVE_READ,
    HR_LEAVE_REQUEST,
    HR_LEAVE_TYPE_READ,
)
from tests.conftest import QueryCounter, assert_query_budget
from tests.modules.hr.conftest import HrPrincipal

_HR = "/api/v1/hr"


def _idem() -> dict[str, str]:
    """A fresh Idempotency-Key header (D-013): every create/submit/approve/reject/accrue endpoint
    requires one."""
    return {"Idempotency-Key": uuid.uuid4().hex}


async def _make_type(client: AsyncClient, code: str = "LT-API", **kw) -> str:
    body = {"code": code, "name": "Annual", "accrual_amount": "2"}
    body.update(kw)
    resp = await client.post(f"{_HR}/leave-types", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _make_employee(client: AsyncClient, code: str = "EMP-LV") -> str:
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


# --- Leave types --------------------------------------------------------------


async def test_create_and_get_leave_type(hr_client: AsyncClient) -> None:
    type_id = await _make_type(hr_client)
    got = await hr_client.get(f"{_HR}/leave-types/{type_id}")
    assert got.status_code == 200
    assert got.json()["code"] == "LT-API"
    assert got.json()["accrual_frequency"] == "MONTHLY"


async def test_leave_type_list_etag(hr_client: AsyncClient) -> None:
    await _make_type(hr_client, code="LT-ETAG")
    first = await hr_client.get(f"{_HR}/leave-types")
    assert first.status_code == 200
    etag = first.headers["etag"]
    second = await hr_client.get(f"{_HR}/leave-types", headers={"If-None-Match": etag})
    assert second.status_code == 304


async def test_leave_type_list_budget(
    hr_client: AsyncClient, query_counter: Callable[[], QueryCounter]
) -> None:
    await _make_type(hr_client, code="LT-BUD")
    await assert_query_budget(hr_client, query_counter, f"{_HR}/leave-types")


# --- Balances + accrual run ---------------------------------------------------


async def test_accrual_and_balance_endpoints(hr_client: AsyncClient) -> None:
    type_id = await _make_type(hr_client, code="LT-ACC", accrual_amount="5")
    emp_id = await _make_employee(hr_client, code="EMP-ACC-API")
    run = await hr_client.post(
        f"{_HR}/leave-balances/accrue",
        params={"frequency": "MONTHLY", "as_of": "2026-06-10"},
        headers=_idem(),
    )
    assert run.status_code == 200, run.text
    assert run.json()["period"] == "2026-06"
    assert run.json()["balances_accrued"] >= 1
    balances = await hr_client.get(f"{_HR}/employees/{emp_id}/leave-balances")
    assert balances.status_code == 200
    rows = {b["leave_type_id"]: b for b in balances.json()}
    assert Decimal(rows[type_id]["balance_days"]) == Decimal("5")


# --- Request approval flow ----------------------------------------------------


async def test_request_submit_approve_decrements(hr_client: AsyncClient) -> None:
    type_id = await _make_type(hr_client, code="LT-FLOW", accrual_amount="10")
    emp_id = await _make_employee(hr_client, code="EMP-FLOW")
    await hr_client.post(
        f"{_HR}/leave-balances/accrue",
        params={"frequency": "MONTHLY", "as_of": "2026-06-01"},
        headers=_idem(),
    )
    created = await hr_client.post(
        f"{_HR}/leave-requests",
        json={
            "employee_id": emp_id,
            "leave_type_id": type_id,
            "start_date": "2026-06-10",
            "end_date": "2026-06-12",
            "days": "3",
        },
        headers=_idem(),
    )
    assert created.status_code == 201, created.text
    req_id = created.json()["id"]
    assert created.json()["request_number"].startswith("LV-")

    submitted = await hr_client.post(f"{_HR}/leave-requests/{req_id}/submit", headers=_idem())
    assert submitted.json()["status"] == "SUBMITTED"
    approved = await hr_client.post(
        f"{_HR}/leave-requests/{req_id}/approve", json={}, headers=_idem()
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"

    balances = await hr_client.get(f"{_HR}/employees/{emp_id}/leave-balances")
    bal = next(b for b in balances.json() if b["leave_type_id"] == type_id)
    assert Decimal(bal["balance_days"]) == Decimal("7")


async def test_request_insufficient_balance_422(hr_client: AsyncClient) -> None:
    type_id = await _make_type(hr_client, code="LT-SHORT", accrual_amount="2")
    emp_id = await _make_employee(hr_client, code="EMP-SHORT")
    await hr_client.post(
        f"{_HR}/leave-balances/accrue",
        params={"frequency": "MONTHLY", "as_of": "2026-06-01"},
        headers=_idem(),
    )
    created = await hr_client.post(
        f"{_HR}/leave-requests",
        json={
            "employee_id": emp_id,
            "leave_type_id": type_id,
            "start_date": "2026-06-10",
            "end_date": "2026-06-20",
            "days": "9",
        },
        headers=_idem(),
    )
    req_id = created.json()["id"]
    await hr_client.post(f"{_HR}/leave-requests/{req_id}/submit", headers=_idem())
    approved = await hr_client.post(
        f"{_HR}/leave-requests/{req_id}/approve", json={}, headers=_idem()
    )
    assert approved.status_code == 422
    assert approved.json()["error"]["code"] == "hr.insufficient_leave_balance"


async def test_cancel_approved_restores(hr_client: AsyncClient) -> None:
    type_id = await _make_type(hr_client, code="LT-CAN", accrual_amount="10")
    emp_id = await _make_employee(hr_client, code="EMP-CAN")
    await hr_client.post(
        f"{_HR}/leave-balances/accrue",
        params={"frequency": "MONTHLY", "as_of": "2026-06-01"},
        headers=_idem(),
    )
    created = await hr_client.post(
        f"{_HR}/leave-requests",
        json={
            "employee_id": emp_id,
            "leave_type_id": type_id,
            "start_date": "2026-06-10",
            "end_date": "2026-06-13",
            "days": "4",
        },
        headers=_idem(),
    )
    req_id = created.json()["id"]
    await hr_client.post(f"{_HR}/leave-requests/{req_id}/submit", headers=_idem())
    await hr_client.post(
        f"{_HR}/leave-requests/{req_id}/approve", json={}, headers=_idem()
    )
    cancel = await hr_client.post(f"{_HR}/leave-requests/{req_id}/cancel")
    assert cancel.status_code == 200, cancel.text
    assert cancel.json()["status"] == "CANCELLED"
    balances = await hr_client.get(f"{_HR}/employees/{emp_id}/leave-balances")
    bal = next(b for b in balances.json() if b["leave_type_id"] == type_id)
    assert Decimal(bal["balance_days"]) == Decimal("10")


async def test_request_list_paginated_and_budget(
    hr_client: AsyncClient, query_counter: Callable[[], QueryCounter]
) -> None:
    type_id = await _make_type(hr_client, code="LT-LIST", accrual_amount="2")
    emp_id = await _make_employee(hr_client, code="EMP-LIST")
    for _ in range(3):
        resp = await hr_client.post(
            f"{_HR}/leave-requests",
            json={
                "employee_id": emp_id,
                "leave_type_id": type_id,
                "start_date": "2026-06-10",
                "end_date": "2026-06-11",
                "days": "1",
            },
            headers=_idem(),
        )
        assert resp.status_code == 201, resp.text
    page = await hr_client.get(f"{_HR}/leave-requests", params={"limit": 2})
    assert page.status_code == 200
    assert len(page.json()["items"]) == 2
    assert page.json()["next_cursor"] is not None
    await assert_query_budget(hr_client, query_counter, f"{_HR}/leave-requests")


async def test_request_list_filters_by_employee(hr_client: AsyncClient) -> None:
    type_id = await _make_type(hr_client, code="LT-FIL", accrual_amount="2")
    emp_a = await _make_employee(hr_client, code="EMP-FA")
    emp_b = await _make_employee(hr_client, code="EMP-FB")
    for emp in (emp_a, emp_b):
        await hr_client.post(
            f"{_HR}/leave-requests",
            json={
                "employee_id": emp,
                "leave_type_id": type_id,
                "start_date": "2026-06-10",
                "end_date": "2026-06-11",
                "days": "1",
            },
            headers=_idem(),
        )
    filtered = await hr_client.get(f"{_HR}/leave-requests", params={"employee_id": emp_a})
    emp_ids = {r["employee_id"] for r in filtered.json()["items"]}
    assert emp_ids == {emp_a}


# --- RBAC ---------------------------------------------------------------------


async def test_request_holder_cannot_approve(
    client: AsyncClient,
    db_session,
    hr_user_factory: Callable[..., "object"],
) -> None:
    """A principal holding ``hr.leave.request`` (but not ``.approve``) can file/submit but is 403 on
    approve — the distinct approval authority (D-040)."""
    from tests.modules.hr.factories import (
        build_employee,
        build_leave_request,
        build_leave_type,
    )

    principal: HrPrincipal = await hr_user_factory(
        slug="hr-req",
        email="req@hr.test",
        keys=(HR_LEAVE_READ, HR_LEAVE_REQUEST),
    )
    employee = await build_employee(db_session, principal.tenant_id, employee_code="EMP-RBAC")
    leave_type = await build_leave_type(db_session, principal.tenant_id, code="LT-RBAC")
    request = await build_leave_request(
        db_session,
        principal.tenant_id,
        employee_id=employee.id,
        leave_type_id=leave_type.id,
        days=Decimal("1"),
    )
    token = await _token(client, principal)
    client.headers["Authorization"] = f"Bearer {token}"

    submitted = await client.post(f"{_HR}/leave-requests/{request.id}/submit", headers=_idem())
    assert submitted.status_code == 200, submitted.text  # request key suffices to submit
    approve = await client.post(
        f"{_HR}/leave-requests/{request.id}/approve", json={}, headers=_idem()
    )
    assert approve.status_code == 403  # but NOT to approve


async def test_type_read_only_cannot_manage(
    client: AsyncClient, hr_user_factory: Callable[..., "object"]
) -> None:
    """A leave-type-read principal is 403 on leave-type create."""
    principal: HrPrincipal = await hr_user_factory(
        slug="hr-ltro", email="ltro@hr.test", keys=(HR_LEAVE_TYPE_READ,)
    )
    token = await _token(client, principal)
    client.headers["Authorization"] = f"Bearer {token}"
    resp = await client.post(
        f"{_HR}/leave-types", json={"code": "LT-NO", "name": "X", "accrual_amount": "1"}
    )
    assert resp.status_code == 403


# --- Tenant isolation ---------------------------------------------------------


async def test_tenant_isolation(hr_client: AsyncClient, hr_client_b: AsyncClient) -> None:
    """A leave type created in tenant A is invisible (404) to tenant B."""
    type_id = await _make_type(hr_client, code="LT-ISO")
    cross = await hr_client_b.get(f"{_HR}/leave-types/{type_id}")
    assert cross.status_code == 404


# --- helper -------------------------------------------------------------------


async def _token(client: AsyncClient, principal: HrPrincipal) -> str:
    resp = await client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": principal.tenant_slug,
            "email": principal.email,
            "password": principal.password,
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]
