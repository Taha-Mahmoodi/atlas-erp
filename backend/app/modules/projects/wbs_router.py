"""Projects WBS-element HTTP sub-router (thin): CRUD nested under a project + the tree (PLAN 11.1).

Mounted by ``router.py`` so it lives under ``/api/v1/projects`` — the WBS routes are nested as
``/projects/{project_id}/wbs-elements`` (the natural parent → children path). Every route is guarded
by a projects WBS permission key (D-009); writes commit through ``run_in_uow`` (D-011). The WBS list
of a project is reference data (the tree), so it carries a conditional-GET ETag (PERFORMANCE §3 /
D-035). A single WBS element is fetched by its own id (not nested) since its id is the costing
object key a posting tags.
"""

import uuid
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends, Request, Response

from app.core.conditional import collection_etag, conditional_response, request_fingerprint
from app.core.deps import CurrentUserDep, SessionDep
from app.core.events import run_in_uow
from app.core.pagination import CursorParams, cursor_params, map_page
from app.core.rbac import require_permission
from app.core.schemas import Page
from app.modules.projects import service
from app.modules.projects.constants import (
    PROJECTS_WBS_MANAGE,
    PROJECTS_WBS_READ,
    WbsStatus,
)
from app.modules.projects.models import WbsElement
from app.modules.projects.schemas import (
    WbsElementCreate,
    WbsElementFilter,
    WbsElementRead,
    WbsElementUpdate,
)

wbs_router = APIRouter()
_CursorParamsDep = Depends(cursor_params)


async def _commit[T](session: SessionDep, work: Callable[[], Awaitable[T]]) -> T:
    """Run a service call inside the D-011 uow, refreshing the ORM result so a sync
    ``model_validate`` never trips MissingGreenlet (the maintenance _commit twin)."""
    holder: list[T] = []

    async def _work() -> None:
        result = await work()
        await session.refresh(result)
        holder.append(result)

    await run_in_uow(session, _work)
    return holder[0]


@wbs_router.get(
    "/{project_id}/wbs-elements",
    response_model=Page[WbsElementRead],
    dependencies=[Depends(require_permission(PROJECTS_WBS_READ))],
)
async def list_wbs_elements(
    project_id: uuid.UUID,
    request: Request,
    response: Response,
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = _CursorParamsDep,
    status: WbsStatus | None = None,
) -> Page[WbsElementRead] | Response:
    """Conditional-GET supported (D-035): collection ETag over the project's WBS tree; the project
    id + status filter fold into the request fingerprint so a filtered 304 is correct."""
    filters = WbsElementFilter(status=status)
    fingerprint = request_fingerprint(params.cursor, params.limit, project_id, status)
    etag = await collection_etag(session, WbsElement, request_fingerprint=fingerprint)

    async def builder() -> Page[WbsElementRead]:
        page = await service.list_wbs_elements(
            session,
            current.tenant_id,
            project_id,
            filters=filters,
            cursor=params.cursor,
            limit=params.limit,
        )
        return map_page(page, WbsElementRead)

    return await conditional_response(request, response, etag, builder)


@wbs_router.post(
    "/{project_id}/wbs-elements",
    response_model=WbsElementRead,
    status_code=201,
    dependencies=[Depends(require_permission(PROJECTS_WBS_MANAGE))],
)
async def create_wbs_element(
    project_id: uuid.UUID,
    payload: WbsElementCreate,
    current: CurrentUserDep,
    session: SessionDep,
) -> WbsElementRead:
    element = await _commit(
        session,
        lambda: service.create_wbs_element(session, current.tenant_id, project_id, payload),
    )
    return WbsElementRead.model_validate(element)


@wbs_router.get(
    "/wbs-elements/{wbs_element_id}",
    response_model=WbsElementRead,
    dependencies=[Depends(require_permission(PROJECTS_WBS_READ))],
)
async def get_wbs_element(
    wbs_element_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> WbsElementRead:
    element = await service.get_wbs_element(session, current.tenant_id, wbs_element_id)
    return WbsElementRead.model_validate(element)


@wbs_router.patch(
    "/wbs-elements/{wbs_element_id}",
    response_model=WbsElementRead,
    dependencies=[Depends(require_permission(PROJECTS_WBS_MANAGE))],
)
async def update_wbs_element(
    wbs_element_id: uuid.UUID,
    payload: WbsElementUpdate,
    current: CurrentUserDep,
    session: SessionDep,
) -> WbsElementRead:
    element = await _commit(
        session,
        lambda: service.update_wbs_element(session, current.tenant_id, wbs_element_id, payload),
    )
    return WbsElementRead.model_validate(element)
