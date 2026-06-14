"""HR HTTP behaviour (PLAN 10.1, D-052): department / position / employee endpoints over the wire,
the D-009 COMPENSATION MASKING through the API, RBAC (read vs manage vs read_compensation),
pagination, the ≤3-query list budgets (PERFORMANCE §6), the conditional-GET ETag on the department +
position reference lists, tenant isolation, the org-chart endpoint, and the guarded compensation
PATCH.

Driven against a real bearer-token client whose tenant has a seeded cost centre + department.
"""

from collections.abc import Callable
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import tenant_context
from app.modules.hr import service
from app.modules.hr.constants import (
    HR_DEPARTMENT_READ,
    HR_EMPLOYEE_MANAGE,
    HR_EMPLOYEE_READ,
    HR_POSITION_READ,
)
from app.modules.hr.schemas import EmployeeCompensationUpdate
from tests.conftest import QueryCounter, assert_query_budget
from tests.modules.hr.conftest import HrApi, HrPrincipal
from tests.modules.hr.factories import build_employee

_HR = "/api/v1/hr"


def _employee_body(code: str, **kw) -> dict:
    body = {
        "employee_code": code,
        "first_name": "Ada",
        "last_name": "Lovelace",
        "hire_date": "2021-01-01",
    }
    body.update(kw)
    return body


# --- Department endpoints -----------------------------------------------------


async def test_create_and_get_department(hr_client: AsyncClient) -> None:
    create = await hr_client.post(f"{_HR}/departments", json={"code": "DEP-API", "name": "Sales"})
    assert create.status_code == 201, create.text
    dept_id = create.json()["id"]
    got = await hr_client.get(f"{_HR}/departments/{dept_id}")
    assert got.status_code == 200
    assert got.json()["code"] == "DEP-API"
    assert got.json()["is_active"] is True


async def test_department_list_etag(hr_api: HrApi) -> None:
    """The department list carries a conditional-GET ETag (D-035): a re-request with If-None-Match
    returns 304."""
    first = await hr_api.client.get(f"{_HR}/departments")
    assert first.status_code == 200
    etag = first.headers["etag"]
    second = await hr_api.client.get(f"{_HR}/departments", headers={"If-None-Match": etag})
    assert second.status_code == 304


async def test_department_list_budget(
    hr_api: HrApi, query_counter: Callable[[], QueryCounter]
) -> None:
    await assert_query_budget(hr_api.client, query_counter, f"{_HR}/departments")


# --- Position endpoints -------------------------------------------------------


async def test_create_and_list_position(hr_api: HrApi) -> None:
    create = await hr_api.client.post(
        f"{_HR}/positions",
        json={"code": "POS-API", "title": "Rep", "department_id": str(hr_api.setup.department_id)},
    )
    assert create.status_code == 201, create.text
    listed = await hr_api.client.get(f"{_HR}/positions")
    assert listed.status_code == 200
    assert any(p["code"] == "POS-API" for p in listed.json()["items"])


async def test_position_list_etag(hr_api: HrApi) -> None:
    first = await hr_api.client.get(f"{_HR}/positions")
    etag = first.headers["etag"]
    second = await hr_api.client.get(f"{_HR}/positions", headers={"If-None-Match": etag})
    assert second.status_code == 304


async def test_position_list_budget(
    hr_api: HrApi, query_counter: Callable[[], QueryCounter]
) -> None:
    await assert_query_budget(hr_api.client, query_counter, f"{_HR}/positions")


# --- Employee endpoints + masking over the wire -------------------------------


async def test_full_rights_sees_compensation(hr_api: HrApi) -> None:
    """A principal with read_compensation sees the real salary/PII in the create + read
    responses."""
    create = await hr_api.client.post(
        f"{_HR}/employees",
        json=_employee_body(
            "EMP-API",
            department_id=str(hr_api.setup.department_id),
            base_salary="150000",
            currency_code="USD",
            national_id="NID-API",
        ),
    )
    assert create.status_code == 201, create.text
    body = create.json()
    assert Decimal(body["base_salary"]) == Decimal("150000")
    assert body["national_id"] == "NID-API"
    got = await hr_api.client.get(f"{_HR}/employees/{body['id']}")
    assert Decimal(got.json()["base_salary"]) == Decimal("150000")
    assert got.json()["currency_code"] == "USD"


