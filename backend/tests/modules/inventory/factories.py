"""Inventory test data builders behind tests/modules/inventory/conftest.py (STRUCTURE §6/§8.4).

Builders go through the REAL service layer under the tenant context (D-025), so tenancy stamping
and audit fire exactly as in production. conftest.py keeps only the thin pytest fixtures.

``build_inventory_setup`` wires a tenant ready to create items: a couple of UoMs (EA, BOX) and a
category whose default costing is MOVING_AVERAGE. ``create_inventory_principal`` mirrors the
finance principal pattern with inventory.* keys (and supports a narrowed ``keys`` grant for the
403 RBAC tests). Where a category needs real finance GL accounts, the builder seeds a small COA
via the finance service first (the cross-module read those accounts validate against).
"""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import run_in_uow
from app.core.rbac import catalog_keys, sync_permission_catalog
from app.core.tenancy import system_context, tenant_context
from app.modules.admin.service import assign_role, create_role, provision_tenant, provision_user
from app.modules.finance import service as finance_service
from app.modules.finance.constants import AccountType
from app.modules.finance.schemas import AccountCreate, FiscalYearCreate
from app.modules.inventory import service
from app.modules.inventory.constants import CostingMethod, MoveType
from app.modules.inventory.count_schemas import StockCountCreate
from app.modules.inventory.models import (
    Bin,
    Item,
    ItemCategory,
    StockCount,
    StockMove,
    Uom,
    Warehouse,
)
from app.modules.inventory.schemas import (
    BinCreate,
    ItemCategoryCreate,
    ItemCreate,
    StockMoveCreate,
    UomConversionCreate,
    UomCreate,
    WarehouseCreate,
)

# EVERY registered inventory.* key (importing inventory.constants registers them), so a new
# inventory permission is auto-granted to the full-rights principal (self-extending). Plus the
# finance setup keys the costing API tests need (a valued move's COGS journal posts to finance, so
# the full-rights stock-ops client must scaffold accounts + an open period — PLAN 5.3).
_FINANCE_SETUP_KEYS = ("finance.account.manage", "finance.period.manage")
_INVENTORY_KEYS = (
    *sorted(key for key in catalog_keys() if key.startswith("inventory.")),
    *_FINANCE_SETUP_KEYS,
)


async def seed_uom(
    session: AsyncSession, tenant_id: uuid.UUID, code: str, name: str
) -> Uom:
    """Create a unit of measure through the real service (D-025)."""
    with tenant_context(tenant_id):
        uom = await service.create_uom(session, tenant_id, UomCreate(code=code, name=name))
        await session.commit()
    return uom


async def build_item_category(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    code: str = "CAT-RAW",
    name: str = "Raw materials",
    costing: CostingMethod = CostingMethod.MOVING_AVERAGE,
    with_accounts: bool = False,
) -> ItemCategory:
    """Create an item category through the real service. ``with_accounts`` seeds a small COA and
    wires the category's inventory/COGS/price-difference accounts to real finance GL accounts so
    the D-029 cross-module validation has something to find."""
    inventory_account_id: uuid.UUID | None = None
    cogs_account_id: uuid.UUID | None = None
    price_difference_account_id: uuid.UUID | None = None
    if with_accounts:
        with tenant_context(tenant_id):
            inventory_account = await finance_service.create_account(
                session,
                tenant_id,
                AccountCreate(code="1300", name="Inventory", account_type=AccountType.ASSET),
            )
            cogs_account = await finance_service.create_account(
                session,
                tenant_id,
                AccountCreate(code="5000", name="COGS", account_type=AccountType.EXPENSE),
            )
            price_diff = await finance_service.create_account(
                session,
                tenant_id,
                AccountCreate(
                    code="5900", name="Price difference", account_type=AccountType.EXPENSE
                ),
            )
            await session.commit()
        inventory_account_id = inventory_account.id
        cogs_account_id = cogs_account.id
        price_difference_account_id = price_diff.id
    with tenant_context(tenant_id):
        category = await service.create_category(
            session,
            tenant_id,
            ItemCategoryCreate(
                code=code,
                name=name,
                default_costing_method=costing,
                inventory_account_id=inventory_account_id,
                cogs_account_id=cogs_account_id,
                price_difference_account_id=price_difference_account_id,
            ),
        )
        await session.commit()
    return category


async def build_item(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    item_code: str,
    category_id: uuid.UUID,
    base_uom_id: uuid.UUID,
    **kwargs: object,
) -> Item:
    """Create an item through the real service (D-025). ``kwargs`` overrides any ItemCreate field
    (item_type, tracking_mode, costing_method, name, ...)."""
    payload_fields: dict[str, object] = {
        "item_code": item_code,
        "name": kwargs.pop("name", f"Item {item_code}"),
        "item_type": kwargs.pop("item_type", "STOCKED"),
        "category_id": category_id,
        "base_uom_id": base_uom_id,
    }
    payload_fields.update(kwargs)
    with tenant_context(tenant_id):
        item = await service.create_item(
            session, tenant_id, ItemCreate(**payload_fields)  # type: ignore[arg-type]
        )
        await session.commit()
    return item


