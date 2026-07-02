"""Production-order HTTP layer (PLAN 8.2), included into the manufacturing router.

A sibling sub-router under the same ``/api/v1/manufacturing`` prefix, mounted by
``router.include_router`` in router.py (the bom_router/routing_router precedent — ONE module
surface,
no second mount in main.py).

RBAC (D-009; distinct authorities):
  - read by ``manufacturing.production_order.read``;
  - create+explode / cancel the order by ``manufacturing.production_order.manage``;
  - release (reserve materials) by ``manufacturing.production_order.release``;
- issue components + finish to stock by ``manufacturing.production_order.execute`` (both POST stock
    + WIP journals — the shop-floor action).

Writes commit through ``run_in_uow`` (D-011) so the order + its N stock ISSUE/RECEIPT moves + N WIP
journals + the order update commit (or roll back) atomically; the document-creating + issue + finish
endpoints are IDEMPOTENT (D-013). The list is O(1) queries + paginated (PERFORMANCE §6).
"""

import uuid

from fastapi import APIRouter, Depends

from app.core.deps import CurrentUserDep, SessionDep
from app.core.events import run_in_uow
from app.core.idempotency import Idempotent, IdempotentDep
from app.core.pagination import CursorParams, cursor_params, map_page
from app.core.rbac import require_permission
from app.core.schemas import Page
from app.modules.manufacturing import service
from app.modules.manufacturing.constants import (
    MFG_PRODUCTION_ORDER_EXECUTE,
    MFG_PRODUCTION_ORDER_MANAGE,
    MFG_PRODUCTION_ORDER_READ,
    MFG_PRODUCTION_ORDER_RELEASE,
    ProductionOrderStatus,
)
from app.modules.manufacturing.schemas import (
    FinishOrderRequest,
    IssueComponentsRequest,
    ProductionOrderComponentRead,
    ProductionOrderCreate,
    ProductionOrderDetail,
    ProductionOrderOperationRead,
    ProductionOrderRead,
)

production_order_router = APIRouter(tags=["manufacturing-production-orders"])

_CursorParamsDep = Depends(cursor_params)
_CreateIdem = Depends(Idempotent("manufacturing.production_order.create"))
_IssueIdem = Depends(Idempotent("manufacturing.production_order.issue"))
_FinishIdem = Depends(Idempotent("manufacturing.production_order.finish"))


async def _order_detail(
    session: SessionDep, tenant_id: uuid.UUID, order_id: uuid.UUID
) -> ProductionOrderDetail:
    order = await service.get_production_order(session, tenant_id, order_id)
    await session.refresh(order)
    components = await service.production_order_components(session, tenant_id, order_id)
    operations = await service.production_order_operations(session, tenant_id, order_id)
    header = ProductionOrderRead.model_validate(order)
    return ProductionOrderDetail(
        **header.model_dump(),
        components=[ProductionOrderComponentRead.model_validate(c) for c in components],
        operations=[ProductionOrderOperationRead.model_validate(o) for o in operations],
    )


@production_order_router.post(
    "/production-orders",
    response_model=ProductionOrderDetail,
    status_code=201,
    dependencies=[Depends(require_permission(MFG_PRODUCTION_ORDER_MANAGE))],
)
async def create_production_order(
    payload: ProductionOrderCreate,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _CreateIdem,
) -> ProductionOrderDetail:
    """Create a DRAFT production order + explode its BOM into reserved components + snapshot its
    routing (PLAN 8.2). 422 ``manufacturing.no_active_bom`` when the item has no active default BOM
    and none is supplied. IDEMPOTENT (D-013)."""
    holder: dict[str, ProductionOrderDetail] = {}

    async def work() -> None:
        order = await service.create_production_order(session, current.tenant_id, payload)
        detail = await _order_detail(session, current.tenant_id, order.id)
        holder["read"] = await idem.capture(detail, status_code=201)

    await run_in_uow(session, work)
    return holder["read"]


