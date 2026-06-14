"""Maintenance-order HTTP layer (PLAN 9.2), included into the maintenance router.

A sibling sub-router under the same ``/api/v1/maintenance`` prefix, mounted by
``router.include_router`` in router.py (the manufacturing bom_router precedent — ONE module surface,
no second mount in main.py). REST: maintenance-order CRUD + the schedule/start/complete/cancel
actions + a filtered, paginated list.

RBAC (D-009; distinct authorities): read by ``maintenance.order.read``; create / schedule / start /
cancel / edit by ``maintenance.order.manage``; COMPLETE (records the actual cost) by
``maintenance.order.complete`` — the distinct value-bearing authority. Writes commit through
``run_in_uow`` (D-011) so the order + its document update + audit rows ride one transaction; the
create + complete endpoints are IDEMPOTENT (D-013). The list is O(1) queries + paginated
(PERFORMANCE §6).
"""

import uuid
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends

from app.core.deps import CurrentUserDep, SessionDep
from app.core.events import run_in_uow
from app.core.idempotency import Idempotent, IdempotentDep
from app.core.pagination import CursorParams, cursor_params, map_page
from app.core.rbac import require_permission
from app.core.schemas import Page
from app.modules.maintenance import service
from app.modules.maintenance.constants import (
    MAINTENANCE_ORDER_COMPLETE,
    MAINTENANCE_ORDER_MANAGE,
    MAINTENANCE_ORDER_READ,
    MaintenanceOrderStatus,
    MaintenanceOrderType,
)
from app.modules.maintenance.schemas import (
    CompleteOrderRequest,
    MaintenanceOrderCreate,
    MaintenanceOrderRead,
    MaintenanceOrderUpdate,
    ScheduleOrderRequest,
)

order_router = APIRouter(tags=["maintenance-orders"])

_CursorParamsDep = Depends(cursor_params)
_CreateIdem = Depends(Idempotent("maintenance.order.create"))
_CompleteIdem = Depends(Idempotent("maintenance.order.complete"))


async def _commit_read[T](
    session: SessionDep, work: Callable[[], Awaitable[object]]
) -> MaintenanceOrderRead:
    """Run a service call inside the D-011 uow and return the order refreshed + validated in the
    async context so a sync ``model_validate`` never trips MissingGreenlet (the bom_router _commit
    twin)."""
    holder: dict[str, MaintenanceOrderRead] = {}

    async def _work() -> None:
        order = await work()
        await session.refresh(order)
        holder["read"] = MaintenanceOrderRead.model_validate(order)

    await run_in_uow(session, _work)
    return holder["read"]


@order_router.post(
    "/maintenance-orders",
    response_model=MaintenanceOrderRead,
    status_code=201,
    dependencies=[Depends(require_permission(MAINTENANCE_ORDER_MANAGE))],
)
async def create_maintenance_order(
    payload: MaintenanceOrderCreate,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _CreateIdem,
) -> MaintenanceOrderRead:
    """Create a CORRECTIVE maintenance order (PLAN 9.2). 422 ``maintenance.equipment_not_active``
    when the equipment is not ACTIVE. IDEMPOTENT (D-013)."""
    holder: dict[str, MaintenanceOrderRead] = {}

    async def work() -> None:
        order = await service.create_corrective(session, current.tenant_id, payload)
        await session.refresh(order)
        read = MaintenanceOrderRead.model_validate(order)
        holder["read"] = await idem.capture(read, status_code=201)

    await run_in_uow(session, work)
    return holder["read"]


@order_router.get(
    "/maintenance-orders",
    response_model=Page[MaintenanceOrderRead],
    dependencies=[Depends(require_permission(MAINTENANCE_ORDER_READ))],
)
async def list_maintenance_orders(
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = _CursorParamsDep,
    equipment_id: uuid.UUID | None = None,
    order_type: MaintenanceOrderType | None = None,
    status: MaintenanceOrderStatus | None = None,
) -> Page[MaintenanceOrderRead]:
    page = await service.list_maintenance_orders(
        session,
        current.tenant_id,
        equipment_id=equipment_id,
        order_type=order_type,
        status=status,
        cursor=params.cursor,
        limit=params.limit,
    )
    return map_page(page, MaintenanceOrderRead)


