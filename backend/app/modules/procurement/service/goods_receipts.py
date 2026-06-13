"""Goods-receipt business logic (PLAN 6.3, D-041): create DRAFT against a PO, post (the heart),
cancel. Reads live in ``goods_receipt_reads.py`` (split at the 400-line cap); the package
``__init__`` re-exports both halves as one surface.

A goods receipt records physical receipt of PO goods. ``create_goods_receipt`` writes a DRAFT
(validates the PO is receivable, each line belongs to it, quantity is within the open quantity,
the bin + item check out, the item matches the PO line) and claims the GR number at creation
(D-040). ``post_goods_receipt`` is the heart: in ONE transaction it raises each PO line's
received_quantity, advances the PO status (PARTIALLY_RECEIVED / RECEIVED), links docflow PO→GR, and
PUBLISHES ``GoodsReceiptPosted`` — inventory's handler creates the stock RECEIPT moves (Dr Inventory
/ Cr GR-IR via the valuation-offset override) and finance posts the journals, all in this same
transaction. A closed receipt period trips a move's journal trigger and rolls the WHOLE post back.

Cross-module rule (STRUCTURE §5 / D-041): procurement NEVER calls inventory's service — the stock
effect goes through the event bus. Procurement reads the GR/IR clearing account via finance/queries
and validates bins via inventory/queries (downward reads), updates its OWN PO/GR rows, and lets
inventory's handler own the moves. The GR↔move link is the docflow 'moved_by' edge the handler
writes, not a cross-module FK.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.core.events import publish
from app.core.exceptions import ConflictError, ValidationFailedError
from app.modules.finance import queries as finance_queries
from app.modules.inventory import queries as inventory_queries
from app.modules.procurement.constants import (
    GOODS_RECEIPT_DOC_TYPE,
    GOODS_RECEIPT_NUMBER_PADDING,
    GOODS_RECEIPT_NUMBER_PREFIX,
    GOODS_RECEIPT_SEQUENCE_NAME,
    PO_RECEIVED_BY_GR_LINK,
    GoodsReceiptStatus,
    PurchaseOrderStatus,
)
from app.modules.procurement.events import GoodsReceiptMove, GoodsReceiptPosted
from app.modules.procurement.models import (
    GoodsReceipt,
    GoodsReceiptLine,
    PurchaseOrder,
    PurchaseOrderLine,
)
from app.modules.procurement.schemas import GoodsReceiptCreate
from app.modules.procurement.service._shared import claim_document_number, validate_quantity
from app.modules.procurement.service.goods_receipt_reads import (
    get_goods_receipt,
    get_goods_receipt_lines,
)

# A PO is receivable once committed (SENT) or while partially received; an APPROVED PO is also
# accepted (a tenant may receive against an approved-but-not-yet-marked-sent order). DRAFT /
# PENDING_APPROVAL / REJECTED / CANCELLED / RECEIVED / CLOSED cannot start a NEW receipt.
_RECEIVABLE_PO_STATUSES = frozenset(
    {
        PurchaseOrderStatus.APPROVED,
        PurchaseOrderStatus.SENT,
        PurchaseOrderStatus.PARTIALLY_RECEIVED,
    }
)


@dataclass(frozen=True)
class _ReceiptLineInput:
    """One validated receipt line: the PO line it receives against, the snapshot item/cost from that
    line, the target bin, the received quantity, optional lot/serial and the inspection flag."""

    purchase_order_line_id: uuid.UUID
    item_id: uuid.UUID
    unit_cost: Decimal
    bin_id: uuid.UUID
    received_quantity: Decimal
    lot_code: str | None
    serial_code: str | None
    requires_inspection: bool


async def _require_receivable_po(
    session: AsyncSession, tenant_id: uuid.UUID, po_id: uuid.UUID
) -> PurchaseOrder:
    po = await session.get(PurchaseOrder, po_id)
    if po is None or po.tenant_id != tenant_id:
        raise ValidationFailedError(
            message="Referenced purchase order does not exist",
            code="procurement.purchase_order_not_found",
            details={"purchase_order_id": str(po_id)},
        )
    if PurchaseOrderStatus(po.status) not in _RECEIVABLE_PO_STATUSES:
        raise ValidationFailedError(
            message=f"A {po.status} purchase order cannot receive goods",
            code="procurement.po_not_receivable",
            details={"purchase_order_id": str(po_id), "status": po.status},
        )
    return po


async def _validate_receipt_line(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    po_id: uuid.UUID,
    po_lines: dict[uuid.UUID, PurchaseOrderLine],
    payload_line: object,
) -> _ReceiptLineInput:
    """Validate one receipt line against its PO line: the line belongs to the PO, the quantity is
    > 0 and within the still-open quantity (over-receipt REJECTED 422 in v1), and the target bin
    exists in inventory (D-029). Snapshots the item + unit_cost from the PO line."""
    po_line = po_lines.get(payload_line.purchase_order_line_id)  # type: ignore[attr-defined]
    if po_line is None:
        raise ValidationFailedError(
            message="The receipt line does not belong to this purchase order",
            code="procurement.gr_line_not_on_po",
            details={
                "purchase_order_id": str(po_id),
                "purchase_order_line_id": str(
                    payload_line.purchase_order_line_id  # type: ignore[attr-defined]
                ),
            },
        )
    qty = validate_quantity(payload_line.received_quantity)  # type: ignore[attr-defined]
    open_qty = Decimal(str(po_line.quantity)) - Decimal(str(po_line.received_quantity))
    if qty > open_qty:
        raise ValidationFailedError(
            message="The received quantity exceeds the purchase-order line's open quantity",
            code="procurement.over_receipt",
            details={
                "purchase_order_line_id": str(po_line.id),
                "open_quantity": str(open_qty),
                "received_quantity": str(qty),
            },
        )
    bin_id = payload_line.bin_id  # type: ignore[attr-defined]
    if not await inventory_queries.bin_exists(session, tenant_id, bin_id):
        raise ValidationFailedError(
            message="The target bin does not exist in inventory",
            code="procurement.gr_bin_not_found",
            details={"bin_id": str(bin_id)},
        )
    requires_inspection = payload_line.requires_inspection  # type: ignore[attr-defined]
    return _ReceiptLineInput(
        purchase_order_line_id=po_line.id,
        item_id=po_line.item_id,
        unit_cost=Decimal(str(po_line.unit_cost)),
        bin_id=bin_id,
        received_quantity=qty,
        lot_code=payload_line.lot_code,  # type: ignore[attr-defined]
        serial_code=payload_line.serial_code,  # type: ignore[attr-defined]
        requires_inspection=bool(requires_inspection),
    )


async def create_goods_receipt(
    session: AsyncSession, tenant_id: uuid.UUID, payload: GoodsReceiptCreate
) -> GoodsReceipt:
    """Create a DRAFT goods receipt against a PO (PLAN 6.3). Validates the PO is receivable, each
    line belongs to it, the quantity is within the open quantity (over-receipt → 422
    procurement.over_receipt), and the bin exists. Snapshots the vendor + per-line item/unit_cost
    from the PO and claims the GR number at creation (D-040). No stock moves yet — that is POST."""
    if not payload.lines:
        raise ValidationFailedError(
            message="A goods receipt needs at least one line",
            code="procurement.gr_no_lines",
        )
    po = await _require_receivable_po(session, tenant_id, payload.purchase_order_id)
    po_lines = {line.id: line for line in await _po_lines(session, tenant_id, po.id)}
    receipt_date = payload.receipt_date or date.today()

    validated = [
        await _validate_receipt_line(session, tenant_id, po.id, po_lines, line)
        for line in payload.lines
    ]

    gr_id = uuid.uuid4()
    document = await docflow.register_document(
        session,
        tenant_id,
        GOODS_RECEIPT_DOC_TYPE,
        gr_id,
        doc_number=None,
        status=GoodsReceiptStatus.DRAFT.value,
    )
    number = await claim_document_number(
        session,
        tenant_id,
        sequence_name=GOODS_RECEIPT_SEQUENCE_NAME,
        prefix=GOODS_RECEIPT_NUMBER_PREFIX,
        padding=GOODS_RECEIPT_NUMBER_PADDING,
        on_date=receipt_date,
    )

    gr = GoodsReceipt(
        id=gr_id,
        tenant_id=tenant_id,
        document_id=document.id,
        gr_number=number,
        status=GoodsReceiptStatus.DRAFT.value,
        purchase_order_id=po.id,
        vendor_id=po.vendor_id,
        warehouse_id=payload.warehouse_id,
        receipt_date=receipt_date,
        notes=payload.notes,
    )
    session.add(gr)
    for index, line in enumerate(validated, start=1):
        session.add(
            GoodsReceiptLine(
                tenant_id=tenant_id,
                gr_id=gr_id,
                line_number=index,
                purchase_order_line_id=line.purchase_order_line_id,
                item_id=line.item_id,
                bin_id=line.bin_id,
                received_quantity=line.received_quantity,
                unit_cost=line.unit_cost,
                lot_code=line.lot_code,
                serial_code=line.serial_code,
                requires_inspection=line.requires_inspection,
            )
        )
    await session.flush()
    await docflow.set_document_status(
        session, tenant_id, document.id, doc_number=number, status=GoodsReceiptStatus.DRAFT.value
    )
    return gr


async def post_goods_receipt(
    session: AsyncSession, tenant_id: uuid.UUID, gr_id: uuid.UUID
) -> GoodsReceipt:
    """Post a DRAFT goods receipt (PLAN 6.3, D-041) — the heart. In ONE transaction: raise each PO
    line's received_quantity, advance the PO status (PARTIALLY_RECEIVED / RECEIVED), link docflow
    PO→GR, set the GR POSTED, and PUBLISH ``GoodsReceiptPosted`` so inventory's handler creates the
    stock RECEIPT moves (Dr Inventory / Cr GR-IR) and finance posts the journals — all here, before
    commit (D-011). A closed receipt period trips a move's journal trigger and rolls it ALL back.

    Idempotent re-post is rejected (a POSTED GR is terminal — corrected by a reversing GR/return,
    Phase 7). The caller commits via uow; the published event is drained in that same uow."""
    gr = await get_goods_receipt(session, tenant_id, gr_id)
    status = GoodsReceiptStatus(gr.status)
    if status == GoodsReceiptStatus.POSTED:
        raise ConflictError(
            message="The goods receipt is already posted",
            code="procurement.gr_already_posted",
            details={"goods_receipt_id": str(gr_id)},
        )
    if status != GoodsReceiptStatus.DRAFT:
        raise ConflictError(
            message=f"A {gr.status} goods receipt cannot be posted",
            code="procurement.gr_not_postable",
            details={"goods_receipt_id": str(gr_id), "status": gr.status},
        )

    # Resolve the GR/IR clearing account up front (finance/queries, downward) — raises 422 if the
    # tenant has not mapped it, so the post fails before any state changes (D-041).
    gr_ir_account_id = await finance_queries.gr_ir_clearing_account(session, tenant_id)

    lines = await get_goods_receipt_lines(session, tenant_id, gr_id)
    po_lines = {line.id: line for line in await _po_lines(session, tenant_id, gr.purchase_order_id)}

    moves: list[GoodsReceiptMove] = []
    for line in lines:
        po_line = po_lines[line.purchase_order_line_id]
        po_line.received_quantity = Decimal(str(po_line.received_quantity)) + Decimal(
            str(line.received_quantity)
        )
        moves.append(
            GoodsReceiptMove(
                item_id=line.item_id,
                bin_id=line.bin_id,
                quantity=Decimal(str(line.received_quantity)),
                unit_cost=Decimal(str(line.unit_cost)),
                lot_code=line.lot_code,
                serial_code=line.serial_code,
                requires_inspection=line.requires_inspection,
            )
        )

    await _advance_po_status(session, tenant_id, gr.purchase_order_id, po_lines.values())

    gr.status = GoodsReceiptStatus.POSTED.value
    gr.posted_at = datetime.now()
    await session.flush()
    await docflow.set_document_status(
        session, tenant_id, gr.document_id, status=GoodsReceiptStatus.POSTED.value
    )
    # Link PO document → GR document ('received_by') for the docflow chain (the GR→move edges are
    # written by inventory's handler when it creates the moves — D-041).
    po = await session.get(PurchaseOrder, gr.purchase_order_id)
    if po is not None:
        await docflow.link_documents(
            session,
            tenant_id,
            predecessor=po.document_id,
            successor=gr.document_id,
            link_type=PO_RECEIVED_BY_GR_LINK,
        )

    # Publish AFTER procurement's own writes settle: inventory's handler creates the moves with the
    # GR/IR offset and finance posts the journals, all drained in this same uow (D-011/D-041).
    publish(
        session,
        GoodsReceiptPosted(
            tenant_id=tenant_id,
            goods_receipt_id=gr.id,
            gr_number=gr.gr_number,
            document_id=gr.document_id,
            warehouse_id=gr.warehouse_id,
            move_date=gr.receipt_date.isoformat(),
            gr_ir_account_id=gr_ir_account_id,
            moves=tuple(moves),
        ),
    )
    return gr


async def cancel_goods_receipt(
    session: AsyncSession, tenant_id: uuid.UUID, gr_id: uuid.UUID
) -> GoodsReceipt:
    """Cancel a DRAFT goods receipt (PLAN 6.3). A POSTED GR is TERMINAL — it has moved stock and
    posted journals, so it is corrected by a reversing GR / a return (Phase 7 RMA), never cancelled
    (v1 has no reverse-GR; documented). Cancelling a DRAFT moves nothing."""
    gr = await get_goods_receipt(session, tenant_id, gr_id)
    if GoodsReceiptStatus(gr.status) != GoodsReceiptStatus.DRAFT:
        raise ConflictError(
            message=f"A {gr.status} goods receipt cannot be cancelled",
            code="procurement.gr_not_cancellable",
            details={"goods_receipt_id": str(gr_id), "status": gr.status},
        )
    gr.status = GoodsReceiptStatus.CANCELLED.value
    await session.flush()
    await docflow.set_document_status(
        session, tenant_id, gr.document_id, status=GoodsReceiptStatus.CANCELLED.value
    )
    return gr


async def _po_lines(
    session: AsyncSession, tenant_id: uuid.UUID, po_id: uuid.UUID
) -> list[PurchaseOrderLine]:
    stmt = select(PurchaseOrderLine).where(
        PurchaseOrderLine.tenant_id == tenant_id, PurchaseOrderLine.po_id == po_id
    )
    return list((await session.execute(stmt)).scalars().all())


async def _advance_po_status(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    po_id: uuid.UUID,
    po_lines,
) -> None:
    """Advance the PO status after a receipt raised the lines' received_quantity (PLAN 6.3):
    RECEIVED when every line is fully received (received >= ordered), else PARTIALLY_RECEIVED. The
    PO + lines are already loaded/mutated in this session, so this reads the in-memory state."""
    fully_received = all(
        Decimal(str(line.received_quantity)) >= Decimal(str(line.quantity)) for line in po_lines
    )
    po = await session.get(PurchaseOrder, po_id)
    if po is None or po.tenant_id != tenant_id:
        return
    new_status = (
        PurchaseOrderStatus.RECEIVED if fully_received else PurchaseOrderStatus.PARTIALLY_RECEIVED
    )
    po.status = new_status.value
    await session.flush()
    await docflow.set_document_status(session, tenant_id, po.document_id, status=new_status.value)
