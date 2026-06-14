"""Timesheet HTTP layer (PLAN 10.3, D-054), included into the hr router.

A sibling sub-router under the same ``/api/v1/hr`` prefix, mounted by ``router.include_router`` in
router.py (the leave-router precedent — ONE module surface at ``/api/v1/hr``, no second mount in
main.py). REST:

- timesheets: CRUD + submit / approve / reject / cancel; a filtered, paginated list
  (employee / status / period range).
- nested time entries: ``GET/POST /timesheets/{id}/time-entries`` + ``DELETE
  /timesheets/{id}/time-entries/{entry_id}`` (a PATCH to update a line) — editable only while the
  timesheet is a DRAFT.
- allocation report: ``GET /timesheets/allocation?by=cost_center|project&from=&to=`` — APPROVED
  time hours grouped by the dimension over the entry-date range (the cost/project allocation
  deliverable).

RBAC (D-009; the manage vs approve split, the leave precedent): timesheets + entries + the report
are read by ``hr.timesheet.read``; create / edit-draft-entries / submit / cancel by
``hr.timesheet.manage``; approve / reject by the DISTINCT ``hr.timesheet.approve`` key. Writes
commit through ``run_in_uow`` (D-011) so audit rows ride the transaction; create / submit / approve
/ reject are IDEMPOTENT (D-013). PERFORMANCE §6: lists are O(1) queries + paginated; the allocation
report is one GROUP-BY query.

``allocation`` is declared BEFORE ``/{timesheet_id}`` so the literal path is matched first.
"""

import uuid
from collections.abc import Awaitable, Callable
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.core.deps import CurrentUserDep, SessionDep
from app.core.events import run_in_uow
from app.core.idempotency import Idempotent, IdempotentDep
from app.core.pagination import CursorParams, cursor_params, map_page
from app.core.rbac import require_permission
from app.core.schemas import Page
from app.modules.hr import service
from app.modules.hr.constants import (
    HR_TIMESHEET_APPROVE,
    HR_TIMESHEET_MANAGE,
    HR_TIMESHEET_READ,
    TimesheetStatus,
)
from app.modules.hr.time_schemas import (
    AllocationDimension,
    AllocationReport,
    AllocationRow,
    TimeEntryCreate,
    TimeEntryRead,
    TimeEntryUpdate,
    TimesheetCreate,
    TimesheetDecision,
    TimesheetFilter,
    TimesheetRead,
    TimesheetUpdate,
)

timesheet_router = APIRouter(tags=["hr-timesheets"])
_CursorParamsDep = Depends(cursor_params)
_CreateIdem = Depends(Idempotent("hr.timesheet.create"))
_SubmitIdem = Depends(Idempotent("hr.timesheet.submit"))
_ApproveIdem = Depends(Idempotent("hr.timesheet.approve"))
_RejectIdem = Depends(Idempotent("hr.timesheet.reject"))


async def _commit_timesheet(
    session: SessionDep, work: Callable[[], Awaitable[object]]
) -> TimesheetRead:
    """Run a timesheet service call inside the D-011 uow and return it refreshed + validated in the
    async context (the hr _commit_read twin)."""
    holder: dict[str, TimesheetRead] = {}

    async def _work() -> None:
        timesheet = await work()
        await session.refresh(timesheet)
        holder["read"] = TimesheetRead.model_validate(timesheet)

    await run_in_uow(session, _work)
    return holder["read"]


# --- Allocation report (declared first so the literal path wins over /{id}) ----


@timesheet_router.get(
    "/timesheets/allocation",
    response_model=AllocationReport,
    dependencies=[Depends(require_permission(HR_TIMESHEET_READ))],
)
async def timesheet_allocation(
    current: CurrentUserDep,
    session: SessionDep,
    by: AllocationDimension,
    date_from: Annotated[date, Query(alias="from")],
    date_to: Annotated[date, Query(alias="to")],
) -> AllocationReport:
    """APPROVED time hours grouped ``by`` cost centre or project over [from, to] (PLAN 10.3): the
    cost/project allocation report. One GROUP-BY query (PERFORMANCE §2)."""
    if by == AllocationDimension.COST_CENTER:
        grouped = await service.hours_by_cost_center(
            session, current.tenant_id, date_from=date_from, date_to=date_to
        )
    else:
        grouped = await service.hours_by_project(
            session, current.tenant_id, date_from=date_from, date_to=date_to
        )
    return AllocationReport(
        by=by,
        date_from=date_from,
        date_to=date_to,
        rows=[AllocationRow(dimension_id=dim_id, hours=hours) for dim_id, hours in grouped],
    )


