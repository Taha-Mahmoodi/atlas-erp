"""HR's cross-module read interface (STRUCTURE §5 / D-052).

HR sits ABOVE finance in the dependency order; nothing imports this yet (it is the newest module),
but it is the ONLY hr file a later module (payroll, projects) may import — kept thin and stable. The
service and router use these reads too. Every function takes an explicit ``tenant_id`` and runs
under
the caller's tenant context, so the D-007 filter applies on top — ordinary tenant-scoped reads.

``employee_manager_chain`` and ``org_chart_for`` back the org-chart / reporting-line views; both are
bounded by ``MAX_HIERARCHY_DEPTH`` (D-052) and the org-chart build issues ONE query for all
employees (PERFORMANCE §6: a bounded recursive read in memory, no per-node N+1).
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.hr.constants import MAX_HIERARCHY_DEPTH
from app.modules.hr.models import Department, Employee


async def get_employee(
    session: AsyncSession, tenant_id: uuid.UUID, employee_id: uuid.UUID
) -> Employee | None:
    """The employee with ``employee_id`` in the tenant, or None. A point lookup on the PK."""
    stmt = select(Employee).where(Employee.tenant_id == tenant_id, Employee.id == employee_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def employee_exists(
    session: AsyncSession, tenant_id: uuid.UUID, employee_id: uuid.UUID
) -> bool:
    """Whether an employee with ``employee_id`` exists in the tenant (a cheap id probe the
    department-manager / employee-manager validation uses)."""
    stmt = select(Employee.id).where(Employee.tenant_id == tenant_id, Employee.id == employee_id)
    return (await session.execute(stmt)).first() is not None


async def get_department(
    session: AsyncSession, tenant_id: uuid.UUID, department_id: uuid.UUID
) -> Department | None:
    """The department with ``department_id`` in the tenant, or None. A point lookup on the PK."""
    stmt = select(Department).where(
        Department.tenant_id == tenant_id, Department.id == department_id
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def department_employees(
    session: AsyncSession, tenant_id: uuid.UUID, department_id: uuid.UUID
) -> list[Employee]:
    """The employees in one department (D-052), ordered by employee_code. Index-served by
    (tenant, department_id, status)."""
    stmt = (
        select(Employee)
        .where(
            Employee.tenant_id == tenant_id,
            Employee.department_id == department_id,
        )
        .order_by(Employee.employee_code)
    )
    return list((await session.execute(stmt)).scalars().all())


async def employee_manager_chain(
    session: AsyncSession, tenant_id: uuid.UUID, employee_id: uuid.UUID
) -> list[Employee]:
    """The reporting chain from ``employee_id`` UP to the top (D-052): [self, manager, manager's
    manager, ...]. Bounded by ``MAX_HIERARCHY_DEPTH`` so a malformed chain (should be impossible
    given the service cycle guard) cannot spin forever. Empty if the employee does not exist."""
    chain: list[Employee] = []
    seen: set[uuid.UUID] = set()
    current_id: uuid.UUID | None = employee_id
    for _ in range(MAX_HIERARCHY_DEPTH):
        if current_id is None or current_id in seen:
            break
        current = await get_employee(session, tenant_id, current_id)
        if current is None:
            break
        chain.append(current)
        seen.add(current.id)
        current_id = current.manager_id
    return chain


async def org_chart_for(
    session: AsyncSession, tenant_id: uuid.UUID, root_employee_id: uuid.UUID | None = None
) -> tuple[list[Employee], dict[uuid.UUID, list[Employee]]]:
    """The data for the reporting org chart (D-052), as (roots, children-by-manager-id).

    ONE query loads every employee in the tenant (PERFORMANCE §6: no per-node N+1); the tree is
    built
    in memory. ``roots`` are the top of the chart — the employee with ``root_employee_id`` when
    given
    (a sub-tree anchored on one manager), else every employee with no manager. ``children`` maps a
    manager id to its direct reports (each list ordered by employee_code, matching the query order).
    The service walks this bounded by ``MAX_HIERARCHY_DEPTH`` to assemble the nested nodes.
    """
    stmt = select(Employee).where(Employee.tenant_id == tenant_id).order_by(Employee.employee_code)
    employees = list((await session.execute(stmt)).scalars().all())
    children: dict[uuid.UUID, list[Employee]] = {}
    for employee in employees:
        if employee.manager_id is not None:
            children.setdefault(employee.manager_id, []).append(employee)
    if root_employee_id is not None:
        roots = [e for e in employees if e.id == root_employee_id]
    else:
        roots = [e for e in employees if e.manager_id is None]
    return roots, children
