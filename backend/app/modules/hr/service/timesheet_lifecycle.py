"""Timesheet approval lifecycle (PLAN 10.3, D-054): submit → approve / reject, and cancel
(reopen-to-draft).

Split out of ``timesheets.py`` (header + entry CRUD) so each file stays under the 400-line cap
(STRUCTURE §8.4; the leave ``leave``/``leave_config``/``leave_accrual`` precedent). The header
lifecycle mirrors the leave-request submit → approve / reject precedent (D-053) but approves at the
HEADER level (the SAP CATS model) — APPROVED is the value-bearing state: only approved entries feed
the allocation aggregates in ``time_allocation.py``.

``from __future__ import annotations`` keeps the model annotations strings at import.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.modules.hr.constants import TimesheetStatus
from app.modules.hr.models import Timesheet
from app.modules.hr.service.timesheets import get_timesheet


async def submit_timesheet(
    session: AsyncSession, tenant_id: uuid.UUID, timesheet_id: uuid.UUID
) -> Timesheet:
    """Submit a DRAFT timesheet (D-054): DRAFT → SUBMITTED, awaiting an approver. Stamps
    ``submitted_at``. Re-submitting a non-draft is a conflict."""
    timesheet = await get_timesheet(session, tenant_id, timesheet_id)
    if TimesheetStatus(timesheet.status) != TimesheetStatus.DRAFT:
        raise ConflictError(
            message="Only a draft timesheet can be submitted",
            code="hr.timesheet_not_draft",
            details={"status": timesheet.status},
        )
    timesheet.status = TimesheetStatus.SUBMITTED.value
    timesheet.submitted_at = datetime.now(UTC)
    await session.flush()
    return timesheet


async def approve_timesheet(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    timesheet_id: uuid.UUID,
    *,
    approved_by: uuid.UUID,
    notes: str | None = None,
) -> Timesheet:
    """Approve a SUBMITTED timesheet (D-054, the ``hr.timesheet.approve`` action): SUBMITTED →
    APPROVED. The value-bearing state — only APPROVED entries feed the allocation aggregates.
    Records the approver + approval time."""
    timesheet = await get_timesheet(session, tenant_id, timesheet_id)
    if TimesheetStatus(timesheet.status) != TimesheetStatus.SUBMITTED:
        raise ConflictError(
            message="Only a submitted timesheet can be approved",
            code="hr.timesheet_not_submitted",
            details={"status": timesheet.status},
        )
    timesheet.status = TimesheetStatus.APPROVED.value
    timesheet.approved_by = approved_by
    timesheet.approved_at = datetime.now(UTC)
    timesheet.notes = notes if notes is not None else timesheet.notes
    await session.flush()
    return timesheet


async def reject_timesheet(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    timesheet_id: uuid.UUID,
    *,
    approved_by: uuid.UUID,
    notes: str | None = None,
) -> Timesheet:
    """Reject a SUBMITTED timesheet (D-054): SUBMITTED → REJECTED. Records the decider + decision
    time."""
    timesheet = await get_timesheet(session, tenant_id, timesheet_id)
    if TimesheetStatus(timesheet.status) != TimesheetStatus.SUBMITTED:
        raise ConflictError(
            message="Only a submitted timesheet can be rejected",
            code="hr.timesheet_not_submitted",
            details={"status": timesheet.status},
        )
    timesheet.status = TimesheetStatus.REJECTED.value
    timesheet.approved_by = approved_by
    timesheet.approved_at = datetime.now(UTC)
    timesheet.notes = notes if notes is not None else timesheet.notes
    await session.flush()
    return timesheet


async def cancel_timesheet(
    session: AsyncSession, tenant_id: uuid.UUID, timesheet_id: uuid.UUID
) -> Timesheet:
    """Cancel (reopen to DRAFT) a SUBMITTED timesheet (D-054): SUBMITTED → DRAFT, so the filer can
    edit and re-submit. A DRAFT is already editable (no-op conflict); an APPROVED / REJECTED
    timesheet is terminal and cannot be reopened."""
    timesheet = await get_timesheet(session, tenant_id, timesheet_id)
    status = TimesheetStatus(timesheet.status)
    if status != TimesheetStatus.SUBMITTED:
        raise ConflictError(
            message="Only a submitted timesheet can be reopened to draft",
            code="hr.timesheet_not_cancellable",
            details={"status": timesheet.status},
        )
    timesheet.status = TimesheetStatus.DRAFT.value
    timesheet.submitted_at = None
    await session.flush()
    return timesheet
