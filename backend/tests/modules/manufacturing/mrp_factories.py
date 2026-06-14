"""MRP test data builders (PLAN 8.3), split out of factories.py at the 400-line cap (STRUCTURE
§8.4). They wire a tenant with real demand (a confirmed undelivered sales order, reorder points) and
real supply (on-hand, open POs, open production orders) plus a multi-level BOM, so an MRP run has
genuine data to net + explode. Everything goes through the REAL service layer under the tenant
context (D-025); re-exported through ``factories`` so call sites keep one import surface.

``build_mrp_setup`` is the workhorse: a finished good (MAKE, active BOM finished ← sub-assembly + a
direct raw), a sub-assembly (MAKE, its own active BOM sub-assembly ← raw2) and the leaf raws (BUY),
all stocked items in a warehouse with an open year and the GL accounts wired, plus an active default
routing on the finished good through one work centre (for the rough capacity check). A confirmed
undelivered sales order for the finished good supplies the level-0 demand. The helpers below seed
additional supply (on-hand, open PO, open production order) and reorder points per item id.
"""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import tenant_context
from app.modules.finance import service as finance_service
from app.modules.finance.schemas import FiscalYearCreate
from app.modules.manufacturing import service as mfg_service
from app.modules.manufacturing.models import Bom
from tests.modules.inventory.factories import (
    build_bin,
    build_item,
    build_item_category,
    build_stock,
    build_warehouse,
    seed_uom,
)
from tests.modules.manufacturing.factories import (
    build_bom,
    build_bom_component,
    build_routing,
    build_routing_operation,
    build_work_center,
)
from tests.modules.procurement.factories import (
    build_approved_item,
    build_po,
    build_vendor,
)
from tests.modules.sales.factories import (
    build_customer,
    build_sales_order,
    confirm_sales_order,
    seed_currency,
)


@dataclass(frozen=True)
class MrpSetup:
    """A tenant wired with real MRP demand + supply + a multi-level BOM (module docstring). Plain
    ids so a rollback cannot break a follow-up payload."""

    tenant_id: uuid.UUID
    ea_uom_id: uuid.UUID
    category_id: uuid.UUID
    warehouse_id: uuid.UUID
    bin_id: uuid.UUID
    customer_id: uuid.UUID
    vendor_id: uuid.UUID
    fiscal_year_id: uuid.UUID
    # Items: finished good (MAKE), sub-assembly (MAKE), raw1 (direct component of finished, BUY),
    # raw2 (component of the sub-assembly, BUY).
    finished_item_id: uuid.UUID
    sub_assembly_item_id: uuid.UUID
    raw1_item_id: uuid.UUID
    raw2_item_id: uuid.UUID
    finished_bom_id: uuid.UUID
    sub_assembly_bom_id: uuid.UUID
    work_center_id: uuid.UUID


async def _activate_bom(session: AsyncSession, tenant_id: uuid.UUID, bom: Bom) -> None:
    with tenant_context(tenant_id):
        await mfg_service.activate_bom(session, tenant_id, bom.id)
        await session.commit()


