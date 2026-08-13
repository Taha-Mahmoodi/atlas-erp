"""Inspection-lot service (PLAN 9.1, D-050): the GR-handler lot creation + list/get + the usage
decision (accept/reject with SCRAP/BLOCK disposition) + cancel.

The DELIBERATELY SMALL v1 QM core (s4hana-parity §QM): no inspection plans, no characteristics, no
results recording, no usage-decision code catalogs, no quality notifications. A lot is created OPEN
by
the goods-receipt handler; a usage decision accepts/rejects the whole lot; a reject dispositions the
rejected stock through the EVENT BUS.

§5 (D-050): this module imports only inventory/queries DOWNWARD (bin existence) + its own events —
NEVER inventory/finance/procurement SERVICE. A reject's stock move is inventory's own work,
triggered
by the ``InspectionDispositioned`` event. The lot creation is invoked by the GR handler (which
itself
runs off procurement's ``GoodsReceiptPosted`` — quality never imports procurement service).

THE ACCEPTED-NEEDS-NO-MOVE RATIONALE (D-050): a v1 inspection lot does NOT hold stock in a separate
quality-inspection bucket — the received stock is already on hand and usable. So an ACCEPT changes
no
stock (it just records the outcome); only a REJECT moves stock (SCRAP out / BLOCK aside).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.core.events import publish
from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.numbering import claim_number, ensure_sequence
from app.core.pagination import (
    DEFAULT_LIMIT,
    OrderKey,
    SortDirection,
    filter_fingerprint,
    paginate,
)
from app.core.schemas import Page
from app.modules.inventory import queries as inventory_queries
from app.modules.quality.constants import (
    INSPECTION_LOT_DOC_TYPE,
    INSPECTION_LOT_NUMBER_PADDING,
    INSPECTION_LOT_NUMBER_PREFIX,
    INSPECTION_LOT_SEQUENCE_NAME,
    InspectionLotStatus,
    InspectionSource,
    RejectDisposition,
)
from app.modules.quality.events import InspectionDispositioned
from app.modules.quality.models import InspectionLot
from app.modules.quality.schemas import InspectionDecideRequest


async def get_inspection_lot(
    session: AsyncSession, tenant_id: uuid.UUID, lot_id: uuid.UUID
) -> InspectionLot:
    """The inspection lot, or 404 ``quality.inspection_lot_not_found``."""
    lot = await session.get(InspectionLot, lot_id)
    if lot is None or lot.tenant_id != tenant_id:
        raise NotFoundError(
            message="Inspection lot not found",
            code="quality.inspection_lot_not_found",
        )
    return lot


async def list_inspection_lots(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    status: InspectionLotStatus | None = None,
    item_id: uuid.UUID | None = None,
    source: InspectionSource | None = None,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Page[InspectionLot]:
    """Keyset-paginated inspection lots ordered by lot_number (D-014). The status/item/source
    filters
    narrow the set (index-served by (tenant, status) / (tenant, item_id)) and fold into the cursor
    fingerprint."""
    stmt = select(InspectionLot).where(InspectionLot.tenant_id == tenant_id)
    if status is not None:
        stmt = stmt.where(InspectionLot.status == status.value)
    if item_id is not None:
        stmt = stmt.where(InspectionLot.item_id == item_id)
    if source is not None:
        stmt = stmt.where(InspectionLot.source == source.value)
    fingerprint = filter_fingerprint(status, item_id, source)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(InspectionLot.lot_number, SortDirection.ASC)],
        pk=InspectionLot.id,
        cursor=cursor,
        limit=limit,
        filters=fingerprint,
    )


async def create_lot_from_receipt_line(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    source_document_id: uuid.UUID,
    item_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    bin_id: uuid.UUID,
    quantity: Decimal,
    inventory_lot_id: uuid.UUID | None,
    serial_id: uuid.UUID | None,
    created_date: date,
) -> InspectionLot:
    """Create one OPEN inspection lot for a flagged GR line (D-050) — called by the GR handler in
    the
    GR post's transaction. Registers the document, claims the gapless QL- number (a permanent
    document at creation, the orders/receipts branch), and snapshots the GR line's item/bin/qty/
    tracked-instance. The docflow GR→lot edge is written by the caller (the handler)."""
    lot_id = uuid.uuid4()
    document = await docflow.register_document(
        session,
        tenant_id,
        INSPECTION_LOT_DOC_TYPE,
        lot_id,
        doc_number=None,
        status=InspectionLotStatus.OPEN.value,
    )
    await ensure_sequence(
        session,
        tenant_id,
        INSPECTION_LOT_SEQUENCE_NAME,
        INSPECTION_LOT_NUMBER_PREFIX,
        INSPECTION_LOT_NUMBER_PADDING,
        year_reset=True,
    )
    number = await claim_number(
        session, tenant_id, INSPECTION_LOT_SEQUENCE_NAME, on_date=created_date
    )
    lot = InspectionLot(
        id=lot_id,
        tenant_id=tenant_id,
        document_id=document.id,
        lot_number=number,
        status=InspectionLotStatus.OPEN.value,
        source=InspectionSource.GOODS_RECEIPT.value,
        source_document_id=source_document_id,
        item_id=item_id,
        warehouse_id=warehouse_id,
        bin_id=bin_id,
        inspect_lot_id=inventory_lot_id,
        serial_id=serial_id,
        quantity=Decimal(str(quantity)),
        accepted_quantity=Decimal(0),
        rejected_quantity=Decimal(0),
        created_date=created_date,
    )
    session.add(lot)
    await session.flush()
    await docflow.set_document_status(
        session,
        tenant_id,
        document.id,
        doc_number=number,
        status=InspectionLotStatus.OPEN.value,
    )
    return lot


def _validate_decision_split(lot: InspectionLot, payload: InspectionDecideRequest) -> None:
    """The accept/reject split must be non-negative and sum to EXACTLY the lot quantity (v1: one
    decision covers the whole lot)."""
    accepted = Decimal(str(payload.accepted_quantity))
    rejected = Decimal(str(payload.rejected_quantity))
    if accepted < 0 or rejected < 0:
        raise ValidationFailedError(
            message="Accepted and rejected quantities must be non-negative",
            code="quality.decision_quantity_invalid",
        )
    if accepted + rejected != Decimal(str(lot.quantity)):
        raise ValidationFailedError(
            message="Accepted plus rejected quantity must equal the lot quantity",
            code="quality.decision_quantity_mismatch",
            details={
                "lot_quantity": str(lot.quantity),
                "accepted_quantity": str(accepted),
                "rejected_quantity": str(rejected),
            },
        )


async def _validate_disposition(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    payload: InspectionDecideRequest,
) -> RejectDisposition:
    """A reject (rejected > 0) requires an IMPLEMENTED disposition; a BLOCK requires a valid
    destination bin. Returns the validated disposition."""
    if payload.disposition is None:
        raise ValidationFailedError(
            message="A rejection requires a disposition",
            code="quality.disposition_required",
        )
    disposition = RejectDisposition(payload.disposition)
    if disposition == RejectDisposition.RETURN_TO_VENDOR:
        raise ValidationFailedError(
            message="RETURN_TO_VENDOR disposition is not implemented in v1",
            code="quality.disposition_not_implemented",
            details={"disposition": disposition.value},
        )
    if disposition == RejectDisposition.BLOCK:
        if payload.blocked_bin_id is None:
            raise ValidationFailedError(
                message="A BLOCK disposition requires a destination blocked bin",
                code="quality.blocked_bin_required",
            )
        if not await inventory_queries.bin_exists(
            session, tenant_id, payload.blocked_bin_id
        ):
            raise ValidationFailedError(
                message="The blocked bin does not exist",
                code="quality.blocked_bin_not_found",
                details={"bin_id": str(payload.blocked_bin_id)},
            )
    return disposition


async def decide(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    lot_id: uuid.UUID,
    payload: InspectionDecideRequest,
    *,
    decision_by: uuid.UUID,
    decided_date: date | None = None,
) -> InspectionLot:
    """The usage DECISION (D-050) — accept/reject the lot. Validates the accept/reject split sums to
    the lot quantity; when rejected > 0 requires a disposition and PUBLISHES
    ``InspectionDispositioned`` so inventory moves the rejected stock (SCRAP = an ADJUSTMENT-out
    write-off; BLOCK = a TRANSFER to the blocked bin). Sets ACCEPTED (rejected == 0) or REJECTED
    (rejected > 0) with both quantities recorded; stamps decided_date/by. ACCEPTED needs NO stock
    move — the accepted stock is already on hand and usable. Idempotent: a decided lot is terminal
    (re-decide → 409). Atomic — a SCRAP write-off into a CLOSED period rolls the whole decision
    back.
    The caller commits via uow; the published event drains in that same uow."""
    lot = await get_inspection_lot(session, tenant_id, lot_id)
    if InspectionLotStatus(lot.status) != InspectionLotStatus.OPEN:
        raise ConflictError(
            message=f"A {lot.status} inspection lot cannot be decided",
            code="quality.lot_not_open",
            details={"lot_id": str(lot_id), "status": lot.status},
        )

    _validate_decision_split(lot, payload)
    accepted = Decimal(str(payload.accepted_quantity))
    rejected = Decimal(str(payload.rejected_quantity))

    disposition: RejectDisposition | None = None
    if rejected > 0:
        disposition = await _validate_disposition(session, tenant_id, payload)

    move_date = decided_date or date.today()
    lot.accepted_quantity = accepted
    lot.rejected_quantity = rejected
    lot.disposition = disposition.value if disposition is not None else None
    lot.decided_date = move_date
    lot.decision_by = decision_by
    lot.notes = payload.notes
    new_status = (
        InspectionLotStatus.ACCEPTED if rejected == 0 else InspectionLotStatus.REJECTED
    )
    lot.status = new_status.value
    await session.flush()
    await docflow.set_document_status(
        session, tenant_id, lot.document_id, status=new_status.value
    )

    # Only a REJECT moves stock — publish AFTER the lot's own writes settle so inventory's handler
    # creates the disposition move (and, for SCRAP, the write-off journal) in this same uow (D-011).
    if rejected > 0 and disposition is not None:
        publish(
            session,
            InspectionDispositioned(
                tenant_id=tenant_id,
                lot_id=lot.id,
                lot_number=lot.lot_number,
                document_id=lot.document_id,
                disposition=disposition.value,
                item_id=lot.item_id,
                rejected_quantity=rejected,
                from_bin_id=lot.bin_id,
                to_bin_id=(
                    payload.blocked_bin_id
                    if disposition == RejectDisposition.BLOCK
                    else None
                ),
                inventory_lot_id=lot.inspect_lot_id,
                serial_id=lot.serial_id,
                move_date=move_date.isoformat(),
            ),
        )
    return lot


async def cancel_lot(
    session: AsyncSession, tenant_id: uuid.UUID, lot_id: uuid.UUID
) -> InspectionLot:
    """Cancel an OPEN inspection lot (D-050) — a flagged GR posted in error, the lot is moot. A
    decided (ACCEPTED/REJECTED) lot is terminal and cannot be cancelled. Moves no stock."""
    lot = await get_inspection_lot(session, tenant_id, lot_id)
    if InspectionLotStatus(lot.status) != InspectionLotStatus.OPEN:
        raise ConflictError(
            message=f"A {lot.status} inspection lot cannot be cancelled",
            code="quality.lot_not_cancellable",
            details={"lot_id": str(lot_id), "status": lot.status},
        )
    lot.status = InspectionLotStatus.CANCELLED.value
    await session.flush()
    await docflow.set_document_status(
        session, tenant_id, lot.document_id, status=InspectionLotStatus.CANCELLED.value
    )
    return lot


__all__ = [
    "cancel_lot",
    "create_lot_from_receipt_line",
    "decide",
    "get_inspection_lot",
    "list_inspection_lots",
]
