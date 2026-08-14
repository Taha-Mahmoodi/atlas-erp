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

from app.core.rbac import catalog_keys, sync_permission_catalog
from app.core.tenancy import system_context, tenant_context
from app.modules.admin.service import assign_role, create_role, provision_tenant, provision_user
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
        dishes[dish_code] = await build_dish(
            session,
            tenant_id,
            setup,
            item_code=dish_code,
            recipe={ingredients[code]: quantity for code, quantity in recipe.items()},
        )
    return Kitchen(setup=setup, dishes=dishes, ingredients=ingredients)


async def build_dish(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    setup: StockSetup,
    *,
    item_code: str,
    recipe: dict[uuid.UUID, Decimal],
) -> uuid.UUID:
    """One sellable dish + its ACTIVE default BOM, against an ALREADY-BUILT ``StockSetup``.

    Split out of ``build_kitchen`` so a test can widen an existing kitchen's menu without seeding a
    second stock setup (``build_stock_setup`` creates EA/BOX with fixed codes and can only run once
    per tenant) — which is what the at-risk query-count test needs. An empty ``recipe`` gets no BOM
    at all: the bottled-beer case.
    """
    dish = await build_item(
        session,
        tenant_id,
        item_code=item_code,
        category_id=setup.category_id,
        base_uom_id=setup.base_uom_id,
        name=f"Dish {item_code}",
    )
    if not recipe:
        return dish.id
    bom = await build_bom(
        session, tenant_id, item_id=dish.id, uom_id=setup.base_uom_id, name=item_code
    )
    for component_item_id, quantity_per in recipe.items():
        await build_bom_component(
            session,
            tenant_id,
            bom.id,
            component_item_id=component_item_id,
            uom_id=setup.base_uom_id,
            quantity_per=quantity_per,
        )
    with tenant_context(tenant_id):
        await mfg_service.activate_bom(session, tenant_id, bom.id)
        await session.commit()
    return dish.id


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


# --- Principals ---------------------------------------------------------------

# EVERY registered hospitality.* key (importing the module's constants registers them), so a new
# hospitality permission is auto-granted to the full-rights principal — self-extending, the
# quality/procurement precedent. The kitchen its tenant needs is seeded through the db_session
# factories (system context), never over the wire, so a staff principal needs only its own keys.
_HOSPITALITY_KEYS = tuple(
    sorted(key for key in catalog_keys() if key.startswith("hospitality."))
)


@dataclass(frozen=True)
class HospitalityPrincipal:
    tenant_id: uuid.UUID
    tenant_slug: str
    user_id: uuid.UUID
    email: str
    password: str


async def create_hospitality_principal(
    session: AsyncSession,
    slug: str = "hsp-acme",
    email: str = "chef@hsp-acme.test",
    password: str = "correct-horse-battery",
    keys: tuple[str, ...] | None = None,
) -> HospitalityPrincipal:
    """Provision a tenant + user and grant a role with the hospitality permission keys through the
    real services (D-025); ``keys`` narrows the grant for the 403 RBAC tests (None = full)."""
    grant = keys if keys is not None else _HOSPITALITY_KEYS
    tenant = await provision_tenant(session, slug=slug, name=slug.title())
    user = await provision_user(session, tenant.id, email=email, password=password)
    with system_context():
        await sync_permission_catalog(session)
    role = await create_role(session, tenant.id, "Kitchen", grant, is_system=True)
    await assign_role(session, tenant.id, user.id, role.id, user.token_version)
    await session.commit()
    return HospitalityPrincipal(
        tenant_id=tenant.id,
        tenant_slug=slug,
        user_id=user.id,
        email=email,
        password=password,
    )


__all__ = [
    "HospitalityPrincipal",
    "Kitchen",
    "build_dish",
    "build_kitchen",
    "build_open_ticket",
    "create_hospitality_principal",
]
