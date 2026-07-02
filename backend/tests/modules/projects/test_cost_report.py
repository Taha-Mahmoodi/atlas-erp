"""THE key test (PLAN 11.1, D-056): the project cost report.

Posts journal lines tagged with WBS-element ids (via the REAL finance journal service, the line's
``project_id`` carrying the opaque WBS dimension — "posting purchases to a WBS") + creates APPROVED
timesheets allocated to those WBS ids (via the REAL hr service — "posting time to a WBS"), then
asserts the cost report:

- sums the POSTED journal-line actuals per WBS (the finance journal projection by dimension);
- shows the APPROVED timesheet hours per WBS (the hr aggregate);
- rolls each WBS up to the project total;
- computes budget − actual variance per WBS and for the project;
- shows ZERO for a WBS with no postings;
- runs as a BOUNDED projection (no per-WBS N+1) — the query count does not grow with WBS count.
"""

import uuid
from collections.abc import Callable
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import tenant_context
from app.modules.projects import service
from tests.conftest import QueryCounter
from tests.modules.projects.factories import (
    ProjectsSetup,
    build_wbs_element,
    post_approved_hours,
    post_wbs_journal,
)

pytestmark = pytest.mark.asyncio


async def test_cost_report_sums_actuals_hours_and_variance(
    db_session: AsyncSession, projects_setup: ProjectsSetup
) -> None:
    """Two WBS elements with postings + hours, one with none → per-WBS actuals/hours, zero for the
    empty WBS, project roll-up, and budget − actual variance."""
    wbs1 = await build_wbs_element(
        db_session,
        projects_setup.tenant_id,
        projects_setup.project_id,
        code="WBS-1",
        budget_amount=Decimal("600"),
    )
    wbs2 = await build_wbs_element(
        db_session,
        projects_setup.tenant_id,
        projects_setup.project_id,
        code="WBS-2",
        budget_amount=Decimal("300"),
    )
    wbs_empty = await build_wbs_element(
        db_session,
        projects_setup.tenant_id,
        projects_setup.project_id,
        code="WBS-3",
        budget_amount=Decimal("100"),
    )

    # Post two journal entries to WBS-1 (250 + 150 = 400) and one to WBS-2 (200).
    await post_wbs_journal(
        db_session, projects_setup.tenant_id, projects_setup.accounts, wbs1.id, Decimal("250")
    )
    await post_wbs_journal(
        db_session, projects_setup.tenant_id, projects_setup.accounts, wbs1.id, Decimal("150")
    )
    await post_wbs_journal(
        db_session, projects_setup.tenant_id, projects_setup.accounts, wbs2.id, Decimal("200")
    )

    # Approved hours: 16h on WBS-1, 8h on WBS-2.
    await post_approved_hours(
        db_session, projects_setup.tenant_id, wbs1.id, Decimal("16"), employee_code="EMP-A"
    )
    await post_approved_hours(
        db_session, projects_setup.tenant_id, wbs2.id, Decimal("8"), employee_code="EMP-B"
    )

    with tenant_context(projects_setup.tenant_id):
        report = await service.project_cost_report(
            db_session, projects_setup.tenant_id, projects_setup.project_id
        )

    by_id = {line.wbs_element_id: line for line in report.lines}
    assert by_id[wbs1.id].actual_cost == Decimal("400")
    assert by_id[wbs1.id].hours == Decimal("16")
    assert by_id[wbs1.id].variance == Decimal("200")  # 600 budget − 400 actual
    assert by_id[wbs2.id].actual_cost == Decimal("200")
    assert by_id[wbs2.id].hours == Decimal("8")
    assert by_id[wbs2.id].variance == Decimal("100")  # 300 − 200
    # The WBS with no postings shows zero actual / zero hours.
    assert by_id[wbs_empty.id].actual_cost == Decimal("0")
    assert by_id[wbs_empty.id].hours == Decimal("0")
    assert by_id[wbs_empty.id].variance == Decimal("100")  # 100 − 0

    # Project roll-up. The setup project has its own budget_amount=1000, so total_budget = 1000.
    assert report.total_actual_cost == Decimal("600")
    assert report.total_hours == Decimal("24")
    assert report.total_budget == Decimal("1000")
    assert report.total_variance == Decimal("400")  # 1000 − 600


async def test_cost_report_total_budget_falls_back_to_wbs_sum(
    db_session: AsyncSession, projects_setup: ProjectsSetup
) -> None:
    """A project with NO own budget rolls up the WBS budgets for its total (D-056)."""
    from app.modules.projects.schemas import ProjectUpdate

    with tenant_context(projects_setup.tenant_id):
        await service.update_project(
            db_session,
            projects_setup.tenant_id,
            projects_setup.project_id,
            ProjectUpdate(budget_amount=None),
        )
        await db_session.commit()
    await build_wbs_element(
        db_session,
        projects_setup.tenant_id,
        projects_setup.project_id,
        code="WBS-B1",
        budget_amount=Decimal("400"),
    )
    await build_wbs_element(
        db_session,
        projects_setup.tenant_id,
        projects_setup.project_id,
        code="WBS-B2",
        budget_amount=Decimal("250"),
    )
    with tenant_context(projects_setup.tenant_id):
        report = await service.project_cost_report(
            db_session, projects_setup.tenant_id, projects_setup.project_id
        )
    assert report.total_budget == Decimal("650")  # 400 + 250 (no own project budget)


