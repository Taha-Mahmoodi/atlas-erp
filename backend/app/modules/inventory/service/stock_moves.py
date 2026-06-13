"""The stock-move WRITE engine (PLAN 5.2, D-020/D-036): create_move (the heart) + reverse_move.

The read paths (``get_move``, ``list_moves``, ``list_on_hand``) live in ``stock_reads.py`` (split at
the 400-line cap); this module imports ``get_move`` from there and the package ``__init__``
re-exports both halves as one surface.

A stock move is the quantity SINGLE SOURCE OF TRUTH and is POSTED-at-creation + IMMUTABLE — there
is no draft phase, no edit, no delete; a correction is a NEW reversing move (the universal-journal
reversal philosophy of D-017 applied to stock). ``create_move``:

1. validates — item is STOCKED; the move_type's required bin sides are present (constants
   MOVE_BIN_SIDES; ADJUSTMENT = exactly one side; TRANSFER = two DIFFERENT bins); bins exist and
   belong to ACTIVE warehouses; quantity > 0; the item's tracking mode is satisfied (lot/serial
   resolved, created on a receipt, required-existing on issue/transfer; serial ⇒ quantity == 1);
2. registers the document + claims the gapless STK number (D-012, at creation — a move is permanent
   at create);
3. inserts the StockMove (POSTED);
4. updates the quant rows in the SAME transaction — decrement from_bin, increment to_bin — through
   ``apply_bin_delta`` (the CHECK >= 0 + the pre-flight check forbid negative stock, D-020);
   transfer deltas are applied in deterministic bin-id order (deadlock avoidance, D-020).

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
) -> StockMove:
    """Create + POST a stock move (the heart, PLAN 5.2). Validates everything (see module
    docstring), claims the gapless STK number, inserts the POSTED move, and updates the quant
    projection in the SAME transaction. Raises 422 InsufficientStockError when an issue/transfer
    exceeds on-hand; NotFound for a missing item; 422 for a non-stocked item or a bin-side rule
    break. The caller commits via uow."""
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

    reversal = await create_move(session, tenant_id, reversal_payload)
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
