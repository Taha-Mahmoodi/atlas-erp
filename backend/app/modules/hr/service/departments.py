"""Department business logic (PLAN 10.1, D-052): CRUD + cost-centre/manager validation + the
hierarchy cycle guard.

The service layer owns every rule (CLAUDE.md rule 7); the router stays thin. ``cost_center_id`` is
an
OPAQUE finance cost-centre id (D-029): validated via ``finance/queries.cost_center_exists`` (the
sanctioned cross-module read, STRUCTURE §5) — never a cross-module FK. ``manager_employee_id`` is a
soft reference to an employee in the same tenant (validated via ``hr/queries.employee_exists`` — the
department↔employee circular dependency is broken by keeping it a plain uuid, D-052). ``parent_id``
forms the department hierarchy; ``_assert_no_parent_cycle`` walks the would-be ancestor chain and
rejects a self-reference or a cycle (bounded by ``MAX_HIERARCHY_DEPTH``).

``from __future__ import annotations`` keeps ``Page[Department]`` (the ORM model) a string at
import;
the router re-validates page items.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.pagination import DEFAULT_LIMIT, OrderKey, SortDirection, filter_fingerprint, paginate
from app.core.schemas import Page
from app.modules.finance import queries as finance_queries
from app.modules.hr import queries as hr_queries
from app.modules.hr.constants import MAX_HIERARCHY_DEPTH
from app.modules.hr.models import Department
from app.modules.hr.schemas import DepartmentCreate, DepartmentFilter, DepartmentUpdate


async def _validate_cost_center(
    session: AsyncSession, tenant_id: uuid.UUID, cost_center_id: uuid.UUID | None
) -> None:
    """A supplied cost-centre id must exist in finance (D-029): validated via the finance queries
    contract, never a cross-module FK. None is skipped (the cost centre is optional)."""
    if cost_center_id is None:
        return
    if not await finance_queries.cost_center_exists(session, tenant_id, cost_center_id):
        raise ValidationFailedError(
            message="Referenced cost centre does not exist",
            code="hr.cost_center_not_found",
            details={"cost_center_id": str(cost_center_id)},
        )


async def _validate_manager_employee(
    session: AsyncSession, tenant_id: uuid.UUID, manager_employee_id: uuid.UUID | None
) -> None:
    """A supplied department-manager employee must exist in the tenant (D-052). The reference is a
    soft uuid (not a composite FK) to break the department↔employee circular dependency; the service
    is the integrity backstop. None is skipped (the manager is optional)."""
    if manager_employee_id is None:
        return
    if not await hr_queries.employee_exists(session, tenant_id, manager_employee_id):
        raise ValidationFailedError(
            message="Referenced manager employee does not exist",
            code="hr.manager_employee_not_found",
            details={"manager_employee_id": str(manager_employee_id)},
        )


async def _assert_no_parent_cycle(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    department_id: uuid.UUID | None,
    parent_id: uuid.UUID | None,
) -> None:
    """Reject a department parent that would create a cycle (D-052). The parent must exist; walking
    UP
    from it must never reach ``department_id`` (the department being edited) — that would close a
    loop. A self-parent is the degenerate case. Bounded by ``MAX_HIERARCHY_DEPTH``."""
    if parent_id is None:
        return
    if parent_id == department_id:
        raise ValidationFailedError(
            message="A department cannot be its own parent",
            code="hr.department_cycle",
            details={"department_id": str(department_id), "parent_id": str(parent_id)},
        )
    current_id: uuid.UUID | None = parent_id
    seen: set[uuid.UUID] = set()
    for _ in range(MAX_HIERARCHY_DEPTH):
        if current_id is None:
            return
        if current_id == department_id:
            raise ValidationFailedError(
                message="Department parent would create a cycle",
                code="hr.department_cycle",
                details={"department_id": str(department_id), "parent_id": str(parent_id)},
            )
        if current_id in seen:
            return
        seen.add(current_id)
        parent = await hr_queries.get_department(session, tenant_id, current_id)
        if parent is None:
            raise ValidationFailedError(
                message="Referenced parent department does not exist",
                code="hr.department_not_found",
                details={"parent_id": str(parent_id)},
            )
        current_id = parent.parent_id
    raise ValidationFailedError(
        message="Department hierarchy is too deep",
        code="hr.department_too_deep",
        details={"max_depth": MAX_HIERARCHY_DEPTH},
    )


async def get_department(
    session: AsyncSession, tenant_id: uuid.UUID, department_id: uuid.UUID
) -> Department:
    department = await session.get(Department, department_id)
    if department is None or department.tenant_id != tenant_id:
        raise NotFoundError(message="Department not found", code="hr.department_not_found")
    return department


async def create_department(
    session: AsyncSession, tenant_id: uuid.UUID, payload: DepartmentCreate
) -> Department:
    """Create a department. Rejects a duplicate code; validates the parent (exists + no cycle), the
    cost centre, and the manager employee when set."""
    existing = (
        await session.execute(
            select(Department.id).where(
                Department.tenant_id == tenant_id, Department.code == payload.code
            )
        )
    ).first()
    if existing is not None:
        raise ConflictError(
            message=f"Department with code {payload.code} already exists",
            code="hr.department_code_conflict",
            details={"code": payload.code},
        )
    await _assert_no_parent_cycle(session, tenant_id, None, payload.parent_id)
    await _validate_cost_center(session, tenant_id, payload.cost_center_id)
    await _validate_manager_employee(session, tenant_id, payload.manager_employee_id)
    department = Department(
        tenant_id=tenant_id,
        code=payload.code,
        name=payload.name,
        description=payload.description,
        parent_id=payload.parent_id,
        cost_center_id=payload.cost_center_id,
        manager_employee_id=payload.manager_employee_id,
        is_active=payload.is_active,
    )
    session.add(department)
    await session.flush()
    return department


async def update_department(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    department_id: uuid.UUID,
    payload: DepartmentUpdate,
) -> Department:
    """Partial update (D-010: mutate the loaded object so the audit diff is captured). ``code`` is
    immutable and absent; a changed parent is re-validated (exists + no cycle), and a changed cost
    centre / manager is re-validated."""
    department = await get_department(session, tenant_id, department_id)
    data = payload.model_dump(exclude_unset=True)
    if "parent_id" in data:
        await _assert_no_parent_cycle(session, tenant_id, department_id, data["parent_id"])
    if "cost_center_id" in data:
        await _validate_cost_center(session, tenant_id, data["cost_center_id"])
    if "manager_employee_id" in data:
        await _validate_manager_employee(session, tenant_id, data["manager_employee_id"])
    for field, value in data.items():
        setattr(department, field, value)
    await session.flush()
    return department


async def list_departments(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    filters: DepartmentFilter,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Page[Department]:
    """Keyset-paginated departments ordered by code (D-014). The is_active / parent filters narrow
    the set and fold into the cursor fingerprint so a cursor cannot bleed across views."""
    stmt = select(Department).where(Department.tenant_id == tenant_id)
    if filters.is_active is not None:
        stmt = stmt.where(Department.is_active == filters.is_active)
    if filters.parent_id is not None:
        stmt = stmt.where(Department.parent_id == filters.parent_id)
    fingerprint = filter_fingerprint(filters.is_active, filters.parent_id)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(Department.code, SortDirection.ASC)],
        pk=Department.id,
        cursor=cursor,
        limit=limit,
        filters=fingerprint,
    )
