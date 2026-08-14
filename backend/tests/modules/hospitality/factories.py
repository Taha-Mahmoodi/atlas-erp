"""Hospitality test data builders (STRUCTURE §6/§8.4), behind the fixtures in conftest.py.

Builders go through the REAL services under the tenant context (D-025), so tenancy stamping, audit,
numbering and costing fire exactly as in production.

``build_kitchen`` is the setup a DEPLETION test needs and a plain availability/ticket test does not:
recipes are manufacturing BOMs and a depletion posts real valued ISSUE moves, so it wires the D-020
costing preconditions (a category with the three GL accounts, an open fiscal year) plus a storeroom
bin holding every ingredient. It reuses the inventory and manufacturing factories rather than
re-implementing them — a menu item IS an inventory item and a recipe IS a BOM (PLAN 19 adds neither
entity).

Note it seeds its own UoMs through ``build_stock_setup``, so it must NOT be combined with
conftest.py's ``menu_setup`` fixture in one test: both create EA/BOX with fixed codes.
"""

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import tenant_context
from app.modules.hospitality.schemas import OrderTicketCreate, OrderTicketLineCreate
from app.modules.hospitality.service import tickets
from app.modules.manufacturing import service as mfg_service
from tests.modules.inventory.factories import (
    StockSetup,
    build_item,
    build_stock,
    build_stock_setup,
)
from tests.modules.manufacturing.factories import build_bom, build_bom_component


@dataclass(frozen=True)
class Kitchen:
    """A tenant that can actually sell a dish: a GL-wired category + an open fiscal year (the D-020
    costing preconditions an ISSUE move needs), a storeroom bin holding every ingredient, and one
    ACTIVE default BOM per dish. Plain ids — the builders commit, expiring ORM instances."""

    setup: StockSetup
    dishes: dict[str, uuid.UUID]
    ingredients: dict[str, uuid.UUID]


async def build_kitchen(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    recipes: dict[str, dict[str, Decimal]],
    *,
    stock: Decimal = Decimal(1000),
    unstocked: frozenset[str] = frozenset(),
) -> Kitchen:
    """Seed ``{dish_code: {ingredient_code: quantity_per}}`` as real items and real ACTIVE BOMs.

    A dish whose recipe is empty gets no BOM at all (the bottled-beer case). Ingredients named in
    ``unstocked`` are created WITHOUT stock — the phantom stock-out Q4 says must not reach the
    guest.
    """
    setup = await build_stock_setup(session, tenant_id)
    ingredient_codes = sorted({code for recipe in recipes.values() for code in recipe})
    ingredients: dict[str, uuid.UUID] = {}
    for code in ingredient_codes:
        item = await build_item(
            session,
            tenant_id,
            item_code=code,
            category_id=setup.category_id,
            base_uom_id=setup.base_uom_id,
            name=f"Ingredient {code}",
        )
        ingredients[code] = item.id
        if code not in unstocked:
            await build_stock(session, tenant_id, item.id, setup.bin_a_id, stock)

    dishes: dict[str, uuid.UUID] = {}
    for dish_code, recipe in recipes.items():
        dish = await build_item(
            session,
            tenant_id,
            item_code=dish_code,
            category_id=setup.category_id,
            base_uom_id=setup.base_uom_id,
            name=f"Dish {dish_code}",
        )
        dishes[dish_code] = dish.id
        if not recipe:
            continue
        bom = await build_bom(
            session, tenant_id, item_id=dish.id, uom_id=setup.base_uom_id, name=dish_code
        )
        for ingredient_code, quantity_per in recipe.items():
            await build_bom_component(
                session,
                tenant_id,
                bom.id,
                component_item_id=ingredients[ingredient_code],
                uom_id=setup.base_uom_id,
                quantity_per=quantity_per,
            )
        with tenant_context(tenant_id):
            await mfg_service.activate_bom(session, tenant_id, bom.id)
            await session.commit()
    return Kitchen(setup=setup, dishes=dishes, ingredients=ingredients)


async def build_open_ticket(
    session: AsyncSession, tenant_id: uuid.UUID, lines: list[tuple[uuid.UUID, str]]
) -> uuid.UUID:
    """Open a ticket through the real service and return its id (the commit expires the object).
    ``lines`` is ``[(item_id, quantity)]`` — the price is irrelevant to depletion, which reads
    quantities only."""
    with tenant_context(tenant_id):
        ticket = await tickets.create_ticket(
            session,
            tenant_id,
            OrderTicketCreate(
                table_code="T7",
                guest_count=4,
                lines=[
                    OrderTicketLineCreate(
                        item_id=item_id,
                        quantity=Decimal(quantity),
                        unit_price=Decimal("18.00"),
                    )
                    for item_id, quantity in lines
                ],
            ),
        )
        await session.commit()
        return ticket.id


__all__ = ["Kitchen", "build_kitchen", "build_open_ticket"]
