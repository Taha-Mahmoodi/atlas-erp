"""Time allocation reporting (PLAN 10.3, D-054): set-based aggregates of APPROVED time hours by cost
centre or by project over a date range — the cost/project allocation deliverable.

These aggregates feed project costing in Phase 11 (``approved_hours_for_project`` in hr/queries is
the per-project hook projects will call) and CO reporting; here they produce the grouped report the
``GET /timesheets/allocation`` endpoint returns. ONLY entries of APPROVED timesheets count — DRAFT /
SUBMITTED / REJECTED time is provisional and must not feed costing (D-054).

A single GROUP-BY query per report (no per-row N+1) over the (tenant, cost_center_id) /
(tenant, project_id) indexes (PERFORMANCE §2). ``from __future__ import annotations`` keeps the
annotations strings at import.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.hr.constants import TimesheetStatus
from app.modules.hr.models import TimeEntry, Timesheet


async def _hours_grouped(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    dimension,  # noqa: ANN001 - an InstrumentedAttribute column (cost_center_id / project_id)
    date_from: date,
    date_to: date,
) -> list[tuple[uuid.UUID | None, Decimal]]:
    """SUM(hours) grouped by ``dimension`` over APPROVED time entries in [date_from, date_to]. One
    query; the unallocated bucket (NULL dimension) is included as a ``None`` key."""
    stmt = (
        select(dimension, func.coalesce(func.sum(TimeEntry.hours), 0))
        .join(Timesheet, Timesheet.id == TimeEntry.timesheet_id)
        .where(
            TimeEntry.tenant_id == tenant_id,
            Timesheet.status == TimesheetStatus.APPROVED.value,
            TimeEntry.entry_date >= date_from,
            TimeEntry.entry_date <= date_to,
        )
        .group_by(dimension)
        .order_by(dimension)
    )
    rows = (await session.execute(stmt)).all()
    return [(dim_id, Decimal(hours)) for dim_id, hours in rows]


async def hours_by_cost_center(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    date_from: date,
    date_to: date,
) -> list[tuple[uuid.UUID | None, Decimal]]:
    """APPROVED time hours grouped by cost centre over [date_from, date_to] (D-054). The
    CO-reporting allocation: a list of (cost_center_id, hours), the unallocated bucket keyed
    ``None``."""
    return await _hours_grouped(session, tenant_id, TimeEntry.cost_center_id, date_from, date_to)


async def hours_by_project(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    date_from: date,
    date_to: date,
) -> list[tuple[uuid.UUID | None, Decimal]]:
    """APPROVED time hours grouped by project over [date_from, date_to] (D-054). The project-costing
    allocation: a list of (project_id, hours), the unallocated bucket keyed ``None``. ``project_id``
    is the opaque projects-module id (Phase 11 will resolve it to a project name)."""
    return await _hours_grouped(session, tenant_id, TimeEntry.project_id, date_from, date_to)
