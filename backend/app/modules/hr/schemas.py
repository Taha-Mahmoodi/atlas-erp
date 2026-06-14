"""HR request/response schemas (Pydantic v2, ApiModel base) for PLAN 10.1.

Create/Update/Read/Filter for the three entities (Department, Position, Employee) plus the dedicated
compensation-write payload and the org-chart response.

THE D-009 MASKING (the headline of 10.1). ``EmployeeRead`` wraps the compensation/PII fields in
``Masked(tp, HR_EMPLOYEE_READ_COMPENSATION)``: at serialization the wrapped serializer emits the
real value only if ``hr.employee.read_compensation`` is in the request's ``current_permissions``
ContextVar, else ``None``. The name/code/department/etc. are always visible. Per the D-009
write-side convention, those masked fields are EXCLUDED from ``EmployeeUpdate`` (a partial update
can never silently null compensation) and are written ONLY through ``EmployeeCompensationUpdate``,
behind the dedicated, ``read_compensation``-guarded endpoint. ``EmployeeCreate`` DOES carry them (a
manager seeding an employee may set initial pay in one call — but the create endpoint itself is
guarded so only a compensation-holder reaches it; see router.py).

Money amounts are ``Decimal`` strings (D-015). A ``code`` is immutable so it is absent from the
Update schemas (the master precedent). The Read schemas carry the server-derived fields
(timestamps).
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from app.core.schemas import ApiModel, Masked
from app.modules.hr.constants import (
    HR_EMPLOYEE_READ_COMPENSATION,
    EmploymentStatus,
    EmploymentType,
)

# --- Department ---------------------------------------------------------------


class DepartmentCreate(ApiModel):
    """Create a department. ``code`` is user-supplied + unique per tenant; ``parent_id`` (optional)
    must exist and not form a cycle; ``cost_center_id`` (optional) is validated in finance (D-029);
    ``manager_employee_id`` (optional) must be an existing employee in the tenant."""

    code: str
    name: str
    description: str | None = None
    parent_id: uuid.UUID | None = None
    cost_center_id: uuid.UUID | None = None
    manager_employee_id: uuid.UUID | None = None
    is_active: bool = True


class DepartmentUpdate(ApiModel):
    """Partial update. ``code`` is immutable (absent here). A changed ``parent_id`` is re-validated
    (existence + no cycle); a changed ``cost_center_id`` / ``manager_employee_id`` is re-validated.
    All fields optional — only the set ones change (exclude_unset)."""

    name: str | None = None
    description: str | None = None
    parent_id: uuid.UUID | None = None
    cost_center_id: uuid.UUID | None = None
    manager_employee_id: uuid.UUID | None = None
    is_active: bool | None = None


class DepartmentRead(ApiModel):
    id: uuid.UUID
    code: str
    name: str
    description: str | None
    parent_id: uuid.UUID | None
    cost_center_id: uuid.UUID | None
    manager_employee_id: uuid.UUID | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class DepartmentFilter(ApiModel):
    """List filters. None means "no constraint"; folded into the cursor's filter fingerprint so a
    cursor cannot cross filtered views."""

    is_active: bool | None = None
    parent_id: uuid.UUID | None = None


# --- Position -----------------------------------------------------------------


class PositionCreate(ApiModel):
    """Create a position. ``code`` is user-supplied + unique; ``department_id`` (optional) must
    exist."""

    code: str
    title: str
    description: str | None = None
    department_id: uuid.UUID | None = None
    is_active: bool = True


class PositionUpdate(ApiModel):
    """Partial update. ``code`` is immutable (absent here). A changed ``department_id`` is
    re-validated."""

    title: str | None = None
    description: str | None = None
    department_id: uuid.UUID | None = None
    is_active: bool | None = None


class PositionRead(ApiModel):
    id: uuid.UUID
    code: str
    title: str
    description: str | None
    department_id: uuid.UUID | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class PositionFilter(ApiModel):
    is_active: bool | None = None
    department_id: uuid.UUID | None = None


# --- Employee -----------------------------------------------------------------


class EmployeeCreate(ApiModel):
    """Create an employee. ``employee_code`` is user-supplied + unique; the department/position/
    manager/user references must exist when set, and the manager must not form a reporting cycle.
    The
    compensation/PII fields ARE accepted here (a manager seeding an employee may set initial pay) —
    the create endpoint is guarded so only a ``read_compensation`` holder reaches it (router.py)."""

    employee_code: str
    first_name: str
    last_name: str
    email: str | None = None
    department_id: uuid.UUID | None = None
    position_id: uuid.UUID | None = None
    manager_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None
    status: EmploymentStatus = EmploymentStatus.ACTIVE
    employment_type: EmploymentType = EmploymentType.FULL_TIME
    hire_date: date
    termination_date: date | None = None
    # Compensation + PII (set at create; thereafter via the dedicated compensation endpoint).
    base_salary: Decimal | None = None
    currency_code: str | None = None
    national_id: str | None = None
    tax_id: str | None = None
    date_of_birth: date | None = None
    bank_account: str | None = None


class EmployeeUpdate(ApiModel):
    """Partial update of an employee's NON-compensation fields. ``employee_code`` is immutable
    (absent). The compensation/PII fields are DELIBERATELY ABSENT (D-009 write-side convention):
    they
    are written only through the dedicated ``PATCH /employees/{id}/compensation`` endpoint, so a
    partial update can never silently null pay/PII. A changed department/position/manager/user is
    re-validated; a changed manager is re-checked for a reporting cycle."""

    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    department_id: uuid.UUID | None = None
    position_id: uuid.UUID | None = None
    manager_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None
    status: EmploymentStatus | None = None
    employment_type: EmploymentType | None = None
    hire_date: date | None = None
    termination_date: date | None = None


class EmployeeCompensationUpdate(ApiModel):
    """The dedicated compensation/PII write payload (D-009/D-052), behind the
    ``hr.employee.read_compensation``-guarded ``PATCH /employees/{id}/compensation`` endpoint. All
    optional — only the set fields change (exclude_unset), so a caller can update salary alone
    without
    touching the PII. This is the ONLY path that writes the masked fields after create."""

    base_salary: Decimal | None = None
    currency_code: str | None = None
    national_id: str | None = None
    tax_id: str | None = None
    date_of_birth: date | None = None
    bank_account: str | None = None


class EmployeeRead(ApiModel):
    """Employee response with the D-009 masked compensation/PII (the headline of 10.1). The
    sensitive fields serialize to their real value only when the request principal holds
    ``hr.employee.read_compensation`` (the ``Masked`` serializer reads the ``current_permissions``
    ContextVar), else ``None``. The non-sensitive fields are always visible."""

    id: uuid.UUID
    employee_code: str
    first_name: str
    last_name: str
    email: str | None
    department_id: uuid.UUID | None
    position_id: uuid.UUID | None
    manager_id: uuid.UUID | None
    user_id: uuid.UUID | None
    status: EmploymentStatus
    employment_type: EmploymentType
    hire_date: date
    termination_date: date | None
    created_at: datetime
    updated_at: datetime
    # --- D-009 masked: real value only with hr.employee.read_compensation, else None ---
    base_salary: Masked(Decimal, HR_EMPLOYEE_READ_COMPENSATION)
    currency_code: Masked(str, HR_EMPLOYEE_READ_COMPENSATION)
    national_id: Masked(str, HR_EMPLOYEE_READ_COMPENSATION)
    tax_id: Masked(str, HR_EMPLOYEE_READ_COMPENSATION)
    date_of_birth: Masked(date, HR_EMPLOYEE_READ_COMPENSATION)
    bank_account: Masked(str, HR_EMPLOYEE_READ_COMPENSATION)


class EmployeeFilter(ApiModel):
    department_id: uuid.UUID | None = None
    status: EmploymentStatus | None = None
    manager_id: uuid.UUID | None = None


# --- Org chart ----------------------------------------------------------------


class OrgChartNode(ApiModel):
    """One node in the reporting org chart (PLAN 10.1, D-052): an employee plus their direct reports
    (recursively). Built bounded-depth by the service; ``reports`` is empty for a leaf. The
    compensation/PII is NOT carried here — the chart is a structural reporting view, name/code/title
    only (so it is safe for any ``hr.employee.read`` holder without leaking pay)."""

    id: uuid.UUID
    employee_code: str
    first_name: str
    last_name: str
    position_id: uuid.UUID | None
    department_id: uuid.UUID | None
    reports: list["OrgChartNode"]


class OrgChartResponse(ApiModel):
    """The org-chart response: the reporting roots (employees with no manager, or the single root
    the caller anchored on) — a pure structural snapshot of the reporting tree."""

    roots: list[OrgChartNode]
