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

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.core.tenancy import system_context
from app.modules.hospitality.constants import TICKET_DEPLETED_BY_MOVE_LINK
from app.modules.hospitality.events import TicketIngredientsConsumed
from app.modules.industry.events import IndustryTemplateApplying
from app.modules.inventory.constants import CostingMethod, MoveType
from app.modules.inventory.models import ItemCategory, Uom
from app.modules.inventory.schemas import StockMoveCreate
from app.modules.inventory.service.stock_moves import create_move
from app.modules.manufacturing.constants import (
    PRODUCTION_ORDER_FINISHED_TO_MOVE_LINK,
    PRODUCTION_ORDER_ISSUED_TO_MOVE_LINK,
)
from app.modules.manufacturing.events import ComponentsIssued, OrderFinished
from app.modules.procurement.constants import GR_MOVED_BY_STOCK_MOVE_LINK
from app.modules.procurement.events import GoodsReceiptPosted
from app.modules.quality.constants import (
    INSPECTION_DISPOSITIONED_BY_MOVE_LINK,
    RejectDisposition,
)
from app.modules.quality.events import InspectionDispositioned
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


async def issue_production_components(
    session: AsyncSession, event: ComponentsIssued
) -> None:
    """Create the stock ISSUE moves for a production order's component issue (D-048), in the issue's
    transaction — a manufacturing twin of ``issue_delivery_moves`` but WITH a valuation-offset
    override.

    One move per component line, each issuing FROM the line's source bin, each passing
    ``valuation_offset_account_id`` = the event's ``wip_account_id`` (the OVERRIDE, mirroring 6.3's
    GR/IR override but on an ISSUE) so the costing engine posts Dr WIP / Cr Inventory at the
    component's moving-average/FIFO cost — instead of the default Dr COGS / Cr Inventory. The
    costing engine COMPUTES the cost of the stock that left, so no unit_cost is passed. Insufficient
    stock at a bin raises InsufficientStockError, rolling the whole issue back (D-020). Links the
    order document to each move document ('issued_to'). Registered via
    ``app.main.register_event_handlers`` (not an import-time ``@on``), so the test harness
    re-registers it after its per-test ``clear_subscriptions`` reset."""
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
                reference=event.order_number,
            ),
            valuation_offset_account_id=event.wip_account_id,
        )
        await docflow.link_documents(
            session,
            event.tenant_id,
            predecessor=event.document_id,
            successor=move.document_id,
            link_type=PRODUCTION_ORDER_ISSUED_TO_MOVE_LINK,
        )


async def issue_ticket_ingredients(
    session: AsyncSession, event: TicketIngredientsConsumed
) -> None:
    """Create the stock ISSUE moves for a fired restaurant ticket's ingredients (PLAN 19, Q4) — the
    hospitality twin of ``issue_delivery_moves``, and like a delivery it passes NO valuation
    override, because an ISSUE's default offset already IS the category's COGS account.

    One move per AGGREGATED ingredient (hospitality collapses a ticket's shared onion/oil/salt
    before publishing, so this loop is ~12 long for a 56-line check), each from the bin the event
    resolved, dated the ticket's FIRE date. Runs inside the DEPLETION JOB's transaction, not the
    sale's — insufficient stock still rolls the whole depletion back (D-020), but it rolls back a
    background job instead of a guest's payment. Links the ticket document to each move document
    ('depleted_by'). Registered via ``app.main.register_event_handlers``."""
    move_date = date.fromisoformat(event.move_date)
    for ingredient in event.ingredients:
        move = await create_move(
            session,
            event.tenant_id,
            StockMoveCreate(
                move_type=MoveType.ISSUE,
                item_id=ingredient.item_id,
                quantity=ingredient.quantity,
                from_bin_id=ingredient.bin_id,
                move_date=move_date,
                reference=event.ticket_number,
            ),
        )
        await docflow.link_documents(
            session,
            event.tenant_id,
            predecessor=event.document_id,
            successor=move.document_id,
            link_type=TICKET_DEPLETED_BY_MOVE_LINK,
        )


async def receive_finished_order_move(
    session: AsyncSession, event: OrderFinished
) -> None:
    """Create the finished-goods RECEIPT move for a finished production order (D-048), in the
    finish's transaction — the INBOUND counterpart of ``issue_production_components``.

    One RECEIPT move for the parent item, receiving INTO the destination bin at the event's
    ``unit_cost`` (= accumulated WIP / finished quantity), passing
    ``valuation_offset_account_id`` = the event's ``wip_account_id`` (the OVERRIDE) so the costing
    posts Dr Inventory / Cr WIP — REVERSING the component issues' WIP debit so WIP nets toward zero.
    A tracked item's lot/serial CODE may create the master instance on the fly (a RECEIPT
    allowance). Links the order document to the move document ('finished_to'). A closed period trips
    the move's WIP journal trigger and rolls the whole finish back. Registered via
    ``app.main.register_event_handlers`` (not an import-time ``@on``)."""
    move_date = date.fromisoformat(event.move_date)
    line = event.move
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
            reference=event.order_number,
        ),
        valuation_offset_account_id=event.wip_account_id,
    )
    await docflow.link_documents(
        session,
        event.tenant_id,
        predecessor=event.document_id,
        successor=move.document_id,
        link_type=PRODUCTION_ORDER_FINISHED_TO_MOVE_LINK,
    )


