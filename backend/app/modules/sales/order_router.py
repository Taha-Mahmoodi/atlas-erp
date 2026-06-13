"""Sales-order HTTP layer (PLAN 7.2), included into the sales router.

A sibling router under the same ``/api/v1/sales`` prefix, mounted by ``router.include_router`` in
router.py (the procurement po_router precedent — ONE module surface, no second mount in main.py).

RBAC (D-009; distinct authorities):
  - read by ``sales.order.read``;
  - create/edit/convert/cancel by ``sales.order.manage``;
  - confirm (the ATP + credit gate) by the distinct ``sales.order.confirm``;
  - credit-release (override a credit block) by the distinct ``sales.order.credit_release``.

Writes commit through ``run_in_uow`` (D-011); the document-creating + convert + confirm + release
endpoints are IDEMPOTENT (D-013). The confirm/release endpoints return the order detail — a
CREDIT_BLOCKED order comes back with status CREDIT_BLOCKED + credit_check_status BLOCKED rather than
an error (the block is a business outcome, not a failure); a backordered confirm still succeeds
(CONFIRMED) — the ATP snapshot is informational. The ATP-check endpoint is a READ surface over the
availability query for the order-entry UI.
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.deps import CurrentUserDep, SessionDep
from app.core.events import run_in_uow
from app.core.idempotency import Idempotent, IdempotentDep
from app.core.pagination import CursorParams, cursor_params, map_page
from app.core.rbac import require_permission
from app.core.schemas import Page
from app.modules.sales import queries as sales_queries
from app.modules.sales import service
from app.modules.sales.constants import (
    SALES_ORDER_CONFIRM,
    SALES_ORDER_CREDIT_RELEASE,
    SALES_ORDER_MANAGE,
    SALES_ORDER_READ,
)
from app.modules.sales.schemas import (
    AtpCheckRequest,
    AtpCheckResponse,
    AtpLineResult,
    ConvertQuoteToOrder,
    SalesOrderCreate,
    SalesOrderDetail,
    SalesOrderLineRead,
    SalesOrderRead,
    SalesOrderUpdate,
)

order_router = APIRouter(tags=["sales-orders"])

CursorParamsDep = Depends(cursor_params)
_CreateIdem = Depends(Idempotent("sales.order.create"))
_ConvertIdem = Depends(Idempotent("sales.order.from_quote"))
_ConfirmIdem = Depends(Idempotent("sales.order.confirm"))
_ReleaseIdem = Depends(Idempotent("sales.order.credit_release"))


async def order_detail(
    session: SessionDep, tenant_id: uuid.UUID, order_id: uuid.UUID
) -> SalesOrderDetail:
    order = await service.get_sales_order(session, tenant_id, order_id)
    await session.refresh(order)
    lines = await service.get_sales_order_lines(session, tenant_id, order_id)
    header = SalesOrderRead.model_validate(order)
    return SalesOrderDetail(
        **header.model_dump(),
        lines=[SalesOrderLineRead.model_validate(line) for line in lines],
    )


@order_router.post(
    "/orders",
    response_model=SalesOrderDetail,
    status_code=201,
    dependencies=[Depends(require_permission(SALES_ORDER_MANAGE))],
)
async def create_sales_order(
    payload: SalesOrderCreate,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _CreateIdem,
) -> SalesOrderDetail:
    """Create a DRAFT order from scratch (PLAN 7.2): customer must be ACTIVE; lines priced from the
    resolver + discounts. IDEMPOTENT (D-013)."""
    holder: dict[str, SalesOrderDetail] = {}

    async def work() -> None:
        order = await service.create_sales_order(session, current.tenant_id, payload)
        detail = await order_detail(session, current.tenant_id, order.id)
        holder["read"] = await idem.capture(detail, status_code=201)

    await run_in_uow(session, work)
    return holder["read"]


@order_router.post(
    "/quotes/{quote_id}/convert-to-order",
    response_model=SalesOrderDetail,
    status_code=201,
    dependencies=[Depends(require_permission(SALES_ORDER_MANAGE))],
)
async def convert_quote_to_order(
    quote_id: uuid.UUID,
    payload: ConvertQuoteToOrder,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _ConvertIdem,
) -> SalesOrderDetail:
    """Convert an ACCEPTED quote into a DRAFT order (PLAN 7.2): copies lines + frozen prices, links
    docflow quote→order, advances the quote to CONVERTED. IDEMPOTENT (D-013)."""
    holder: dict[str, SalesOrderDetail] = {}

    async def work() -> None:
        order = await service.convert_quote_to_order(
            session, current.tenant_id, quote_id, payload
        )
        detail = await order_detail(session, current.tenant_id, order.id)
        holder["read"] = await idem.capture(detail, status_code=201)

    await run_in_uow(session, work)
    return holder["read"]


@order_router.get(
    "/orders",
    response_model=Page[SalesOrderRead],
    dependencies=[Depends(require_permission(SALES_ORDER_READ))],
)
async def list_sales_orders(
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
    status: str | None = None,
    customer_id: uuid.UUID | None = None,
) -> Page[SalesOrderRead]:
    page = await service.list_sales_orders(
        session,
        current.tenant_id,
        status=status,
        customer_id=customer_id,
        cursor=params.cursor,
        limit=params.limit,
    )
    return map_page(page, SalesOrderRead)


@order_router.post(
    "/orders/atp",
    response_model=AtpCheckResponse,
    dependencies=[Depends(require_permission(SALES_ORDER_READ))],
)
async def check_atp(
    payload: AtpCheckRequest, current: CurrentUserDep, session: SessionDep
) -> AtpCheckResponse:
    """Available-to-promise preview over a set of lines (PLAN 7.2, D-044): per line, available =
    on-hand − committed + on-order. Informational (a shortfall flags a backorder; the hard block is
    credit at confirm). A read surface for the order-entry UI."""
    on_date = payload.on_date or date.today()
    results: list[AtpLineResult] = []
    for line in payload.lines:
        atp = await sales_queries.atp_check(
            session,
            current.tenant_id,
            item_id=line.item_id,
            quantity=line.quantity,
            on_date=on_date,
        )
        results.append(
            AtpLineResult(
                item_id=atp.item_id,
                requested_quantity=atp.requested_quantity,
                on_hand=atp.on_hand,
                committed=atp.committed,
                on_order=atp.on_order,
                available=atp.available,
                atp_ok=atp.atp_ok,
                backordered=not atp.atp_ok,
                shortfall=atp.shortfall,
            )
        )
    return AtpCheckResponse(on_date=on_date, lines=results)


@order_router.get(
    "/orders/atp",
    response_model=AtpCheckResponse,
    dependencies=[Depends(require_permission(SALES_ORDER_READ))],
)
async def check_atp_single(
    current: CurrentUserDep,
    session: SessionDep,
    item_id: Annotated[uuid.UUID, Query()],
    quantity: Annotated[Decimal, Query(gt=0)],
    check_date: Annotated[date | None, Query(alias="date")] = None,
) -> AtpCheckResponse:
    """Single-item ATP check (PLAN 7.2): the GET convenience over the same availability query for a
    quick one-line UI lookup (the POST variant takes a line set). ``date`` defaults to today."""
    on_date = check_date or date.today()
    atp = await sales_queries.atp_check(
        session,
        current.tenant_id,
        item_id=item_id,
        quantity=quantity,
        on_date=on_date,
    )
    return AtpCheckResponse(
        on_date=on_date,
        lines=[
            AtpLineResult(
                item_id=atp.item_id,
                requested_quantity=atp.requested_quantity,
                on_hand=atp.on_hand,
                committed=atp.committed,
                on_order=atp.on_order,
                available=atp.available,
                atp_ok=atp.atp_ok,
                backordered=not atp.atp_ok,
                shortfall=atp.shortfall,
            )
        ],
    )


@order_router.get(
    "/orders/{order_id}",
    response_model=SalesOrderDetail,
    dependencies=[Depends(require_permission(SALES_ORDER_READ))],
)
async def get_sales_order(
    order_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> SalesOrderDetail:
    return await order_detail(session, current.tenant_id, order_id)


@order_router.patch(
    "/orders/{order_id}",
    response_model=SalesOrderDetail,
    dependencies=[Depends(require_permission(SALES_ORDER_MANAGE))],
)
async def update_sales_order(
    order_id: uuid.UUID,
    payload: SalesOrderUpdate,
    current: CurrentUserDep,
    session: SessionDep,
) -> SalesOrderDetail:
    holder: dict[str, SalesOrderDetail] = {}

    async def work() -> None:
        await service.update_sales_order(session, current.tenant_id, order_id, payload)
        holder["read"] = await order_detail(session, current.tenant_id, order_id)

    await run_in_uow(session, work)
    return holder["read"]


@order_router.post(
    "/orders/{order_id}/confirm",
    response_model=SalesOrderDetail,
    dependencies=[Depends(require_permission(SALES_ORDER_CONFIRM))],
)
async def confirm_sales_order(
    order_id: uuid.UUID,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _ConfirmIdem,
) -> SalesOrderDetail:
    """Confirm an order (PLAN 7.2) — the ATP + credit gate (sales.order.confirm). Within the credit
    limit ⇒ CONFIRMED (backordered lines still confirm); over it ⇒ CREDIT_BLOCKED (returned, not an
    error). IDEMPOTENT (D-013)."""
    holder: dict[str, SalesOrderDetail] = {}

    async def work() -> None:
        await service.confirm_order(session, current.tenant_id, order_id)
        detail = await order_detail(session, current.tenant_id, order_id)
        holder["read"] = await idem.capture(detail)

    await run_in_uow(session, work)
    return holder["read"]


@order_router.post(
    "/orders/{order_id}/credit-release",
    response_model=SalesOrderDetail,
    dependencies=[Depends(require_permission(SALES_ORDER_CREDIT_RELEASE))],
)
async def release_order_credit(
    order_id: uuid.UUID,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _ReleaseIdem,
) -> SalesOrderDetail:
    """Release a CREDIT_BLOCKED order past the limit (PLAN 7.2, sales.order.credit_release) and
    confirm it (credit_check_status RELEASED → CONFIRMED). IDEMPOTENT (D-013)."""
    holder: dict[str, SalesOrderDetail] = {}

    async def work() -> None:
        await service.release_credit(session, current.tenant_id, order_id)
        detail = await order_detail(session, current.tenant_id, order_id)
        holder["read"] = await idem.capture(detail)

    await run_in_uow(session, work)
    return holder["read"]


@order_router.post(
    "/orders/{order_id}/cancel",
    response_model=SalesOrderDetail,
    dependencies=[Depends(require_permission(SALES_ORDER_MANAGE))],
)
async def cancel_sales_order(
    order_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> SalesOrderDetail:
    holder: dict[str, SalesOrderDetail] = {}

    async def work() -> None:
        await service.cancel_sales_order(session, current.tenant_id, order_id)
        holder["read"] = await order_detail(session, current.tenant_id, order_id)

    await run_in_uow(session, work)
    return holder["read"]