# --- Timesheets ---------------------------------------------------------------


@timesheet_router.post(
    "/timesheets",
    response_model=TimesheetRead,
    status_code=201,
    dependencies=[Depends(require_permission(HR_TIMESHEET_MANAGE))],
)
async def create_timesheet(
    payload: TimesheetCreate,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _CreateIdem,
) -> TimesheetRead:
    """Open a DRAFT timesheet for an employee over a period (PLAN 10.3). IDEMPOTENT (D-013)."""
    holder: dict[str, TimesheetRead] = {}

    async def work() -> None:
        timesheet = await service.create_timesheet(session, current.tenant_id, payload)
        await session.refresh(timesheet)
        holder["read"] = await idem.capture(TimesheetRead.model_validate(timesheet))

    await run_in_uow(session, work)
    return holder["read"]


@timesheet_router.get(
    "/timesheets",
    response_model=Page[TimesheetRead],
    dependencies=[Depends(require_permission(HR_TIMESHEET_READ))],
)
async def list_timesheets(
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = _CursorParamsDep,
    employee_id: uuid.UUID | None = None,
    status: TimesheetStatus | None = None,
    period_from: date | None = None,
    period_to: date | None = None,
) -> Page[TimesheetRead]:
    """Paginated timesheets, newest period first (PLAN 10.3). Filters: employee / status / period
    range (on period_start)."""
    filters = TimesheetFilter(
        employee_id=employee_id,
        status=status,
        period_from=period_from,
        period_to=period_to,
    )
    page = await service.list_timesheets(
        session, current.tenant_id, filters=filters, cursor=params.cursor, limit=params.limit
    )
    return map_page(page, TimesheetRead)


