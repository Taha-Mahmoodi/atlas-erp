"""Department service tests (PLAN 10.1, D-052): CRUD, code uniqueness, parent/cost-centre/manager
validation, and the hierarchy CYCLE GUARD.

Driven through the real service under the tenant context (D-025).
"""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.tenancy import tenant_context
from app.modules.hr import service
from app.modules.hr.schemas import DepartmentCreate, DepartmentUpdate
from tests.modules.hr.factories import build_department, build_employee, build_hr_setup


async def test_create_and_get_department(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    setup = await build_hr_setup(db_session, tenant_a)
    with tenant_context(tenant_a):
        got = await service.get_department(db_session, tenant_a, setup.department_id)
    assert got.code == setup.department_code
    assert got.cost_center_id == setup.cost_center_id
    assert got.is_active is True


async def test_duplicate_code_rejected(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    await build_department(db_session, tenant_a, code="DEP-DUP")
    with tenant_context(tenant_a), pytest.raises(ConflictError):
        await service.create_department(
            db_session, tenant_a, DepartmentCreate(code="DEP-DUP", name="Dup")
        )


async def test_unknown_cost_center_rejected(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    with tenant_context(tenant_a), pytest.raises(ValidationFailedError) as exc:
        await service.create_department(
            db_session,
            tenant_a,
            DepartmentCreate(code="DEP-CC", name="Bad CC", cost_center_id=uuid.uuid4()),
        )
    assert exc.value.code == "hr.cost_center_not_found"


async def test_unknown_manager_employee_rejected(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    with tenant_context(tenant_a), pytest.raises(ValidationFailedError) as exc:
        await service.create_department(
            db_session,
            tenant_a,
            DepartmentCreate(code="DEP-MGR", name="Bad mgr", manager_employee_id=uuid.uuid4()),
        )
    assert exc.value.code == "hr.manager_employee_not_found"


async def test_manager_employee_set_when_valid(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """The department↔employee soft link: an existing employee can be the department's manager (the
    circular reference resolved by the plain-uuid manager_employee_id, D-052)."""
    dept = await build_department(db_session, tenant_a, code="DEP-OK")
    emp = await build_employee(db_session, tenant_a, department_id=dept.id)
    with tenant_context(tenant_a):
        updated = await service.update_department(
            db_session,
            tenant_a,
            dept.id,
            DepartmentUpdate(manager_employee_id=emp.id),
        )
    assert updated.manager_employee_id == emp.id


async def test_unknown_parent_rejected(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    with tenant_context(tenant_a), pytest.raises(ValidationFailedError) as exc:
        await service.create_department(
            db_session,
            tenant_a,
            DepartmentCreate(code="DEP-P", name="Bad parent", parent_id=uuid.uuid4()),
        )
    assert exc.value.code == "hr.department_not_found"


async def test_hierarchy_built(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    """A two-level hierarchy: child.parent_id points at the parent."""
    parent = await build_department(db_session, tenant_a, code="DEP-ROOT")
    child = await build_department(db_session, tenant_a, code="DEP-CHILD", parent_id=parent.id)
    assert child.parent_id == parent.id


async def test_self_parent_rejected(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    dept = await build_department(db_session, tenant_a, code="DEP-SELF")
    with tenant_context(tenant_a), pytest.raises(ValidationFailedError) as exc:
        await service.update_department(
            db_session, tenant_a, dept.id, DepartmentUpdate(parent_id=dept.id)
        )
    assert exc.value.code == "hr.department_cycle"


async def test_parent_cycle_rejected(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    """THE hierarchy cycle guard: A -> B -> C, then making A the parent of C closes a loop (C's
    parent is A, A's parent would become C). Rejected before the row is written."""
    a = await build_department(db_session, tenant_a, code="DEP-A")
    b = await build_department(db_session, tenant_a, code="DEP-B", parent_id=a.id)
    c = await build_department(db_session, tenant_a, code="DEP-C", parent_id=b.id)
    # Try to set A's parent to C — A is an ancestor of C, so this would create a cycle.
    with tenant_context(tenant_a), pytest.raises(ValidationFailedError) as exc:
        await service.update_department(
            db_session, tenant_a, a.id, DepartmentUpdate(parent_id=c.id)
        )
    assert exc.value.code == "hr.department_cycle"


async def test_update_department_fields(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    dept = await build_department(db_session, tenant_a, code="DEP-UPD")
    with tenant_context(tenant_a):
        updated = await service.update_department(
            db_session,
            tenant_a,
            dept.id,
            DepartmentUpdate(name="Renamed", is_active=False),
        )
    assert updated.name == "Renamed"
    assert updated.is_active is False


async def test_get_missing_department_raises(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    with tenant_context(tenant_a), pytest.raises(NotFoundError):
        await service.get_department(db_session, tenant_a, uuid.uuid4())