async def disposition_rejected_stock(
    session: AsyncSession, event: InspectionDispositioned
) -> None:
    """Move the REJECTED stock for a rejected inspection lot (D-050), in the decision's transaction
    —
    the quality twin of the GR/delivery bridges.

    SCRAP → an ADJUSTMENT-out (``from_bin`` set, no ``to_bin``): the costing engine offsets an
    ADJUSTMENT-down to the price-difference / inventory-adjustment account (the write-off), so the
    move posts Dr inventory-adjustment / Cr Inventory at the stock's book value — total on-hand
    drops. BLOCK → a TRANSFER from the receiving bin to the event's blocked/QI bin: value-neutral (a
    within-warehouse transfer publishes no costing journal), so total on-hand is unchanged but the
    stock leaves the usable bin. The costing engine COMPUTES the cost of the stock that left, so no
    unit_cost is passed. Insufficient stock at the bin raises InsufficientStockError, rolling the
    decision back (D-020). Links the inspection-lot document → 'dispositioned_by' → move document.
    Registered via ``app.main.register_event_handlers`` (not an import-time ``@on``)."""
    move_date = date.fromisoformat(event.move_date)
    disposition = RejectDisposition(event.disposition)
    if disposition == RejectDisposition.SCRAP:
        payload = StockMoveCreate(
            move_type=MoveType.ADJUSTMENT,
            item_id=event.item_id,
            quantity=event.rejected_quantity,
            from_bin_id=event.from_bin_id,
            lot_id=event.inventory_lot_id,
            serial_id=event.serial_id,
            move_date=move_date,
            reference=event.lot_number,
        )
    else:  # BLOCK — a quarantine transfer to the blocked bin
        payload = StockMoveCreate(
            move_type=MoveType.TRANSFER,
            item_id=event.item_id,
            quantity=event.rejected_quantity,
            from_bin_id=event.from_bin_id,
            to_bin_id=event.to_bin_id,
            lot_id=event.inventory_lot_id,
            serial_id=event.serial_id,
            move_date=move_date,
            reference=event.lot_number,
        )
    move = await create_move(session, event.tenant_id, payload)
    await docflow.link_documents(
        session,
        event.tenant_id,
        predecessor=event.document_id,
        successor=move.document_id,
        link_type=INSPECTION_DISPOSITIONED_BY_MOVE_LINK,
    )


async def provision_inventory_for_template(
    session: AsyncSession, event: IndustryTemplateApplying
) -> None:
    """Create the inventory slice (UoMs + item categories) of an applied industry template (PLAN
    14.1, D-060), idempotently, in the apply's transaction — the §5-clean provisioning seam: the
    industry module publishes ``IndustryTemplateApplying`` and inventory reacts here, creating ITS
    OWN master rows through its own models (industry never imports inventory/service).

    Idempotency (D-060): every create is SKIP-IF-EXISTS by code (the natural key), so re-applying
    the same template never duplicates. Item categories carry the template's default costing method
    (retail/healthcare FIFO, manufacturing/construction moving-average) but NO GL-account wiring —
    that is wired later when stocked items post moves (D-029); a provisioning preset only seeds the
    method. Runs under ``system_context`` so tenant_id is stamped explicitly. Registered via
    ``app.main.register_event_handlers`` (the D-011 seam)."""
    template = event.template
    tenant_id = event.tenant_id
    with system_context():
        existing_uoms = {
            code
            for (code,) in (
                await session.execute(select(Uom.code).where(Uom.tenant_id == tenant_id))
            ).all()
        }
        for uom in template.uoms:
            if uom.code not in existing_uoms:
                session.add(Uom(tenant_id=tenant_id, code=uom.code, name=uom.name))
        existing_categories = {
            code
            for (code,) in (
                await session.execute(
                    select(ItemCategory.code).where(ItemCategory.tenant_id == tenant_id)
                )
            ).all()
        }
        for category in template.item_categories:
            if category.code in existing_categories:
                continue
            session.add(
                ItemCategory(
                    tenant_id=tenant_id,
                    code=category.code,
                    name=category.name,
                    default_costing_method=CostingMethod(
                        category.default_costing_method
                    ).value,
                )
            )
        await session.flush()


__all__ = [
    "disposition_rejected_stock",
    "issue_delivery_moves",
    "issue_production_components",
    "issue_ticket_ingredients",
    "provision_inventory_for_template",
    "receive_finished_order_move",
    "receive_goods_receipt_moves",
    "receive_return_moves",
]
