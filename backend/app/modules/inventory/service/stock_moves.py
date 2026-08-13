"""The stock-move WRITE engine (PLAN 5.2, D-020/D-036): create_move (the heart) + reverse_move.

The read paths (``get_move``, ``list_moves``, ``list_on_hand``) live in ``stock_reads.py`` (split at
the 400-line cap); this module imports ``get_move`` from there and the package ``__init__``
re-exports both halves as one surface.

A stock move is the quantity SINGLE SOURCE OF TRUTH and is POSTED-at-creation + IMMUTABLE — no draft
phase, no edit, no delete; a correction is a NEW reversing move (D-017 applied to stock).
``create_move`` validates (item STOCKED; move_type's required bin sides present per MOVE_BIN_SIDES —
ADJUSTMENT one side, TRANSFER two DIFFERENT bins; bins exist in ACTIVE warehouses; quantity > 0;
tracking mode satisfied — lot/serial resolved, created on a receipt, serial ⇒ qty 1), registers the
document + claims the gapless STK number at creation (D-012), inserts the POSTED StockMove, and
updates the quant rows in the SAME transaction via ``apply_bin_delta`` (the CHECK >= 0 forbids
negative stock; transfer deltas applied in bin-id order for deadlock avoidance, D-020).

The whole thing is one unit of work: move + quant updates commit or roll back together, so the
ledger and the projection can never disagree. Idempotency (D-013) is owned by the endpoint.
Inventory imports only finance/queries downward (STRUCTURE §5); this engine imports neither.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.core.events import publish
from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.numbering import claim_number, ensure_sequence
from app.modules.inventory.constants import (
    MOVE_BIN_SIDES,
    STOCK_MOVE_DOC_TYPE,
    STOCK_MOVE_NUMBER_PADDING,
    STOCK_MOVE_NUMBER_PREFIX,
    STOCK_MOVE_REVERSES_LINK,
    STOCK_MOVE_SEQUENCE_NAME,
    ItemType,
    MoveStatus,
    MoveType,
    TrackingMode,
)
from app.modules.inventory.models import Bin, Item, StockMove
from app.modules.inventory.schemas import StockMoveCreate
from app.modules.inventory.service import costing, costing_reversal
from app.modules.inventory.service.stock_quants import (
    apply_bin_delta,
    resolve_lot,
    resolve_serial,
)
from app.modules.inventory.service.stock_reads import get_move


async def _require_stocked_item(
    session: AsyncSession, tenant_id: uuid.UUID, item_id: uuid.UUID
) -> Item:
    item = await session.get(Item, item_id)
    if item is None or item.tenant_id != tenant_id:
        raise NotFoundError(message="Item not found", code="inventory.item_not_found")
    if ItemType(item.item_type) != ItemType.STOCKED:
        raise ValidationFailedError(
            message="Only stocked items participate in stock moves",
            code="inventory.item_not_stocked",
            details={"item_id": str(item_id), "item_type": item.item_type},
        )
    return item


async def _require_active_bin(
    session: AsyncSession, tenant_id: uuid.UUID, bin_id: uuid.UUID, *, side: str
) -> Bin:
    """The bin exists, belongs to this tenant, and its warehouse is active. A move never lands stock
    in (or pulls from) a bin whose warehouse was deactivated."""
    bin_row = await session.get(Bin, bin_id)
    if bin_row is None or bin_row.tenant_id != tenant_id:
        raise ValidationFailedError(
            message=f"The {side} bin does not exist",
            code="inventory.bin_not_found",
            details={"bin_id": str(bin_id), "side": side},
        )
    if not bin_row.is_active:
        raise ValidationFailedError(
            message=f"The {side} bin is inactive",
            code="inventory.bin_inactive",
            details={"bin_id": str(bin_id), "side": side},
        )
    return bin_row


def _validate_bin_sides(
    move_type: MoveType, from_bin_id: uuid.UUID | None, to_bin_id: uuid.UUID | None
) -> None:
    """Enforce the move_type ⇒ required-bin-side rule (constants.MOVE_BIN_SIDES). ADJUSTMENT is the
    special case: EXACTLY ONE side. TRANSFER additionally requires the two bins to differ."""
    if move_type == MoveType.ADJUSTMENT:
        if (from_bin_id is None) == (to_bin_id is None):
            raise ValidationFailedError(
                message="An adjustment sets exactly one of from_bin / to_bin",
                code="inventory.adjustment_one_side",
            )
        return
    from_required, to_required = MOVE_BIN_SIDES[move_type]
    if from_required and from_bin_id is None:
        raise ValidationFailedError(
            message=f"{move_type.value} requires a from_bin",
            code="inventory.move_from_bin_required",
        )
    if not from_required and from_bin_id is not None:
        raise ValidationFailedError(
            message=f"{move_type.value} must not set a from_bin",
            code="inventory.move_from_bin_forbidden",
        )
    if to_required and to_bin_id is None:
        raise ValidationFailedError(
            message=f"{move_type.value} requires a to_bin",
            code="inventory.move_to_bin_required",
        )
    if not to_required and to_bin_id is not None:
        raise ValidationFailedError(
            message=f"{move_type.value} must not set a to_bin",
            code="inventory.move_to_bin_forbidden",
        )
    if move_type == MoveType.TRANSFER and from_bin_id == to_bin_id:
        raise ValidationFailedError(
            message="A transfer must move between two different bins",
            code="inventory.transfer_same_bin",
        )


def _is_inbound(move_type: MoveType, to_bin_id: uuid.UUID | None) -> bool:
    """Whether the move adds stock (the costing-inbound side): a RECEIPT, or a positive ADJUSTMENT
    (to_bin set). The inbound side is where the REQUIRED entry unit_cost applies (D-020)."""
    return move_type == MoveType.RECEIPT or (
        move_type == MoveType.ADJUSTMENT and to_bin_id is not None
    )


def _validate_unit_cost(payload: StockMoveCreate, move_type: MoveType) -> Decimal | None:
    """Costing input rule (D-020): a RECEIPT / positive ADJUSTMENT REQUIRES ``unit_cost`` (the value
    stock enters at, >= 0 — an explicit ZERO is the documented quantity-only correction: a count-up
    of stock with no book cost enters at 0 value and posts no journal, #87). An ISSUE / negative
    ADJUSTMENT / TRANSFER IGNORE any passed cost — the engine computes the outbound cost / carries
    the current valuation — so the move stores it as None and the engine fills it. Returns the
    validated entry cost (None for the computed sides)."""
    if _is_inbound(move_type, payload.to_bin_id):
        if payload.unit_cost is None or Decimal(payload.unit_cost) < 0:
            raise ValidationFailedError(
                message="A receipt or stock-increase requires a non-negative unit cost",
                code="inventory.receipt_unit_cost_required",
            )
        return Decimal(payload.unit_cost)
    return None


async def _apply_quant_deltas(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    item_id: uuid.UUID,
    lot_id: uuid.UUID | None,
    from_bin_id: uuid.UUID | None,
    to_bin_id: uuid.UUID | None,
    quantity: Decimal,
) -> None:
    """Update the maintained quant projection for one move (D-036): decrement from_bin, increment
    to_bin. The two sides are applied in deterministic bin-id order (deadlock avoidance, D-020:
    concurrent movers touching the same pair lock it in the same order). A decrement raises
    InsufficientStockError if it would go negative (no-negative-stock, D-020)."""
    deltas: list[tuple[uuid.UUID, Decimal]] = []
    if from_bin_id is not None:
        deltas.append((from_bin_id, -quantity))
    if to_bin_id is not None:
        deltas.append((to_bin_id, quantity))
    # Lock/update in ascending bin-id order so two concurrent transfers between the same bins
    # never deadlock by locking the pair in opposite orders (D-020 deadlock avoidance).
    for bin_id, delta in sorted(deltas, key=lambda pair: pair[0].bytes):
        await apply_bin_delta(session, tenant_id, item_id, bin_id, lot_id, delta)


async def create_move(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    payload: StockMoveCreate,
    *,
    reversal_of: StockMove | None = None,
    valuation_offset_account_id: uuid.UUID | None = None,
) -> StockMove:
    """Create + POST a stock move (the heart, PLAN 5.2/5.3). Validates everything (see module
    docstring), claims the gapless STK number, inserts the POSTED move, updates the quant
    projection, runs COSTING and publishes the valuation event — all in ONE transaction (D-020). 422
    InsufficientStockError when an issue/transfer exceeds on-hand; NotFound for a missing item; 422
    for a non-stocked item or a bin-side rule break. The caller commits via uow.

    ``reversal_of`` (set by ``reverse_move``) runs the costing REVERSAL path: the reversing move
    replays the original's FIFO consumptions / re-applies its moving-average value and emits the
    OPPOSITE valuation event so the COGS journal is reversed too (D-020).

    ``valuation_offset_account_id`` (PLAN 6.3, D-041) OVERRIDES the receipt's standard
    valuation-offset (price-difference): the procurement goods-receipt path passes the GR/IR
    clearing account, so the StockValued event carries it as ``offset_account_id`` and the finance
    handler credits GR/IR. Ignored on non-receipt types and on a reversal. None ⇒ unchanged."""
    move_type = MoveType(payload.move_type)
    quantity = Decimal(payload.quantity)
    if quantity <= 0:
        raise ValidationFailedError(
            message="Move quantity must be greater than zero",
            code="inventory.move_quantity_invalid",
            details={"quantity": str(quantity)},
        )

    item = await _require_stocked_item(session, tenant_id, payload.item_id)
    _validate_bin_sides(move_type, payload.from_bin_id, payload.to_bin_id)
    # Costing input (D-020): a RECEIPT/positive-ADJUSTMENT requires the entry cost; computed sides
    # ignore it. Validated BEFORE any write so a missing cost fails fast (no number burned). A
    # reversal carries its cost from the original move (the costing reversal path), so it does not
    # need (and does not pass) an entry cost — skip the requirement.
    entry_cost = None if reversal_of is not None else _validate_unit_cost(payload, move_type)
    if payload.from_bin_id is not None:
        await _require_active_bin(session, tenant_id, payload.from_bin_id, side="from")
    if payload.to_bin_id is not None:
        await _require_active_bin(session, tenant_id, payload.to_bin_id, side="to")

    # A receipt MAY create a lot/serial master instance (5.1 deferred that to receipts); an
    # issue/transfer/adjustment-decrease must reference one that already exists with stock.
    create_instance = move_type == MoveType.RECEIPT
    lot_id = await resolve_lot(
        session,
        tenant_id,
        item,
        lot_id=payload.lot_id,
        lot_code=payload.lot_code,
        create_if_missing=create_instance,
    )
    serial_id = await resolve_serial(
        session,
        tenant_id,
        item,
        serial_id=payload.serial_id,
        serial_code=payload.serial_code,
        create_if_missing=create_instance,
    )
    if TrackingMode(item.tracking_mode) == TrackingMode.SERIAL and quantity != 1:
        raise ValidationFailedError(
            message="A serial-tracked move has quantity 1 (a serial moves wholesale)",
            code="inventory.serial_quantity_invalid",
            details={"quantity": str(quantity)},
        )

    move_date = payload.move_date or date.today()
    move_id = uuid.uuid4()
    document = await docflow.register_document(
        session,
        tenant_id,
        STOCK_MOVE_DOC_TYPE,
        move_id,
        doc_number=None,
        status=MoveStatus.POSTED.value,
    )
    # A move is permanent at creation (POSTED immediately), so the number is claimed now (D-012
    # claim-at-permanence, the orders/receipts branch, not the draft branch).
    await ensure_sequence(
        session,
        tenant_id,
        STOCK_MOVE_SEQUENCE_NAME,
        STOCK_MOVE_NUMBER_PREFIX,
        STOCK_MOVE_NUMBER_PADDING,
        year_reset=True,
    )
    move_number = await claim_number(
        session, tenant_id, STOCK_MOVE_SEQUENCE_NAME, on_date=move_date
    )

    move = StockMove(
        id=move_id,
        tenant_id=tenant_id,
        document_id=document.id,
        move_number=move_number,
        move_type=move_type.value,
        item_id=item.id,
        quantity=quantity,
        base_uom_id=item.base_uom_id,
        from_bin_id=payload.from_bin_id,
        to_bin_id=payload.to_bin_id,
        lot_id=lot_id,
        serial_id=serial_id,
        move_date=move_date,
        reference=payload.reference,
        posted=True,
        # The validated entry cost on an inbound move; the costing engine fills the computed cost on
        # an outbound/transfer move below (D-020).
        unit_cost=entry_cost,
    )
    session.add(move)
    await session.flush()

    await docflow.set_document_status(
        session, tenant_id, document.id, doc_number=move_number, status=MoveStatus.POSTED.value
    )
    await _apply_quant_deltas(
        session,
        tenant_id,
        item.id,
        lot_id,
        payload.from_bin_id,
        payload.to_bin_id,
        quantity,
    )
    # Costing IN THE SAME TRANSACTION (D-020), right after the quant update: update the
    # valuation/layers, write the computed cost onto the move, and publish StockValued BEFORE the
    # uow drains it — so move + quant + valuation + journal commit or roll back as one. A
    # value-neutral within-warehouse transfer returns no event (no journal).
    if reversal_of is not None:
        result = await costing_reversal.reverse_costing(
            session, tenant_id, item, move, reversal_of
        )
    else:
        result = await costing.apply_costing(
            session, tenant_id, item, move,
            valuation_offset_account_id=valuation_offset_account_id,
        )
    if result.event is not None:
        publish(session, result.event)
    return move


async def reverse_move(
    session: AsyncSession, tenant_id: uuid.UUID, move_id: uuid.UUID
) -> StockMove:
    """Reverse a posted move by posting an OPPOSITE move (PLAN 5.2): same item/quantity/lot/serial
    with from_bin and to_bin SWAPPED, linked to the original via docflow ('reverses'). The ledger
    stays append-only — corrections are new moves, never edits (D-017 philosophy). The reversing
    move restores the quants the original changed; a reversal that would itself go negative (the
    stock already left) raises InsufficientStockError like any other move. A move may be reversed
    once (a second reverse of the same original is rejected)."""
    original = await get_move(session, tenant_id, move_id)
    # Guard against double-reversal: a reversing move points back via docflow 'reverses'. Cheap
    # check — has any move already reversed this one?
    if await _already_reversed(session, tenant_id, original.document_id):
        raise ConflictError(
            message="This stock move has already been reversed",
            code="inventory.move_already_reversed",
        )

    reversal_payload = StockMoveCreate(
        move_type=MoveType(original.move_type),
        item_id=original.item_id,
        quantity=Decimal(original.quantity),
        # Swap the directions so the reversing move undoes the original's quant deltas.
        from_bin_id=original.to_bin_id,
        to_bin_id=original.from_bin_id,
        lot_id=original.lot_id,
        serial_id=original.serial_id,
        move_date=date.today(),
        reference=f"Reversal of {original.move_number}",
    )
    # A reversal of a RECEIPT swaps to an ISSUE-shaped move (from set, to NULL) and vice versa; for
    # ADJUSTMENT/TRANSFER the swap stays the same move_type. The bin-side validator accepts the
    # swapped shape because the move_type's required side follows the populated bin.
    reversal_payload = _retype_for_reversal(reversal_payload, MoveType(original.move_type))

    # Pass the original so create_move runs the costing REVERSAL (replay), not a fresh valuation,
    # and
    # publishes the OPPOSITE StockValued event so the COGS journal is reversed in the same
    # transaction (D-020).
    reversal = await create_move(
        session, tenant_id, reversal_payload, reversal_of=original
    )
    await docflow.link_documents(
        session,
        tenant_id,
        predecessor=original.document_id,
        successor=reversal.document_id,
        link_type=STOCK_MOVE_REVERSES_LINK,
    )
    return reversal


def _retype_for_reversal(payload: StockMoveCreate, original_type: MoveType) -> StockMoveCreate:
    """A RECEIPT reverses as an ISSUE and an ISSUE as a RECEIPT (the bin sides flip, so the type
    must too, or the bin-side validator rejects the swapped shape). TRANSFER and ADJUSTMENT keep
    their type — a swapped TRANSFER is still a TRANSFER, and a swapped ADJUSTMENT (the single side
    moves to the other side) is still an ADJUSTMENT."""
    if original_type == MoveType.RECEIPT:
        return payload.model_copy(update={"move_type": MoveType.ISSUE})
    if original_type == MoveType.ISSUE:
        return payload.model_copy(update={"move_type": MoveType.RECEIPT})
    return payload


async def _already_reversed(
    session: AsyncSession, tenant_id: uuid.UUID, document_id: uuid.UUID
) -> bool:
    """Whether a 'reverses' edge already points FROM this move's document (it has been reversed)."""
    chain = await docflow.get_document_chain(session, tenant_id, document_id)
    return any(
        edge.link_type == STOCK_MOVE_REVERSES_LINK
        and edge.predecessor_document_id == document_id
        for edge in chain.edges
    )
