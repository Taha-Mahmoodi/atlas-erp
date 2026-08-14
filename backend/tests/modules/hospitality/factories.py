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
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import API_KEY_PREFIX, mint_api_key
from app.core.models import ApiKey
from app.core.rbac import catalog_keys, sync_permission_catalog
from app.core.tenancy import system_context, tenant_context
from app.modules.admin.service import assign_role, create_role, provision_tenant, provision_user
from app.modules.finance import service as finance_service
from app.modules.hospitality.schemas import OrderTicketCreate, OrderTicketLineCreate
from app.modules.hospitality.service import tickets
from app.modules.manufacturing import service as mfg_service
from app.modules.sales import service as sales_service
from app.modules.sales.schemas import PriceListCreate, PriceListItemCreate
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


# --- Menu prices (PLAN 19 Task 7) ---------------------------------------------

# The ONE menu price list a property keeps: GENERAL (no customer group — a walk-in has no customer
# record), ACTIVE, open-ended from a fixed early date so date-window arithmetic is deterministic.
MENU_PRICE_LIST_CODE = "MENU"
MENU_PRICE_LIST_FROM = date(2026, 1, 1)


async def seed_menu_currency(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    code: str = "USD",
    is_functional: bool = True,
) -> str:
    """Create a currency in finance through the real service (D-025). FUNCTIONAL by default: it is
    what the order write narrows price resolution to, so a menu price in another currency can never
    be struck onto a check the ticket has no currency column to qualify (D-019)."""
    with tenant_context(tenant_id):
        await finance_service.create_currency(
            session, tenant_id, code=code, name=code, is_functional=is_functional
        )
        await session.commit()
    return code


async def build_menu_price_list(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    code: str = MENU_PRICE_LIST_CODE,
    currency_code: str = "USD",
) -> uuid.UUID:
    """The property's menu price list, through the real service (D-025). Returns its id. A second
    call with another ``code``/``currency_code`` seeds the foreign-currency list."""
    with tenant_context(tenant_id):
        price_list = await sales_service.create_price_list(
            session,
            tenant_id,
            PriceListCreate(
                code=code,
                name=f"{code} prices",
                currency_code=currency_code,
                valid_from=MENU_PRICE_LIST_FROM,
            ),
        )
        await session.commit()
        return price_list.id


async def build_menu_price(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    price_list_id: uuid.UUID,
    item_id: uuid.UUID,
    unit_price: str,
) -> None:
    """Put ``item_id`` on a menu price list at ``unit_price`` (the real service, D-025)."""
    with tenant_context(tenant_id):
        await sales_service.add_price_list_item(
            session,
            tenant_id,
            price_list_id,
            PriceListItemCreate(item_id=item_id, unit_price=Decimal(unit_price)),
        )
        await session.commit()


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


async def mint_website_key(
    session: AsyncSession,
    principal: HospitalityPrincipal,
    *,
    name: str = "website",
    scopes: list[str] | None = None,
) -> str:
    """Issue a D-069 machine credential bound to ``principal``'s user and return the key string.

    The ApiKey row is written directly rather than through ``POST /api/v1/admin/api-keys``: minting
    over the wire needs ``admin.apikey.manage``, which is a core key the hospitality principal
    deliberately does not hold, and D-070 would then also demand an explicit scope list. The row is
    the credential — ``core/deps._authenticate_api_key`` reads nothing else.

    ``scopes=None`` inherits the user's permissions unnarrowed; a list NARROWS them (never widens),
    which is what the 403 test drives.
    """
    full, digest = mint_api_key(principal.tenant_id)
    with tenant_context(principal.tenant_id):
        session.add(
            ApiKey(
                user_id=principal.user_id,
                name=name,
                prefix=f"{API_KEY_PREFIX}{principal.tenant_id.hex}",
                secret_sha256=digest,
                scopes=scopes,
            )
        )
        await session.commit()
    return full


__all__ = [
    "MENU_PRICE_LIST_CODE",
    "HospitalityPrincipal",
    "Kitchen",
    "build_dish",
    "build_kitchen",
    "build_menu_price",
    "build_menu_price_list",
    "build_open_ticket",
    "create_hospitality_principal",
    "mint_website_key",
    "seed_menu_currency",
]
