"""Timesheet header + time-entry management (PLAN 10.3, D-054): create a DRAFT timesheet, add /
update / remove time entries (DRAFT only) — with the maintained ``total_hours`` and the
project/cost-centre allocation.

The service layer owns every rule (CLAUDE.md rule 7); the router stays thin. The approval lifecycle
(submit → approve / reject, cancel) lives in ``timesheet_lifecycle.py`` (the leave
``leave``/``leave_config`` split precedent) — entries are frozen once the header leaves DRAFT.

THE ALLOCATION (the headline of 10.3, D-054):
- ``cost_center_id`` on a time entry is an OPAQUE finance cost-centre id VALIDATED via
  ``finance/queries.cost_center_exists`` when set (D-029) — a bad id is a 422.
- ``project_id`` is an OPAQUE projects-module id stored AS-IS and NOT validated in v1 — the projects
  module is Phase 11 (not yet built), so there is no table to validate against; the validation hook
  wires up when ``projects/queries`` exists (D-054). Do NOT create a forward dependency on projects.

THE MAINTAINED TOTAL. ``Timesheet.total_hours`` is kept in step with the sum of its entry ``hours``
on every line add / update / remove (a denormalized running total, the stock-balance precedent) so
the header carries the period total without a per-read aggregate.

The allocation REPORTING (set-based aggregates over APPROVED entries) lives in
``time_allocation.py``; reads + pagination live in ``time_reads.py``. ``from __future__ import
annotations`` keeps the model annotations strings at import.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.numbering import claim_number, ensure_sequence
from app.modules.finance import queries as finance_queries
from app.modules.hr import queries as hr_queries
from app.modules.hr.constants import (
    TIMESHEET_NUMBER_PADDING,
    TIMESHEET_NUMBER_PREFIX,
    TIMESHEET_SEQUENCE_NAME,
    TimesheetStatus,
)
from app.modules.hr.models import TimeEntry, Timesheet
from app.modules.hr.time_schemas import (
    TimeEntryCreate,
    TimeEntryUpdate,
    TimesheetCreate,
    TimesheetUpdate,
)

# --- Loads + guards -----------------------------------------------------------


async def get_timesheet(
    session: AsyncSession, tenant_id: uuid.UUID, timesheet_id: uuid.UUID
) -> Timesheet:
    timesheet = await session.get(Timesheet, timesheet_id)
    if timesheet is None or timesheet.tenant_id != tenant_id:
        raise NotFoundError(message="Timesheet not found", code="hr.timesheet_not_found")
    return timesheet


async def get_time_entry(
    session: AsyncSession, tenant_id: uuid.UUID, entry_id: uuid.UUID
) -> TimeEntry:
    entry = await session.get(TimeEntry, entry_id)
    if entry is None or entry.tenant_id != tenant_id:
        raise NotFoundError(message="Time entry not found", code="hr.time_entry_not_found")
    return entry


def _require_draft(timesheet: Timesheet) -> None:
    """Lines are editable only while the header is a DRAFT (D-054)."""
    if TimesheetStatus(timesheet.status) != TimesheetStatus.DRAFT:
        raise ConflictError(
            message="Only a draft timesheet can be edited",
            code="hr.timesheet_not_draft",
            details={"status": timesheet.status},
        )


def _validate_period(period_start: date, period_end: date) -> None:
    if period_end < period_start:
        raise ValidationFailedError(
            message="The period end cannot be before the period start",
            code="hr.timesheet_period_invalid",
            details={"period_start": str(period_start), "period_end": str(period_end)},
        )


def _validate_entry_in_period(timesheet: Timesheet, entry_date: date, hours: Decimal) -> None:
    if not (timesheet.period_start <= entry_date <= timesheet.period_end):
        raise ValidationFailedError(
            message="The entry date must fall within the timesheet period",
            code="hr.time_entry_date_out_of_period",
            details={
                "entry_date": str(entry_date),
                "period_start": str(timesheet.period_start),
                "period_end": str(timesheet.period_end),
            },
        )
    if hours <= 0:
        raise ValidationFailedError(
            message="Time-entry hours must be greater than zero",
            code="hr.time_entry_hours_invalid",
            details={"hours": str(hours)},
        )


async def _validate_cost_center(
    session: AsyncSession, tenant_id: uuid.UUID, cost_center_id: uuid.UUID | None
) -> None:
    """A supplied cost-centre id must exist in finance (D-029) — VALIDATED via finance/queries (the
    department cost-centre precedent). ``project_id`` is deliberately NOT validated here: the
    projects module is Phase 11 (D-054)."""
    if cost_center_id is None:
        return
    if not await finance_queries.cost_center_exists(session, tenant_id, cost_center_id):
        raise ValidationFailedError(
            message="Referenced cost centre does not exist",
            code="hr.cost_center_not_found",
            details={"cost_center_id": str(cost_center_id)},
        )


# --- Timesheet header ---------------------------------------------------------


async def create_timesheet(
    session: AsyncSession, tenant_id: uuid.UUID, payload: TimesheetCreate
) -> Timesheet:
    """Open a DRAFT timesheet for an employee over a period (D-054). Validates the employee exists
    and ``period_end >= period_start``; claims a gapless ``TS-`` number at creation. Rejects a
    duplicate (employee, period_start). No entries yet — ``total_hours`` starts at 0."""
    if not await hr_queries.employee_exists(session, tenant_id, payload.employee_id):
        raise ValidationFailedError(
            message="Referenced employee does not exist",
            code="hr.employee_not_found",
            details={"employee_id": str(payload.employee_id)},
        )
    _validate_period(payload.period_start, payload.period_end)
    if await _timesheet_for_period(session, tenant_id, payload.employee_id, payload.period_start):
        raise ConflictError(
            message="A timesheet for this employee and period already exists",
            code="hr.timesheet_period_conflict",
            details={
                "employee_id": str(payload.employee_id),
                "period_start": str(payload.period_start),
            },
        )

    await ensure_sequence(
        session,
        tenant_id,
        TIMESHEET_SEQUENCE_NAME,
        TIMESHEET_NUMBER_PREFIX,
        TIMESHEET_NUMBER_PADDING,
        year_reset=True,
    )
    number = await claim_number(
        session, tenant_id, TIMESHEET_SEQUENCE_NAME, on_date=payload.period_start
    )
    timesheet = Timesheet(
        tenant_id=tenant_id,
        timesheet_number=number,
        employee_id=payload.employee_id,
        period_start=payload.period_start,
        period_end=payload.period_end,
        status=TimesheetStatus.DRAFT.value,
        total_hours=Decimal(0),
        notes=payload.notes,
    )
    session.add(timesheet)
    await session.flush()
    return timesheet


async def _timesheet_for_period(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    period_start: date,
) -> bool:
    """Whether a timesheet already exists for (employee, period_start) — the UNIQUE-guard probe."""
    stmt = select(Timesheet.id).where(
        Timesheet.tenant_id == tenant_id,
        Timesheet.employee_id == employee_id,
        Timesheet.period_start == period_start,
    )
    return (await session.execute(stmt)).first() is not None


async def update_timesheet(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    timesheet_id: uuid.UUID,
    payload: TimesheetUpdate,
) -> Timesheet:
    """Partial update of a DRAFT timesheet header (D-054). Only a draft is editable; ``employee_id``
    is immutable. A changed period is re-validated and must still contain every existing entry."""
    timesheet = await get_timesheet(session, tenant_id, timesheet_id)
    _require_draft(timesheet)
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(timesheet, field, value)
    _validate_period(timesheet.period_start, timesheet.period_end)
    if "period_start" in data or "period_end" in data:
        await _assert_entries_within_period(session, tenant_id, timesheet)
    await session.flush()
    return timesheet


async def _assert_entries_within_period(
    session: AsyncSession, tenant_id: uuid.UUID, timesheet: Timesheet
) -> None:
    """A narrowed period must not orphan an existing entry's ``entry_date`` (D-054)."""
    entries = await hr_queries.time_entries_for_timesheet(session, tenant_id, timesheet.id)
    for entry in entries:
        if not (timesheet.period_start <= entry.entry_date <= timesheet.period_end):
            raise ValidationFailedError(
                message="An existing time entry falls outside the new period",
                code="hr.time_entry_date_out_of_period",
                details={
                    "entry_date": str(entry.entry_date),
                    "period_start": str(timesheet.period_start),
                    "period_end": str(timesheet.period_end),
                },
            )


