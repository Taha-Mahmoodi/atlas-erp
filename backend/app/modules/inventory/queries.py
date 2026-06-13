"""Inventory's cross-module read interface (STRUCTURE §5).

Inventory sits just above finance in the dependency order: every module above it (procurement,
sales, manufacturing) may import THIS file to read inventory state synchronously, and inventory
imports only finance/queries downward. Keep this surface thin and stable — it is a contract; it is
the ONLY inventory file other modules import.

For PLAN 5.1 it exposes the item-master reads those modules will need: existence checks, the
item's base UoM and costing method, and the category's GL-account wiring (so the COGS handler can
resolve where to post when stock issues land in 5.2+). PLAN 5.2 adds the ON-HAND projection reads
(``total_on_hand``, ``on_hand_by_bin``, ``on_hand_by_lot``) — what sales ATP and procurement will
call: they read the MAINTAINED ``inv_stock_quants`` projection (D-036), an indexed aggregate, never
an unbounded SUM over the move history (PERFORMANCE §1).

Every function takes an explicit ``tenant_id`` and runs under the caller's tenant context, so the
D-007 filter applies on top of the explicit predicate — ordinary tenant-scoped reads, not a bypass.
"""

import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.inventory.constants import CostingMethod
from app.modules.inventory.models import (
    Bin,
    CostLayer,
    Item,
    ItemCategory,
    ItemValuation,
    Lot,
    SerialNumber,
    StockQuant,
    Uom,
)


