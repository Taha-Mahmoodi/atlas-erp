"""Outbound-delivery HTTP layer (PLAN 7.3), included into the sales router.

A sibling router under the same ``/api/v1/sales`` prefix, mounted by ``router.include_router`` in
router.py (the order_router precedent — ONE module surface, no second mount in main.py).

RBAC (D-009; distinct authorities):
  - read by ``sales.delivery.read``;
  - create/cancel the DRAFT by ``sales.delivery.manage``;
  - the POST action (issue stock + post the COGS journal) by the distinct ``sales.delivery.post``
    (the journal.post / goods_receipt.post precedent — building a delivery note and shipping it are
    separate rights).

Writes commit through ``run_in_uow`` (D-011) so the delivery + its N stock ISSUE moves + N COGS
journals + the order update commit (or roll back) atomically; the document-creating + post endpoints
are IDEMPOTENT (D-013). The list is O(1) queries + paginated (PERFORMANCE §6).
"""

import uuid

from fastapi import APIRouter, Depends

from app.core.deps import CurrentUserDep, SessionDep
from app.core.events import run_in_uow
from app.core.idempotency import Idempotent, IdempotentDep
from app.core.pagination import CursorParams, cursor_params, map_page
from app.core.rbac import require_permission
from app.core.schemas import Page
from app.modules.sales import service
from app.modules.sales.constants import (
    SALES_DELIVERY_MANAGE,
    SALES_DELIVERY_POST,
    SALES_DELIVERY_READ,
)
from app.modules.sales.schemas import (
    DeliveryCreate,
    DeliveryDetail,
    DeliveryLineRead,
    DeliveryRead,
)

delivery_router = APIRouter(tags=["sales-deliveries"])

CursorParamsDep = Depends(cursor_params)
_CreateIdem = Depends(Idempotent("sales.delivery.create"))
_PostIdem = Depends(Idempotent("sales.delivery.post"))


async def delivery_detail(
    session: SessionDep, tenant_id: uuid.UUID, delivery_id: uuid.UUID
) -> DeliveryDetail:
    delivery = await service.get_delivery(session, tenant_id, delivery_id)
    await session.refresh(delivery)
    lines = await service.get_delivery_lines(session, tenant_id, delivery_id)
    header = DeliveryRead.model_validate(delivery)
    return DeliveryDetail(
        **header.model_dump(),
        lines=[DeliveryLineRead.model_validate(line) for line in lines],
    )


@delivery_router.post(
    "/deliveries",
    response_model=DeliveryDetail,
    status_code=201,
    dependencies=[Depends(require_permission(SALES_DELIVERY_MANAGE))],
)
async def create_delivery(
    payload: DeliveryCreate,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _CreateIdem,
) -> DeliveryDetail:
    """Create a DRAFT delivery against a sales order (PLAN 7.3): the order must be deliverable
    (CONFIRMED / PARTIALLY_DELIVERED), each line within the open-to-deliver quantity (over-delivery
    → 422), the source bin holds enough stock. IDEMPOTENT (D-013)."""
    holder: dict[str, DeliveryDetail] = {}

    async def work() -> None:
        delivery = await service.create_delivery(session, current.tenant_id, payload)
        detail = await delivery_detail(session, current.tenant_id, delivery.id)
        holder["read"] = await idem.capture(detail, status_code=201)

    await run_in_uow(session, work)
    return holder["read"]


@delivery_router.get(
    "/deliveries",
    response_model=Page[DeliveryRead],
    dependencies=[Depends(require_permission(SALES_DELIVERY_READ))],
)
async def list_deliveries(
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
    sales_order_id: uuid.UUID | None = None,
    status: str | None = None,
) -> Page[DeliveryRead]:
    page = await service.list_deliveries(
        session,
        current.tenant_id,
        sales_order_id=sales_order_id,
        status=status,
        cursor=params.cursor,
        limit=params.limit,
    )
    return map_page(page, DeliveryRead)


@delivery_router.get(
    "/deliveries/{delivery_id}",
    response_model=DeliveryDetail,
    dependencies=[Depends(require_permission(SALES_DELIVERY_READ))],
)
async def get_delivery(
    delivery_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> DeliveryDetail:
    return await delivery_detail(session, current.tenant_id, delivery_id)


@delivery_router.post(
    "/deliveries/{delivery_id}/post",
    response_model=DeliveryDetail,
    dependencies=[Depends(require_permission(SALES_DELIVERY_POST))],
)
async def post_delivery(
    delivery_id: uuid.UUID,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _PostIdem,
) -> DeliveryDetail:
    """Post a DRAFT delivery (PLAN 7.3, D-045): creates the stock ISSUE moves (Dr COGS / Cr
    Inventory via the event bus, COGS the default issue offset), raises the order line
    delivered_quantity, advances the order status — all one transaction. A closed delivery period or
    insufficient stock rolls the whole post back. IDEMPOTENT (D-013)."""
    holder: dict[str, DeliveryDetail] = {}

    async def work() -> None:
        await service.post_delivery(session, current.tenant_id, delivery_id)
        detail = await delivery_detail(session, current.tenant_id, delivery_id)
        holder["read"] = await idem.capture(detail)

    await run_in_uow(session, work)
    return holder["read"]


@delivery_router.post(
    "/deliveries/{delivery_id}/cancel",
    response_model=DeliveryDetail,
    dependencies=[Depends(require_permission(SALES_DELIVERY_MANAGE))],
)
async def cancel_delivery(
    delivery_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> DeliveryDetail:
    """Cancel a DRAFT delivery (PLAN 7.3). A POSTED delivery is terminal (corrected by a return /
    RMA, 7.4)."""
    holder: dict[str, DeliveryDetail] = {}

    async def work() -> None:
        await service.cancel_delivery(session, current.tenant_id, delivery_id)
        holder["read"] = await delivery_detail(session, current.tenant_id, delivery_id)

    await run_in_uow(session, work)
    return holder["read"]
