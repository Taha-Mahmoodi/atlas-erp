"""The project cost report (PLAN 11.1, D-056): a BOUNDED projection over the universal journal +
approved timesheet hours + the simple budget.

For a project the report shows, per WBS element: ``budget`` (the element's ``budget_amount``),
``actual_cost`` (the sum of POSTED journal lines tagged with that WBS-element id — the opaque
project dimension, via ``finance/queries.costs_by_project_dimension``), ``hours`` (approved hours
allocated to that WBS id, via ``hr/queries.approved_hours_by_project``) and ``variance`` (budget −
actual). The lines roll up to a project total. The WBS element id IS the costing object the postings
carry (D-056); projects posts nothing — it READS the journal projection + the hr aggregate DOWNWARD
(STRUCTURE §5 / D-029), keeping finance/hr at the bottom of the dependency order.

PERFORMANCE §6 — the report is BOUNDED, never N+1: it loads the project's WBS structure ONCE
(``wbs_elements_for_project``), then runs ONE finance projection over ALL the WBS ids and ONE hr
aggregate over ALL the WBS ids — three queries total regardless of WBS count (plus the project
lookup). The per-WBS roll-up is pure in-memory dict lookups.
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.finance import queries as finance_queries
from app.modules.hr import queries as hr_queries
from app.modules.projects import queries as projects_queries
from app.modules.projects.schemas import ProjectCostReport, WbsCostLine
from app.modules.projects.service.projects import get_project


async def project_cost_report(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    project_id: uuid.UUID,
    *,
    as_of: date | None = None,
) -> ProjectCostReport:
    """Build the cost report for one project (D-056). 404 if the project is missing / cross-tenant.

    ``as_of`` (optional) bounds the actuals cumulatively to that posting date; omit for all the
    postings. ``total_budget`` is the project's own ``budget_amount`` when set, else the sum of the
    WBS budgets (so a project that budgets at the WBS level still gets a project-level variance);
    ``total_variance`` = total_budget − total_actual_cost."""
    project = await get_project(session, tenant_id, project_id)
    elements = await projects_queries.wbs_elements_for_project(session, tenant_id, project_id)
    wbs_ids = [element.id for element in elements]

    # ONE finance projection + ONE hr aggregate over ALL the WBS ids (PERFORMANCE §6: no per-WBS
    # N+1). Both return only the ids that have data; an element with none defaults to zero below.
    actuals = await finance_queries.costs_by_project_dimension(
        session, tenant_id, wbs_ids, date_to=as_of
    )
    hours = await hr_queries.approved_hours_by_project(
        session, tenant_id, wbs_ids, date_to=as_of
    )

    lines: list[WbsCostLine] = []
    total_actual = Decimal(0)
    total_hours = Decimal(0)
    sum_of_wbs_budgets = Decimal(0)
    for element in elements:
        budget = element.budget_amount if element.budget_amount is not None else Decimal(0)
        actual = actuals.get(element.id, Decimal(0))
        element_hours = hours.get(element.id, Decimal(0))
        sum_of_wbs_budgets += budget
        total_actual += actual
        total_hours += element_hours
        lines.append(
            WbsCostLine(
                wbs_element_id=element.id,
                code=element.code,
                name=element.name,
                status=element.status,
                parent_id=element.parent_id,
                budget_amount=budget,
                actual_cost=actual,
                hours=element_hours,
                variance=budget - actual,
            )
        )

    total_budget = (
        project.budget_amount if project.budget_amount is not None else sum_of_wbs_budgets
    )
    return ProjectCostReport(
        project_id=project.id,
        project_code=project.code,
        project_name=project.name,
        project_status=project.status,
        as_of_date=as_of,
        total_budget=total_budget,
        total_actual_cost=total_actual,
        total_hours=total_hours,
        total_variance=total_budget - total_actual,
        lines=lines,
    )
