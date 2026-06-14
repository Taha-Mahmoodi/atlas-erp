"""Employee service tests (PLAN 10.1, D-052): CRUD, code uniqueness, department/position/manager/
user existence, the org-chart reporting CYCLE GUARD, the dedicated compensation write path, and the
org-chart build.

Driven through the real service under the tenant context (D-025).
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.tenancy import tenant_context
from app.modules.admin.service import provision_user
from app.modules.hr import queries as hr_queries
from app.modules.hr import service
from app.modules.hr.constants import EmploymentStatus
from app.modules.hr.schemas import (
    EmployeeCompensationUpdate,
    EmployeeCreate,
    EmployeeUpdate,
)
from tests.modules.hr.factories import (
    build_department,
    build_employee,
    build_position,
)


def _new_employee(code: str, **kw) -> EmployeeCreate:
    return EmployeeCreate(
        employee_code=code,
        first_name=kw.pop("first_name", "Test"),
        last_name=kw.pop("last_name", "Person"),
        hire_date=kw.pop("hire_date", date(2021, 1, 1)),
        **kw,
    )


# --- CRUD + references --------------------------------------------------------


async def test_create_and_get_employee(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    dept = await build_department(db_session, tenant_a, code="DEP-E")
    position = await build_position(db_session, tenant_a, code="POS-E", department_id=dept.id)
    emp = await build_employee(
        db_session,
        tenant_a,
        employee_code="EMP-1",
        department_id=dept.id,
        position_id=position.id,
    )
    with tenant_context(tenant_a):
        got = await service.get_employee(db_session, tenant_a, emp.id)
    assert got.employee_code == "EMP-1"
    assert got.department_id == dept.id
    assert got.position_id == position.id
    assert got.status == EmploymentStatus.ACTIVE.value


async def test_duplicate_code_rejected(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    await build_employee(db_session, tenant_a, employee_code="EMP-DUP")
    with tenant_context(tenant_a), pytest.raises(ConflictError):
        await service.create_employee(db_session, tenant_a, _new_employee("EMP-DUP"))


async def test_unknown_department_rejected(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    with tenant_context(tenant_a), pytest.raises(ValidationFailedError) as exc:
        await service.create_employee(
            db_session, tenant_a, _new_employee("EMP-BD", department_id=uuid.uuid4())
        )
    assert exc.value.code == "hr.department_not_found"


async def test_unknown_position_rejected(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    with tenant_context(tenant_a), pytest.raises(ValidationFailedError) as exc:
        await service.create_employee(
            db_session, tenant_a, _new_employee("EMP-BP", position_id=uuid.uuid4())
        )
    assert exc.value.code == "hr.position_not_found"


async def test_unknown_manager_rejected(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    with tenant_context(tenant_a), pytest.raises(ValidationFailedError) as exc:
        await service.create_employee(
            db_session, tenant_a, _new_employee("EMP-BM", manager_id=uuid.uuid4())
        )
    assert exc.value.code == "hr.manager_not_found"


async def test_unknown_user_rejected(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    with tenant_context(tenant_a), pytest.raises(ValidationFailedError) as exc:
        await service.create_employee(
            db_session, tenant_a, _new_employee("EMP-BU", user_id=uuid.uuid4())
        )
    assert exc.value.code == "hr.user_not_found"


async def test_valid_user_link(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    """An employee can link to an existing core user (the opaque, validated user_id — an employee
    MAY also be a system user, D-052)."""
    user = await provision_user(db_session, tenant_a, email="login@acme.test", password="pw-123456")
    await db_session.commit()
    emp = await build_employee(db_session, tenant_a, employee_code="EMP-U", user_id=user.id)
    assert emp.user_id == user.id


# --- The manager-cycle guard (THE org-chart guard) ----------------------------


async def test_self_manager_rejected(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    emp = await build_employee(db_session, tenant_a, employee_code="EMP-SELF")
    with tenant_context(tenant_a), pytest.raises(ValidationFailedError) as exc:
        await service.update_employee(
            db_session, tenant_a, emp.id, EmployeeUpdate(manager_id=emp.id)
        )
    assert exc.value.code == "hr.manager_cycle"


async def test_manager_cycle_rejected(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    """THE manager-cycle guard: A reports to nobody; B reports to A; C reports to B. Making A report
    to C would close the reporting loop (A -> C -> B -> A). Rejected before the row is written."""
    a = await build_employee(db_session, tenant_a, employee_code="EMP-A")
    b = await build_employee(db_session, tenant_a, employee_code="EMP-B", manager_id=a.id)
    c = await build_employee(db_session, tenant_a, employee_code="EMP-C", manager_id=b.id)
    with tenant_context(tenant_a), pytest.raises(ValidationFailedError) as exc:
        await service.update_employee(db_session, tenant_a, a.id, EmployeeUpdate(manager_id=c.id))
    assert exc.value.code == "hr.manager_cycle"


async def test_valid_reporting_line(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    a = await build_employee(db_session, tenant_a, employee_code="EMP-RA")
    b = await build_employee(db_session, tenant_a, employee_code="EMP-RB", manager_id=a.id)
    with tenant_context(tenant_a):
        chain = await hr_queries.employee_manager_chain(db_session, tenant_a, b.id)
    assert [e.employee_code for e in chain] == ["EMP-RB", "EMP-RA"]


# --- The compensation write path (D-009/D-052) --------------------------------


async def test_set_compensation_updates_only_set_fields(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """The dedicated set_compensation path updates only the supplied fields (exclude_unset):
    updating
    the salary alone leaves the PII untouched."""
    emp = await build_employee(
        db_session,
        tenant_a,
        employee_code="EMP-COMP",
        base_salary=Decimal("100000"),
        national_id="NID-KEEP",
    )
    with tenant_context(tenant_a):
        updated = await service.set_compensation(
            db_session,
            tenant_a,
            emp.id,
            EmployeeCompensationUpdate(base_salary=Decimal("130000")),
        )
    assert updated.base_salary == Decimal("130000")
    assert updated.national_id == "NID-KEEP"  # untouched


async def test_compensation_currency_defaulted(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """Setting a salary without a currency on an employee that has none defaults the currency."""
    emp = await build_employee(
        db_session,
        tenant_a,
        employee_code="EMP-CUR",
        base_salary=None,
        currency_code=None,
    )
    with tenant_context(tenant_a):
        updated = await service.set_compensation(
            db_session, tenant_a, emp.id, EmployeeCompensationUpdate(base_salary=Decimal("90000"))
        )
    assert updated.currency_code == "USD"


# --- The org-chart build ------------------------------------------------------


async def test_org_chart_build(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    """A reporting tree: CEO -> (VP1 -> IC1), VP2. The org chart roots on the manager-less CEO and
    nests the reports recursively."""
    ceo = await build_employee(db_session, tenant_a, employee_code="EMP-CEO")
    vp1 = await build_employee(db_session, tenant_a, employee_code="EMP-VP1", manager_id=ceo.id)
    await build_employee(db_session, tenant_a, employee_code="EMP-VP2", manager_id=ceo.id)
    await build_employee(db_session, tenant_a, employee_code="EMP-IC1", manager_id=vp1.id)

    with tenant_context(tenant_a):
        chart = await service.org_chart(db_session, tenant_a)

    assert len(chart.roots) == 1
    root = chart.roots[0]
    assert root.employee_code == "EMP-CEO"
    report_codes = sorted(r.employee_code for r in root.reports)
    assert report_codes == ["EMP-VP1", "EMP-VP2"]
    vp1_node = next(r for r in root.reports if r.employee_code == "EMP-VP1")
    assert [r.employee_code for r in vp1_node.reports] == ["EMP-IC1"]


async def test_org_chart_anchored_on_subtree(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    """Anchoring on a mid-tree manager returns just that sub-tree."""
    ceo = await build_employee(db_session, tenant_a, employee_code="EMP-X-CEO")
    vp = await build_employee(db_session, tenant_a, employee_code="EMP-X-VP", manager_id=ceo.id)
    await build_employee(db_session, tenant_a, employee_code="EMP-X-IC", manager_id=vp.id)

    with tenant_context(tenant_a):
        chart = await service.org_chart(db_session, tenant_a, root_employee_id=vp.id)

    assert len(chart.roots) == 1
    assert chart.roots[0].employee_code == "EMP-X-VP"
    assert [r.employee_code for r in chart.roots[0].reports] == ["EMP-X-IC"]


async def test_org_chart_unknown_root_raises(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    with tenant_context(tenant_a), pytest.raises(NotFoundError):
        await service.org_chart(db_session, tenant_a, root_employee_id=uuid.uuid4())


async def test_update_status_and_termination(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    emp = await build_employee(db_session, tenant_a, employee_code="EMP-TERM")
    with tenant_context(tenant_a):
        updated = await service.update_employee(
            db_session,
            tenant_a,
            emp.id,
            EmployeeUpdate(status=EmploymentStatus.TERMINATED, termination_date=date(2025, 6, 1)),
        )
    assert updated.status == EmploymentStatus.TERMINATED.value
    assert updated.termination_date == date(2025, 6, 1)