@production_order_router.get(
    "/production-orders",
    response_model=Page[ProductionOrderRead],
    dependencies=[Depends(require_permission(MFG_PRODUCTION_ORDER_READ))],
)
async def list_production_orders(
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = _CursorParamsDep,
    item_id: uuid.UUID | None = None,
    status: ProductionOrderStatus | None = None,
) -> Page[ProductionOrderRead]:
    page = await service.list_production_orders(
        session,
        current.tenant_id,
        item_id=item_id,
        status=status,
        cursor=params.cursor,
        limit=params.limit,
    )
    return map_page(page, ProductionOrderRead)


@production_order_router.get(
    "/production-orders/{order_id}",
    response_model=ProductionOrderDetail,
    dependencies=[Depends(require_permission(MFG_PRODUCTION_ORDER_READ))],
)
async def get_production_order(
    order_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> ProductionOrderDetail:
    return await _order_detail(session, current.tenant_id, order_id)


@production_order_router.post(
    "/production-orders/{order_id}/release",
    response_model=ProductionOrderDetail,
    dependencies=[Depends(require_permission(MFG_PRODUCTION_ORDER_RELEASE))],
)
async def release_production_order(
    order_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> ProductionOrderDetail:
    """Release a DRAFT order — reserve materials (DRAFT→RELEASED, PLAN 8.2)."""
    holder: dict[str, ProductionOrderDetail] = {}

    async def work() -> None:
        await service.release_order(session, current.tenant_id, order_id)
        holder["read"] = await _order_detail(session, current.tenant_id, order_id)

    await run_in_uow(session, work)
    return holder["read"]


@production_order_router.post(
    "/production-orders/{order_id}/issue-components",
    response_model=ProductionOrderDetail,
    dependencies=[Depends(require_permission(MFG_PRODUCTION_ORDER_EXECUTE))],
)
async def issue_components(
    order_id: uuid.UUID,
    payload: IssueComponentsRequest,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _IssueIdem,
) -> ProductionOrderDetail:
    """Issue components to WIP (PLAN 8.2, D-048): creates the stock ISSUE moves (Dr WIP / Cr
    Inventory via the event bus, the WIP-offset override) and raises issued quantities — all one
    transaction. A closed period or insufficient stock rolls the whole issue back. IDEMPOTENT
    (D-013)."""
    holder: dict[str, ProductionOrderDetail] = {}

    async def work() -> None:
        await service.issue_components(session, current.tenant_id, order_id, payload)
        detail = await _order_detail(session, current.tenant_id, order_id)
        holder["read"] = await idem.capture(detail)

    await run_in_uow(session, work)
    return holder["read"]


@production_order_router.post(
    "/production-orders/{order_id}/finish",
    response_model=ProductionOrderDetail,
    dependencies=[Depends(require_permission(MFG_PRODUCTION_ORDER_EXECUTE))],
)
async def finish_order(
    order_id: uuid.UUID,
    payload: FinishOrderRequest,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _FinishIdem,
) -> ProductionOrderDetail:
    """Finish a production order to stock (PLAN 8.2, D-048): creates the finished-goods RECEIPT
    move (Dr Inventory / Cr WIP via the event bus) and, on the final finish, the WIP-variance entry
    so WIP nets to zero — all one transaction. A closed period rolls the whole finish back.
    IDEMPOTENT (D-013)."""
    holder: dict[str, ProductionOrderDetail] = {}

    async def work() -> None:
        await service.finish_order(session, current.tenant_id, order_id, payload)
        detail = await _order_detail(session, current.tenant_id, order_id)
        holder["read"] = await idem.capture(detail)

    await run_in_uow(session, work)
    return holder["read"]


@production_order_router.post(
    "/production-orders/{order_id}/cancel",
    response_model=ProductionOrderDetail,
    dependencies=[Depends(require_permission(MFG_PRODUCTION_ORDER_MANAGE))],
)
async def cancel_production_order(
    order_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> ProductionOrderDetail:
    """Cancel a DRAFT/RELEASED order (PLAN 8.2). Once components are issued the order is IN_PROGRESS
    and must be FINISHED — issued stock + WIP cannot strand."""
    holder: dict[str, ProductionOrderDetail] = {}

    async def work() -> None:
        await service.cancel_order(session, current.tenant_id, order_id)
        holder["read"] = await _order_detail(session, current.tenant_id, order_id)

    await run_in_uow(session, work)
    return holder["read"]