@order_router.get(
    "/maintenance-orders/{order_id}",
    response_model=MaintenanceOrderRead,
    dependencies=[Depends(require_permission(MAINTENANCE_ORDER_READ))],
)
async def get_maintenance_order(
    order_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> MaintenanceOrderRead:
    order = await service.get_maintenance_order(session, current.tenant_id, order_id)
    return MaintenanceOrderRead.model_validate(order)


@order_router.patch(
    "/maintenance-orders/{order_id}",
    response_model=MaintenanceOrderRead,
    dependencies=[Depends(require_permission(MAINTENANCE_ORDER_MANAGE))],
)
async def update_maintenance_order(
    order_id: uuid.UUID,
    payload: MaintenanceOrderUpdate,
    current: CurrentUserDep,
    session: SessionDep,
) -> MaintenanceOrderRead:
    return await _commit_read(
        session,
        lambda: service.update_order(session, current.tenant_id, order_id, payload),
    )


@order_router.post(
    "/maintenance-orders/{order_id}/schedule",
    response_model=MaintenanceOrderRead,
    dependencies=[Depends(require_permission(MAINTENANCE_ORDER_MANAGE))],
)
async def schedule_maintenance_order(
    order_id: uuid.UUID,
    payload: ScheduleOrderRequest,
    current: CurrentUserDep,
    session: SessionDep,
) -> MaintenanceOrderRead:
    """Schedule a DRAFT order (→ SCHEDULED) on a planned date (PLAN 9.2)."""
    return await _commit_read(
        session,
        lambda: service.schedule_order(
            session, current.tenant_id, order_id, payload.scheduled_date
        ),
    )


@order_router.post(
    "/maintenance-orders/{order_id}/start",
    response_model=MaintenanceOrderRead,
    dependencies=[Depends(require_permission(MAINTENANCE_ORDER_MANAGE))],
)
async def start_maintenance_order(
    order_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> MaintenanceOrderRead:
    """Start work on a SCHEDULED order (→ IN_PROGRESS, PLAN 9.2)."""
    return await _commit_read(
        session, lambda: service.start_order(session, current.tenant_id, order_id)
    )


@order_router.post(
    "/maintenance-orders/{order_id}/complete",
    response_model=MaintenanceOrderRead,
    dependencies=[Depends(require_permission(MAINTENANCE_ORDER_COMPLETE))],
)
async def complete_maintenance_order(
    order_id: uuid.UUID,
    payload: CompleteOrderRequest,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _CompleteIdem,
) -> MaintenanceOrderRead:
    """Complete an order (→ COMPLETED): records ``actual_cost`` on the order (record-only, no GL,
    D-051). IDEMPOTENT (D-013)."""
    holder: dict[str, MaintenanceOrderRead] = {}

    async def work() -> None:
        order = await service.complete_order(session, current.tenant_id, order_id, payload)
        await session.refresh(order)
        read = MaintenanceOrderRead.model_validate(order)
        holder["read"] = await idem.capture(read)

    await run_in_uow(session, work)
    return holder["read"]


@order_router.post(
    "/maintenance-orders/{order_id}/cancel",
    response_model=MaintenanceOrderRead,
    dependencies=[Depends(require_permission(MAINTENANCE_ORDER_MANAGE))],
)
async def cancel_maintenance_order(
    order_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> MaintenanceOrderRead:
    """Cancel a non-terminal order (→ CANCELLED, PLAN 9.2)."""
    return await _commit_read(
        session, lambda: service.cancel_order(session, current.tenant_id, order_id)
    )
