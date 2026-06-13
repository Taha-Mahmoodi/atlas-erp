"""Inventory domain-event handlers (D-011/D-041) — the cross-module GR → stock-move bridge.

Subscribes to ``procurement.goods_receipt.posted`` and creates one stock RECEIPT move per GR line in
the SAME transaction as the GR post (D-011 run_in_uow drains before commit). This is the SANCTIONED
cross-module mechanism (STRUCTURE §5): procurement must NOT import inventory's service, so the GR
post publishes ``GoodsReceiptPosted`` (a plain typed event — the only procurement file this handler
imports) and inventory reacts by calling its OWN ``stock_moves.create_move``. The mirror of the
existing inventory→finance pattern (inventory publishes StockValued, finance/handlers posts the
journal) — here procurement publishes, inventory handles.

Each move passes ``valuation_offset_account_id`` = the GR/IR clearing account from the event, so the
move's costing event (StockValued) carries it as ``offset_account_id`` and finance's COGS handler
credits GR/IR — yielding Dr Inventory / Cr GR-IR (the three-way-match's clearing leg) instead of
the standalone price-difference offset. The whole chain — GR + N moves + N inventory-debit/GR-IR
journals — lands in ONE transaction; any failure (a closed receipt period trips a move's period
trigger, insufficient anything) rolls the WHOLE GR post back (D-020 all-or-nothing).

The GR↔move linkage is recorded in DOCFLOW (GR document → 'moved_by' → move document, D-041), NOT a
cross-module FK — inventory owns the move, so it writes the edge from its side; procurement reads
the chain to render the flow. Procurement updates its own PO received_quantity + GR status in the
same transaction after publishing (it owns those tables); the handler never writes a procurement
row.

Registration: ``app.main.register_event_handlers`` subscribes this at the app factory (the
deterministic D-011 registration seam), so the test harness re-registers after its per-test
``clear_subscriptions`` reset without a module re-import.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.modules.inventory.constants import MoveType
from app.modules.inventory.schemas import StockMoveCreate
from app.modules.inventory.service.stock_moves import create_move
from app.modules.procurement.constants import GR_MOVED_BY_STOCK_MOVE_LINK
from app.modules.procurement.events import GoodsReceiptPosted


async def receive_goods_receipt_moves(
    session: AsyncSession, event: GoodsReceiptPosted
) -> None:
    """Create the stock RECEIPT moves for a posted goods receipt (D-041), in the GR's transaction.

    One move per GR line, each offsetting to the event's GR/IR clearing account so the costing
    event posts Dr Inventory / Cr GR-IR. Links the GR document to each move document ('moved_by') so
    the docflow chain shows PO → GR → move(s). Registered via ``app.main.register_event_handlers``
    (not an import-time ``@on``), so the test harness re-registers it after its per-test reset."""
    move_date = date.fromisoformat(event.move_date)
    for line in event.moves:
        move = await create_move(
            session,
            event.tenant_id,
            StockMoveCreate(
                move_type=MoveType.RECEIPT,
                item_id=line.item_id,
                quantity=line.quantity,
                to_bin_id=line.bin_id,
                lot_code=line.lot_code,
                serial_code=line.serial_code,
                move_date=move_date,
                unit_cost=line.unit_cost,
                reference=event.gr_number,
            ),
            valuation_offset_account_id=event.gr_ir_account_id,
        )
        await docflow.link_documents(
            session,
            event.tenant_id,
            predecessor=event.document_id,
            successor=move.document_id,
            link_type=GR_MOVED_BY_STOCK_MOVE_LINK,
        )


__all__ = ["receive_goods_receipt_moves"]