async def get_item(
    session: AsyncSession, tenant_id: uuid.UUID, item_id: uuid.UUID
) -> Item | None:
    """The item with ``item_id`` in the tenant, or None. Lets another module read an item's master
    fields (name, type, base UoM, costing method) without importing inventory models directly."""
    stmt = select(Item).where(Item.tenant_id == tenant_id, Item.id == item_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def item_exists(
    session: AsyncSession, tenant_id: uuid.UUID, item_id: uuid.UUID
) -> bool:
    """Whether an item with ``item_id`` exists in the tenant. The cheap existence check a sales or
    procurement line uses to validate its item_id dimension (the inventory analogue of finance's
    ``account_exists_by_id``)."""
    stmt = select(Item.id).where(Item.tenant_id == tenant_id, Item.id == item_id)
    return (await session.execute(stmt)).first() is not None


async def uom_exists(
    session: AsyncSession, tenant_id: uuid.UUID, uom_id: uuid.UUID
) -> bool:
    """Whether a unit of measure with ``uom_id`` exists in the tenant. The UoM analogue of
    ``item_exists``: a manufacturing BOM header/component references the parent/component UoM by
    opaque id (D-029) and validates it through this contract before writing — UoMs and items are
    distinct inventory entities, so this cannot be folded into ``item_exists``."""
    stmt = select(Uom.id).where(Uom.tenant_id == tenant_id, Uom.id == uom_id)
    return (await session.execute(stmt)).first() is not None


async def get_costing_method(
    session: AsyncSession, tenant_id: uuid.UUID, item_id: uuid.UUID
) -> CostingMethod | None:
    """The item's costing method (D-020), or None if the item does not exist. The costing engine
    (5.3) reads this to choose moving-average vs FIFO; exposed so other modules can too."""
    stmt = select(Item.costing_method).where(
        Item.tenant_id == tenant_id, Item.id == item_id
    )
    value = (await session.execute(stmt)).scalar_one_or_none()
    return CostingMethod(value) if value is not None else None


async def get_base_uom(
    session: AsyncSession, tenant_id: uuid.UUID, item_id: uuid.UUID
) -> uuid.UUID | None:
    """The item's base UoM id (the unit it is stored/costed in), or None if the item does not
    exist. A document line in another UoM converts to this base via ``service.convert_quantity``."""
    stmt = select(Item.base_uom_id).where(
        Item.tenant_id == tenant_id, Item.id == item_id
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_category_accounts(
    session: AsyncSession, tenant_id: uuid.UUID, item_id: uuid.UUID
) -> tuple[uuid.UUID | None, uuid.UUID | None, uuid.UUID | None] | None:
    """The GL-account wiring (inventory, COGS, price-difference) of an item's category (D-020),
    or None if the item does not exist. The COGS handler (5.2+) resolves where to post a goods
    issue from this tuple. Any element may be None when the category has not wired that account
    yet — the issuing flow validates presence before it posts. One join, item -> category."""
    stmt = (
        select(
            ItemCategory.inventory_account_id,
            ItemCategory.cogs_account_id,
            ItemCategory.price_difference_account_id,
        )
        .join(Item, Item.category_id == ItemCategory.id)
        .where(Item.tenant_id == tenant_id, Item.id == item_id)
    )
    row = (await session.execute(stmt)).first()
    return (row[0], row[1], row[2]) if row is not None else None


async def bin_exists(
    session: AsyncSession, tenant_id: uuid.UUID, bin_id: uuid.UUID
) -> bool:
    """Whether a bin with ``bin_id`` exists in the tenant (PLAN 6.3). A goods receipt validates the
    target bin its stock lands in through this contract (D-029) rather than importing inventory
    models. Existence only — the move engine re-checks the bin is in an ACTIVE warehouse when it
    posts, so a receipt against an inactive-warehouse bin still fails (at post), loud."""
    stmt = select(Bin.id).where(Bin.tenant_id == tenant_id, Bin.id == bin_id)
    return (await session.execute(stmt)).first() is not None


async def lot_id_for_code(
    session: AsyncSession, tenant_id: uuid.UUID, item_id: uuid.UUID, lot_code: str
) -> uuid.UUID | None:
    """The id of an EXISTING lot for an item, by its lot_code (PLAN 7.3), or None. A sales delivery
    (an outbound ISSUE) must reference an existing lot by id — unlike a receipt, an issue never
    creates a lot — so the delivery resolves the human ``lot_code`` to a lot id through this
    contract (D-029) before issuing. Index-served by (tenant, item_id)."""
    stmt = select(Lot.id).where(
        Lot.tenant_id == tenant_id, Lot.item_id == item_id, Lot.lot_code == lot_code
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def serial_id_for_code(
    session: AsyncSession, tenant_id: uuid.UUID, item_id: uuid.UUID, serial_code: str
) -> uuid.UUID | None:
    """The id of an EXISTING serial for an item, by its serial_code (PLAN 7.3), or None. The serial
    twin of ``lot_id_for_code``: a delivery resolves a serial-tracked line's ``serial_code`` to a
    serial id before issuing (D-029). Index-served by (tenant, item_id)."""
    stmt = select(SerialNumber.id).where(
        SerialNumber.tenant_id == tenant_id,
        SerialNumber.item_id == item_id,
        SerialNumber.serial_code == serial_code,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


# --- On-hand projection reads (PLAN 5.2) --------------------------------------
# These read the MAINTAINED inv_stock_quants projection (D-036), kept in lock-step with the move
# ledger so on-hand is an indexed aggregate over a small current-state table, not a SUM over
# unbounded move history (PERFORMANCE §1). MoneyType/QuantityType propagation keeps the SUM exact on
# both engines (D-015); ``func.coalesce(..., 0)`` makes an item with no stock read 0, not None.


async def total_on_hand(
    session: AsyncSession, tenant_id: uuid.UUID, item_id: uuid.UUID
) -> Decimal:
    """Total on-hand quantity of an item across ALL bins and lots (PLAN 5.2). The number sales ATP
    starts from. Reads inv_stock_quants (the maintained projection), index-served by
    ``(tenant_id, item_id)``."""
    stmt = select(func.coalesce(func.sum(StockQuant.on_hand_qty), 0)).where(
        StockQuant.tenant_id == tenant_id, StockQuant.item_id == item_id
    )
    return (await session.execute(stmt)).scalar_one()


async def on_hand(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    item_id: uuid.UUID,
    bin_id: uuid.UUID | None = None,
    lot_id: uuid.UUID | None = None,
) -> Decimal:
    """On-hand quantity of an item, optionally narrowed to one bin and/or one lot (PLAN 5.2). With
    no bin/lot this is ``total_on_hand``; with a bin it is that bin's stock; with a lot it is that
    lot's stock (in the bin if also given). Reads the maintained projection."""
    stmt = select(func.coalesce(func.sum(StockQuant.on_hand_qty), 0)).where(
        StockQuant.tenant_id == tenant_id, StockQuant.item_id == item_id
    )
    if bin_id is not None:
        stmt = stmt.where(StockQuant.bin_id == bin_id)
    if lot_id is not None:
        stmt = stmt.where(StockQuant.lot_id == lot_id)
    return (await session.execute(stmt)).scalar_one()


async def items_below_reorder_point(
    session: AsyncSession, tenant_id: uuid.UUID
) -> list[tuple[uuid.UUID, Decimal, Decimal, Decimal]]:
    """Items whose total on-hand is AT OR BELOW their reorder point (PLAN 6.4, D-042) — the
    consumption-based replenishment scan. Returns ``(item_id, on_hand, reorder_point,
    reorder_quantity)`` for each ACTIVE item that carries a positive reorder point, has a positive
    reorder quantity, and whose on-hand (the maintained ``inv_stock_quants`` projection, summed per
    item) has fallen to or under that point. Procurement's reorder scan turns each into a draft
    requisition line for ``reorder_quantity``.

    SET-BASED (no per-item N+1, PERFORMANCE §2): the on-hand sum is a LEFT JOIN + GROUP BY over the
    quant projection (items with no stock read 0 via coalesce), and the reorder predicate filters in
    SQL. Inventory OWNS reorder_point/reorder_quantity (5.1); the DRAFT requisition is a procurement
    document (6.2) — this query is the contract procurement reads, never importing inventory
    models."""
    on_hand_sum = func.coalesce(func.sum(StockQuant.on_hand_qty), 0)
    stmt = (
        select(
            Item.id,
            on_hand_sum.label("on_hand"),
            Item.reorder_point,
            Item.reorder_quantity,
        )
        .join(
            StockQuant,
            (StockQuant.tenant_id == Item.tenant_id) & (StockQuant.item_id == Item.id),
            isouter=True,
        )
        .where(
            Item.tenant_id == tenant_id,
            Item.is_active.is_(True),
            Item.reorder_point.is_not(None),
            Item.reorder_point > 0,
            Item.reorder_quantity.is_not(None),
            Item.reorder_quantity > 0,
        )
        .group_by(Item.id, Item.reorder_point, Item.reorder_quantity)
        .having(on_hand_sum <= Item.reorder_point)
        .order_by(Item.item_code)
    )
    rows = (await session.execute(stmt)).all()
    return [
        (row[0], Decimal(row[1]), Decimal(row[2]), Decimal(row[3]))
        for row in rows
    ]


async def on_hand_by_bin(
    session: AsyncSession, tenant_id: uuid.UUID, item_id: uuid.UUID
) -> dict[uuid.UUID, Decimal]:
    """Per-bin on-hand totals for an item (PLAN 5.2): ``{bin_id: qty}`` summed across that bin's
    lots. Bins with zero net stock are absent (the move service deletes a quant when it hits 0, so
    the projection holds only live stock). What a bin-level stock-overview screen reads."""
    stmt = (
        select(StockQuant.bin_id, func.sum(StockQuant.on_hand_qty))
        .where(StockQuant.tenant_id == tenant_id, StockQuant.item_id == item_id)
        .group_by(StockQuant.bin_id)
    )
    rows = (await session.execute(stmt)).all()
    return {row[0]: row[1] for row in rows}


async def on_hand_by_lot(
    session: AsyncSession, tenant_id: uuid.UUID, item_id: uuid.UUID
) -> dict[uuid.UUID, Decimal]:
    """Per-lot on-hand totals for a LOT-tracked item (PLAN 5.2): ``{lot_id: qty}`` summed across
    bins. Quants with a NULL lot (fungible stock) are excluded — this view is for tracked items
    where lot traceability matters."""
    stmt = (
        select(StockQuant.lot_id, func.sum(StockQuant.on_hand_qty))
        .where(
            StockQuant.tenant_id == tenant_id,
            StockQuant.item_id == item_id,
            StockQuant.lot_id.is_not(None),
        )
        .group_by(StockQuant.lot_id)
    )
    rows = (await session.execute(stmt)).all()
    return {row[0]: row[1] for row in rows}


# --- Valuation reads (PLAN 5.3, D-020/D-037) ----------------------------------
# These read the VALUE SSOT (inv_item_valuations for moving-average, inv_cost_layers for FIFO), kept
# in lock-step with every move in the same transaction (D-037). The inventory-value dashboard KPI
# and
# valuation reports read these. MoneyType/QuantityType propagation keeps the SUMs exact (D-015).


async def item_value(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    item_id: uuid.UUID,
    warehouse_id: uuid.UUID | None = None,
) -> Decimal:
    """The current total inventory VALUE of an item (PLAN 5.3), optionally narrowed to one
    warehouse.

    For a MOVING_AVERAGE item this sums ``inv_item_valuations.total_value``; for a FIFO item it sums
    ``remaining_qty × unit_cost`` over the live cost layers. An item uses exactly one method, so the
    other source contributes 0. The FIFO product is summed in PYTHON (each factor already a typed
    Decimal) rather than ``func.sum(qty × cost)``, because multiplying two scaled-integer columns on
    SQLite yields a ×10^12 value that the MoneyType result processor cannot un-scale (D-015 trigger
    discipline: SQL never multiplies two stored money/quantity columns)."""
    valuation_stmt = select(
        func.coalesce(func.sum(ItemValuation.total_value), 0)
    ).where(ItemValuation.tenant_id == tenant_id, ItemValuation.item_id == item_id)
    layer_stmt = select(CostLayer.remaining_qty, CostLayer.unit_cost).where(
        CostLayer.tenant_id == tenant_id,
        CostLayer.item_id == item_id,
        CostLayer.remaining_qty > 0,
    )
    if warehouse_id is not None:
        valuation_stmt = valuation_stmt.where(ItemValuation.warehouse_id == warehouse_id)
        layer_stmt = layer_stmt.where(CostLayer.warehouse_id == warehouse_id)
    mav_value = Decimal((await session.execute(valuation_stmt)).scalar_one())
    fifo_value = sum(
        (Decimal(qty) * Decimal(cost) for qty, cost in (await session.execute(layer_stmt)).all()),
        Decimal(0),
    )
    return mav_value + fifo_value


async def valuation_summary(
    session: AsyncSession, tenant_id: uuid.UUID
) -> dict[uuid.UUID, Decimal]:
    """Total inventory value per item across the tenant (PLAN 5.3): ``{item_id: value}`` — the
    moving-average totals plus the FIFO live-layer values, merged per item. What the inventory-value
    dashboard KPI sums. The moving-average totals are grouped in SQL; the FIFO layer products are
    summed in Python per item (D-015: no SQL multiply of two scaled money/quantity columns).
    PERFORMANCE §6: two reads, no per-item N+1."""
    mav_rows = (
        await session.execute(
            select(ItemValuation.item_id, func.sum(ItemValuation.total_value))
            .where(ItemValuation.tenant_id == tenant_id)
            .group_by(ItemValuation.item_id)
        )
    ).all()
    layer_rows = (
        await session.execute(
            select(CostLayer.item_id, CostLayer.remaining_qty, CostLayer.unit_cost).where(
                CostLayer.tenant_id == tenant_id, CostLayer.remaining_qty > 0
            )
        )
    ).all()
    totals: dict[uuid.UUID, Decimal] = {}
    for item_id_, value in mav_rows:
        if value is not None:
            totals[item_id_] = totals.get(item_id_, Decimal(0)) + Decimal(value)
    for item_id_, qty, cost in layer_rows:
        totals[item_id_] = totals.get(item_id_, Decimal(0)) + Decimal(qty) * Decimal(cost)
    return totals


async def current_unit_cost(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    item_id: uuid.UUID,
    warehouse_id: uuid.UUID,
) -> Decimal:
    """The item's current per-unit BOOK cost in a warehouse (PLAN 5.4): the moving-average
    ``avg_unit_cost`` for a MOVING_AVERAGE item, or the weighted average of the live FIFO layers for
    a FIFO item — the SAME source a value-neutral transfer uses for its ledger cost
    (costing._current_unit_cost). A positive count variance enters stock at this cost so the value
    added matches the book cost (rather than an arbitrary entry price). Returns 0 when no
    valuation/layer exists yet (an item the system thinks is empty, counted positive — the
    adjustment then enters at 0 cost, a quantity-only correction with no value impact, which the
    operator can re-cost via a later receipt). The FIFO layer product is summed in PYTHON (D-015: no
    SQL multiply of two scaled money/quantity columns). One read for the MAV row, one for the FIFO
    layers (no per-layer N+1)."""
    valuation = (
        await session.execute(
            select(ItemValuation.avg_unit_cost).where(
                ItemValuation.tenant_id == tenant_id,
                ItemValuation.item_id == item_id,
                ItemValuation.warehouse_id == warehouse_id,
            )
        )
    ).scalar_one_or_none()
    if valuation is not None:
        return Decimal(valuation)
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
