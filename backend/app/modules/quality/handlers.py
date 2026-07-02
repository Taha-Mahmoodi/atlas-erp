"""Quality domain-event handlers (D-011/D-050) — the goods-receipt → inspection-lot bridge.

``create_inspection_lots_for_receipt`` subscribes to procurement's ``GoodsReceiptPosted`` and
creates
one OPEN ``InspectionLot`` per GR line flagged ``requires_inspection=True``, in the SAME transaction
as the GR post (D-011 run_in_uow drains before commit). This is the SANCTIONED cross-module
mechanism
(STRUCTURE §5): quality must NOT import procurement's service, so the GR post publishes
``GoodsReceiptPosted`` (a plain typed event — the only procurement file this handler imports) and
quality reacts by creating its OWN lots.

The handler runs ALONGSIDE inventory's ``receive_goods_receipt_moves`` on the same event key. D-011
dispatches handlers for one key in REGISTRATION order, and inventory is registered before quality
(the module import order), so inventory's handler has already created each move (and, for a tracked
item, the lot/serial master instance) by the time this runs — letting this handler resolve the GR
line's lot/serial CODE to the inventory instance id via inventory/queries for the lot's traceability
columns. A flagged GR thus atomically creates its inspection lots; an unflagged line creates none.

The GR↔lot linkage is recorded in DOCFLOW (GR document → 'inspected_by' → lot document, D-050), NOT
a
cross-module FK — quality owns the lot, so it writes the edge from its side. Registration:
``app.main.register_event_handlers`` subscribes this at the app factory (the deterministic D-011
seam), so the test harness re-registers after its per-test ``clear_subscriptions`` reset.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.modules.inventory import queries as inventory_queries
from app.modules.procurement.events import GoodsReceiptPosted
from app.modules.quality.constants import GR_INSPECTED_BY_LOT_LINK
from app.modules.quality.service import create_lot_from_receipt_line


async def create_inspection_lots_for_receipt(
    session: AsyncSession, event: GoodsReceiptPosted
) -> None:
    """Create the OPEN inspection lots for a posted goods receipt (D-050), in the GR's transaction.

    One lot per GR line flagged ``requires_inspection=True`` (an unflagged line creates none). Each
    lot snapshots the GR line's item / bin / quantity / lot-serial and links the GR document →
    'inspected_by' → the lot document so the docflow chain shows PO → GR → inspection lot.
    Registered
    via ``app.main.register_event_handlers`` (not an import-time ``@on``), so the test harness
    re-registers it after its per-test reset."""
    move_date = date.fromisoformat(event.move_date)
    for line in event.moves:
        if not line.requires_inspection:
            continue
        # Inventory's handler ran first (registration order, D-011) and created the lot/serial
        # instance for a tracked item, so the CODE now resolves to an id for the lot's traceability.
        inventory_lot_id = (
            await inventory_queries.lot_id_for_code(
                session, event.tenant_id, line.item_id, line.lot_code
            )
            if line.lot_code is not None
            else None
        )
        serial_id = (
            await inventory_queries.serial_id_for_code(
                session, event.tenant_id, line.item_id, line.serial_code
            )
            if line.serial_code is not None
            else None
        )
        lot = await create_lot_from_receipt_line(
            session,
            event.tenant_id,
            source_document_id=event.document_id,
            item_id=line.item_id,
            warehouse_id=event.warehouse_id,
            bin_id=line.bin_id,
            quantity=line.quantity,
            inventory_lot_id=inventory_lot_id,
            serial_id=serial_id,
            created_date=move_date,
        )
        await docflow.link_documents(
            session,
            event.tenant_id,
            predecessor=event.document_id,
            successor=lot.document_id,
            link_type=GR_INSPECTED_BY_LOT_LINK,
        )


__all__ = ["create_inspection_lots_for_receipt"]
