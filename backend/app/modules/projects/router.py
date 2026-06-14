"""Projects HTTP layer (thin): parse -> call service -> return schema (PLAN 11.1).

REST under ``/api/v1/projects``: projects (CRUD + filtered list + the cost report) here, with the
WBS-element surface (``wbs_router``, nested under a project) mounted as a sibling sub-router at the
foot of this file so the whole module is ONE surface at ``/api/v1/projects`` — the maintenance
order_router / plan_router include precedent (no second mount in main.py). Every route is guarded by
a projects permission key (D-009); writes commit through ``run_in_uow`` (D-011) so audit rows ride
the same transaction. The project list is reference data, so it carries a conditional-GET ETag
(PERFORMANCE §3 / D-035). The cost report is a bounded journal projection (PERFORMANCE §6 / D-056) —
guarded by the dedicated ``projects.report.read`` key.
"""

import uuid
from collections.abc import Awaitable, Callable
from datetime import date

from fastapi import APIRouter, Depends, Request, Response

from app.core.conditional import collection_etag, conditional_response, request_fingerprint
from app.core.deps import CurrentUserDep, SessionDep
from app.core.events import run_in_uow
from app.core.pagination import CursorParams, cursor_params, map_page
from app.core.rbac import require_permission
from app.core.schemas import Page
from app.modules.projects import service
from app.modules.projects.constants import (
    PROJECTS_PROJECT_MANAGE,
    PROJECTS_PROJECT_READ,
    PROJECTS_REPORT_READ,
    ProjectStatus,
)
from app.modules.projects.models import Project
from app.modules.projects.schemas import (
    ProjectCostReport,
    ProjectCreate,
    ProjectFilter,
    ProjectRead,
    ProjectUpdate,
)
from app.modules.projects.wbs_router import wbs_router

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])
_CursorParamsDep = Depends(cursor_params)


async def _commit[T](session: SessionDep, work: Callable[[], Awaitable[T]]) -> T:
    """Run a service call inside the D-011 uow, refreshing the ORM result in the async context so a
    sync ``model_validate`` never trips MissingGreenlet (the maintenance _commit twin)."""
    holder: list[T] = []

    async def _work() -> None:
        result = await work()
        await session.refresh(result)
        holder.append(result)

    await run_in_uow(session, _work)
    return holder[0]


@router.get(
    "",
    response_model=Page[ProjectRead],
    dependencies=[Depends(require_permission(PROJECTS_PROJECT_READ))],
)
async def list_projects(
    request: Request,
    response: Response,
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = _CursorParamsDep,
    status: ProjectStatus | None = None,
) -> Page[ProjectRead] | Response:
    """Conditional-GET supported (D-035): collection ETag over the project reference list; the
    status filter folds into the request fingerprint so a filtered 304 is correct."""
    filters = ProjectFilter(status=status)
    fingerprint = request_fingerprint(params.cursor, params.limit, status)
    etag = await collection_etag(session, Project, request_fingerprint=fingerprint)

    async def builder() -> Page[ProjectRead]:
        page = await service.list_projects(
            session,
            current.tenant_id,
            filters=filters,
            cursor=params.cursor,
            limit=params.limit,
        )
        return map_page(page, ProjectRead)

    return await conditional_response(request, response, etag, builder)


@router.post(
    "",
    response_model=ProjectRead,
    status_code=201,
    dependencies=[Depends(require_permission(PROJECTS_PROJECT_MANAGE))],
)
async def create_project(
    payload: ProjectCreate, current: CurrentUserDep, session: SessionDep
) -> ProjectRead:
    project = await _commit(
        session, lambda: service.create_project(session, current.tenant_id, payload)
    )
    return ProjectRead.model_validate(project)


@router.get(
    "/{project_id}",
    response_model=ProjectRead,
    dependencies=[Depends(require_permission(PROJECTS_PROJECT_READ))],
)
async def get_project(
    project_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> ProjectRead:
    project = await service.get_project(session, current.tenant_id, project_id)
    return ProjectRead.model_validate(project)


@router.patch(
    "/{project_id}",
    response_model=ProjectRead,
    dependencies=[Depends(require_permission(PROJECTS_PROJECT_MANAGE))],
)
async def update_project(
    project_id: uuid.UUID,
    payload: ProjectUpdate,
    current: CurrentUserDep,
    session: SessionDep,
) -> ProjectRead:
    project = await _commit(
        session,
        lambda: service.update_project(session, current.tenant_id, project_id, payload),
    )
    return ProjectRead.model_validate(project)


@router.get(
    "/{project_id}/cost-report",
    response_model=ProjectCostReport,
    dependencies=[Depends(require_permission(PROJECTS_REPORT_READ))],
)
async def get_cost_report(
    project_id: uuid.UUID,
    current: CurrentUserDep,
    session: SessionDep,
    as_of: date | None = None,
) -> ProjectCostReport:
    """The project cost report (D-056): per-WBS actuals (finance journal projection) + approved
    hours (hr) + budget variance, rolled up to the project. A bounded projection (PERFORMANCE §6) —
    read via finance/hr queries, not their services. ``as_of`` bounds the actuals cumulatively."""
    return await service.project_cost_report(
        session, current.tenant_id, project_id, as_of=as_of
    )


# The WBS-element surface (CRUD nested under a project + the tree) is a sibling sub-router mounted
# here, so the whole module is ONE surface at /api/v1/projects.
router.include_router(wbs_router)
