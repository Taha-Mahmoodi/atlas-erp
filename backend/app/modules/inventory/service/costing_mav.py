"""Moving-average costing mechanics (PLAN 5.3, D-020): the ``inv_item_valuations`` row math, split
from ``costing.py`` to keep both <400 lines (the FIFO half is ``costing_fifo.py``).

This file owns ONLY the moving-average state updates + the current-cost reads; the orchestration and
reversal sequencing live in ``costing.py``. Every function runs in the move's transaction and locks
the (item, warehouse) row ``with_for_update`` (PG row lock serializing concurrent movers; SQLite
no-op + single-writer lock, D-020).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationFailedError
from app.core.money import quantize_for_currency
from app.modules.inventory.models import CostLayer, ItemValuation


async def locked_valuation(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    item_id: uuid.UUID,
    warehouse_id: uuid.UUID,
) -> ItemValuation | None:
    """Load the (item, warehouse) moving-average row FOR UPDATE (PG lock serializing movers; SQLite
    no-op, D-020), or None if it does not exist yet."""
    stmt = (
        select(ItemValuation)
        .where(
            ItemValuation.tenant_id == tenant_id,
            ItemValuation.item_id == item_id,
            ItemValuation.warehouse_id == warehouse_id,
        )
        .with_for_update()
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def mav_receive(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    item_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    qty: Decimal,
    unit_cost: Decimal,
) -> None:
    """Moving-average RECEIPT (D-020): total_value += qty × unit_cost; on_hand += qty; avg =
    total_value / on_hand UNROUNDED (full precision, so issues don't drift)."""
    valuation = await locked_valuation(session, tenant_id, item_id, warehouse_id)
    receipt_value = qty * unit_cost
    if valuation is None:
        session.add(
            ItemValuation(
                tenant_id=tenant_id,
                item_id=item_id,
                warehouse_id=warehouse_id,
                on_hand_qty=qty,
                avg_unit_cost=unit_cost,
                total_value=receipt_value,
            )
        )
        await session.flush()
        return
    new_qty = Decimal(valuation.on_hand_qty) + qty
    new_value = Decimal(valuation.total_value) + receipt_value
    valuation.on_hand_qty = new_qty
    valuation.total_value = new_value
    valuation.avg_unit_cost = new_value / new_qty if new_qty > 0 else Decimal(0)
    await session.flush()


async def mav_issue(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    item_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    qty: Decimal,
    currency_code: str,
) -> tuple[Decimal, Decimal]:
    """Moving-average ISSUE (D-020): cogs = quantize(qty × avg, currency dp, HALF_UP); total_value
    -=
    cogs; on_hand -= qty. When on_hand hits exactly 0 the residual total_value is FLUSHED — returned
    as the signed price-difference amount so value and quantity never disagree. Returns (cogs,
    residual_flush)."""
    valuation = await locked_valuation(session, tenant_id, item_id, warehouse_id)
    if valuation is None:
        # The 5.2 quant pre-flight guarantees stock exists, so a missing valuation is a
        # costing/quant divergence — never reachable on the happy path.
        raise ValidationFailedError(
            message="No moving-average valuation exists for the issued stock",
            code="inventory.costing_valuation_missing",
            details={"item_id": str(item_id), "warehouse_id": str(warehouse_id)},
        )
    cogs = quantize_for_currency(qty * Decimal(valuation.avg_unit_cost), currency_code)
    new_qty = Decimal(valuation.on_hand_qty) - qty
    residual_flush = Decimal(0)
    if new_qty <= 0:
        # On-hand hit (exactly) zero: flush whatever total_value remains after removing this COGS so
        # the row lands at value 0 with quantity 0 (D-020 — rounding drift absorbed here). A
        # positive
        # residual means leftover value (Dr price-difference); negative means over-issued value.
        residual_flush = Decimal(valuation.total_value) - cogs
        valuation.on_hand_qty = Decimal(0)
        valuation.total_value = Decimal(0)
        # avg_unit_cost is left as-is (meaningless at zero stock; the next receipt resets it).
    else:
        valuation.on_hand_qty = new_qty
        valuation.total_value = Decimal(valuation.total_value) - cogs
    await session.flush()
    return cogs, residual_flush


async def mav_avg_cost(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    item_id: uuid.UUID,
    warehouse_id: uuid.UUID,
) -> Decimal:
    """The current moving-average unit cost of an (item, warehouse), or 0 if none — used for a
    value-neutral within-warehouse transfer's ledger row (no write)."""
    valuation = await locked_valuation(session, tenant_id, item_id, warehouse_id)
    return Decimal(valuation.avg_unit_cost) if valuation is not None else Decimal(0)


async def fifo_weighted_cost(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    item_id: uuid.UUID,
    warehouse_id: uuid.UUID,
) -> Decimal:
    """The weighted-average cost of an (item, warehouse)'s LIVE FIFO layers (Σ value / Σ qty), or 0
    if none — used for a value-neutral within-warehouse transfer's ledger row (no write). The qty ×
    cost product is summed in PYTHON (each factor already a typed Decimal), never ``func.sum(qty ×
    cost)`` — multiplying two scaled-integer columns on SQLite yields a ×10^12 value the MoneyType
    result processor cannot un-scale (D-015 trigger discipline)."""
    rows = (
        await session.execute(
            select(CostLayer.remaining_qty, CostLayer.unit_cost).where(
                CostLayer.tenant_id == tenant_id,
                CostLayer.item_id == item_id,
                CostLayer.warehouse_id == warehouse_id,
                CostLayer.remaining_qty > 0,
            )
        )
    ).all()
    total_qty = sum((Decimal(qty) for qty, _cost in rows), Decimal(0))
    total_value = sum((Decimal(qty) * Decimal(cost) for qty, cost in rows), Decimal(0))
    return (total_value / total_qty) if total_qty > 0 else Decimal(0)


__all__ = [
    "fifo_weighted_cost",
    "locked_valuation",
    "mav_avg_cost",
    "mav_issue",
    "mav_receive",
]
