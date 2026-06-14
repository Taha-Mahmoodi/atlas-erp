"""Leave configuration logic (PLAN 10.2, D-053): leave-type CRUD + balance reads.

Split out of ``leave.py`` so each leave file stays under the 400-line cap (the request lifecycle is
the busier concern). The leave TYPE is the configuration the accrual run and a request reference;
``get_leave_type`` is reused by the request-create validation in ``leave.py``. Leave BALANCES are
read-only over the API — they are written by the accrual run (``leave_accrual.py``) and the request
approve/cancel transitions (``leave.py``).

``from __future__ import annotations`` keeps ``Page[LeaveType]`` a string at import.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.pagination import DEFAULT_LIMIT, OrderKey, SortDirection, filter_fingerprint, paginate
from app.core.schemas import Page
from app.modules.hr import queries as hr_queries
from app.modules.hr.models import LeaveBalance, LeaveType
from app.modules.hr.schemas import LeaveTypeCreate, LeaveTypeFilter, LeaveTypeUpdate


def _validate_accrual(accrual_amount: Decimal, max_balance: Decimal | None) -> None:
    """The leave-type accrual invariants (D-053): ``accrual_amount`` >= 0, and when a cap is set it
    must be >= ``accrual_amount`` (a cap below one period's grant would make every accrual a no-op —
    a misconfiguration, rejected)."""
    if accrual_amount < 0:
        raise ValidationFailedError(
            message="Accrual amount cannot be negative",
            code="hr.leave_accrual_invalid",
            details={"accrual_amount": str(accrual_amount)},
        )
    if max_balance is not None and max_balance < accrual_amount:
        raise ValidationFailedError(
            message="Maximum balance cannot be below the accrual amount",
            code="hr.leave_max_balance_invalid",
            details={"max_balance": str(max_balance), "accrual_amount": str(accrual_amount)},
        )


async def get_leave_type(
    session: AsyncSession, tenant_id: uuid.UUID, leave_type_id: uuid.UUID
) -> LeaveType:
    leave_type = await session.get(LeaveType, leave_type_id)
    if leave_type is None or leave_type.tenant_id != tenant_id:
        raise NotFoundError(message="Leave type not found", code="hr.leave_type_not_found")
    return leave_type


async def create_leave_type(
    session: AsyncSession, tenant_id: uuid.UUID, payload: LeaveTypeCreate
) -> LeaveType:
    """Create a leave type. Rejects a duplicate code; validates the accrual invariants."""
    existing = (
        await session.execute(
            select(LeaveType.id).where(
                LeaveType.tenant_id == tenant_id, LeaveType.code == payload.code
            )
        )
    ).first()
    if existing is not None:
        raise ConflictError(
            message=f"Leave type with code {payload.code} already exists",
            code="hr.leave_type_code_conflict",
            details={"code": payload.code},
        )
    _validate_accrual(payload.accrual_amount, payload.max_balance)
    leave_type = LeaveType(
        tenant_id=tenant_id,
        code=payload.code,
        name=payload.name,
        accrual_frequency=payload.accrual_frequency,
        accrual_amount=payload.accrual_amount,
        max_balance=payload.max_balance,
        unit=payload.unit,
        is_paid=payload.is_paid,
        is_active=payload.is_active,
    )
    session.add(leave_type)
    await session.flush()
    return leave_type


async def update_leave_type(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    leave_type_id: uuid.UUID,
    payload: LeaveTypeUpdate,
) -> LeaveType:
    """Partial update (D-010: mutate the loaded object). ``code`` is immutable (absent). A changed
    accrual amount / cap is re-validated against the resulting pair."""
    leave_type = await get_leave_type(session, tenant_id, leave_type_id)
    data = payload.model_dump(exclude_unset=True)
    new_amount = data.get("accrual_amount", leave_type.accrual_amount)
    new_cap = data.get("max_balance", leave_type.max_balance)
    if "accrual_amount" in data or "max_balance" in data:
        _validate_accrual(new_amount, new_cap)
    for field, value in data.items():
        setattr(leave_type, field, value)
    await session.flush()
    return leave_type


async def list_leave_types(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    filters: LeaveTypeFilter,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Page[LeaveType]:
    """Keyset-paginated leave types ordered by code (D-014). The is_active / frequency filters
    narrow the set and fold into the cursor fingerprint."""
    stmt = select(LeaveType).where(LeaveType.tenant_id == tenant_id)
    if filters.is_active is not None:
        stmt = stmt.where(LeaveType.is_active == filters.is_active)
    if filters.accrual_frequency is not None:
        stmt = stmt.where(LeaveType.accrual_frequency == filters.accrual_frequency)
    fingerprint = filter_fingerprint(filters.is_active, filters.accrual_frequency)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(LeaveType.code, SortDirection.ASC)],
        pk=LeaveType.id,
        cursor=cursor,
        limit=limit,
        filters=fingerprint,
    )


async def list_leave_balances(
    session: AsyncSession, tenant_id: uuid.UUID, employee_id: uuid.UUID
) -> list[LeaveBalance]:
    """One employee's leave balances (D-053). 404 if the employee does not exist (a clean error over
    the wire), else the (possibly empty) balance list."""
    if not await hr_queries.employee_exists(session, tenant_id, employee_id):
        raise NotFoundError(message="Employee not found", code="hr.employee_not_found")
    return await hr_queries.leave_balances_for_employee(session, tenant_id, employee_id)
