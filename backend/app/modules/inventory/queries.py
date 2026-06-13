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
from app.modules.inventory.models import Item, ItemCategory, StockQuant


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
