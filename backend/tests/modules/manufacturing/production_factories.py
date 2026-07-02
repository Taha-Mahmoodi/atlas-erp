"""Production-order test data builders (PLAN 8.2), split out of factories.py at the 400-line cap
(STRUCTURE §8.4). ``build_production_order_setup`` wires a tenant fully for the issue→finish flow;
``build_production_order`` creates an order through the real service in a uow. Re-exported through
``factories`` so call sites keep one import surface.
"""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import run_in_uow
from app.core.tenancy import tenant_context
from app.modules.finance import service as finance_service
from app.modules.finance.constants import PRODUCTION_VARIANCE, WIP_CLEARING, AccountType
from app.modules.finance.schemas import AccountCreate, FiscalYearCreate
from app.modules.inventory import service as inventory_service
from app.modules.manufacturing import service
from app.modules.manufacturing.models import ProductionOrder
from app.modules.manufacturing.schemas import ProductionOrderCreate
from tests.modules.inventory.factories import (
    build_bin,
    build_item,
    build_item_category,
    build_stock,
    build_warehouse,
    seed_uom,
)
from tests.modules.manufacturing.factories import build_bom, build_bom_component


@dataclass(frozen=True)
class ProductionOrderSetup:
    """A tenant fully wired to run a production order through issue→finish (PLAN 8.2): a parent
    finished-good item and a component item (both STOCKED, the category wires the inventory/COGS/
    price-difference GL accounts), an OPEN fiscal year, a warehouse with two default-eligible bins,
    the WIP clearing + production-variance posting defaults mapped, component on-hand stock seeded,
    and an ACTIVE default BOM (parent ← component) ready to explode. Plain ids so a rollback cannot
    break a follow-up payload. The account ids are exposed so the WIP-nets-to-zero proof reads the
    trial balance."""

    tenant_id: uuid.UUID
    parent_item_id: uuid.UUID
    component_item_id: uuid.UUID
    ea_uom_id: uuid.UUID
    category_id: uuid.UUID
    warehouse_id: uuid.UUID
    bin_id: uuid.UUID
    finished_bin_id: uuid.UUID
    bom_id: uuid.UUID
    inventory_account_id: uuid.UUID
    cogs_account_id: uuid.UUID
    price_difference_account_id: uuid.UUID
    wip_account_id: uuid.UUID
    variance_account_id: uuid.UUID
    fiscal_year_id: uuid.UUID


async def _map_posting_default(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    purpose: str,
    code: str,
    name: str,
    account_type: AccountType,
) -> uuid.UUID:
    """Create a GL account and map it as a posting default (the procurement _map_gr_ir_clearing
    precedent). Returns the account id."""
    with tenant_context(tenant_id):
        account = await finance_service.create_account(
            session, tenant_id, AccountCreate(code=code, name=name, account_type=account_type)
        )
        await session.commit()
        await finance_service.set_posting_default(session, tenant_id, purpose, account.id)
        await session.commit()
    return account.id


async def build_production_order_setup(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    map_wip: bool = True,
    map_variance: bool = True,
    component_on_hand: Decimal = Decimal(100),
    component_unit_cost: Decimal = Decimal(3),
    quantity_per: Decimal = Decimal(2),
    scrap_percent: Decimal = Decimal(0),
) -> ProductionOrderSetup:
    """Wire a tenant for the full production-order flow (PLAN 8.2). Builds the inventory stock setup
    (a category with GL accounts + an open year), a parent + component STOCKED item, a warehouse
    with a source bin (default) + a finished bin, seeds component on-hand at the unit cost, maps the
    WIP + variance posting defaults (unless asked not to — the unmapped-error tests), and an ACTIVE
    default BOM (parent ← component at ``quantity_per`` with ``scrap_percent``)."""
    ea = await seed_uom(session, tenant_id, "EA", "Each")
    await seed_uom(session, tenant_id, "BOX", "Box")
    category = await build_item_category(session, tenant_id, with_accounts=True)
    parent = await build_item(
        session, tenant_id, item_code="FG-1", category_id=category.id, base_uom_id=ea.id,
        name="Finished good",
    )
    component = await build_item(
        session, tenant_id, item_code="RM-1", category_id=category.id, base_uom_id=ea.id,
        name="Raw material",
    )
    with tenant_context(tenant_id):
        year = await finance_service.create_fiscal_year(
            session,
            tenant_id,
            FiscalYearCreate(code="2026", name="FY2026", start_date=date(2026, 1, 1)),
        )
        await session.commit()
    warehouse = await build_warehouse(session, tenant_id)
    source_bin = await build_bin(
        session, tenant_id, warehouse.id, code="A1", name="Source", is_default=True
    )
    finished_bin = await build_bin(
        session, tenant_id, warehouse.id, code="FG", name="Finished goods"
    )
    if component_on_hand > 0:
        await build_stock(
            session, tenant_id, component.id, source_bin.id, component_on_hand,
            unit_cost=component_unit_cost,
        )

    wip_account_id = (
        await _map_posting_default(
            session, tenant_id, WIP_CLEARING, "1400", "WIP clearing", AccountType.ASSET
        )
        if map_wip
        else uuid.uuid4()
    )
    variance_account_id = (
        await _map_posting_default(
            session, tenant_id, PRODUCTION_VARIANCE, "5910", "Production variance",
            AccountType.EXPENSE,
        )
        if map_variance
        else uuid.uuid4()
    )

    bom = await build_bom(session, tenant_id, item_id=parent.id, uom_id=ea.id)
    await build_bom_component(
        session, tenant_id, bom.id, component_item_id=component.id, uom_id=ea.id,
        quantity_per=quantity_per, scrap_percent=scrap_percent,
    )
    with tenant_context(tenant_id):
        await service.activate_bom(session, tenant_id, bom.id)
        await session.commit()
        category = await inventory_service.get_category(session, tenant_id, category.id)
    return ProductionOrderSetup(
        tenant_id=tenant_id,
        parent_item_id=parent.id,
        component_item_id=component.id,
        ea_uom_id=ea.id,
        category_id=category.id,
        warehouse_id=warehouse.id,
        bin_id=source_bin.id,
        finished_bin_id=finished_bin.id,
        bom_id=bom.id,
        inventory_account_id=category.inventory_account_id,
        cogs_account_id=category.cogs_account_id,
        price_difference_account_id=category.price_difference_account_id,
        wip_account_id=wip_account_id,
        variance_account_id=variance_account_id,
        fiscal_year_id=year.id,
    )


async def build_production_order(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    payload: ProductionOrderCreate,
) -> ProductionOrder:
    """Create a production order through the REAL service inside a uow (D-025), so numbering +
    docflow and the BOM explosion fire exactly as in production. Returns the order re-read after the
    uow commit."""
    holder: dict[str, uuid.UUID] = {}

    async def work() -> None:
        with tenant_context(tenant_id):
            order = await service.create_production_order(session, tenant_id, payload)
            holder["id"] = order.id

    with tenant_context(tenant_id):
        await run_in_uow(session, work)
        return await service.get_production_order(session, tenant_id, holder["id"])
