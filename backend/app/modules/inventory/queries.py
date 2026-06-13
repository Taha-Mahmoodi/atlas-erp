"""Inventory's cross-module read interface (STRUCTURE §5).

Inventory sits just above finance in the dependency order: every module above it (procurement,
sales, manufacturing) may import THIS file to read inventory state synchronously, and inventory
imports only finance/queries downward. Keep this surface thin and stable — it is a contract; it is
the ONLY inventory file other modules import.

For PLAN 5.1 it exposes the item-master reads those modules will need: existence checks, the
item's base UoM and costing method, and the category's GL-account wiring (so the COGS handler can
resolve where to post when stock issues land in 5.2+). Stock on-hand/availability reads join here
once moves exist (5.2+).

Every function takes an explicit ``tenant_id`` and runs under the caller's tenant context, so the
D-007 filter applies on top of the explicit predicate — ordinary tenant-scoped reads, not a bypass.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.inventory.constants import CostingMethod
from app.modules.inventory.models import Item, ItemCategory


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