@timesheet_router.get(
    "/timesheets/{timesheet_id}",
    response_model=TimesheetRead,
    dependencies=[Depends(require_permission(HR_TIMESHEET_READ))],
)
async def get_timesheet(
    timesheet_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> TimesheetRead:
    timesheet = await service.get_timesheet(session, current.tenant_id, timesheet_id)
    return TimesheetRead.model_validate(timesheet)


@timesheet_router.patch(
    "/timesheets/{timesheet_id}",
    response_model=TimesheetRead,
    dependencies=[Depends(require_permission(HR_TIMESHEET_MANAGE))],
)
async def update_timesheet(
    timesheet_id: uuid.UUID,
    payload: TimesheetUpdate,
    current: CurrentUserDep,
    session: SessionDep,
) -> TimesheetRead:
    return await _commit_timesheet(
        session,
        lambda: service.update_timesheet(session, current.tenant_id, timesheet_id, payload),
    )


# --- Nested time entries ------------------------------------------------------


@timesheet_router.get(
    "/timesheets/{timesheet_id}/time-entries",
    response_model=list[TimeEntryRead],
    dependencies=[Depends(require_permission(HR_TIMESHEET_READ))],
)
async def list_time_entries(
    timesheet_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> list[TimeEntryRead]:
    """The time-entry lines of one timesheet (PLAN 10.3). 404 if the timesheet does not exist."""
    entries = await service.list_time_entries(session, current.tenant_id, timesheet_id)
    return [TimeEntryRead.model_validate(e) for e in entries]


@timesheet_router.post(
    "/timesheets/{timesheet_id}/time-entries",
    response_model=TimeEntryRead,
    status_code=201,
    dependencies=[Depends(require_permission(HR_TIMESHEET_MANAGE))],
)
async def add_time_entry(
    timesheet_id: uuid.UUID,
    payload: TimeEntryCreate,
    current: CurrentUserDep,
    session: SessionDep,
) -> TimeEntryRead:
    """Record a time-entry line on a DRAFT timesheet (PLAN 10.3): date-in-period + hours > 0 +
    cost-centre-exists-if-set; ``project_id`` stored as-is (NOT validated — projects is Phase 11).
    Raises the header ``total_hours``."""
    holder: dict[str, TimeEntryRead] = {}

    async def work() -> None:
        entry = await service.add_time_entry(session, current.tenant_id, timesheet_id, payload)
        await session.refresh(entry)
        holder["read"] = TimeEntryRead.model_validate(entry)

    await run_in_uow(session, work)
    return holder["read"]


@timesheet_router.patch(
    "/timesheets/{timesheet_id}/time-entries/{entry_id}",
    response_model=TimeEntryRead,
    dependencies=[Depends(require_permission(HR_TIMESHEET_MANAGE))],
)
async def update_time_entry(
    timesheet_id: uuid.UUID,
    entry_id: uuid.UUID,
    payload: TimeEntryUpdate,
    current: CurrentUserDep,
    session: SessionDep,
) -> TimeEntryRead:
    """Update a time-entry line on a DRAFT timesheet (PLAN 10.3). Adjusts ``total_hours`` by the
    hours delta."""
    holder: dict[str, TimeEntryRead] = {}

    async def work() -> None:
        entry = await service.update_time_entry(
            session, current.tenant_id, timesheet_id, entry_id, payload
        )
        await session.refresh(entry)
        holder["read"] = TimeEntryRead.model_validate(entry)

    await run_in_uow(session, work)
    return holder["read"]


@timesheet_router.delete(
    "/timesheets/{timesheet_id}/time-entries/{entry_id}",
    status_code=204,
    dependencies=[Depends(require_permission(HR_TIMESHEET_MANAGE))],
)
async def remove_time_entry(
    timesheet_id: uuid.UUID,
    entry_id: uuid.UUID,
    current: CurrentUserDep,
    session: SessionDep,
) -> Response:
    """Delete a time-entry line from a DRAFT timesheet (PLAN 10.3). Lowers ``total_hours``."""

    async def work() -> None:
        await service.remove_time_entry(session, current.tenant_id, timesheet_id, entry_id)

    await run_in_uow(session, work)
    return Response(status_code=204)


# --- Lifecycle ----------------------------------------------------------------


@timesheet_router.post(
    "/timesheets/{timesheet_id}/submit",
    response_model=TimesheetRead,
    dependencies=[Depends(require_permission(HR_TIMESHEET_MANAGE))],
)
async def submit_timesheet(
    timesheet_id: uuid.UUID,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _SubmitIdem,
) -> TimesheetRead:
    """Submit a DRAFT timesheet for approval (PLAN 10.3). IDEMPOTENT (D-013)."""
    holder: dict[str, TimesheetRead] = {}

    async def work() -> None:
        timesheet = await service.submit_timesheet(session, current.tenant_id, timesheet_id)
        await session.refresh(timesheet)
        holder["read"] = await idem.capture(TimesheetRead.model_validate(timesheet))

    await run_in_uow(session, work)
    return holder["read"]


@timesheet_router.post(
    "/timesheets/{timesheet_id}/approve",
    response_model=TimesheetRead,
    dependencies=[Depends(require_permission(HR_TIMESHEET_APPROVE))],
)
async def approve_timesheet(
    timesheet_id: uuid.UUID,
    payload: TimesheetDecision,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _ApproveIdem,
) -> TimesheetRead:
    """Approve a SUBMITTED timesheet (PLAN 10.3, the ``hr.timesheet.approve`` action): its entries
    become eligible for the allocation aggregates. IDEMPOTENT (D-013)."""
    holder: dict[str, TimesheetRead] = {}

    async def work() -> None:
        timesheet = await service.approve_timesheet(
            session,
            current.tenant_id,
            timesheet_id,
            approved_by=current.user_id,
            notes=payload.notes,
        )
        await session.refresh(timesheet)
        holder["read"] = await idem.capture(TimesheetRead.model_validate(timesheet))

    await run_in_uow(session, work)
    return holder["read"]


@timesheet_router.post(
    "/timesheets/{timesheet_id}/reject",
    response_model=TimesheetRead,
    dependencies=[Depends(require_permission(HR_TIMESHEET_APPROVE))],
)
async def reject_timesheet(
    timesheet_id: uuid.UUID,
    payload: TimesheetDecision,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _RejectIdem,
) -> TimesheetRead:
    """Reject a SUBMITTED timesheet (PLAN 10.3). IDEMPOTENT (D-013)."""
    holder: dict[str, TimesheetRead] = {}

    async def work() -> None:
        timesheet = await service.reject_timesheet(
            session,
            current.tenant_id,
            timesheet_id,
            approved_by=current.user_id,
            notes=payload.notes,
        )
        await session.refresh(timesheet)
        holder["read"] = await idem.capture(TimesheetRead.model_validate(timesheet))

    await run_in_uow(session, work)
    return holder["read"]


@timesheet_router.post(
    "/timesheets/{timesheet_id}/cancel",
    response_model=TimesheetRead,
    dependencies=[Depends(require_permission(HR_TIMESHEET_MANAGE))],
)
async def cancel_timesheet(
    timesheet_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> TimesheetRead:
    """Reopen a SUBMITTED timesheet to DRAFT (PLAN 10.3) so the filer can edit and re-submit."""
    return await _commit_timesheet(
        session, lambda: service.cancel_timesheet(session, current.tenant_id, timesheet_id)
    )