# --- Time entries (DRAFT only; maintain total_hours) --------------------------


async def add_time_entry(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    timesheet_id: uuid.UUID,
    payload: TimeEntryCreate,
) -> TimeEntry:
    """Add a time-entry line to a DRAFT timesheet (D-054). Validates the date is in the period,
    hours > 0, and the cost centre exists if set; ``project_id`` is stored AS-IS (NOT validated —
    projects is Phase 11). Raises the header ``total_hours`` by the entry hours."""
    timesheet = await get_timesheet(session, tenant_id, timesheet_id)
    _require_draft(timesheet)
    _validate_entry_in_period(timesheet, payload.entry_date, payload.hours)
    await _validate_cost_center(session, tenant_id, payload.cost_center_id)
    entry = TimeEntry(
        tenant_id=tenant_id,
        timesheet_id=timesheet_id,
        entry_date=payload.entry_date,
        hours=payload.hours,
        project_id=payload.project_id,
        cost_center_id=payload.cost_center_id,
        task_description=payload.task_description,
        is_billable=payload.is_billable,
    )
    session.add(entry)
    timesheet.total_hours += payload.hours
    await session.flush()
    return entry


async def update_time_entry(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    timesheet_id: uuid.UUID,
    entry_id: uuid.UUID,
    payload: TimeEntryUpdate,
) -> TimeEntry:
    """Partial update of a time entry on a DRAFT timesheet (D-054). A changed date is re-validated
    against the period; a changed cost centre is re-validated; a changed hours adjusts the header
    ``total_hours`` by the delta."""
    timesheet = await get_timesheet(session, tenant_id, timesheet_id)
    _require_draft(timesheet)
    entry = await get_time_entry(session, tenant_id, entry_id)
    if entry.timesheet_id != timesheet_id:
        raise NotFoundError(
            message="Time entry does not belong to this timesheet",
            code="hr.time_entry_not_found",
        )
    data = payload.model_dump(exclude_unset=True)
    old_hours = entry.hours
    if "cost_center_id" in data:
        await _validate_cost_center(session, tenant_id, data["cost_center_id"])
    for field, value in data.items():
        setattr(entry, field, value)
    _validate_entry_in_period(timesheet, entry.entry_date, entry.hours)
    if entry.hours != old_hours:
        timesheet.total_hours += entry.hours - old_hours
    await session.flush()
    return entry


async def remove_time_entry(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    timesheet_id: uuid.UUID,
    entry_id: uuid.UUID,
) -> None:
    """Delete a time entry from a DRAFT timesheet (D-054). Lowers the header ``total_hours`` by the
    removed entry's hours."""
    timesheet = await get_timesheet(session, tenant_id, timesheet_id)
    _require_draft(timesheet)
    entry = await get_time_entry(session, tenant_id, entry_id)
    if entry.timesheet_id != timesheet_id:
        raise NotFoundError(
            message="Time entry does not belong to this timesheet",
            code="hr.time_entry_not_found",
        )
    timesheet.total_hours -= entry.hours
    await session.delete(entry)
    await session.flush()
