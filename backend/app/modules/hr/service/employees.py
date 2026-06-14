"""Employee business logic (PLAN 10.1, D-052): CRUD + reference validation + the org-chart cycle
guard + the dedicated compensation/PII write path.

The service layer owns every rule (CLAUDE.md rule 7); the router stays thin. An employee's
department/position/manager references must exist in the tenant when set; ``user_id`` is an OPAQUE
core users id validated via a core user probe (an employee MAY also be a system user — never a hard
FK to core_users). ``manager_id`` forms the org-chart reporting line; ``_assert_no_manager_cycle``
walks the would-be reporting chain UP and rejects a self-reference or a cycle (bounded by
``MAX_HIERARCHY_DEPTH``).

THE COMPENSATION WRITE PATH (D-009/D-052). The masked compensation/PII fields are written by
``create_employee`` (initial values) and ``set_compensation`` (the dedicated, ``read_compensation``-
guarded path) ONLY — they are deliberately absent from ``update_employee`` so a non-compensation
update can never silently null pay/PII.

``from __future__ import annotations`` keeps ``Page[Employee]`` a string at import; the router
re-validates page items.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.models import User
from app.core.pagination import DEFAULT_LIMIT, OrderKey, SortDirection, filter_fingerprint, paginate
from app.core.schemas import Page
from app.modules.hr import queries as hr_queries
from app.modules.hr.constants import DEFAULT_COMPENSATION_CURRENCY, MAX_HIERARCHY_DEPTH
from app.modules.hr.models import Employee, Position
from app.modules.hr.schemas import (
    EmployeeCompensationUpdate,
    EmployeeCreate,
    EmployeeFilter,
    EmployeeUpdate,
)

# The compensation/PII attribute names — the masked set written only at create + via
# set_compensation
# (D-052). Kept here so create + set_compensation stay in lockstep.
_COMPENSATION_FIELDS = (
    "base_salary",
    "currency_code",
    "national_id",
    "tax_id",
    "date_of_birth",
    "bank_account",
)


async def _validate_department(
    session: AsyncSession, tenant_id: uuid.UUID, department_id: uuid.UUID | None
) -> None:
    if department_id is None:
        return
    if await hr_queries.get_department(session, tenant_id, department_id) is None:
        raise ValidationFailedError(
            message="Referenced department does not exist",
            code="hr.department_not_found",
            details={"department_id": str(department_id)},
        )


async def _validate_position(
    session: AsyncSession, tenant_id: uuid.UUID, position_id: uuid.UUID | None
) -> None:
    if position_id is None:
        return
    found = (
        await session.execute(
            select(Position.id).where(Position.tenant_id == tenant_id, Position.id == position_id)
        )
    ).first()
    if found is None:
        raise ValidationFailedError(
            message="Referenced position does not exist",
            code="hr.position_not_found",
            details={"position_id": str(position_id)},
        )


async def _validate_user(
    session: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID | None
) -> None:
    """A supplied login ``user_id`` must reference a core user in the tenant (D-029): an OPAQUE id
    validated via a core user probe (core is below all modules — a downward read), never a hard FK.
    None is skipped (not every employee has a login)."""
    if user_id is None:
        return
    found = (
        await session.execute(
            select(User.id).where(User.tenant_id == tenant_id, User.id == user_id)
        )
    ).first()
    if found is None:
        raise ValidationFailedError(
            message="Referenced user account does not exist",
            code="hr.user_not_found",
            details={"user_id": str(user_id)},
        )


async def _assert_no_manager_cycle(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID | None,
    manager_id: uuid.UUID | None,
) -> None:
    """Reject a manager that would create a reporting cycle (D-052). The manager must exist; walking
    UP the reporting chain from it must never reach ``employee_id`` — that would close a loop. A
    self-manager is the degenerate case. Bounded by ``MAX_HIERARCHY_DEPTH``."""
    if manager_id is None:
        return
    if manager_id == employee_id:
        raise ValidationFailedError(
            message="An employee cannot report to themselves",
            code="hr.manager_cycle",
            details={"employee_id": str(employee_id), "manager_id": str(manager_id)},
        )
    current_id: uuid.UUID | None = manager_id
    seen: set[uuid.UUID] = set()
    for _ in range(MAX_HIERARCHY_DEPTH):
        if current_id is None:
            return
        if current_id == employee_id:
            raise ValidationFailedError(
                message="Manager assignment would create a reporting cycle",
                code="hr.manager_cycle",
                details={"employee_id": str(employee_id), "manager_id": str(manager_id)},
            )
        if current_id in seen:
            return
        seen.add(current_id)
        manager = await hr_queries.get_employee(session, tenant_id, current_id)
        if manager is None:
            raise ValidationFailedError(
                message="Referenced manager does not exist",
                code="hr.manager_not_found",
                details={"manager_id": str(manager_id)},
            )
        current_id = manager.manager_id
    raise ValidationFailedError(
        message="Reporting line is too deep",
        code="hr.reporting_too_deep",
        details={"max_depth": MAX_HIERARCHY_DEPTH},
    )


async def get_employee(
    session: AsyncSession, tenant_id: uuid.UUID, employee_id: uuid.UUID
) -> Employee:
    employee = await session.get(Employee, employee_id)
    if employee is None or employee.tenant_id != tenant_id:
        raise NotFoundError(message="Employee not found", code="hr.employee_not_found")
    return employee


async def create_employee(
    session: AsyncSession, tenant_id: uuid.UUID, payload: EmployeeCreate
) -> Employee:
    """Create an employee. Rejects a duplicate employee_code; validates department/position/manager/
    user when set, and rejects a manager that would form a reporting cycle. Sets the
    compensation/PII
    from the payload (the only fields the general update cannot touch), defaulting the currency to
    ``DEFAULT_COMPENSATION_CURRENCY`` when a salary is given without one."""
    existing = (
        await session.execute(
            select(Employee.id).where(
                Employee.tenant_id == tenant_id,
                Employee.employee_code == payload.employee_code,
            )
        )
    ).first()
    if existing is not None:
        raise ConflictError(
            message=f"Employee with code {payload.employee_code} already exists",
            code="hr.employee_code_conflict",
            details={"employee_code": payload.employee_code},
        )
    await _validate_department(session, tenant_id, payload.department_id)
    await _validate_position(session, tenant_id, payload.position_id)
    await _validate_user(session, tenant_id, payload.user_id)
    await _assert_no_manager_cycle(session, tenant_id, None, payload.manager_id)
    currency = payload.currency_code
    if payload.base_salary is not None and currency is None:
        currency = DEFAULT_COMPENSATION_CURRENCY
    employee = Employee(
        tenant_id=tenant_id,
        employee_code=payload.employee_code,
        first_name=payload.first_name,
        last_name=payload.last_name,
        email=payload.email,
        department_id=payload.department_id,
        position_id=payload.position_id,
        manager_id=payload.manager_id,
        user_id=payload.user_id,
        status=payload.status,
        employment_type=payload.employment_type,
        hire_date=payload.hire_date,
        termination_date=payload.termination_date,
        base_salary=payload.base_salary,
        currency_code=currency,
        national_id=payload.national_id,
        tax_id=payload.tax_id,
        date_of_birth=payload.date_of_birth,
        bank_account=payload.bank_account,
    )
    session.add(employee)
    await session.flush()
    return employee


async def update_employee(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    payload: EmployeeUpdate,
) -> Employee:
    """Partial update of NON-compensation fields (D-009 write-side convention: the masked
    compensation/PII fields are absent from ``EmployeeUpdate`` and edited only via
    set_compensation).
    ``employee_code`` is immutable; a changed department/position/user is re-validated; a changed
    manager is re-checked for a reporting cycle."""
    employee = await get_employee(session, tenant_id, employee_id)
    data = payload.model_dump(exclude_unset=True)
    if "department_id" in data:
        await _validate_department(session, tenant_id, data["department_id"])
    if "position_id" in data:
        await _validate_position(session, tenant_id, data["position_id"])
    if "user_id" in data:
        await _validate_user(session, tenant_id, data["user_id"])
    if "manager_id" in data:
        await _assert_no_manager_cycle(session, tenant_id, employee_id, data["manager_id"])
    for field, value in data.items():
        setattr(employee, field, value)
    await session.flush()
    return employee


async def set_compensation(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    payload: EmployeeCompensationUpdate,
) -> Employee:
    """The dedicated compensation/PII write path (D-009/D-052), behind the
    ``hr.employee.read_compensation`` guard at the router. Only the SET fields change
    (exclude_unset),
    so a caller can update salary alone without touching the PII. When a salary is set without a
    currency and the employee has none, default it (``DEFAULT_COMPENSATION_CURRENCY``)."""
    employee = await get_employee(session, tenant_id, employee_id)
    data = payload.model_dump(exclude_unset=True)
    for field in data:
        # Defensive: the schema only carries compensation fields, but pin the writable set so this
        # path can never mutate a non-compensation column.
        if field in _COMPENSATION_FIELDS:
            setattr(employee, field, data[field])
    if (
        data.get("base_salary") is not None
        and "currency_code" not in data
        and employee.currency_code is None
    ):
        employee.currency_code = DEFAULT_COMPENSATION_CURRENCY
    await session.flush()
    return employee


async def list_employees(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    filters: EmployeeFilter,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Page[Employee]:
    """Keyset-paginated employees ordered by employee_code (D-014). The department/status/manager
    filters narrow the set (index-served by (tenant, department, status)) and fold into the cursor
    fingerprint so a cursor cannot bleed across views. The masked Read still serializes within the
    ≤3-query budget — masking is a per-field serializer, not an extra query (PERFORMANCE §6)."""
    stmt = select(Employee).where(Employee.tenant_id == tenant_id)
    if filters.department_id is not None:
        stmt = stmt.where(Employee.department_id == filters.department_id)
    if filters.status is not None:
        stmt = stmt.where(Employee.status == filters.status)
    if filters.manager_id is not None:
        stmt = stmt.where(Employee.manager_id == filters.manager_id)
    fingerprint = filter_fingerprint(filters.department_id, filters.status, filters.manager_id)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(Employee.employee_code, SortDirection.ASC)],
        pk=Employee.id,
        cursor=cursor,
        limit=limit,
        filters=fingerprint,
    )
