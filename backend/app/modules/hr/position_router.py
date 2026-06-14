"""Position HTTP layer (PLAN 10.1), included into the hr router.

A sibling sub-router under the same ``/api/v1/hr`` prefix. REST: position CRUD + a filtered,
paginated list with a conditional-GET ETag (positions are reference data — PERFORMANCE §3 / D-035).

RBAC (D-009): read by ``hr.position.read``; create/edit by ``hr.position.manage``. Writes commit
through ``run_in_uow`` (D-011). The list is O(1) queries + paginated (PERFORMANCE §6).
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
from app.modules.hr import service
from app.modules.hr.constants import HR_POSITION_MANAGE, HR_POSITION_READ
from app.modules.hr.models import Position
from app.modules.hr.schemas import (
    PositionCreate,
    PositionFilter,
    PositionRead,
    PositionUpdate,
)

position_router = APIRouter(tags=["hr-positions"])
_CursorParamsDep = Depends(cursor_params)


async def _commit_read[T](
    session: SessionDep, work: Callable[[], Awaitable[object]]
) -> PositionRead:
    """Run a service call inside the D-011 uow and return the position refreshed + validated in the
    async context (the maintenance _commit twin)."""
    holder: dict[str, PositionRead] = {}

    async def _work() -> None:
        position = await work()
        await session.refresh(position)
        holder["read"] = PositionRead.model_validate(position)

    await run_in_uow(session, _work)
    return holder["read"]


@position_router.post(
    "/positions",
    response_model=PositionRead,
    status_code=201,
    dependencies=[Depends(require_permission(HR_POSITION_MANAGE))],
)
async def create_position(
    payload: PositionCreate, current: CurrentUserDep, session: SessionDep
) -> PositionRead:
    return await _commit_read(
        session, lambda: service.create_position(session, current.tenant_id, payload)
    )


@position_router.get(
    "/positions",
    response_model=Page[PositionRead],
    dependencies=[Depends(require_permission(HR_POSITION_READ))],
)
async def list_positions(
    request: Request,
    response: Response,
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = _CursorParamsDep,
    is_active: bool | None = None,
    department_id: uuid.UUID | None = None,
) -> Page[PositionRead] | Response:
    """Conditional-GET supported (D-035): the is_active / department filters fold into the
    fingerprint so a filtered 304 is correct."""
    fingerprint = request_fingerprint(params.cursor, params.limit, is_active, department_id)
    etag = await collection_etag(session, Position, request_fingerprint=fingerprint)

    async def builder() -> Page[PositionRead]:
        page = await service.list_positions(
            session,
            current.tenant_id,
            filters=PositionFilter(is_active=is_active, department_id=department_id),
            cursor=params.cursor,
            limit=params.limit,
        )
        return map_page(page, PositionRead)

    return await conditional_response(request, response, etag, builder)


@position_router.get(
    "/positions/{position_id}",
    response_model=PositionRead,
    dependencies=[Depends(require_permission(HR_POSITION_READ))],
)
async def get_position(
    position_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> PositionRead:
    position = await service.get_position(session, current.tenant_id, position_id)
    return PositionRead.model_validate(position)


@position_router.patch(
    "/positions/{position_id}",
    response_model=PositionRead,
    dependencies=[Depends(require_permission(HR_POSITION_MANAGE))],
)
async def update_position(
    position_id: uuid.UUID,
    payload: PositionUpdate,
    current: CurrentUserDep,
    session: SessionDep,
) -> PositionRead:
    return await _commit_read(
        session,
        lambda: service.update_position(session, current.tenant_id, position_id, payload),
    )