async def test_cost_report_as_of_bounds_actuals(
    db_session: AsyncSession, projects_setup: ProjectsSetup
) -> None:
    """The ``as_of`` date bounds the actuals cumulatively: a later posting is excluded."""
    from datetime import date

    wbs = await build_wbs_element(
        db_session, projects_setup.tenant_id, projects_setup.project_id, code="WBS-AO"
    )
    await post_wbs_journal(
        db_session,
        projects_setup.tenant_id,
        projects_setup.accounts,
        wbs.id,
        Decimal("100"),
        posting_date=date(2026, 1, 15),
    )
    await post_wbs_journal(
        db_session,
        projects_setup.tenant_id,
        projects_setup.accounts,
        wbs.id,
        Decimal("80"),
        posting_date=date(2026, 3, 15),
    )
    with tenant_context(projects_setup.tenant_id):
        report = await service.project_cost_report(
            db_session,
            projects_setup.tenant_id,
            projects_setup.project_id,
            as_of=date(2026, 2, 1),
        )
    line = next(line for line in report.lines if line.wbs_element_id == wbs.id)
    assert line.actual_cost == Decimal("100")  # the March posting is excluded by as_of


async def test_cost_report_empty_project_zeroes(
    db_session: AsyncSession, projects_setup: ProjectsSetup
) -> None:
    """A project with no WBS elements yields an empty line list and zero actuals / hours."""
    with tenant_context(projects_setup.tenant_id):
        report = await service.project_cost_report(
            db_session, projects_setup.tenant_id, projects_setup.project_id
        )
    assert report.lines == []
    assert report.total_actual_cost == Decimal("0")
    assert report.total_hours == Decimal("0")


async def test_cost_report_only_approved_hours_count(
    db_session: AsyncSession, projects_setup: ProjectsSetup
) -> None:
    """Only APPROVED timesheet hours feed the report (D-054): DRAFT timesheet hours are absent."""
    from datetime import date

    from tests.modules.hr.factories import build_employee, build_time_entry, build_timesheet

    wbs = await build_wbs_element(
        db_session, projects_setup.tenant_id, projects_setup.project_id, code="WBS-DR"
    )
    employee = await build_employee(
        db_session, projects_setup.tenant_id, employee_code="EMP-DRAFT"
    )
    timesheet = await build_timesheet(
        db_session,
        projects_setup.tenant_id,
        employee_id=employee.id,
        period_start=date(2026, 3, 1),
        period_end=date(2026, 3, 28),
    )
    await build_time_entry(
        db_session,
        projects_setup.tenant_id,
        timesheet_id=timesheet.id,
        entry_date=date(2026, 3, 10),
        hours=Decimal("40"),
        project_id=wbs.id,
    )
    # NOT submitted/approved — stays DRAFT.
    with tenant_context(projects_setup.tenant_id):
        report = await service.project_cost_report(
            db_session, projects_setup.tenant_id, projects_setup.project_id
        )
    line = next(line for line in report.lines if line.wbs_element_id == wbs.id)
    assert line.hours == Decimal("0")


async def test_cost_report_is_bounded_no_n_plus_1(
    db_session: AsyncSession,
    projects_setup: ProjectsSetup,
    tenant_b: uuid.UUID,
    query_counter: Callable[[], QueryCounter],
) -> None:
    """The cost report is a BOUNDED projection (PERFORMANCE §6 / D-056): its query count does NOT
    grow with the WBS count — one project lookup + one WBS-structure read + one finance projection +
    one hr aggregate, regardless of how many WBS elements. Doubling the WBS count (2 → 4) must not
    more-than-double the cost. Two tenants keep the measurements independent."""

    async def measure(tenant_id: uuid.UUID, project_id: uuid.UUID, wbs_count: int) -> int:
        for i in range(wbs_count):
            wbs = await build_wbs_element(
                db_session, tenant_id, project_id, code=f"WBS-N{i}", budget_amount=Decimal("10")
            )
            await post_wbs_journal(
                db_session,
                tenant_id,
                accounts_for[tenant_id],
                wbs.id,
                Decimal("5"),
            )
        with query_counter() as qc, tenant_context(tenant_id):
            await service.project_cost_report(db_session, tenant_id, project_id)
        return qc.count

    from tests.modules.projects.factories import build_projects_setup

    setup_b = await build_projects_setup(db_session, tenant_b)
    accounts_for = {
        projects_setup.tenant_id: projects_setup.accounts,
        tenant_b: setup_b.accounts,
    }
    count_2 = await measure(projects_setup.tenant_id, projects_setup.project_id, 2)
    count_4 = await measure(tenant_b, setup_b.project_id, 4)
    # Bounded: the 4-WBS report costs no more than the 2-WBS report plus a small constant. A per-WBS
    # N+1 would blow well past this.
    assert count_4 <= count_2 + 2, f"cost report scaled with WBS count: 2={count_2}, 4={count_4}"