async def test_employee_list_paginated_and_budget(
    hr_api: HrApi, query_counter: Callable[[], QueryCounter]
) -> None:
    for i in range(3):
        resp = await hr_api.client.post(
            f"{_HR}/employees",
            json=_employee_body(f"EMP-L{i}", department_id=str(hr_api.setup.department_id)),
        )
        assert resp.status_code == 201, resp.text
    page = await hr_api.client.get(f"{_HR}/employees", params={"limit": 2})
    assert page.status_code == 200
    assert len(page.json()["items"]) == 2
    assert page.json()["next_cursor"] is not None
    await assert_query_budget(hr_api.client, query_counter, f"{_HR}/employees")


async def test_employee_list_filters_by_department(hr_api: HrApi) -> None:
    other = await hr_api.client.post(
        f"{_HR}/departments", json={"code": "DEP-OTHER", "name": "Other"}
    )
    other_id = other.json()["id"]
    await hr_api.client.post(
        f"{_HR}/employees",
        json=_employee_body("EMP-D1", department_id=str(hr_api.setup.department_id)),
    )
    await hr_api.client.post(
        f"{_HR}/employees", json=_employee_body("EMP-D2", department_id=other_id)
    )
    filtered = await hr_api.client.get(
        f"{_HR}/employees", params={"department_id": str(hr_api.setup.department_id)}
    )
    codes = {e["employee_code"] for e in filtered.json()["items"]}
    assert "EMP-D1" in codes
    assert "EMP-D2" not in codes


# --- The compensation PATCH (guarded) -----------------------------------------


async def test_compensation_patch_updates_pay(hr_api: HrApi) -> None:
    create = await hr_api.client.post(
        f"{_HR}/employees", json=_employee_body("EMP-CP", base_salary="100000")
    )
    emp_id = create.json()["id"]
    patched = await hr_api.client.patch(
        f"{_HR}/employees/{emp_id}/compensation", json={"base_salary": "140000"}
    )
    assert patched.status_code == 200, patched.text
    assert Decimal(patched.json()["base_salary"]) == Decimal("140000")


async def test_general_update_cannot_set_compensation(hr_api: HrApi) -> None:
    """The masked fields are excluded from the general update schema: posting base_salary to the
    PATCH /employees/{id} body is ignored (extra field), the salary unchanged."""
    create = await hr_api.client.post(
        f"{_HR}/employees", json=_employee_body("EMP-GU", base_salary="100000")
    )
    emp_id = create.json()["id"]
    await hr_api.client.patch(
        f"{_HR}/employees/{emp_id}",
        json={"first_name": "Grace", "base_salary": "999999"},
    )
    got = await hr_api.client.get(f"{_HR}/employees/{emp_id}")
    assert got.json()["first_name"] == "Grace"
    # the general update could not touch the masked field — pay unchanged.
    assert Decimal(got.json()["base_salary"]) == Decimal("100000")


# --- The org-chart endpoint ---------------------------------------------------


async def test_org_chart_endpoint(hr_api: HrApi) -> None:
    ceo = await hr_api.client.post(f"{_HR}/employees", json=_employee_body("EMP-OC-CEO"))
    ceo_id = ceo.json()["id"]
    await hr_api.client.post(
        f"{_HR}/employees", json=_employee_body("EMP-OC-VP", manager_id=ceo_id)
    )
    chart = await hr_api.client.get(f"{_HR}/employees/org-chart")
    assert chart.status_code == 200
    roots = chart.json()["roots"]
    ceo_node = next(r for r in roots if r["employee_code"] == "EMP-OC-CEO")
    assert [r["employee_code"] for r in ceo_node["reports"]] == ["EMP-OC-VP"]


# --- RBAC ---------------------------------------------------------------------


async def test_read_only_cannot_manage(
    client: AsyncClient,
    hr_user_factory: Callable[..., "object"],
) -> None:
    """A read-only principal (employee.read only) is 403 on create."""
    principal: HrPrincipal = await hr_user_factory(
        slug="hr-ro", email="ro@hr.test", keys=(HR_EMPLOYEE_READ,)
    )
    token = await _token(client, principal)
    client.headers["Authorization"] = f"Bearer {token}"
    resp = await client.post(f"{_HR}/employees", json=_employee_body("EMP-RO"))
    assert resp.status_code == 403