async def build_mrp_setup(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    sales_quantity: str = "10",
    finished_qty_per_sub: Decimal = Decimal(2),
    finished_qty_per_raw1: Decimal = Decimal(3),
    sub_qty_per_raw2: Decimal = Decimal(4),
    routing_setup_minutes: Decimal = Decimal(60),
    routing_run_minutes: Decimal = Decimal(10),
) -> MrpSetup:
    """Wire the full multi-level MRP scenario (module docstring): a finished good with an active BOM
    (finished ← sub-assembly + raw1) and an active routing, a sub-assembly with its own active BOM
    (sub-assembly ← raw2), the leaf raws (BUY), an OPEN year, a warehouse, a customer with a
    confirmed undelivered sales order for ``sales_quantity`` of the finished good, and a vendor."""
    ea = await seed_uom(session, tenant_id, "EA", "Each")
    await seed_uom(session, tenant_id, "BOX", "Box")
    category = await build_item_category(session, tenant_id, with_accounts=True)
    await seed_currency(session, tenant_id)  # USD functional currency (sales + procurement + buy)

    with tenant_context(tenant_id):
        year = await finance_service.create_fiscal_year(
            session,
            tenant_id,
            FiscalYearCreate(code="2026", name="FY2026", start_date=date(2026, 1, 1)),
        )
        await session.commit()

    finished = await build_item(
        session, tenant_id, item_code="FG-1", category_id=category.id, base_uom_id=ea.id,
        name="Finished good",
    )
    sub = await build_item(
        session, tenant_id, item_code="SA-1", category_id=category.id, base_uom_id=ea.id,
        name="Sub-assembly",
    )
    raw1 = await build_item(
        session, tenant_id, item_code="RM-1", category_id=category.id, base_uom_id=ea.id,
        name="Raw 1",
    )
    raw2 = await build_item(
        session, tenant_id, item_code="RM-2", category_id=category.id, base_uom_id=ea.id,
        name="Raw 2",
    )

    warehouse = await build_warehouse(session, tenant_id)
    source_bin = await build_bin(
        session, tenant_id, warehouse.id, code="A1", name="Source", is_default=True
    )

    # Finished BOM: finished ← sub-assembly (MAKE) + raw1 (BUY).
    finished_bom = await build_bom(session, tenant_id, item_id=finished.id, uom_id=ea.id)
    await build_bom_component(
        session, tenant_id, finished_bom.id, component_item_id=sub.id, uom_id=ea.id,
        quantity_per=finished_qty_per_sub,
    )
    await build_bom_component(
        session, tenant_id, finished_bom.id, component_item_id=raw1.id, uom_id=ea.id,
        quantity_per=finished_qty_per_raw1,
    )
    await _activate_bom(session, tenant_id, finished_bom)

    # Sub-assembly BOM: sub-assembly ← raw2 (BUY).
    sub_bom = await build_bom(session, tenant_id, item_id=sub.id, uom_id=ea.id, version="1")
    await build_bom_component(
        session, tenant_id, sub_bom.id, component_item_id=raw2.id, uom_id=ea.id,
        quantity_per=sub_qty_per_raw2,
    )
    await _activate_bom(session, tenant_id, sub_bom)

    # An active default routing on the finished good through one work centre (rough capacity check).
    work_center = await build_work_center(
        session, tenant_id, capacity_hours_per_day=Decimal(8), efficiency_percent=Decimal(100)
    )
    routing = await build_routing(session, tenant_id, item_id=finished.id)
    await build_routing_operation(
        session, tenant_id, routing.id, work_center_id=work_center.id,
        setup_time_minutes=routing_setup_minutes,
        run_time_minutes_per_unit=routing_run_minutes,
    )
    with tenant_context(tenant_id):
        await mfg_service.activate_routing(session, tenant_id, routing.id)
        await session.commit()

    customer = await build_customer(
        session, tenant_id, customer_code="MRP-CUST", credit_limit=Decimal(10_000_000)
    )
    vendor = await build_vendor(session, tenant_id, vendor_code="MRP-VEND")
    # A sales order line must be > 0; ``sales_quantity="0"`` means "no independent sales demand"
    # (the reorder-only / pure-BUY scenarios), so skip the order entirely.
    if Decimal(sales_quantity) > 0:
        order = await build_sales_order(
            session, tenant_id, customer_id=customer.id, item_id=finished.id, uom_id=ea.id,
            quantity=sales_quantity, unit_price="100",
        )
        await confirm_sales_order(session, tenant_id, order.id)

    return MrpSetup(
        tenant_id=tenant_id,
        ea_uom_id=ea.id,
        category_id=category.id,
        warehouse_id=warehouse.id,
        bin_id=source_bin.id,
        customer_id=customer.id,
        vendor_id=vendor.id,
        fiscal_year_id=year.id,
        finished_item_id=finished.id,
        sub_assembly_item_id=sub.id,
        raw1_item_id=raw1.id,
        raw2_item_id=raw2.id,
        finished_bom_id=finished_bom.id,
        sub_assembly_bom_id=sub_bom.id,
        work_center_id=work_center.id,
    )


async def seed_mrp_on_hand(
    session: AsyncSession,
    setup: MrpSetup,
    item_id: uuid.UUID,
    quantity: Decimal,
) -> None:
    """Seed on-hand supply for an item by posting a RECEIPT move (D-025) — the maintained quant
    projection MRP nets against."""
    await build_stock(
        session, setup.tenant_id, item_id, setup.bin_id, quantity, unit_cost=Decimal(1)
    )


async def set_reorder_point(
    session: AsyncSession,
    setup: MrpSetup,
    item_id: uuid.UUID,
    *,
    reorder_point: Decimal,
    reorder_quantity: Decimal,
) -> None:
    """Set an item's reorder point + quantity through the real inventory service (D-025) so the
    reorder scan (``items_below_reorder_point``) raises consumption-based demand for it."""
    from app.modules.inventory import service as inventory_service
    from app.modules.inventory.schemas import ItemUpdate

    with tenant_context(setup.tenant_id):
        await inventory_service.update_item(
            session,
            setup.tenant_id,
            item_id,
            ItemUpdate(reorder_point=reorder_point, reorder_quantity=reorder_quantity),
        )
        await session.commit()


async def build_open_po(
    session: AsyncSession,
    setup: MrpSetup,
    item_id: uuid.UUID,
    quantity: str,
) -> None:
    """Create an open (SENT, un-received) purchase order line for ``item_id`` so MRP nets it as
    incoming supply (``open_incoming_quantity`` counts SENT/APPROVED PO lines) — approve the item
    for the vendor, raise the PO, then send it (the sales ``seed_on_order`` precedent, D-025)."""
    from app.core.events import run_in_uow
    from app.modules.procurement import service as proc_service

    await build_approved_item(session, setup.tenant_id, setup.vendor_id, item_id)
    po = await build_po(
        session, setup.tenant_id, vendor_id=setup.vendor_id, item_id=item_id,
        uom_id=setup.ea_uom_id, quantity=quantity,
    )

    async def work() -> None:
        with tenant_context(setup.tenant_id):
            await proc_service.send_purchase_order(session, setup.tenant_id, po.id)

    with tenant_context(setup.tenant_id):
        await run_in_uow(session, work)
