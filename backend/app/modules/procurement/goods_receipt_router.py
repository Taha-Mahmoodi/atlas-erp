"""Goods-receipt HTTP layer (PLAN 6.3), included into the procurement router.

Reads guarded by ``procurement.goods_receipt.read``; create/cancel the DRAFT by
``procurement.goods_receipt.manage``; the POST action (move stock + post the GR/IR journal) by the
distinct ``procurement.goods_receipt.post`` key (the journal.post precedent — building a document
and committing it are separate rights). Writes commit through ``run_in_uow`` (D-011) so the GR + its
N stock moves + N inventory-debit/GR-IR journals + the PO update commit (or roll back) atomically;
the document-creating + post endpoints are IDEMPOTENT (D-013). The list is O(1) queries + paginated
(PERFORMANCE §6).
"""

import uuid

from fastapi import APIRouter, Depends

from app.core.deps import CurrentUserDep, SessionDep
from app.core.events import run_in_uow
from app.core.idempotency import Idempotent, IdempotentDep
from app.core.pagination import CursorParams, cursor_params, map_page
from app.core.rbac import require_permission
from app.core.schemas import Page
from app.modules.procurement import service
from app.modules.procurement.constants import (
    PROCUREMENT_GOODS_RECEIPT_MANAGE,
    PROCUREMENT_GOODS_RECEIPT_POST,
    PROCUREMENT_GOODS_RECEIPT_READ,
)
from app.modules.procurement.schemas import (
    GoodsReceiptCreate,
    GoodsReceiptDetail,
    GoodsReceiptLineRead,
    GoodsReceiptRead,
)

goods_receipt_router = APIRouter(tags=["procurement-goods-receipts"])

CursorParamsDep = Depends(cursor_params)
_CreateIdem = Depends(Idempotent("procurement.goods_receipt.create"))
_PostIdem = Depends(Idempotent("procurement.goods_receipt.post"))


async def gr_detail(
    session: SessionDep, tenant_id: uuid.UUID, gr_id: uuid.UUID
) -> GoodsReceiptDetail:
    gr = await service.get_goods_receipt(session, tenant_id, gr_id)
    await session.refresh(gr)
    lines = await service.get_goods_receipt_lines(session, tenant_id, gr_id)
    header = GoodsReceiptRead.model_validate(gr)
    return GoodsReceiptDetail(
        **header.model_dump(),
        lines=[GoodsReceiptLineRead.model_validate(line) for line in lines],
    )


@goods_receipt_router.post(
    "/goods-receipts",
    response_model=GoodsReceiptDetail,
    status_code=201,
    dependencies=[Depends(require_permission(PROCUREMENT_GOODS_RECEIPT_MANAGE))],
)
async def create_goods_receipt(
    payload: GoodsReceiptCreate,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _CreateIdem,
) -> GoodsReceiptDetail:
    """Create a DRAFT goods receipt against a PO (PLAN 6.3): the PO must be receivable, each line
    within the open quantity (over-receipt → 422). IDEMPOTENT (D-013)."""
    holder: dict[str, GoodsReceiptDetail] = {}

    async def work() -> None:
        gr = await service.create_goods_receipt(session, current.tenant_id, payload)
        detail = await gr_detail(session, current.tenant_id, gr.id)
        holder["read"] = await idem.capture(detail, status_code=201)

    await run_in_uow(session, work)
    return holder["read"]


@goods_receipt_router.get(
    "/goods-receipts",
    response_model=Page[GoodsReceiptRead],
    dependencies=[Depends(require_permission(PROCUREMENT_GOODS_RECEIPT_READ))],
)
async def list_goods_receipts(
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
    purchase_order_id: uuid.UUID | None = None,
    status: str | None = None,
) -> Page[GoodsReceiptRead]:
    page = await service.list_goods_receipts(
        session,
        current.tenant_id,
        purchase_order_id=purchase_order_id,
        status=status,
        cursor=params.cursor,
        limit=params.limit,
    )
    return map_page(page, GoodsReceiptRead)


@goods_receipt_router.get(
    "/goods-receipts/{gr_id}",
    response_model=GoodsReceiptDetail,
    dependencies=[Depends(require_permission(PROCUREMENT_GOODS_RECEIPT_READ))],
)
async def get_goods_receipt(
    gr_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> GoodsReceiptDetail:
    return await gr_detail(session, current.tenant_id, gr_id)


@goods_receipt_router.post(
    "/goods-receipts/{gr_id}/post",
    response_model=GoodsReceiptDetail,
    dependencies=[Depends(require_permission(PROCUREMENT_GOODS_RECEIPT_POST))],
)
async def post_goods_receipt(
    gr_id: uuid.UUID,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _PostIdem,
) -> GoodsReceiptDetail:
    """Post a DRAFT goods receipt (PLAN 6.3, D-041): creates the stock RECEIPT moves (Dr Inventory /
    Cr GR-IR via the event bus), raises the PO received_quantity, advances the PO status — all one
    transaction. A closed receipt period rolls the whole post back. IDEMPOTENT (D-013)."""
    holder: dict[str, GoodsReceiptDetail] = {}

    async def work() -> None:
        await service.post_goods_receipt(session, current.tenant_id, gr_id)
        detail = await gr_detail(session, current.tenant_id, gr_id)
        holder["read"] = await idem.capture(detail)

    await run_in_uow(session, work)
    return holder["read"]


@goods_receipt_router.post(
    "/goods-receipts/{gr_id}/cancel",
    response_model=GoodsReceiptDetail,
    dependencies=[Depends(require_permission(PROCUREMENT_GOODS_RECEIPT_MANAGE))],
)
async def cancel_goods_receipt(
    gr_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> GoodsReceiptDetail:
    """Cancel a DRAFT goods receipt (PLAN 6.3). A POSTED GR is terminal (corrected by a reversing
    GR / return, Phase 7)."""
    holder: dict[str, GoodsReceiptDetail] = {}

    async def work() -> None:
        await service.cancel_goods_receipt(session, current.tenant_id, gr_id)
        holder["read"] = await gr_detail(session, current.tenant_id, gr_id)

    await run_in_uow(session, work)
    return holder["read"]