async def add_conversion(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    item_id: uuid.UUID,
    alt_uom_id: uuid.UUID,
    factor_to_base: Decimal,
) -> None:
    """Add an alternate-UoM conversion to an item through the real service (D-025)."""
    with tenant_context(tenant_id):
        await service.create_conversion(
            session,
            tenant_id,
            item_id,
            UomConversionCreate(alt_uom_id=alt_uom_id, factor_to_base=factor_to_base),
        )
        await session.commit()


@dataclass(frozen=True)
class InventorySetup:
    """A tenant ready to create items: EA/BOX UoM ids and a MOVING_AVERAGE category id (no GL
    accounts wired — tests that need them build a category with ``with_accounts=True``). Plain ids
    so a rollback (expiring loaded ORM objects) cannot break a follow-up payload."""

    tenant_id: uuid.UUID
    category_id: uuid.UUID
    ea_uom_id: uuid.UUID
    box_uom_id: uuid.UUID


async def build_inventory_setup(
    session: AsyncSession, tenant_id: uuid.UUID
) -> InventorySetup:
    """EA + BOX units and a MOVING_AVERAGE raw-materials category (PLAN 5.1)."""
    ea = await seed_uom(session, tenant_id, "EA", "Each")
    box = await seed_uom(session, tenant_id, "BOX", "Box")
    category = await build_item_category(session, tenant_id)
    return InventorySetup(
        tenant_id=tenant_id,
        category_id=category.id,
        ea_uom_id=ea.id,
        box_uom_id=box.id,
    )


# --- Stock topology + moves (PLAN 5.2) ----------------------------------------


async def build_warehouse(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    code: str = "WH-MAIN",
    name: str = "Main warehouse",
) -> Warehouse:
    """Create a warehouse through the real service (D-025)."""
    with tenant_context(tenant_id):
        warehouse = await service.create_warehouse(
            session, tenant_id, WarehouseCreate(code=code, name=name)
        )
        await session.commit()
    return warehouse


async def build_bin(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    *,
    code: str = "A1",
    name: str = "Bin A1",
    is_default: bool = False,
) -> Bin:
    """Create a bin in a warehouse through the real service (D-025)."""
    with tenant_context(tenant_id):
        bin_row = await service.create_bin(
            session,
            tenant_id,
            BinCreate(
                warehouse_id=warehouse_id, code=code, name=name, is_default=is_default
            ),
        )
        await session.commit()
    return bin_row


async def build_move(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    payload: StockMoveCreate,
) -> StockMove:
    """Post a stock move through the real service inside a uow (D-025), so numbering, docflow and
    quant maintenance fire exactly as in production. Returns the persisted move by id (re-read after
    the uow commit so the caller holds a live, refreshed row)."""
    holder: dict[str, uuid.UUID] = {}

    async def work() -> None:
        with tenant_context(tenant_id):
            move = await service.create_move(session, tenant_id, payload)
            holder["id"] = move.id

    with tenant_context(tenant_id):
        await run_in_uow(session, work)
        return await service.get_move(session, tenant_id, holder["id"])


async def build_stock(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    item_id: uuid.UUID,
    bin_id: uuid.UUID,
    quantity: Decimal,
    *,
    lot_id: uuid.UUID | None = None,
    lot_code: str | None = None,
    serial_code: str | None = None,
    move_date: date | None = None,
    unit_cost: Decimal = Decimal(1),
) -> StockMove:
    """Seed on-hand stock by posting a RECEIPT move into a bin (D-025) — the production path, so the
    quant projection is maintained and the on-hand reads are real. Optional lot/serial create the
    tracked-instance master on the receipt (5.1 deferred that to receipts). ``unit_cost`` is the
    entry cost the costing engine values the stock at (PLAN 5.3); defaulted to 1 so quantity-only
    tests are unaffected by valuation."""
    return await build_move(
        session,
        tenant_id,
        StockMoveCreate(
            move_type=MoveType.RECEIPT,
            item_id=item_id,
            quantity=quantity,
            to_bin_id=bin_id,
            lot_id=lot_id,
            lot_code=lot_code,
            serial_code=serial_code,
            move_date=move_date,
            unit_cost=unit_cost,
        ),
    )


