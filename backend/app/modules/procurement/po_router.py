"""Purchase-order HTTP layer (PLAN 6.2), included into the procurement router.

Reads guarded by ``procurement.po.read``; create/send/convert/cancel by ``procurement.po.manage``;
approve/reject (clearing a pending-approval PO) by the distinct ``procurement.po.approve`` key. The
convert-from-RFQ action lives here (it produces a PO). Writes commit through ``run_in_uow`` (D-011);
the document-creating + convert + send + approve endpoints are IDEMPOTENT (D-013).
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
    PROCUREMENT_PO_APPROVE,
    PROCUREMENT_PO_MANAGE,
    PROCUREMENT_PO_READ,
    ApprovalDecision,
)
from app.modules.procurement.schemas import (
    ApprovalDecisionPayload,
    PurchaseOrderCreate,
    PurchaseOrderDetail,
    PurchaseOrderFromRfq,
    PurchaseOrderLineRead,
    PurchaseOrderRead,
)

po_router = APIRouter(tags=["procurement-purchase-orders"])

CursorParamsDep = Depends(cursor_params)
_CreateIdem = Depends(Idempotent("procurement.po.create"))
_FromRfqIdem = Depends(Idempotent("procurement.po.from_rfq"))
_SendIdem = Depends(Idempotent("procurement.po.send"))
_DecideIdem = Depends(Idempotent("procurement.po.decide"))


async def po_detail(
    session: SessionDep, tenant_id: uuid.UUID, po_id: uuid.UUID
) -> PurchaseOrderDetail:
    po = await service.get_purchase_order(session, tenant_id, po_id)
    await session.refresh(po)
    lines = await service.get_purchase_order_lines(session, tenant_id, po_id)
    header = PurchaseOrderRead.model_validate(po)
    return PurchaseOrderDetail(
        **header.model_dump(),
        lines=[PurchaseOrderLineRead.model_validate(line) for line in lines],
    )


@po_router.post(
    "/purchase-orders",
    response_model=PurchaseOrderDetail,
    status_code=201,
    dependencies=[Depends(require_permission(PROCUREMENT_PO_MANAGE))],
)
async def create_purchase_order(
    payload: PurchaseOrderCreate,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _CreateIdem,
) -> PurchaseOrderDetail:
    """Create a DRAFT PO from scratch (PLAN 6.2): vendor must be ACTIVE + every item approved.
    IDEMPOTENT (D-013)."""
    holder: dict[str, PurchaseOrderDetail] = {}

    async def work() -> None:
        po = await service.create_purchase_order(session, current.tenant_id, payload)
        detail = await po_detail(session, current.tenant_id, po.id)
        holder["read"] = await idem.capture(detail, status_code=201)

    await run_in_uow(session, work)
    return holder["read"]


@po_router.post(
    "/rfqs/{rfq_id}/convert-to-po",
    response_model=PurchaseOrderDetail,
    status_code=201,
    dependencies=[Depends(require_permission(PROCUREMENT_PO_MANAGE))],
)
async def convert_rfq_to_po(
    rfq_id: uuid.UUID,
    payload: PurchaseOrderFromRfq,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _FromRfqIdem,
) -> PurchaseOrderDetail:
    """Order a QUOTED RFQ into a PO (PLAN 6.2): copies lines with the quoted prices + links docflow.
    IDEMPOTENT (D-013)."""
    holder: dict[str, PurchaseOrderDetail] = {}

    async def work() -> None:
        po = await service.convert_rfq_to_po(session, current.tenant_id, rfq_id, payload)
        detail = await po_detail(session, current.tenant_id, po.id)
        holder["read"] = await idem.capture(detail, status_code=201)

    await run_in_uow(session, work)
    return holder["read"]


@po_router.get(
    "/purchase-orders",
    response_model=Page[PurchaseOrderRead],
    dependencies=[Depends(require_permission(PROCUREMENT_PO_READ))],
)
async def list_purchase_orders(
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
    status: str | None = None,
    vendor_id: uuid.UUID | None = None,
) -> Page[PurchaseOrderRead]:
    page = await service.list_purchase_orders(
        session,
        current.tenant_id,
        status=status,
        vendor_id=vendor_id,
        cursor=params.cursor,
        limit=params.limit,
    )
    return map_page(page, PurchaseOrderRead)


@po_router.get(
    "/purchase-orders/{po_id}",
    response_model=PurchaseOrderDetail,
    dependencies=[Depends(require_permission(PROCUREMENT_PO_READ))],
)
async def get_purchase_order(
    po_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> PurchaseOrderDetail:
    return await po_detail(session, current.tenant_id, po_id)


@po_router.post(
    "/purchase-orders/{po_id}/send",
    response_model=PurchaseOrderDetail,
    dependencies=[Depends(require_permission(PROCUREMENT_PO_MANAGE))],
)
async def send_purchase_order(
    po_id: uuid.UUID,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _SendIdem,
) -> PurchaseOrderDetail:
    """Send a PO (PLAN 6.2): the approval-threshold rule decides PENDING_APPROVAL vs auto-approve →
    SENT. IDEMPOTENT (D-013)."""
    holder: dict[str, PurchaseOrderDetail] = {}

    async def work() -> None:
        await service.send_purchase_order(session, current.tenant_id, po_id)
        detail = await po_detail(session, current.tenant_id, po_id)
        holder["read"] = await idem.capture(detail)

    await run_in_uow(session, work)
    return holder["read"]


@po_router.post(
    "/purchase-orders/{po_id}/decision",
    response_model=PurchaseOrderDetail,
    dependencies=[Depends(require_permission(PROCUREMENT_PO_APPROVE))],
)
async def decide_purchase_order(
    po_id: uuid.UUID,
    payload: ApprovalDecisionPayload,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _DecideIdem,
) -> PurchaseOrderDetail:
    """Approve or reject a PENDING_APPROVAL PO (PLAN 6.2, the procurement.po.approve action). An
    approved PO records the approver + timestamp and becomes sendable. IDEMPOTENT (D-013)."""
    holder: dict[str, PurchaseOrderDetail] = {}

    async def work() -> None:
        await service.decide_purchase_order(
            session,
            current.tenant_id,
            po_id,
            approved=ApprovalDecision(payload.decision) == ApprovalDecision.APPROVED,
            approver_id=current.user_id,
        )
        detail = await po_detail(session, current.tenant_id, po_id)
        holder["read"] = await idem.capture(detail)

    await run_in_uow(session, work)
    return holder["read"]


@po_router.post(
    "/purchase-orders/{po_id}/cancel",
    response_model=PurchaseOrderDetail,
    dependencies=[Depends(require_permission(PROCUREMENT_PO_MANAGE))],
)
async def cancel_purchase_order(
    po_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> PurchaseOrderDetail:
    holder: dict[str, PurchaseOrderDetail] = {}

    async def work() -> None:
        await service.cancel_purchase_order(session, current.tenant_id, po_id)
        holder["read"] = await po_detail(session, current.tenant_id, po_id)

    await run_in_uow(session, work)
    return holder["read"]
