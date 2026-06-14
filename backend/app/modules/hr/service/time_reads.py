"""Timesheet reads (PLAN 10.3, D-054): the keyset-paginated timesheet list and the time-entry list
of one timesheet.

Split out of ``timesheets.py`` so the lifecycle file stays under the 400-line cap (the leave
``leave``/``leave_config`` precedent). ``from __future__ import annotations`` keeps ``Page[...]`` of
the ORM models a string at import.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import DEFAULT_LIMIT, OrderKey, SortDirection, filter_fingerprint, paginate
from app.core.schemas import Page
from app.modules.hr import queries as hr_queries
from app.modules.hr.models import TimeEntry, Timesheet
from app.modules.hr.service.timesheets import get_timesheet
from app.modules.hr.time_schemas import TimesheetFilter


async def list_timesheets(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    filters: TimesheetFilter,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Page[Timesheet]:
    """Keyset-paginated timesheets, newest period first (D-014). The employee / status /
    period-range filters fold into the cursor fingerprint; the (tenant, employee_id, status) index
    serves the filtered page (PERFORMANCE §6)."""
    stmt = select(Timesheet).where(Timesheet.tenant_id == tenant_id)
    if filters.employee_id is not None:
        stmt = stmt.where(Timesheet.employee_id == filters.employee_id)
    if filters.status is not None:
        stmt = stmt.where(Timesheet.status == filters.status)
    if filters.period_from is not None:
        stmt = stmt.where(Timesheet.period_start >= filters.period_from)
    if filters.period_to is not None:
        stmt = stmt.where(Timesheet.period_start <= filters.period_to)
    fingerprint = filter_fingerprint(
        filters.employee_id, filters.status, filters.period_from, filters.period_to
    )
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(Timesheet.period_start, SortDirection.DESC)],
        pk=Timesheet.id,
        cursor=cursor,
        limit=limit,
        filters=fingerprint,
    )


async def list_time_entries(
    session: AsyncSession, tenant_id: uuid.UUID, timesheet_id: uuid.UUID
) -> list[TimeEntry]:
    """The time-entry lines of one timesheet, ordered by entry_date (D-054). 404 if the timesheet
    does not exist (a clean error over the wire)."""
    await get_timesheet(session, tenant_id, timesheet_id)
    return await hr_queries.time_entries_for_timesheet(session, tenant_id, timesheet_id)
