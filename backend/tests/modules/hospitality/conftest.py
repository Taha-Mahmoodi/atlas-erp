"""Hospitality test fixtures (STRUCTURE §6): a menu item to hang availability and tickets off.

A menu item IS an ordinary inventory ``Item`` (PLAN 19 adds no second item entity), so the setup is
two calls into the inventory factories and there is nothing for a hospitality ``factories.py`` to
own yet — these thin fixtures are the whole surface. Promote to ``factories.py`` when Task 6/7 need
a builder that composes more than this.

``build_inventory_setup`` seeds EA and BOX with FIXED codes, so it must run ONCE per tenant; every
dish then comes from ``make_dish``. No GL accounts and no fiscal year are wired: neither
availability nor an order ticket moves stock or posts a journal (ingredient depletion is a separate
BACKGROUND concern, Q4/Task 5).
"""

import uuid
from collections.abc import Awaitable, Callable

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from tests.modules.inventory.factories import (
    InventorySetup,
    build_inventory_setup,
    build_item,
)

__all__ = ["InventorySetup"]


@pytest.fixture
async def menu_setup(db_session: AsyncSession, tenant_a: uuid.UUID) -> InventorySetup:
    """EA/BOX units and a category — the minimum a sellable item needs."""
    return await build_inventory_setup(db_session, tenant_a)


@pytest.fixture
def make_dish(
    db_session: AsyncSession, tenant_a: uuid.UUID, menu_setup: InventorySetup
) -> Callable[..., Awaitable[uuid.UUID]]:
    """Create one sellable menu item and return its id. Ids rather than ORM objects: a ticket test
    commits repeatedly, and an expired instance would fail on attribute access."""

    async def _make(item_code: str, name: str) -> uuid.UUID:
        item = await build_item(
            db_session,
            tenant_a,
            item_code=item_code,
            category_id=menu_setup.category_id,
            base_uom_id=menu_setup.ea_uom_id,
            name=name,
        )
        return item.id

    return _make


@pytest.fixture
async def dish_id(make_dish: Callable[..., Awaitable[uuid.UUID]]) -> uuid.UUID:
    """The single dish most tests need."""
    return await make_dish("DISH-001", "Caprese")
