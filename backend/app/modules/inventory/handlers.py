"""Inventory domain-event handlers (D-011/D-041/D-045) — the cross-module document → stock-move
bridges.

TWO symmetric handlers. ``receive_goods_receipt_moves`` (INBOUND, below) creates RECEIPT moves for
a posted goods receipt; ``issue_delivery_moves`` (OUTBOUND, its twin, D-045) creates ISSUE moves for
a posted sales delivery. The KEY asymmetry: a receipt passes ``valuation_offset_account_id`` = the
GR/IR clearing account (so the move credits GR/IR); a delivery passes NO override, because an ISSUE
move's DEFAULT valuation offset IS the item-category COGS account (the costing engine routes an
ISSUE to COGS) — so a delivery posts Dr COGS / Cr Inventory with no account on the event. COGS *is*
the issue offset.

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
from app.modules.sales.constants import (
    DELIVERY_MOVED_BY_STOCK_MOVE_LINK,
    RETURN_RECEIVED_BY_STOCK_MOVE_LINK,
)
from app.modules.sales.events import DeliveryShipped, ReturnReceived


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


async def issue_delivery_moves(session: AsyncSession, event: DeliveryShipped) -> None:
    """Create the stock ISSUE moves for a posted delivery (D-045), in the delivery's transaction —
    the OUTBOUND twin of ``receive_goods_receipt_moves``.

    One move per delivery line, each issuing FROM the line's source bin. NO
    ``valuation_offset_account_id``: an ISSUE move's default offset is the item-category COGS
    account (the costing engine routes an ISSUE to COGS), so each move's costing event posts Dr COGS
    / Cr Inventory with no override — unlike the GR/IR receipt. The costing engine COMPUTES the COGS
    of the stock that left (FIFO layers / moving-average), so no unit_cost is passed. Insufficient
    stock at a bin raises InsufficientStockError, rolling the delivery post back (D-020). Links the
    delivery document to each move document ('moved_by') so the docflow chain shows order →
    delivery → move(s). Registered via ``app.main.register_event_handlers`` (not an import-time
    ``@on``), so the test harness re-registers it after its per-test reset."""
    move_date = date.fromisoformat(event.move_date)
    for line in event.moves:
        move = await create_move(
            session,
            event.tenant_id,
            StockMoveCreate(
                move_type=MoveType.ISSUE,
                item_id=line.item_id,
                quantity=line.quantity,
                from_bin_id=line.bin_id,
                lot_id=line.lot_id,
                serial_id=line.serial_id,
                move_date=move_date,
                reference=event.delivery_number,
            ),
        )
        await docflow.link_documents(
            session,
            event.tenant_id,
            predecessor=event.document_id,
            successor=move.document_id,
            link_type=DELIVERY_MOVED_BY_STOCK_MOVE_LINK,
        )


async def receive_return_moves(session: AsyncSession, event: ReturnReceived) -> None:
    """Create the stock RECEIPT moves for a posted sales return (D-046), in the return's transaction
    — the REVERSE of ``issue_delivery_moves`` (a return is a delivery run backwards).

    One move per return line, each receiving INTO the line's destination bin at the supplied
    ``unit_cost`` (the goods' current book cost). Each passes ``valuation_offset_account_id`` =
    the event's ``cogs_account_id`` (the OVERRIDE, mirroring 6.3's GR/IR override), so the costing
    event posts Dr Inventory / Cr COGS — REVERSING the original issue's COGS (a delivery's issue was
    Dr COGS / Cr Inventory). A tracked item's lot/serial CODE may create the master instance on the
    fly (a RECEIPT allowance, unlike an issue). Links the return document to each move document
    ('received_by') so the docflow chain shows order → return → move(s). A closed return period
    trips
    a move's valuation journal trigger and rolls the whole return post back. Registered via
    ``app.main.register_event_handlers`` (not an import-time ``@on``)."""
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
                reference=event.return_number,
            ),
            valuation_offset_account_id=event.cogs_account_id,
        )
        await docflow.link_documents(
            session,
            event.tenant_id,
            predecessor=event.document_id,
            successor=move.document_id,
            link_type=RETURN_RECEIVED_BY_STOCK_MOVE_LINK,
        )


__all__ = [
    "issue_delivery_moves",
    "receive_goods_receipt_moves",
    "receive_return_moves",
]