@dataclass(frozen=True)
class StockSetup:
    """A tenant ready to post stock moves AND value them (PLAN 5.2/5.3): a STOCKED item whose
    category wires the three GL accounts, an OPEN fiscal year (so the COGS journal can post), a
    warehouse and two bins (A1, A2). The account ids + category id are exposed so costing tests can
    assert against the posted journal. Plain ids so a rollback (expiring loaded ORM objects) cannot
    break a follow-up payload."""

    tenant_id: uuid.UUID
    item_id: uuid.UUID
    category_id: uuid.UUID
    base_uom_id: uuid.UUID
    warehouse_id: uuid.UUID
    bin_a_id: uuid.UUID
    bin_b_id: uuid.UUID
    inventory_account_id: uuid.UUID
    cogs_account_id: uuid.UUID
    price_difference_account_id: uuid.UUID
    fiscal_year_id: uuid.UUID


async def build_stock_setup(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    tracking_mode: str = "NONE",
    costing: CostingMethod = CostingMethod.MOVING_AVERAGE,
) -> StockSetup:
    """A STOCKED item (EA base) whose category wires the GL accounts, an OPEN 2026 fiscal year, plus
    a warehouse with two bins (PLAN 5.2/5.3). ``tracking_mode`` makes the item lot-/serial-tracked;
    ``costing`` picks MOVING_AVERAGE or FIFO. The wired accounts + open period are the costing
    preconditions (D-020): without them a valued move's COGS journal cannot post."""
    ea = await seed_uom(session, tenant_id, "EA", "Each")
    await seed_uom(session, tenant_id, "BOX", "Box")
    category = await build_item_category(
        session, tenant_id, costing=costing, with_accounts=True
    )
    item = await build_item(
        session,
        tenant_id,
        item_code="STK-ITEM",
        category_id=category.id,
        base_uom_id=ea.id,
        tracking_mode=tracking_mode,
        costing_method=costing,
    )
    year = await _seed_open_year(session, tenant_id)
    warehouse = await build_warehouse(session, tenant_id)
    bin_a = await build_bin(session, tenant_id, warehouse.id, code="A1", name="Bin A1")
    bin_b = await build_bin(session, tenant_id, warehouse.id, code="A2", name="Bin A2")
    # Re-read the category for its (committed) account ids — the build commit expired the object.
    with tenant_context(tenant_id):
        category = await service.get_category(session, tenant_id, category.id)
    return StockSetup(
        tenant_id=tenant_id,
        item_id=item.id,
        category_id=category.id,
        base_uom_id=ea.id,
        warehouse_id=warehouse.id,
        bin_a_id=bin_a.id,
        bin_b_id=bin_b.id,
        inventory_account_id=category.inventory_account_id,
        cogs_account_id=category.cogs_account_id,
        price_difference_account_id=category.price_difference_account_id,
        fiscal_year_id=year.id,
    )


async def build_count(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    payload: StockCountCreate,
) -> StockCount:
    """Create a count through the REAL service inside a uow (D-025), so numbering, docflow and the
    line snapshot fire exactly as in production. Returns the persisted count re-read after the uow
    commit (PLAN 5.4)."""
    holder: dict[str, uuid.UUID] = {}

    async def work() -> None:
        with tenant_context(tenant_id):
            count = await service.create_count(session, tenant_id, payload)
            holder["id"] = count.id

    with tenant_context(tenant_id):
        await run_in_uow(session, work)
        return await service.get_count(session, tenant_id, holder["id"])


async def _seed_open_year(session: AsyncSession, tenant_id: uuid.UUID):
    """Create the 2026 fiscal year (12 OPEN periods) through the real finance service so the COGS
    journal a valued move posts (PLAN 5.3) lands in an open period (D-018)."""
    with tenant_context(tenant_id):
        year = await finance_service.create_fiscal_year(
            session,
            tenant_id,
            FiscalYearCreate(code="2026", name="FY2026", start_date=date(2026, 1, 1)),
        )
        await session.commit()
    return year


@dataclass(frozen=True)
class InventoryPrincipal:
    tenant_id: uuid.UUID
    tenant_slug: str
    user_id: uuid.UUID
    email: str
    password: str


async def create_inventory_principal(
    session: AsyncSession,
    slug: str = "inv-acme",
    email: str = "ops@inv-acme.test",
    password: str = "correct-horse-battery",
    keys: tuple[str, ...] = _INVENTORY_KEYS,
) -> InventoryPrincipal:
    """Provision a tenant + user and grant a role with the inventory permission keys through the
    real services (D-025); ``keys`` narrows the grant for the 403 RBAC tests."""
    tenant = await provision_tenant(session, slug=slug, name=slug.title())
    user = await provision_user(session, tenant.id, email=email, password=password)
    with system_context():
        await sync_permission_catalog(session)
    role = await create_role(session, tenant.id, "Inventory", keys, is_system=True)
    await assign_role(session, tenant.id, user.id, role.id, user.token_version)
    await session.commit()
    return InventoryPrincipal(
        tenant_id=tenant.id,
        tenant_slug=slug,
        user_id=user.id,
        email=email,
        password=password,
    )
