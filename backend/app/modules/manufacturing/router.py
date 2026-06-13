"""Manufacturing HTTP layer (thin): parse -> call service -> return schema (PLAN 8.1).

REST under ``/api/v1/manufacturing``: work-centres (CRUD + filtered list) here, with the BOM surface
(``bom_router``) and the routing surface (``routing_router``) mounted as sibling sub-routers at the
foot of this file so the whole module stays ONE surface at ``/api/v1/manufacturing`` — the finance
journal_router / inventory stock_router include precedent (no second mount in main.py). Every route
is guarded by a manufacturing permission key (D-009); writes commit through ``run_in_uow`` (D-011)
so audit rows ride the same transaction. The work-centre list is reference data, so it carries a
conditional-GET ETag (PERFORMANCE §3 / D-035).
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
from app.modules.manufacturing import service
from app.modules.manufacturing.bom_router import bom_router
from app.modules.manufacturing.constants import (
    MFG_WORKCENTER_MANAGE,
    MFG_WORKCENTER_READ,
)
from app.modules.manufacturing.models import WorkCenter
from app.modules.manufacturing.routing_router import routing_router
from app.modules.manufacturing.schemas import (
    WorkCenterCreate,
    WorkCenterFilter,
    WorkCenterRead,
    WorkCenterUpdate,
)

router = APIRouter(prefix="/api/v1/manufacturing", tags=["manufacturing"])
_CursorParamsDep = Depends(cursor_params)


async def _commit[T](session: SessionDep, work: Callable[[], Awaitable[T]]) -> T:
    """Run a service call inside the D-011 uow, refreshing the ORM result in the async context so a
    sync ``model_validate`` never trips MissingGreenlet (the inventory _commit twin)."""
    holder: list[T] = []

    async def _work() -> None:
        result = await work()
        await session.refresh(result)
        holder.append(result)

    await run_in_uow(session, _work)
    return holder[0]


@router.get(
    "/work-centers",
    response_model=Page[WorkCenterRead],
    dependencies=[Depends(require_permission(MFG_WORKCENTER_READ))],
)
async def list_work_centers(
    request: Request,
    response: Response,
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = _CursorParamsDep,
    is_active: bool | None = None,
) -> Page[WorkCenterRead] | Response:
    """Conditional-GET supported (D-035): collection ETag over the work-centre reference list; the
    active filter folds into the request fingerprint so a filtered 304 is correct."""
    filters = WorkCenterFilter(is_active=is_active)
    fingerprint = request_fingerprint(params.cursor, params.limit, is_active)
    etag = await collection_etag(session, WorkCenter, request_fingerprint=fingerprint)

    async def builder() -> Page[WorkCenterRead]:
        page = await service.list_work_centers(
            session,
            current.tenant_id,
            filters=filters,
            cursor=params.cursor,
            limit=params.limit,
        )
        return map_page(page, WorkCenterRead)

    return await conditional_response(request, response, etag, builder)


@router.post(
    "/work-centers",
    response_model=WorkCenterRead,
    status_code=201,
    dependencies=[Depends(require_permission(MFG_WORKCENTER_MANAGE))],
)
async def create_work_center(
    payload: WorkCenterCreate, current: CurrentUserDep, session: SessionDep
) -> WorkCenterRead:
    work_center = await _commit(
        session, lambda: service.create_work_center(session, current.tenant_id, payload)
    )
    return WorkCenterRead.model_validate(work_center)


@router.get(
    "/work-centers/{work_center_id}",
    response_model=WorkCenterRead,
    dependencies=[Depends(require_permission(MFG_WORKCENTER_READ))],
)
async def get_work_center(
    work_center_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> WorkCenterRead:
    work_center = await service.get_work_center(session, current.tenant_id, work_center_id)
    return WorkCenterRead.model_validate(work_center)


@router.patch(
    "/work-centers/{work_center_id}",
    response_model=WorkCenterRead,
    dependencies=[Depends(require_permission(MFG_WORKCENTER_MANAGE))],
)
async def update_work_center(
    work_center_id: uuid.UUID,
    payload: WorkCenterUpdate,
    current: CurrentUserDep,
    session: SessionDep,
) -> WorkCenterRead:
    work_center = await _commit(
        session,
        lambda: service.update_work_center(session, current.tenant_id, work_center_id, payload),
    )
    return WorkCenterRead.model_validate(work_center)


# The BOM surface (boms + nested components) and the routing surface (routings + nested operations)
# are sibling sub-routers mounted here, so the whole module is ONE surface at /api/v1/manufacturing.
router.include_router(bom_router)
router.include_router(routing_router)
