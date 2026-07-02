"""Costing reversal sequencing (PLAN 5.3, D-020), split from ``costing.py`` to keep it <400 lines.

``reverse_costing`` undoes a move's valuation symmetrically for its reversing move, in the SAME
transaction: a reversed ISSUE replays its FIFO LayerConsumptions backward onto the exact layers
(restoring remaining_qty) / re-adds the moving-average value at the ORIGINAL cost; a reversed
RECEIPT
zeros its FIFO layer (only valid if unconsumed) / removes the moving-average value. The reversing
move records the SAME cost it undoes and emits the OPPOSITE StockValued event so the COGS/inventory
journal is reversed too (the Dr/Cr flip falls out of the reversing move_type's handler branch).

Imports the shared helpers + ``apply_costing`` from ``costing.py`` (one-directional: reversal ->
costing); ``costing.py`` re-exports ``reverse_costing`` so call sites use one import surface.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationFailedError
from app.modules.inventory.constants import CostingMethod, MoveType
from app.modules.inventory.models import Item, StockMove
from app.modules.inventory.service import costing as _costing
from app.modules.inventory.service import costing_fifo, costing_mav


async def reverse_costing(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    item: Item,
    reversal_move: StockMove,
    original_move: StockMove,
) -> _costing.CostingResult:
    """Undo ``original_move``'s valuation for its just-created ``reversal_move`` (D-020).

    ``reversal_move`` is the opposite move (RECEIPT reverses as ISSUE-shaped and vice versa).
    Returns
    a CostingResult whose event is the OPPOSITE-direction StockValued the handler posts as the
    reversing journal."""
    method = CostingMethod(item.costing_method)
    qty = Decimal(reversal_move.quantity)
    currency_code = await _costing._costing_currency(session, tenant_id)
    inventory_account_id, cogs_account_id, price_diff_account_id = (
        await _costing._category_accounts(session, tenant_id, item.id)
    )
    original_type = MoveType(original_move.move_type)
    warehouse_id = await _reversal_warehouse(session, tenant_id, reversal_move)

    if original_type == MoveType.RECEIPT:
        # Reversing a receipt removes the value it added — the EXACT reverse of the receipt's
        # Dr inventory / Cr price-difference, i.e. Dr price-difference / Cr inventory (offset =
        # price-difference, outbound).
        if method == CostingMethod.MOVING_AVERAGE:
            unit_cost = _original_unit_cost(original_move)
            await costing_mav.mav_issue(
                session, tenant_id, item.id, warehouse_id, qty, currency_code
            )
            total_cost = qty * unit_cost
        else:
            total_cost = await costing_fifo.reverse_receipt_layer(
                session, tenant_id, original_receipt_move_id=original_move.id
            )
            unit_cost = (total_cost / qty) if qty > 0 else Decimal(0)
        reversal_move.unit_cost = unit_cost
        event = _costing._build_event(
            reversal_move, warehouse_id, qty, total_cost, Decimal(0),
            inventory_account_id, price_diff_account_id, price_diff_account_id,
            is_inbound=False,
        )
        return _costing.CostingResult(unit_cost=unit_cost, event=event)

    if original_type == MoveType.ISSUE:
        # Reversing an issue restores the value (and exact FIFO layers) it removed — the EXACT
        # reverse of the issue's Dr COGS / Cr inventory, i.e. Dr inventory / Cr COGS (offset = COGS,
        # inbound).
        if method == CostingMethod.MOVING_AVERAGE:
            unit_cost = _original_unit_cost(original_move)
            await costing_mav.mav_receive(
                session, tenant_id, item.id, warehouse_id, qty, unit_cost
            )
            total_cost = qty * unit_cost
        else:
            total_cost = await costing_fifo.reverse_issue_consumptions(
                session,
                tenant_id,
                original_issue_move_id=original_move.id,
                currency_code=currency_code,
            )
            unit_cost = (total_cost / qty) if qty > 0 else Decimal(0)
        reversal_move.unit_cost = unit_cost
        event = _costing._build_event(
            reversal_move, warehouse_id, qty, total_cost, Decimal(0),
            inventory_account_id, cogs_account_id, price_diff_account_id,
            is_inbound=True,
        )
        return _costing.CostingResult(unit_cost=unit_cost, event=event)

    # TRANSFER / ADJUSTMENT reversal: the reversing move is the same shape (TRANSFER) or an
    # opposite-side ADJUSTMENT, so the ordinary apply_costing path values it correctly (a reversed
    # within-warehouse transfer is value-neutral; a reversed adjustment swaps the side).
    return await _costing.apply_costing(session, tenant_id, item, reversal_move)


async def _reversal_warehouse(
    session: AsyncSession, tenant_id: uuid.UUID, reversal_move: StockMove
) -> uuid.UUID:
    """The warehouse the reversing move's value applies to: its populated bin side."""
    bin_id = reversal_move.to_bin_id or reversal_move.from_bin_id
    if bin_id is None:
        raise ValidationFailedError(
            message="The reversing move has no warehouse side to value",
            code="inventory.costing_no_side",
            details={"move_id": str(reversal_move.id)},
        )
    return await _costing._warehouse_of_bin(session, tenant_id, bin_id)


def _original_unit_cost(original_move: StockMove) -> Decimal:
    """The cost the ORIGINAL move recorded (D-020): moving-average reversal re-applies that exact
    cost so the valuation returns to its prior state, never a re-derived current average."""
    return (
        Decimal(original_move.unit_cost)
        if original_move.unit_cost is not None
        else Decimal(0)
    )


__all__ = ["reverse_costing"]
