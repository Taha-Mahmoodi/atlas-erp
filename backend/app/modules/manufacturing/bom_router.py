"""BOM HTTP layer (thin): parse -> call service -> return schema (PLAN 8.1).

A sibling sub-router (mounted into the module router) so each router file stays under the STRUCTURE
§3 400-line cap — the finance ap_router / inventory stock_router include precedent. REST under the
``/api/v1/manufacturing`` prefix the parent router owns: BOM header CRUD + filtered list, the
activate/deactivate actions, and the nested components GET/POST/DELETE. Every route is guarded by a
manufacturing permission key (D-009). Writes commit through ``run_in_uow`` (D-011) so audit rows
ride the same transaction; results are validated into their Read schema AFTER the uow commits.

The BOM list is semi-reference data, so it carries a conditional-GET ETag (PERFORMANCE §3 / D-035)
with the item/status filters folded into the request fingerprint.
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
from app.modules.manufacturing.constants import MFG_BOM_MANAGE, MFG_BOM_READ, BomStatus
from app.modules.manufacturing.models import Bom
from app.modules.manufacturing.schemas import (
    BomComponentCreate,
    BomComponentRead,
    BomCreate,
    BomRead,
    BomUpdate,
)

bom_router = APIRouter()
_CursorParamsDep = Depends(cursor_params)


async def _commit[T](session: SessionDep, work: Callable[[], Awaitable[T]]) -> T:
    """Run a service call inside the D-011 uow, returning its ORM result refreshed in the async
    context so a sync ``model_validate`` never trips MissingGreenlet (the inventory _commit
    twin)."""
    holder: list[T] = []

    async def _work() -> None:
        result = await work()
        await session.refresh(result)
        holder.append(result)

    await run_in_uow(session, _work)
    return holder[0]


@bom_router.get(
    "/boms",
    response_model=Page[BomRead],
    dependencies=[Depends(require_permission(MFG_BOM_READ))],
)
async def list_boms(
    request: Request,
    response: Response,
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = _CursorParamsDep,
    item_id: uuid.UUID | None = None,
    status: BomStatus | None = None,
) -> Page[BomRead] | Response:
    """Conditional-GET supported (D-035): the item/status filters fold into the fingerprint so a
    filtered 304 is correct."""
    fingerprint = request_fingerprint(params.cursor, params.limit, item_id, status)
    etag = await collection_etag(session, Bom, request_fingerprint=fingerprint)

    async def builder() -> Page[BomRead]:
        page = await service.list_boms(
            session,
            current.tenant_id,
            item_id=item_id,
            status=status,
            cursor=params.cursor,
            limit=params.limit,
        )
        return map_page(page, BomRead)

    return await conditional_response(request, response, etag, builder)


@bom_router.post(
    "/boms",
    response_model=BomRead,
    status_code=201,
    dependencies=[Depends(require_permission(MFG_BOM_MANAGE))],
)
async def create_bom(
    payload: BomCreate, current: CurrentUserDep, session: SessionDep
) -> BomRead:
    bom = await _commit(session, lambda: service.create_bom(session, current.tenant_id, payload))
    return BomRead.model_validate(bom)


@bom_router.get(
    "/boms/{bom_id}",
    response_model=BomRead,
    dependencies=[Depends(require_permission(MFG_BOM_READ))],
)
async def get_bom(
    bom_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> BomRead:
    bom = await service.get_bom(session, current.tenant_id, bom_id)
    return BomRead.model_validate(bom)


@bom_router.patch(
    "/boms/{bom_id}",
    response_model=BomRead,
    dependencies=[Depends(require_permission(MFG_BOM_MANAGE))],
)
async def update_bom(
    bom_id: uuid.UUID, payload: BomUpdate, current: CurrentUserDep, session: SessionDep
) -> BomRead:
    bom = await _commit(
        session, lambda: service.update_bom(session, current.tenant_id, bom_id, payload)
    )
    return BomRead.model_validate(bom)


@bom_router.post(
    "/boms/{bom_id}/activate",
    response_model=BomRead,
    dependencies=[Depends(require_permission(MFG_BOM_MANAGE))],
)
async def activate_bom(
    bom_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> BomRead:
    """Activate a DRAFT BOM — it becomes the item's ACTIVE default and is frozen (D-047)."""
    bom = await _commit(session, lambda: service.activate_bom(session, current.tenant_id, bom_id))
    return BomRead.model_validate(bom)


@bom_router.post(
    "/boms/{bom_id}/deactivate",
    response_model=BomRead,
    dependencies=[Depends(require_permission(MFG_BOM_MANAGE))],
)
async def deactivate_bom(
    bom_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> BomRead:
    """Deactivate an ACTIVE BOM — it becomes INACTIVE; the item loses its active default (D-047)."""
    bom = await _commit(session, lambda: service.deactivate_bom(session, current.tenant_id, bom_id))
    return BomRead.model_validate(bom)


# --- Components (nested under a BOM) -------------------------------------------


@bom_router.get(
    "/boms/{bom_id}/components",
    response_model=list[BomComponentRead],
    dependencies=[Depends(require_permission(MFG_BOM_READ))],
)
async def list_bom_components(
    bom_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> list[BomComponentRead]:
    await service.get_bom(session, current.tenant_id, bom_id)  # 404 if the BOM is absent
    components = await service.bom_components_for(session, current.tenant_id, bom_id)
    return [BomComponentRead.model_validate(component) for component in components]


@bom_router.post(
    "/boms/{bom_id}/components",
    response_model=BomComponentRead,
    status_code=201,
    dependencies=[Depends(require_permission(MFG_BOM_MANAGE))],
)
async def add_bom_component(
    bom_id: uuid.UUID,
    payload: BomComponentCreate,
    current: CurrentUserDep,
    session: SessionDep,
) -> BomComponentRead:
    component = await _commit(
        session, lambda: service.add_component(session, current.tenant_id, bom_id, payload)
    )
    return BomComponentRead.model_validate(component)


@bom_router.delete(
    "/boms/{bom_id}/components/{component_id}",
    status_code=204,
    dependencies=[Depends(require_permission(MFG_BOM_MANAGE))],
)
async def delete_bom_component(
    bom_id: uuid.UUID,
    component_id: uuid.UUID,
    current: CurrentUserDep,
    session: SessionDep,
) -> Response:
    async def _work() -> None:
        await service.delete_component(session, current.tenant_id, bom_id, component_id)

    await run_in_uow(session, _work)
    return Response(status_code=204)