async def test_department_read_only_cannot_manage(
    client: AsyncClient, hr_user_factory: Callable[..., "object"]
) -> None:
    """A department-read principal is 403 on department create."""
    principal: HrPrincipal = await hr_user_factory(
        slug="hr-dro", email="dro@hr.test", keys=(HR_DEPARTMENT_READ,)
    )
    token = await _token(client, principal)
    client.headers["Authorization"] = f"Bearer {token}"
    resp = await client.post(f"{_HR}/departments", json={"code": "DEP-X", "name": "X"})
    assert resp.status_code == 403


async def test_position_read_only_cannot_manage(
    client: AsyncClient, hr_user_factory: Callable[..., "object"]
) -> None:
    """A position-read principal is 403 on position create."""
    principal: HrPrincipal = await hr_user_factory(
        slug="hr-pro", email="pro@hr.test", keys=(HR_POSITION_READ,)
    )
    token = await _token(client, principal)
    client.headers["Authorization"] = f"Bearer {token}"
    resp = await client.post(f"{_HR}/positions", json={"code": "POS-X", "title": "X"})
    assert resp.status_code == 403


async def test_manage_without_compensation_cannot_create(
    client: AsyncClient, hr_user_factory: Callable[..., "object"]
) -> None:
    """Create requires BOTH manage AND read_compensation (it accepts initial pay). A manage-only
    principal (no read_compensation) is 403 on create."""
    principal: HrPrincipal = await hr_user_factory(
        slug="hr-mgr", email="mgr@hr.test", keys=(HR_EMPLOYEE_READ, HR_EMPLOYEE_MANAGE)
    )
    token = await _token(client, principal)
    client.headers["Authorization"] = f"Bearer {token}"
    resp = await client.post(f"{_HR}/employees", json=_employee_body("EMP-MGR"))
    assert resp.status_code == 403


async def test_manage_without_compensation_gets_masked_reads(
    client: AsyncClient,
    db_session: AsyncSession,
    hr_user_factory: Callable[..., "object"],
) -> None:
    """A manage-but-not-compensation principal CAN read employees, but the compensation/PII is
    masked
    (None) — the D-009 serializer per-request gate. AND they are 403 on the compensation
    endpoint."""
    principal: HrPrincipal = await hr_user_factory(
        slug="hr-mask",
        email="mask@hr.test",
        keys=(HR_EMPLOYEE_READ, HR_EMPLOYEE_MANAGE),
    )
    # Seed an employee directly in that principal's tenant (the service, not the API — the principal
    # itself can't create with pay), then give it real pay via the service so the read has something
    # to mask.
    employee = await build_employee(
        db_session, principal.tenant_id, employee_code="EMP-MASKED", base_salary=None
    )
    with tenant_context(principal.tenant_id):
        await service.set_compensation(
            db_session,
            principal.tenant_id,
            employee.id,
            EmployeeCompensationUpdate(base_salary=Decimal("111111"), national_id="NID-HIDDEN"),
        )
        await db_session.commit()

    token = await _token(client, principal)
    client.headers["Authorization"] = f"Bearer {token}"

    got = await client.get(f"{_HR}/employees/{employee.id}")
    assert got.status_code == 200
    body = got.json()
    assert body["employee_code"] == "EMP-MASKED"  # structural fields visible
    assert body["base_salary"] is None  # MASKED
    assert body["national_id"] is None  # MASKED

    # And the compensation endpoint is forbidden.
    patch = await client.patch(
        f"{_HR}/employees/{employee.id}/compensation", json={"base_salary": "200000"}
    )
    assert patch.status_code == 403


# --- Tenant isolation ---------------------------------------------------------


async def test_tenant_isolation(hr_api: HrApi, hr_client_b: AsyncClient) -> None:
    """An employee created in tenant A is invisible (404) to tenant B."""
    create = await hr_api.client.post(f"{_HR}/employees", json=_employee_body("EMP-ISO"))
    emp_id = create.json()["id"]
    cross = await hr_client_b.get(f"{_HR}/employees/{emp_id}")
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
