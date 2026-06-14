"""Reporting HTTP layer (thin): parse -> call service -> return schema (PLAN 13.1, D-058).

ONE surface at ``/api/v1/reporting``: a SINGLE role-based dashboard endpoint. The CLIENT makes ONE
call (PERFORMANCE §4: one screen ≤ 3 calls) and gets back every KPI it is permitted to see — the
endpoint is guarded by the base ``reporting.dashboard.read`` key (the price of admission) and the
service then gates each KPI by the SOURCE module's read permission (role-based, D-058), so the
response shape IS the caller's role.

NO ETag (PERFORMANCE §3, documented). KPI cards are LIVE figures (a posted journal / shipped
delivery changes them immediately), so a conditional-GET would serve stale numbers; the dashboard
is a read-only aggregate with no write, so it needs no uow either. A single guarded GET, no
pagination (it returns a fixed bundle, not a collection).
"""

from datetime import date

from fastapi import APIRouter, Depends

from app.core.deps import CurrentUserDep, SessionDep
from app.core.rbac import require_permission
from app.modules.reporting import service
from app.modules.reporting.constants import REPORTING_DASHBOARD_READ
from app.modules.reporting.schemas import DashboardResponse

router = APIRouter(prefix="/api/v1/reporting", tags=["reporting"])


@router.get(
    "/dashboard",
    response_model=DashboardResponse,
    response_model_exclude_none=True,
    dependencies=[Depends(require_permission(REPORTING_DASHBOARD_READ))],
)
async def get_dashboard(
    current: CurrentUserDep,
    session: SessionDep,
    as_of: date | None = None,
) -> DashboardResponse:
    """The role-based KPI dashboard (D-058): cash position, AR/AP aging, inventory value, open sales
    / purchase orders, OTD%, WIP — but ONLY the KPIs the caller's role permits (each gated by the
    source module's read permission). One call returns the whole permitted bundle; ``as_of`` bounds
    the date-bounded figures (cash / aging / WIP), defaulting to today. ``exclude_none`` drops the
    KPIs the caller may not see so the JSON carries only the role's cards."""
    return await service.dashboard_kpis(
        session, current.tenant_id, current.permissions, as_of=as_of
    )
