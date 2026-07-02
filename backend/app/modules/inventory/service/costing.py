"""The costing engine (PLAN 5.3, D-020/D-037): moving-average AND FIFO valuation per (item,
warehouse), computed in the SAME transaction as the stock move, right after the quant update and
BEFORE the move's costing event is published.

The move ledger + quants stay the QUANTITY SSOT; ``inv_item_valuations`` (moving-average) and
``inv_cost_layers`` + ``inv_layer_consumptions`` (FIFO) are the VALUE SSOT (D-037). Which engine a
(item, warehouse) uses is the item's ``costing_method``.

``apply_costing`` is the single entry point ``create_move`` calls. It:
1. resolves the move's direction + warehouse(s) from its bins,
2. runs the moving-average or FIFO update (receipt adds value, issue computes + removes it),
3. writes the computed cost back onto the move (``unit_cost``),
4. returns a ``CostingResult`` carrying the ``StockValued`` event (or None for a value-neutral
   within-warehouse transfer) for ``create_move`` to publish.

Reversal: ``reverse_costing`` undoes a move's valuation symmetrically — a reversed ISSUE replays its
FIFO consumptions backward / re-adds moving-average value; a reversed RECEIPT zeros its layer /
removes moving-average value. The reversing move publishes the OPPOSITE costing event so the COGS
journal is reversed too.

The moving-average row math lives in ``costing_mav.py`` and the FIFO layer mechanics in
``costing_fifo.py`` (split at the 400-line cap); this file owns the orchestration + reversal
sequencing + the StockValued event build.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationFailedError
from app.modules.finance import queries as finance_queries
from app.modules.inventory import queries as inventory_queries
from app.modules.inventory.constants import (
    DEFAULT_COSTING_CURRENCY,
    CostingMethod,
    MoveType,
)
from app.modules.inventory.events import StockValued
from app.modules.inventory.models import Bin, Item, StockMove
from app.modules.inventory.service import costing_fifo, costing_mav


@dataclass(frozen=True)
class CostingResult:
    """What ``apply_costing`` produced for one move: the computed unit cost (written onto the move)
    and the ``StockValued`` event to publish (None when the move moved no value — a within-warehouse
    transfer — so no journal is posted, D-037)."""

    unit_cost: Decimal | None
    event: StockValued | None


async def _warehouse_of_bin(
    session: AsyncSession, tenant_id: uuid.UUID, bin_id: uuid.UUID
) -> uuid.UUID:
    """The warehouse a bin belongs to (valuation is per warehouse, not per bin — D-037). The bin was
    already validated by the move engine, so a missing one here is an invariant break, not user
    input."""
    warehouse_id = (
        await session.execute(
            select(Bin.warehouse_id).where(
                Bin.tenant_id == tenant_id, Bin.id == bin_id
            )
        )
    ).scalar_one_or_none()
    if warehouse_id is None:
        raise ValidationFailedError(
            message="The bin has no warehouse for valuation",
            code="inventory.costing_bin_warehouse_missing",
            details={"bin_id": str(bin_id)},
        )
    return warehouse_id


async def _costing_currency(session: AsyncSession, tenant_id: uuid.UUID) -> str:
    """The currency the COGS/inventory journal posts in (D-015): the tenant's functional currency
    when configured, else the v1 single-currency default. Costs quantize to its decimals."""
    func_code = await finance_queries.functional_currency_or_none(session, tenant_id)
    return func_code or DEFAULT_COSTING_CURRENCY


async def _category_accounts(
    session: AsyncSession, tenant_id: uuid.UUID, item_id: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """The item category's three GL account ids (inventory, COGS, price-difference), REQUIRED before
    a stocked move can value (D-020/D-029). A STOCKED item whose category has not wired them cannot
    post a move — the value would have nowhere to land — so this raises a clear 422."""
    accounts = await inventory_queries.get_category_accounts(session, tenant_id, item_id)
    if accounts is None or any(account_id is None for account_id in accounts):
        raise ValidationFailedError(
            message="The item's category must wire inventory, COGS and price-difference accounts "
            "before stock can be valued",
            code="inventory.category_accounts_unwired",
            details={"item_id": str(item_id)},
        )
    return accounts  # type: ignore[return-value]


# --- Orchestration ------------------------------------------------------------


async def apply_costing(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    item: Item,
    move: StockMove,
    *,
    valuation_offset_account_id: uuid.UUID | None = None,
) -> CostingResult:
    """Run costing for a just-created move IN THE SAME TRANSACTION (D-020), after the quant update.

    Resolves direction + warehouse(s), runs the moving-average or FIFO engine, writes the computed
    ``unit_cost`` back onto the move, and returns the ``StockValued`` event for ``create_move`` to
    publish (None for a value-neutral within-warehouse transfer). RECEIPT/positive-ADJUSTMENT use
    the
    move's passed ``unit_cost`` (the entry cost); ISSUE/negative-ADJUSTMENT IGNORE it and
    compute.

    ``valuation_offset_account_id`` (PLAN 6.3, D-041) OVERRIDES the standard offset on BOTH the
    inbound (RECEIPT, normally price-difference → GR/IR for a goods receipt) and the outbound
    (ISSUE, normally COGS → WIP for a component issue, PLAN 8.2 D-048) side. The ADJUSTMENT-down /
    transfer paths ignore it."""
    move_type = MoveType(move.move_type)
    qty = Decimal(move.quantity)
    method = CostingMethod(item.costing_method)
    currency_code = await _costing_currency(session, tenant_id)
    accounts = await _category_accounts(session, tenant_id, item.id)

    from_warehouse_id = (
        await _warehouse_of_bin(session, tenant_id, move.from_bin_id)
        if move.from_bin_id is not None
        else None
    )
    to_warehouse_id = (
        await _warehouse_of_bin(session, tenant_id, move.to_bin_id)
        if move.to_bin_id is not None
        else None
    )

    if move_type == MoveType.TRANSFER:
        return await _apply_transfer(
            session, tenant_id, item, move, qty, method, currency_code,
            from_warehouse_id, to_warehouse_id,
        )

    # Direction is structural: a populated to_bin warehouse is inbound (RECEIPT / increase), a
    # populated from_bin warehouse is outbound (ISSUE / decrease). ADJUSTMENT sets exactly one side.
    if to_warehouse_id is not None:
        return await _apply_inbound(
            session, tenant_id, item, move, qty, method, to_warehouse_id, accounts,
            valuation_offset_account_id=valuation_offset_account_id,
        )
    if from_warehouse_id is not None:
        return await _apply_outbound(
            session, tenant_id, item, move, qty, method, currency_code,
            from_warehouse_id, accounts,
            valuation_offset_account_id=valuation_offset_account_id,
        )
    raise ValidationFailedError(
        message="The move has no warehouse side to value",
        code="inventory.costing_no_side",
        details={"move_id": str(move.id)},
    )


async def _apply_inbound(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    item: Item,
    move: StockMove,
    qty: Decimal,
    method: CostingMethod,
    warehouse_id: uuid.UUID,
    accounts: tuple[uuid.UUID, uuid.UUID, uuid.UUID],
    *,
    valuation_offset_account_id: uuid.UUID | None = None,
) -> CostingResult:
    """RECEIPT / positive ADJUSTMENT: stock enters at the move's REQUIRED ``unit_cost`` (the entry
    cost). Updates the moving-average row or creates a FIFO layer, and emits a value-increasing
    StockValued event the handler posts as Dr inventory."""
    unit_cost = _require_entry_cost(move)
    total_cost = qty * unit_cost
    if method == CostingMethod.MOVING_AVERAGE:
        await costing_mav.mav_receive(session, tenant_id, item.id, warehouse_id, qty, unit_cost)
    else:
        await costing_fifo.create_layer(
            session,
            tenant_id,
            item_id=item.id,
            warehouse_id=warehouse_id,
            receipt_move_id=move.id,
            received_at=move.move_date,
            qty=qty,
            unit_cost=unit_cost,
        )
    move.unit_cost = unit_cost
    inventory_account_id, _cogs_account_id, price_diff_account_id = accounts
    # A receipt / stock-increase offsets to the price-difference (inventory-adjustment) account by
    # default — a STANDALONE receipt (opening balance, manual stock-in) has no procurement GR/IR
    # clearing. The procurement goods-receipt path (6.3, D-041) OVERRIDES the offset to its GR/IR
    # clearing account via ``valuation_offset_account_id`` so the handler credits GR/IR.
    offset_account_id = valuation_offset_account_id or price_diff_account_id
    event = _build_event(
        move, warehouse_id, qty, total_cost, Decimal(0),
        inventory_account_id, offset_account_id, price_diff_account_id,
        is_inbound=True,
    )
    return CostingResult(unit_cost=unit_cost, event=event)


async def _apply_outbound(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    item: Item,
    move: StockMove,
    qty: Decimal,
    method: CostingMethod,
    currency_code: str,
    warehouse_id: uuid.UUID,
    accounts: tuple[uuid.UUID, uuid.UUID, uuid.UUID],
    *,
    valuation_offset_account_id: uuid.UUID | None = None,
) -> CostingResult:
    """ISSUE / negative ADJUSTMENT: the engine COMPUTES the cost of the stock that left (the passed
    unit_cost is ignored). MAV quantizes qty × avg + flushes residual at zero on-hand; FIFO sums
    per-layer costs. Emits a value-decreasing StockValued event posting Dr COGS / Cr inventory — or,
    when ``valuation_offset_account_id`` overrides COGS (a component issue to WIP, PLAN 8.2), Dr WIP
    / Cr inventory."""
    residual_flush = Decimal(0)
    if method == CostingMethod.MOVING_AVERAGE:
        cogs, residual_flush = await costing_mav.mav_issue(
            session, tenant_id, item.id, warehouse_id, qty, currency_code
        )
    else:
        cogs = await costing_fifo.consume_layers(
            session,
            tenant_id,
            item_id=item.id,
            warehouse_id=warehouse_id,
            issue_move_id=move.id,
            qty=qty,
            currency_code=currency_code,
        )
    unit_cost = (cogs / qty) if qty > 0 else Decimal(0)
    move.unit_cost = unit_cost
    inventory_account_id, cogs_account_id, price_diff_account_id = accounts
    # An ISSUE charges COGS; an ADJUSTMENT-down is a write-off, so it offsets to price-difference
    # (D-020). The ``valuation_offset_account_id`` OVERRIDE (PLAN 8.2, D-048) routes a manufacturing
    # component ISSUE to the WIP clearing account instead of COGS (Dr WIP / Cr Inventory) — applied
    # only on an ISSUE, mirroring how the inbound override applies only on a RECEIPT.
    if MoveType(move.move_type) == MoveType.ISSUE:
        offset_account_id = valuation_offset_account_id or cogs_account_id
    else:
        offset_account_id = price_diff_account_id
    event = _build_event(
        move, warehouse_id, qty, cogs, residual_flush,
        inventory_account_id, offset_account_id, price_diff_account_id,
        is_inbound=False,
    )
    return CostingResult(unit_cost=unit_cost, event=event)


async def _apply_transfer(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    item: Item,
    move: StockMove,
    qty: Decimal,
    method: CostingMethod,
    currency_code: str,
    from_warehouse_id: uuid.UUID | None,
    to_warehouse_id: uuid.UUID | None,
) -> CostingResult:
    """TRANSFER carries cost at the current valuation. Within ONE warehouse it is fully
    value-neutral — the valuation/layers don't change and NO journal is posted (D-037). Between
    warehouses the value moves WITH the stock (issue from source at current cost, receive into dest
    at that same cost) but, because both warehouses share the one inventory account in v1, the net
    journal is still zero — so a transfer never publishes a StockValued event. The computed transfer
    unit cost is still written onto the move for the ledger."""
    if from_warehouse_id is None or to_warehouse_id is None:
        raise ValidationFailedError(
            message="A transfer needs both warehouses to value",
            code="inventory.costing_transfer_sides",
            details={"move_id": str(move.id)},
        )
    if from_warehouse_id == to_warehouse_id:
        # Same warehouse: only the bin changed; value is unchanged. Carry the current cost onto the
        # move for the ledger, touch nothing else, post no journal.
        move.unit_cost = await _current_unit_cost(
            session, tenant_id, item, from_warehouse_id, method
        )
        return CostingResult(unit_cost=move.unit_cost, event=None)

    # Cross-warehouse: remove value from the source and add it to the destination at the SAME cost,
    # so the value follows the stock between warehouses while the net GL effect is nil.
    if method == CostingMethod.MOVING_AVERAGE:
        cost, residual = await costing_mav.mav_issue(
            session, tenant_id, item.id, from_warehouse_id, qty, currency_code
        )
        unit_cost = (cost / qty) if qty > 0 else Decimal(0)
        # #84: when the issue empties the source, mav_issue flushes the rounding residual out of
        # the source valuation. A transfer posts no journal to absorb it, so fold it into the
        # destination receipt — total value is conserved and the subledger stays on the GL.
        await costing_mav.mav_receive(
            session, tenant_id, item.id, to_warehouse_id, qty, unit_cost, extra_value=residual
        )
    else:
        cost = await costing_fifo.consume_layers(
            session,
            tenant_id,
            item_id=item.id,
            warehouse_id=from_warehouse_id,
            issue_move_id=move.id,
            qty=qty,
            currency_code=currency_code,
        )
        unit_cost = (cost / qty) if qty > 0 else Decimal(0)
        await costing_fifo.create_layer(
            session,
            tenant_id,
            item_id=item.id,
            warehouse_id=to_warehouse_id,
            receipt_move_id=move.id,
            received_at=move.move_date,
            qty=qty,
            unit_cost=unit_cost,
        )
    move.unit_cost = unit_cost
    return CostingResult(unit_cost=unit_cost, event=None)


async def _current_unit_cost(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    item: Item,
    warehouse_id: uuid.UUID,
    method: CostingMethod,
) -> Decimal:
    """The current per-unit cost of an (item, warehouse) for a value-neutral transfer's ledger
    entry:
    the moving-average avg, or the FIFO weighted average of the live layers. Reads only (no
    writes)."""
    if method == CostingMethod.MOVING_AVERAGE:
        return await costing_mav.mav_avg_cost(session, tenant_id, item.id, warehouse_id)
    return await costing_mav.fifo_weighted_cost(session, tenant_id, item.id, warehouse_id)


def _require_entry_cost(move: StockMove) -> Decimal:
    """A RECEIPT / positive ADJUSTMENT REQUIRES the entry unit_cost (D-020) — without it the value
    entering inventory is undefined. Validated at the service edge (create_move) too; this is the
    last guard before the value lands."""
    if move.unit_cost is None:
        raise ValidationFailedError(
            message="A receipt requires a unit cost (the value at which stock enters)",
            code="inventory.receipt_unit_cost_required",
            details={"move_id": str(move.id)},
        )
    return Decimal(move.unit_cost)


def _build_event(
    move: StockMove,
    warehouse_id: uuid.UUID,
    qty: Decimal,
    total_cost: Decimal,
    residual_flush: Decimal,
    inventory_account_id: uuid.UUID,
    offset_account_id: uuid.UUID,
    price_diff_account_id: uuid.UUID,
    *,
    is_inbound: bool,
) -> StockValued:
    return StockValued(
        tenant_id=move.tenant_id,
        move_id=move.id,
        move_number=move.move_number,
        move_type=move.move_type,
        is_inbound=is_inbound,
        item_id=move.item_id,
        warehouse_id=warehouse_id,
        quantity=qty,
        total_cost=total_cost,
        residual_to_price_difference=residual_flush,
        move_date=move.move_date.isoformat(),
        document_id=move.document_id,
        inventory_account_id=inventory_account_id,
        offset_account_id=offset_account_id,
        price_difference_account_id=price_diff_account_id,
    )


# Reversal sequencing lives in costing_reversal.py (kept here under 400 lines); re-exported so call
# sites keep one ``from ...service.costing import reverse_costing``. Imported at the END to avoid a
# cycle: costing_reversal imports the shared helpers + apply_costing from THIS module.
from app.modules.inventory.service.costing_reversal import reverse_costing  # noqa: E402

__all__ = ["CostingResult", "apply_costing", "reverse_costing"]
