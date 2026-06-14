"""HR time-tracking request/response schemas (Pydantic v2, ApiModel base) for PLAN 10.3, D-054.

Split out of ``schemas.py`` (the 10.1/10.2 schemas) so each schema file stays under the 400-line cap
(STRUCTURE §8.4; the finance ``*_schemas.py`` sibling-file precedent). Create/Update/Read/Filter for
the ``Timesheet`` header and the ``TimeEntry`` lines, the approve/reject decision payload, and the
allocation report (the cost/project allocation deliverable).

Money / hour amounts are ``Decimal`` strings (D-015). A timesheet number is immutable so it is
absent from the Update schema. The Read schemas carry the server-derived fields (number, totals,
timestamps, approver).
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from app.core.schemas import ApiModel
from app.modules.hr.constants import TimesheetStatus

# --- Timesheet ----------------------------------------------------------------


class TimesheetCreate(ApiModel):
    """Open a DRAFT timesheet for an employee over a period. The employee must exist in the tenant;
    ``period_end`` >= ``period_start`` (validated in the service); a gapless ``TS-`` number is
    claimed at creation. One timesheet per (employee, period_start). Time entries are added through
    the nested time-entry sub-resource once the header exists."""

    employee_id: uuid.UUID
    period_start: date
    period_end: date
    notes: str | None = None


class TimesheetUpdate(ApiModel):
    """Partial update of a DRAFT timesheet's header (only a draft is editable). ``employee_id`` is
    immutable (absent). A changed period is re-validated (``end >= start``) and must still contain
    every existing entry's ``entry_date``. All fields optional — only the set ones change."""

    period_start: date | None = None
    period_end: date | None = None
    notes: str | None = None


class TimesheetRead(ApiModel):
    id: uuid.UUID
    timesheet_number: str
    employee_id: uuid.UUID
    period_start: date
    period_end: date
    status: TimesheetStatus
    total_hours: Decimal
    submitted_at: datetime | None
    approved_at: datetime | None
    approved_by: uuid.UUID | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class TimesheetFilter(ApiModel):
    """List filters. None means "no constraint"; folded into the cursor's filter fingerprint so a
    cursor cannot cross filtered views. ``period_from`` / ``period_to`` bound the header period
    (period_start within the range)."""

    employee_id: uuid.UUID | None = None
    status: TimesheetStatus | None = None
    period_from: date | None = None
    period_to: date | None = None


class TimesheetDecision(ApiModel):
    """The approve/reject decision payload (PLAN 10.3): ``notes`` is the optional decision note the
    approver records. The endpoint splits approve vs reject (distinct routes), so the route carries
    the verb."""

    notes: str | None = None


# --- Time entry ---------------------------------------------------------------


class TimeEntryCreate(ApiModel):
    """Record a time-entry line on a DRAFT timesheet. ``entry_date`` must fall within the header
    period; ``hours`` > 0 (a Decimal string, D-015). THE ALLOCATION: ``project_id`` is an OPAQUE
    projects-module id, stored as-is and NOT validated in v1 (projects is Phase 11, D-054);
    ``cost_center_id`` is an OPAQUE finance cost-centre id VALIDATED against finance when set
    (D-029). ``is_billable`` flags billable work."""

    entry_date: date
    hours: Decimal
    project_id: uuid.UUID | None = None
    cost_center_id: uuid.UUID | None = None
    task_description: str | None = None
    is_billable: bool = False


class TimeEntryUpdate(ApiModel):
    """Partial update of a time-entry line (only while the timesheet is a DRAFT). A changed
    ``entry_date`` is re-validated against the period; a changed ``cost_center_id`` is re-validated
    against finance; a changed ``hours`` must stay > 0. All fields optional — only the set ones
    change (exclude_unset)."""

    entry_date: date | None = None
    hours: Decimal | None = None
    project_id: uuid.UUID | None = None
    cost_center_id: uuid.UUID | None = None
    task_description: str | None = None
    is_billable: bool | None = None


class TimeEntryRead(ApiModel):
    id: uuid.UUID
    timesheet_id: uuid.UUID
    entry_date: date
    hours: Decimal
    project_id: uuid.UUID | None
    cost_center_id: uuid.UUID | None
    task_description: str | None
    is_billable: bool
    created_at: datetime
    updated_at: datetime


# --- Allocation report --------------------------------------------------------


class AllocationDimension(StrEnum):
    """The dimension the allocation report groups APPROVED time by (PLAN 10.3): COST_CENTER or
    PROJECT — the cost/project allocation deliverable feeding project costing (Phase 11) + CO
    reporting."""

    COST_CENTER = "cost_center"
    PROJECT = "project"


class AllocationRow(ApiModel):
    """One row of the allocation report: a dimension id (cost-centre or project id; ``None`` for the
    unallocated bucket) and the summed APPROVED ``hours`` for it over the requested date range."""

    dimension_id: uuid.UUID | None
    hours: Decimal


class AllocationReport(ApiModel):
    """The allocation report: APPROVED time hours grouped ``by`` cost centre or project over the
    [``date_from``, ``date_to``] entry-date range (PLAN 10.3, D-054)."""

    by: AllocationDimension
    date_from: date
    date_to: date
    rows: list[AllocationRow]
