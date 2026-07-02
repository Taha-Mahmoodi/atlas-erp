"""Routing HTTP layer (thin): parse -> call service -> return schema (PLAN 8.1).

A sibling sub-router mounted into the module router (the bom_router precedent). REST under the
``/api/v1/manufacturing`` prefix: routing header CRUD + filtered list, activate/deactivate, and the
nested operations GET/POST/DELETE. Every route is guarded by a manufacturing permission key (D-009);
writes commit through ``run_in_uow`` (D-011). The routing list carries a conditional-GET ETag
(PERFORMANCE §3 / D-035) with the item/status filters in the fingerprint.
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
from app.modules.manufacturing.constants import (
    MFG_ROUTING_MANAGE,
    MFG_ROUTING_READ,
    RoutingStatus,
)
from app.modules.manufacturing.models import Routing
from app.modules.manufacturing.schemas import (
    RoutingCreate,
    RoutingOperationCreate,
    RoutingOperationRead,
    RoutingRead,
    RoutingUpdate,
)

routing_router = APIRouter()
_CursorParamsDep = Depends(cursor_params)


async def _commit[T](session: SessionDep, work: Callable[[], Awaitable[T]]) -> T:
    """Run a service call inside the D-011 uow, refreshing the ORM result in the async context (the
    bom_router _commit twin)."""
    holder: list[T] = []

    async def _work() -> None:
        result = await work()
        await session.refresh(result)
        holder.append(result)

    await run_in_uow(session, _work)
    return holder[0]


@routing_router.get(
    "/routings",
    response_model=Page[RoutingRead],
    dependencies=[Depends(require_permission(MFG_ROUTING_READ))],
)
async def list_routings(
    request: Request,
    response: Response,
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = _CursorParamsDep,
    item_id: uuid.UUID | None = None,
    status: RoutingStatus | None = None,
) -> Page[RoutingRead] | Response:
    """Conditional-GET supported (D-035): the item/status filters fold into the fingerprint."""
    fingerprint = request_fingerprint(params.cursor, params.limit, item_id, status)
    etag = await collection_etag(session, Routing, request_fingerprint=fingerprint)

    async def builder() -> Page[RoutingRead]:
        page = await service.list_routings(
            session,
            current.tenant_id,
            item_id=item_id,
            status=status,
            cursor=params.cursor,
            limit=params.limit,
        )
        return map_page(page, RoutingRead)

    return await conditional_response(request, response, etag, builder)


@routing_router.post(
    "/routings",
    response_model=RoutingRead,
    status_code=201,
    dependencies=[Depends(require_permission(MFG_ROUTING_MANAGE))],
)
async def create_routing(
    payload: RoutingCreate, current: CurrentUserDep, session: SessionDep
) -> RoutingRead:
    routing = await _commit(
        session, lambda: service.create_routing(session, current.tenant_id, payload)
    )
    return RoutingRead.model_validate(routing)


@routing_router.get(
    "/routings/{routing_id}",
    response_model=RoutingRead,
    dependencies=[Depends(require_permission(MFG_ROUTING_READ))],
)
async def get_routing(
    routing_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> RoutingRead:
    routing = await service.get_routing(session, current.tenant_id, routing_id)
    return RoutingRead.model_validate(routing)


@routing_router.patch(
    "/routings/{routing_id}",
    response_model=RoutingRead,
    dependencies=[Depends(require_permission(MFG_ROUTING_MANAGE))],
)
async def update_routing(
    routing_id: uuid.UUID,
    payload: RoutingUpdate,
    current: CurrentUserDep,
    session: SessionDep,
) -> RoutingRead:
    routing = await _commit(
        session, lambda: service.update_routing(session, current.tenant_id, routing_id, payload)
    )
    return RoutingRead.model_validate(routing)


@routing_router.post(
    "/routings/{routing_id}/activate",
    response_model=RoutingRead,
    dependencies=[Depends(require_permission(MFG_ROUTING_MANAGE))],
)
async def activate_routing(
    routing_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> RoutingRead:
    """Activate a DRAFT routing — it becomes the item's ACTIVE default and is frozen (D-047)."""
    routing = await _commit(
        session, lambda: service.activate_routing(session, current.tenant_id, routing_id)
    )
    return RoutingRead.model_validate(routing)


@routing_router.post(
    "/routings/{routing_id}/deactivate",
    response_model=RoutingRead,
    dependencies=[Depends(require_permission(MFG_ROUTING_MANAGE))],
)
async def deactivate_routing(
    routing_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> RoutingRead:
    """Deactivate an ACTIVE routing — it becomes INACTIVE and the item loses its active default."""
    routing = await _commit(
        session, lambda: service.deactivate_routing(session, current.tenant_id, routing_id)
    )
    return RoutingRead.model_validate(routing)


# --- Operations (nested under a routing) --------------------------------------


@routing_router.get(
    "/routings/{routing_id}/operations",
    response_model=list[RoutingOperationRead],
    dependencies=[Depends(require_permission(MFG_ROUTING_READ))],
)
async def list_routing_operations(
    routing_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> list[RoutingOperationRead]:
    await service.get_routing(session, current.tenant_id, routing_id)  # 404 if absent
    operations = await service.routing_operations_for(session, current.tenant_id, routing_id)
    return [RoutingOperationRead.model_validate(operation) for operation in operations]


@routing_router.post(
    "/routings/{routing_id}/operations",
    response_model=RoutingOperationRead,
    status_code=201,
    dependencies=[Depends(require_permission(MFG_ROUTING_MANAGE))],
)
async def add_routing_operation(
    routing_id: uuid.UUID,
    payload: RoutingOperationCreate,
    current: CurrentUserDep,
    session: SessionDep,
) -> RoutingOperationRead:
    operation = await _commit(
        session, lambda: service.add_operation(session, current.tenant_id, routing_id, payload)
    )
    return RoutingOperationRead.model_validate(operation)


@routing_router.delete(
    "/routings/{routing_id}/operations/{operation_id}",
    status_code=204,
    dependencies=[Depends(require_permission(MFG_ROUTING_MANAGE))],
)
async def delete_routing_operation(
    routing_id: uuid.UUID,
    operation_id: uuid.UUID,
    current: CurrentUserDep,
    session: SessionDep,
) -> Response:
    async def _work() -> None:
        await service.delete_operation(session, current.tenant_id, routing_id, operation_id)

    await run_in_uow(session, _work)
    return Response(status_code=204)
