"""Reporting HTTP layer (thin): parse -> call service/builder -> return schema (PLAN 13.1/13.2,
D-058/D-059).

ONE surface at ``/api/v1/reporting`` with two areas: the role-based KPI DASHBOARD (13.1) and the
ad-hoc REPORT BUILDER (13.2). Both are ROLE-BASED — guarded by a base reporting key (the price of
admission) then gated per KPI / per reportable entity by the SOURCE module's read permission, so the
response shape IS the caller's role.

THE REPORT-BUILDER ROUTES (D-059):
- ``GET  /reports/entities`` — the whitelist catalog, filtered to the entities the caller's role
  permits (so a UI builds a role-correct picker). Base perm: ``reporting.report.run``.
- ``POST /reports/run``     — body = ReportSpec → ReportResult JSON for the grid (capped 10k).
- ``POST /reports/export``  — same spec → a STREAMING CSV response (PERFORMANCE §3, lazy, never
  materialized). Both require ``reporting.report.run`` AND the named entity's source permission
  (enforced in-handler since the entity is in the body, 403 ``rbac.permission_denied``).

NO ETag (PERFORMANCE §3, documented). KPI cards + report results are LIVE figures, so a
conditional-GET would serve stale numbers; both areas are read-only with no write, so no uow.
"""

from datetime import date

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.core.deps import CurrentUserDep, SessionDep
from app.core.exceptions import PermissionDeniedError
from app.core.rbac import require_permission
from app.modules.reporting import report_builder, service
from app.modules.reporting.constants import REPORTING_DASHBOARD_READ, REPORTING_REPORT_RUN
from app.modules.reporting.report_registry import get_entity, list_entities
from app.modules.reporting.schemas import (
    DashboardResponse,
    ReportEntityDescriptor,
    ReportEntityList,
    ReportResult,
    ReportSpec,
)

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


# --- Report builder (PLAN 13.2, D-059) ----------------------------------------


def _require_entity_permission(spec: ReportSpec, current: CurrentUserDep) -> None:
    """Gate the named entity by its SOURCE module's read permission (role-based, D-059) — a finance
    role can only report on finance entities, etc. The entity is in the body, so this runs in the
    handler, not as a route dependency. An unknown entity is left to the builder's 400; a known
    entity the caller lacks the source permission for is 403 ``rbac.permission_denied``."""
    entity = get_entity(spec.entity)
    if entity is not None and entity.source_permission not in current.permissions:
        raise PermissionDeniedError(
            code="rbac.permission_denied",
            message=f"Missing permission: {entity.source_permission}",
            details={"permission": entity.source_permission},
        )


@router.get(
    "/reports/entities",
    response_model=ReportEntityList,
    dependencies=[Depends(require_permission(REPORTING_REPORT_RUN))],
)
async def list_report_entities(current: CurrentUserDep) -> ReportEntityList:
    """The report-builder whitelist catalog (D-059), filtered to the entities the caller's role
    permits (each gated by its source read permission) so a UI builds a role-correct picker. Base
    perm ``reporting.report.run``; the per-entity source perm decides what appears."""
    entities = [
        ReportEntityDescriptor(
            key=entity.key,
            label=entity.label,
            columns=[
                {
                    "name": name,
                    "label": column.label,
                    "type": column.type,
                    "filterable": column.filterable,
                    "groupable": column.groupable,
                    "is_aggregatable": column.is_aggregatable,
                }
                for name, column in entity.columns.items()
            ],
        )
        for entity in list_entities()
        if entity.source_permission in current.permissions
    ]
    return ReportEntityList(entities=entities)


@router.post(
    "/reports/run",
    response_model=ReportResult,
    dependencies=[Depends(require_permission(REPORTING_REPORT_RUN))],
)
async def run_report(
    spec: ReportSpec, current: CurrentUserDep, session: SessionDep
) -> ReportResult:
    """Run an ad-hoc report (D-059): validate the spec against the whitelist, build the ORM select
    with typed binds (no injection), run it tenant-filtered (D-007 auto-scopes), cap at 10k rows,
    return the JSON grid. Needs ``reporting.report.run`` AND the entity's source read permission."""
    _require_entity_permission(spec, current)
    return await report_builder.run_report(session, spec)


@router.post(
    "/reports/export",
    dependencies=[Depends(require_permission(REPORTING_REPORT_RUN))],
)
async def export_report(
    spec: ReportSpec, current: CurrentUserDep, session: SessionDep
) -> StreamingResponse:
    """Export an ad-hoc report as STREAMING CSV (D-059, PERFORMANCE §3): the same spec as
    ``/reports/run`` but the rows are generated lazily and streamed (never materialized in memory),
    so a result larger than the 10k JSON cap is served here. Same RBAC as run."""
    _require_entity_permission(spec, current)
    # Validate the spec eagerly so a malformed report is a 400 BEFORE the streaming body starts (a
    # 200 then a mid-stream error would be unrecoverable for the client). The builder's generator
    # re-validates, but this surfaces the error as a normal envelope response.
    report_builder.validate_spec(spec)
    return StreamingResponse(
        report_builder.stream_report_csv(session, spec),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{spec.entity}.csv"'},
    )
