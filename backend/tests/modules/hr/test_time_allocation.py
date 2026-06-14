"""Time allocation aggregates (PLAN 10.3, D-054): ``hours_by_cost_center`` / ``hours_by_project``
and the ``approved_hours_for_*`` queries — set-based SUMs over APPROVED time entries only.

Driven through the real service under the tenant context (D-025). The key invariant: only entries of
APPROVED timesheets count; DRAFT / SUBMITTED time is provisional and must not feed costing.
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import tenant_context
from app.modules.finance import service as finance_service
from app.modules.finance.controlling_schemas import CostCenterCreate
from app.modules.hr import queries as hr_queries
from app.modules.hr import service
from tests.modules.hr.conftest import HrSetup
from tests.modules.hr.factories import build_employee, build_time_entry, build_timesheet

_APPROVER = uuid.uuid4()


async def _second_cost_center(session: AsyncSession, setup: HrSetup) -> uuid.UUID:
    with tenant_context(setup.tenant_id):
        center = await finance_service.create_cost_center(
            session, setup.tenant_id, CostCenterCreate(code="CC-2", name="Second")
        )
        await session.commit()
        return center.id


async def _approved_timesheet_with_entries(
    session: AsyncSession,
    setup: HrSetup,
    entries: list[dict],
    *,
    period_start: date = date(2026, 6, 1),
    period_end: date = date(2026, 6, 30),
) -> None:
    """An employee with an APPROVED timesheet carrying ``entries``."""
    employee = await build_employee(
        session, setup.tenant_id, employee_code=f"EMP-{uuid.uuid4().hex[:6]}"
    )
    timesheet = await build_timesheet(
        session,
        setup.tenant_id,
        employee_id=employee.id,
        period_start=period_start,
        period_end=period_end,
    )
    for entry in entries:
        await build_time_entry(session, setup.tenant_id, timesheet_id=timesheet.id, **entry)
    with tenant_context(setup.tenant_id):
        await service.submit_timesheet(session, setup.tenant_id, timesheet.id)
        await service.approve_timesheet(
            session, setup.tenant_id, timesheet.id, approved_by=_APPROVER
        )
        await session.commit()


async def test_hours_by_cost_center_sums_approved(
    db_session: AsyncSession, hr_setup: HrSetup
) -> None:
    cc_a = hr_setup.cost_center_id
    cc_b = await _second_cost_center(db_session, hr_setup)
    await _approved_timesheet_with_entries(
        db_session,
        hr_setup,
        [
            {"entry_date": date(2026, 6, 2), "hours": Decimal("8"), "cost_center_id": cc_a},
            {"entry_date": date(2026, 6, 3), "hours": Decimal("4"), "cost_center_id": cc_a},
            {"entry_date": date(2026, 6, 4), "hours": Decimal("6"), "cost_center_id": cc_b},
        ],
    )
    with tenant_context(hr_setup.tenant_id):
        rows = await service.hours_by_cost_center(
            db_session, hr_setup.tenant_id, date_from=date(2026, 6, 1), date_to=date(2026, 6, 30)
        )
    by_cc = dict(rows)
    assert by_cc[cc_a] == Decimal("12")
    assert by_cc[cc_b] == Decimal("6")


async def test_hours_by_project_sums_approved(
    db_session: AsyncSession, hr_setup: HrSetup
) -> None:
    proj_a = uuid.uuid4()
    proj_b = uuid.uuid4()
    await _approved_timesheet_with_entries(
        db_session,
        hr_setup,
        [
            {"entry_date": date(2026, 6, 2), "hours": Decimal("5"), "project_id": proj_a},
            {"entry_date": date(2026, 6, 3), "hours": Decimal("3"), "project_id": proj_a},
            {"entry_date": date(2026, 6, 4), "hours": Decimal("2"), "project_id": proj_b},
        ],
    )
    with tenant_context(hr_setup.tenant_id):
        rows = await service.hours_by_project(
            db_session, hr_setup.tenant_id, date_from=date(2026, 6, 1), date_to=date(2026, 6, 30)
        )
    by_proj = dict(rows)
    assert by_proj[proj_a] == Decimal("8")
    assert by_proj[proj_b] == Decimal("2")


async def test_only_approved_entries_count(
    db_session: AsyncSession, hr_setup: HrSetup
) -> None:
    """A DRAFT timesheet's entries must NOT feed the aggregate — only APPROVED time is costed."""
    cc = hr_setup.cost_center_id
    # An approved sheet contributing 8 hours.
    await _approved_timesheet_with_entries(
        db_session,
        hr_setup,
        [{"entry_date": date(2026, 6, 2), "hours": Decimal("8"), "cost_center_id": cc}],
    )
    # A DRAFT sheet (never submitted) with 100 hours on the same cost centre — excluded.
    employee = await build_employee(
        db_session, hr_setup.tenant_id, employee_code=f"EMP-{uuid.uuid4().hex[:6]}"
    )
    draft = await build_timesheet(
        db_session, hr_setup.tenant_id, employee_id=employee.id
    )
    await build_time_entry(
        db_session,
        hr_setup.tenant_id,
        timesheet_id=draft.id,
        hours=Decimal("100"),
        cost_center_id=cc,
    )
    with tenant_context(hr_setup.tenant_id):
        rows = await service.hours_by_cost_center(
            db_session, hr_setup.tenant_id, date_from=date(2026, 6, 1), date_to=date(2026, 6, 30)
        )
    assert dict(rows)[cc] == Decimal("8")


async def test_date_range_bounds_the_aggregate(
    db_session: AsyncSession, hr_setup: HrSetup
) -> None:
    cc = hr_setup.cost_center_id
    await _approved_timesheet_with_entries(
        db_session,
        hr_setup,
        [
            {"entry_date": date(2026, 6, 2), "hours": Decimal("8"), "cost_center_id": cc},
            {"entry_date": date(2026, 6, 20), "hours": Decimal("5"), "cost_center_id": cc},
        ],
    )
    with tenant_context(hr_setup.tenant_id):
        rows = await service.hours_by_cost_center(
            db_session, hr_setup.tenant_id, date_from=date(2026, 6, 1), date_to=date(2026, 6, 10)
        )
    assert dict(rows)[cc] == Decimal("8")  # the June-20 entry is outside the window


async def test_approved_hours_for_project_query(
    db_session: AsyncSession, hr_setup: HrSetup
) -> None:
    """The Phase-11 hook ``approved_hours_for_project`` returns the per-project approved total."""
    proj = uuid.uuid4()
    await _approved_timesheet_with_entries(
        db_session,
        hr_setup,
        [
            {"entry_date": date(2026, 6, 2), "hours": Decimal("7"), "project_id": proj},
            {"entry_date": date(2026, 6, 3), "hours": Decimal("3"), "project_id": proj},
        ],
    )
    with tenant_context(hr_setup.tenant_id):
        total = await hr_queries.approved_hours_for_project(
            db_session, hr_setup.tenant_id, proj
        )
    assert total == Decimal("10")


async def test_approved_hours_for_cost_center_query(
    db_session: AsyncSession, hr_setup: HrSetup
) -> None:
    cc = hr_setup.cost_center_id
    await _approved_timesheet_with_entries(
        db_session,
        hr_setup,
        [{"entry_date": date(2026, 6, 2), "hours": Decimal("9"), "cost_center_id": cc}],
    )
    with tenant_context(hr_setup.tenant_id):
        total = await hr_queries.approved_hours_for_cost_center(
            db_session, hr_setup.tenant_id, cc
        )
    assert total == Decimal("9")
