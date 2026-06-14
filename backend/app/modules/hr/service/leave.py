"""Leave-request lifecycle (PLAN 10.2, D-053): create → submit → approve/reject → cancel, with the
balance decrement on approve and restore on cancel-of-approved.

The service layer owns every rule (CLAUDE.md rule 7); the router stays thin. The request lifecycle
mirrors the procurement requisition submit→approve→reject precedent (D-040), without a value
threshold — every SUBMITTED request awaits a distinct ``hr.leave.approve`` holder. Leave-TYPE CRUD
and balance reads live in ``leave_config.py``; the accrual run in ``leave_accrual.py``.

THE BALANCE EFFECT (the headline of 10.2, D-053):
- APPROVE decrements the employee's balance for the type by ``days`` (raising ``taken_to_date``). If
  the balance is insufficient → 422 ``hr.insufficient_leave_balance`` (v1 BLOCKS negative balances;
  an allow-negative leave type is the documented later). A missing balance row counts as 0
  available.
- CANCEL of an APPROVED request RESTORES the balance (adds ``days`` back, lowers ``taken_to_date``);
  cancel from DRAFT/SUBMITTED has no balance effect.

``from __future__ import annotations`` keeps ``Page[...]`` of the ORM models a string at import.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.numbering import claim_number, ensure_sequence
from app.core.pagination import DEFAULT_LIMIT, OrderKey, SortDirection, filter_fingerprint, paginate
from app.core.schemas import Page
from app.modules.hr import queries as hr_queries
from app.modules.hr.constants import (
    LEAVE_REQUEST_NUMBER_PADDING,
    LEAVE_REQUEST_NUMBER_PREFIX,
    LEAVE_REQUEST_SEQUENCE_NAME,
    LeaveRequestStatus,
)
from app.modules.hr.models import LeaveBalance, LeaveRequest
from app.modules.hr.schemas import (
    LeaveRequestCreate,
    LeaveRequestFilter,
    LeaveRequestUpdate,
)
from app.modules.hr.service.leave_config import get_leave_type

# --- Leave request lifecycle --------------------------------------------------


async def get_leave_request(
    session: AsyncSession, tenant_id: uuid.UUID, request_id: uuid.UUID
) -> LeaveRequest:
    request = await session.get(LeaveRequest, request_id)
    if request is None or request.tenant_id != tenant_id:
        raise NotFoundError(message="Leave request not found", code="hr.leave_request_not_found")
    return request


def _validate_request_dates(start_date: date, end_date: date, days: Decimal) -> None:
    if end_date < start_date:
        raise ValidationFailedError(
            message="The end date cannot be before the start date",
            code="hr.leave_dates_invalid",
            details={"start_date": str(start_date), "end_date": str(end_date)},
        )
    if days <= 0:
        raise ValidationFailedError(
            message="Leave days must be greater than zero",
            code="hr.leave_days_invalid",
            details={"days": str(days)},
        )


async def create_leave_request(
    session: AsyncSession, tenant_id: uuid.UUID, payload: LeaveRequestCreate
) -> LeaveRequest:
    """Create a DRAFT leave request (D-053). Validates the employee + leave type exist, days > 0 and
    end >= start; claims a gapless ``LV-`` number at creation (D-040 precedent). No balance effect
    until approve."""
    if not await hr_queries.employee_exists(session, tenant_id, payload.employee_id):
        raise ValidationFailedError(
            message="Referenced employee does not exist",
            code="hr.employee_not_found",
            details={"employee_id": str(payload.employee_id)},
        )
    # Validate the leave type exists (load raises a clean 404-shaped error if not).
    await get_leave_type(session, tenant_id, payload.leave_type_id)
    _validate_request_dates(payload.start_date, payload.end_date, payload.days)

    await ensure_sequence(
        session,
        tenant_id,
        LEAVE_REQUEST_SEQUENCE_NAME,
        LEAVE_REQUEST_NUMBER_PREFIX,
        LEAVE_REQUEST_NUMBER_PADDING,
        year_reset=True,
    )
    number = await claim_number(
        session, tenant_id, LEAVE_REQUEST_SEQUENCE_NAME, on_date=payload.start_date
    )
    request = LeaveRequest(
        tenant_id=tenant_id,
        request_number=number,
        employee_id=payload.employee_id,
        leave_type_id=payload.leave_type_id,
        start_date=payload.start_date,
        end_date=payload.end_date,
        days=payload.days,
        status=LeaveRequestStatus.DRAFT.value,
        reason=payload.reason,
        notes=payload.notes,
    )
    session.add(request)
    await session.flush()
    return request


async def update_leave_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    payload: LeaveRequestUpdate,
) -> LeaveRequest:
    """Partial update of a DRAFT leave request (D-053). Only a DRAFT is editable; ``employee_id`` /
    ``leave_type_id`` are immutable. The resulting date range / days is re-validated."""
    request = await get_leave_request(session, tenant_id, request_id)
    if LeaveRequestStatus(request.status) != LeaveRequestStatus.DRAFT:
        raise ConflictError(
            message="Only a draft leave request can be edited",
            code="hr.leave_request_not_draft",
            details={"status": request.status},
        )
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(request, field, value)
    _validate_request_dates(request.start_date, request.end_date, request.days)
    await session.flush()
    return request


async def submit_leave_request(
    session: AsyncSession, tenant_id: uuid.UUID, request_id: uuid.UUID
) -> LeaveRequest:
    """Submit a DRAFT leave request (D-053): DRAFT → SUBMITTED, awaiting an approver. Re-submitting
    a non-draft is a conflict."""
    request = await get_leave_request(session, tenant_id, request_id)
    if LeaveRequestStatus(request.status) != LeaveRequestStatus.DRAFT:
        raise ConflictError(
            message="Only a draft leave request can be submitted",
            code="hr.leave_request_not_draft",
            details={"status": request.status},
        )
    request.status = LeaveRequestStatus.SUBMITTED.value
    await session.flush()
    return request


async def _balance_for_update(
    session: AsyncSession, tenant_id: uuid.UUID, employee_id: uuid.UUID, leave_type_id: uuid.UUID
) -> LeaveBalance | None:
    return await hr_queries.get_leave_balance(session, tenant_id, employee_id, leave_type_id)


async def approve_leave_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    approved_by: uuid.UUID,
    notes: str | None = None,
) -> LeaveRequest:
    """Approve a SUBMITTED leave request (D-053, the ``hr.leave.approve`` action). DECREMENTS the
    employee's balance for the type by ``days`` (raising ``taken_to_date``); if the available
    balance is below ``days`` → 422 ``hr.insufficient_leave_balance`` (v1 blocks negative balances).
    A missing balance row counts as 0 available. Records the approver + decision time."""
    request = await get_leave_request(session, tenant_id, request_id)
    if LeaveRequestStatus(request.status) != LeaveRequestStatus.SUBMITTED:
        raise ConflictError(
            message="Only a submitted leave request can be approved",
            code="hr.leave_request_not_submitted",
            details={"status": request.status},
        )
    balance = await _balance_for_update(
        session, tenant_id, request.employee_id, request.leave_type_id
    )
    available = balance.balance_days if balance is not None else Decimal(0)
    if available < request.days:
        raise ValidationFailedError(
            message="Insufficient leave balance for this request",
            code="hr.insufficient_leave_balance",
            details={"available": str(available), "requested": str(request.days)},
        )
    balance.balance_days -= request.days
    balance.taken_to_date += request.days
    request.status = LeaveRequestStatus.APPROVED.value
    request.approved_by = approved_by
    request.decided_at = datetime.now(UTC)
    request.notes = notes if notes is not None else request.notes
    await session.flush()
    return request


async def reject_leave_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    approved_by: uuid.UUID,
    notes: str | None = None,
) -> LeaveRequest:
    """Reject a SUBMITTED leave request (D-053): SUBMITTED → REJECTED. No balance effect. Records
    the decider + decision time."""
    request = await get_leave_request(session, tenant_id, request_id)
    if LeaveRequestStatus(request.status) != LeaveRequestStatus.SUBMITTED:
        raise ConflictError(
            message="Only a submitted leave request can be rejected",
            code="hr.leave_request_not_submitted",
            details={"status": request.status},
        )
    request.status = LeaveRequestStatus.REJECTED.value
    request.approved_by = approved_by
    request.decided_at = datetime.now(UTC)
    request.notes = notes if notes is not None else request.notes
    await session.flush()
    return request


async def cancel_leave_request(
    session: AsyncSession, tenant_id: uuid.UUID, request_id: uuid.UUID
) -> LeaveRequest:
    """Cancel a leave request (D-053). Allowed from DRAFT/SUBMITTED (no balance effect) or APPROVED
    (RESTORES the balance: adds ``days`` back, lowers ``taken_to_date``). A terminal request
    (REJECTED/CANCELLED) cannot be cancelled."""
    request = await get_leave_request(session, tenant_id, request_id)
    status = LeaveRequestStatus(request.status)
    if status in (LeaveRequestStatus.REJECTED, LeaveRequestStatus.CANCELLED):
        raise ConflictError(
            message=f"A {request.status} leave request cannot be cancelled",
            code="hr.leave_request_not_cancellable",
            details={"status": request.status},
        )
    if status == LeaveRequestStatus.APPROVED:
        balance = await _balance_for_update(
            session, tenant_id, request.employee_id, request.leave_type_id
        )
        if balance is not None:
            balance.balance_days += request.days
            balance.taken_to_date -= request.days
    request.status = LeaveRequestStatus.CANCELLED.value
    await session.flush()
    return request


async def list_leave_requests(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    filters: LeaveRequestFilter,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Page[LeaveRequest]:
    """Keyset-paginated leave requests, newest first (D-014). The employee / status / leave-type
    filters fold into the cursor fingerprint; the (tenant, employee_id, status) index serves the
    filtered page."""
    stmt = select(LeaveRequest).where(LeaveRequest.tenant_id == tenant_id)
    if filters.employee_id is not None:
        stmt = stmt.where(LeaveRequest.employee_id == filters.employee_id)
    if filters.status is not None:
        stmt = stmt.where(LeaveRequest.status == filters.status)
    if filters.leave_type_id is not None:
        stmt = stmt.where(LeaveRequest.leave_type_id == filters.leave_type_id)
    fingerprint = filter_fingerprint(filters.employee_id, filters.status, filters.leave_type_id)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(LeaveRequest.created_at, SortDirection.DESC)],
        pk=LeaveRequest.id,
        cursor=cursor,
        limit=limit,
        filters=fingerprint,
    )
