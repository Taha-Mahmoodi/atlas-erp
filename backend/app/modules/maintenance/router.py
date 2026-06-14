"""Maintenance HTTP layer (thin): parse -> call service -> return schema (PLAN 9.2).

REST under ``/api/v1/maintenance``: equipment (CRUD + filtered list) here, with the
maintenance-order surface (``order_router``) and the maintenance-plan surface (``plan_router``)
mounted as sibling sub-routers at the foot of this file so the whole module is ONE surface at
``/api/v1/maintenance`` — the manufacturing bom_router / production_order_router include precedent
(no second mount in main.py). Every route is guarded by a maintenance permission key (D-009); writes
commit through ``run_in_uow`` (D-011) so audit rows ride the same transaction. The equipment list is
reference data, so it carries a conditional-GET ETag (PERFORMANCE §3 / D-035).
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
from app.modules.maintenance import service
from app.modules.maintenance.constants import (
    MAINTENANCE_EQUIPMENT_MANAGE,
    MAINTENANCE_EQUIPMENT_READ,
    EquipmentStatus,
)
from app.modules.maintenance.models import Equipment
from app.modules.maintenance.order_router import order_router
from app.modules.maintenance.plan_router import plan_router
from app.modules.maintenance.schemas import (
    EquipmentCreate,
    EquipmentFilter,
    EquipmentRead,
    EquipmentUpdate,
)

router = APIRouter(prefix="/api/v1/maintenance", tags=["maintenance"])
_CursorParamsDep = Depends(cursor_params)


async def _commit[T](session: SessionDep, work: Callable[[], Awaitable[T]]) -> T:
    """Run a service call inside the D-011 uow, refreshing the ORM result in the async context so a
    sync ``model_validate`` never trips MissingGreenlet (the manufacturing _commit twin)."""
    holder: list[T] = []

    async def _work() -> None:
        result = await work()
        await session.refresh(result)
        holder.append(result)

    await run_in_uow(session, _work)
    return holder[0]


@router.get(
    "/equipment",
    response_model=Page[EquipmentRead],
    dependencies=[Depends(require_permission(MAINTENANCE_EQUIPMENT_READ))],
)
async def list_equipment(
    request: Request,
    response: Response,
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = _CursorParamsDep,
    status: EquipmentStatus | None = None,
) -> Page[EquipmentRead] | Response:
    """Conditional-GET supported (D-035): collection ETag over the equipment reference list; the
    status filter folds into the request fingerprint so a filtered 304 is correct."""
    filters = EquipmentFilter(status=status)
    fingerprint = request_fingerprint(params.cursor, params.limit, status)
    etag = await collection_etag(session, Equipment, request_fingerprint=fingerprint)

    async def builder() -> Page[EquipmentRead]:
        page = await service.list_equipment(
            session,
            current.tenant_id,
            filters=filters,
            cursor=params.cursor,
            limit=params.limit,
        )
        return map_page(page, EquipmentRead)

    return await conditional_response(request, response, etag, builder)


@router.post(
    "/equipment",
    response_model=EquipmentRead,
    status_code=201,
    dependencies=[Depends(require_permission(MAINTENANCE_EQUIPMENT_MANAGE))],
)
async def create_equipment(
    payload: EquipmentCreate, current: CurrentUserDep, session: SessionDep
) -> EquipmentRead:
    equipment = await _commit(
        session, lambda: service.create_equipment(session, current.tenant_id, payload)
    )
    return EquipmentRead.model_validate(equipment)


@router.get(
    "/equipment/{equipment_id}",
    response_model=EquipmentRead,
    dependencies=[Depends(require_permission(MAINTENANCE_EQUIPMENT_READ))],
)
async def get_equipment(
    equipment_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> EquipmentRead:
    equipment = await service.get_equipment(session, current.tenant_id, equipment_id)
    return EquipmentRead.model_validate(equipment)


@router.patch(
    "/equipment/{equipment_id}",
    response_model=EquipmentRead,
    dependencies=[Depends(require_permission(MAINTENANCE_EQUIPMENT_MANAGE))],
)
async def update_equipment(
    equipment_id: uuid.UUID,
    payload: EquipmentUpdate,
    current: CurrentUserDep,
    session: SessionDep,
) -> EquipmentRead:
    equipment = await _commit(
        session,
        lambda: service.update_equipment(session, current.tenant_id, equipment_id, payload),
    )
    return EquipmentRead.model_validate(equipment)


# The maintenance-order surface (orders + schedule/start/complete/cancel) and the maintenance-plan
# surface (plans + activate/deactivate + the run-preventive generation) are sibling sub-routers
# mounted here, so the whole module is ONE surface at /api/v1/maintenance.
router.include_router(order_router)
router.include_router(plan_router)
