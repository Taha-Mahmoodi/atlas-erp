"""Service-level MRP engine tests (PLAN 8.3, D-049): demand gathering, supply netting, and the
multi-level BOM explosion.

Cover single-level BUY netting, multi-level MAKE explosion (quantities multiplied through the BOM,
scrap inflation), supply netting (on-hand / open PO / open production order), reorder-point demand,
and the explosion cycle guard. The capacity check, conversion, and firm/cancel/regeneration proofs
live in test_mrp_planning.py; the job/HTTP path in test_mrp_api.py. The run is driven through the
real service inside a uow (D-025) via the shared helper.
"""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import tenant_context
from app.modules.manufacturing import service
from app.modules.manufacturing.constants import (
    MRP_MAX_EXPLOSION_LEVELS,
    PlannedOrderStatus,
    PlannedOrderType,
)
from app.modules.manufacturing.models import PlannedOrder
from tests.modules.manufacturing._mrp_shared import planned_by_item, run_mrp
from tests.modules.manufacturing.mrp_factories import (
    MrpSetup,
    build_mrp_setup,
    build_open_po,
    seed_mrp_on_hand,
    set_reorder_point,
)


@pytest.fixture
async def mrp_setup(db_session: AsyncSession, tenant_a: uuid.UUID) -> MrpSetup:
    """A tenant wired with a confirmed undelivered sales order, a multi-level BOM, a routing, and a
    vendor — real demand + supply for the MRP run to net + explode."""
    return await build_mrp_setup(db_session, tenant_a)


# --- single-level BUY ---------------------------------------------------------


async def test_buy_item_demand_minus_on_hand_makes_planned_purchase(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """A BUY raw (no active BOM) below its reorder point with no covering supply → a PLANNED
    PURCHASE order for the reorder quantity. No sales demand (so the finished BOM does not explode);
    only a reorder point on raw1, a BUY leaf."""
    setup = await build_mrp_setup(db_session, tenant_a, sales_quantity="0")
    await set_reorder_point(
        db_session, setup, setup.raw1_item_id,
        reorder_point=Decimal(50), reorder_quantity=Decimal(80),
    )
    run = await run_mrp(db_session, tenant_a)
    planned = await planned_by_item(db_session, tenant_a, run.id)
    assert setup.raw1_item_id in planned
    order = planned[setup.raw1_item_id]
    assert order.order_type == PlannedOrderType.BUY.value
    assert order.quantity == Decimal(80)
    assert order.status == PlannedOrderStatus.PLANNED.value


async def test_on_hand_covering_demand_makes_no_planned_order(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """On-hand at/above the reorder point → no shortfall → no planned order for that item."""
    setup = await build_mrp_setup(db_session, tenant_a, sales_quantity="0")
    await set_reorder_point(
        db_session, setup, setup.raw1_item_id,
        reorder_point=Decimal(50), reorder_quantity=Decimal(80),
    )
    await seed_mrp_on_hand(db_session, setup, setup.raw1_item_id, Decimal(100))  # above reorder
    run = await run_mrp(db_session, tenant_a)
    planned = await planned_by_item(db_session, tenant_a, run.id)
    assert setup.raw1_item_id not in planned


# --- multi-level MAKE explosion -----------------------------------------------


async def test_make_item_explodes_bom_into_dependent_planned_orders(
    db_session: AsyncSession, mrp_setup: MrpSetup
) -> None:
    """A finished good (active BOM) with sales demand 10 explodes:

    - finished: PLANNED PRODUCTION 10 (level 0)
    - sub-assembly (qty_per 2): 10 × 2 = 20 PLANNED PRODUCTION (level 1, itself MAKE → explodes)
    - raw1 (qty_per 3, direct component of finished): 10 × 3 = 30 PLANNED PURCHASE (level 1)
    - raw2 (qty_per 4 of sub-assembly): 20 × 4 = 80 PLANNED PURCHASE (level 2)
    """
    setup = mrp_setup
    run = await run_mrp(db_session, setup.tenant_id)
    planned = await planned_by_item(db_session, setup.tenant_id, run.id)

    finished = planned[setup.finished_item_id]
    assert finished.order_type == PlannedOrderType.MAKE.value
    assert finished.quantity == Decimal(10)
    assert finished.level == 0

    sub = planned[setup.sub_assembly_item_id]
    assert sub.order_type == PlannedOrderType.MAKE.value
    assert sub.quantity == Decimal(20)  # 10 × 2
    assert sub.level == 1

    raw1 = planned[setup.raw1_item_id]
    assert raw1.order_type == PlannedOrderType.BUY.value
    assert raw1.quantity == Decimal(30)  # 10 × 3
    assert raw1.level == 1

    raw2 = planned[setup.raw2_item_id]
    assert raw2.order_type == PlannedOrderType.BUY.value
    assert raw2.quantity == Decimal(80)  # 20 × 4
    assert raw2.level == 2

    assert run.planned_make_count == 2  # finished + sub-assembly
    assert run.planned_buy_count == 2  # raw1 + raw2


async def test_scrap_percent_inflates_dependent_demand(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """A component's scrap_percent inflates the exploded dependent demand: a finished good with a
    single component at qty_per 3 and scrap 10% over sales demand 10 → 10 × 3 × 1.10 = 33."""
    from tests.modules.inventory.factories import (
        build_item,
        build_item_category,
        seed_uom,
    )
    from tests.modules.manufacturing.factories import build_bom, build_bom_component
    from tests.modules.sales.factories import (
        build_customer,
        build_sales_order,
        confirm_sales_order,
        seed_currency,
    )

    ea = await seed_uom(db_session, tenant_a, "EA", "Each")
    category = await build_item_category(db_session, tenant_a, with_accounts=True)
    await seed_currency(db_session, tenant_a)
    finished = await build_item(
        db_session, tenant_a, item_code="SCR-FG", category_id=category.id, base_uom_id=ea.id,
    )
    raw = await build_item(
        db_session, tenant_a, item_code="SCR-RM", category_id=category.id, base_uom_id=ea.id,
    )
    bom = await build_bom(db_session, tenant_a, item_id=finished.id, uom_id=ea.id)
    await build_bom_component(
        db_session, tenant_a, bom.id, component_item_id=raw.id, uom_id=ea.id,
        quantity_per=Decimal(3), scrap_percent=Decimal(10),
    )
    with tenant_context(tenant_a):
        await service.activate_bom(db_session, tenant_a, bom.id)
        await db_session.commit()
    customer = await build_customer(
        db_session, tenant_a, customer_code="SCR-C", credit_limit=Decimal(10_000_000)
    )
    order = await build_sales_order(
        db_session, tenant_a, customer_id=customer.id, item_id=finished.id, uom_id=ea.id,
        quantity="10", unit_price="100",
    )
    await confirm_sales_order(db_session, tenant_a, order.id)

    run = await run_mrp(db_session, tenant_a)
    planned = await planned_by_item(db_session, tenant_a, run.id)
    assert planned[raw.id].quantity == Decimal(33)  # 10 × 3 × 1.10


# --- supply netting -----------------------------------------------------------


async def test_on_hand_reduces_planned_production_quantity(
    db_session: AsyncSession, mrp_setup: MrpSetup
) -> None:
    """On-hand of a MAKE item reduces its net production quantity (and therefore its explosion)."""
    setup = mrp_setup
    await seed_mrp_on_hand(db_session, setup, setup.finished_item_id, Decimal(4))  # demand 10 - 4
    run = await run_mrp(db_session, setup.tenant_id)
    planned = await planned_by_item(db_session, setup.tenant_id, run.id)
    assert planned[setup.finished_item_id].quantity == Decimal(6)  # 10 - 4
    assert planned[setup.sub_assembly_item_id].quantity == Decimal(12)  # 6 × 2
    assert planned[setup.raw1_item_id].quantity == Decimal(18)  # 6 × 3
    assert planned[setup.raw2_item_id].quantity == Decimal(48)  # 12 × 4


async def test_open_po_reduces_planned_purchase_quantity(
    db_session: AsyncSession, mrp_setup: MrpSetup
) -> None:
    """An open (SENT) PO for a BUY raw nets as incoming supply, reducing the planned purchase."""
    setup = mrp_setup
    await build_open_po(db_session, setup, setup.raw1_item_id, "10")  # 30 needed - 10 on order
    run = await run_mrp(db_session, setup.tenant_id)
    planned = await planned_by_item(db_session, setup.tenant_id, run.id)
    assert planned[setup.raw1_item_id].quantity == Decimal(20)  # 30 - 10


async def test_open_production_order_reduces_planned_production(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """An open production order for a MAKE item nets as supply, reducing the planned production."""
    from app.modules.manufacturing.schemas import ProductionOrderCreate
    from tests.modules.manufacturing.production_factories import build_production_order

    setup = await build_mrp_setup(db_session, tenant_a, sales_quantity="10")
    # An open (DRAFT) production order for 4 finished goods → 10 - 4 = 6 net production.
    await build_production_order(
        db_session, tenant_a,
        ProductionOrderCreate(
            item_id=setup.finished_item_id, quantity=Decimal(4), warehouse_id=setup.warehouse_id,
        ),
    )
    run = await run_mrp(db_session, tenant_a)
    planned = await planned_by_item(db_session, tenant_a, run.id)
    assert planned[setup.finished_item_id].quantity == Decimal(6)  # 10 - 4 open order


# --- reorder-point demand independent of sales --------------------------------


async def test_reorder_point_demand_adds_to_sales_demand(
    db_session: AsyncSession, mrp_setup: MrpSetup
) -> None:
    """A reorder point on the finished good adds to the sales demand (both are level-0 demand)."""
    setup = mrp_setup
    await set_reorder_point(
        db_session, setup, setup.finished_item_id,
        reorder_point=Decimal(5), reorder_quantity=Decimal(7),
    )
    run = await run_mrp(db_session, setup.tenant_id)
    planned = await planned_by_item(db_session, setup.tenant_id, run.id)
    # sales 10 + reorder 7 = 17 net (on-hand 0 < reorder point 5 so the reorder fires).
    assert planned[setup.finished_item_id].quantity == Decimal(17)


async def test_shared_component_keeps_dependent_and_independent_demand(
    db_session: AsyncSession, mrp_setup: MrpSetup
) -> None:
    """Regression for #76: raw1 has independent reorder demand AND is a component of the
    finished good. Netting on first encounter used to plan only the reorder 50 and DROP the 30
    dependent units from the finished good's explosion; low-level-code netting plans 80."""
    setup = mrp_setup
    await set_reorder_point(
        db_session, setup, setup.raw1_item_id,
        reorder_point=Decimal(5), reorder_quantity=Decimal(50),
    )
    run = await run_mrp(db_session, setup.tenant_id)
    planned = await planned_by_item(db_session, setup.tenant_id, run.id)
    # raw1 = reorder 50 (independent) + 3 x 10 (dependent from finished) = 80.
    assert planned[setup.raw1_item_id].quantity == Decimal(80)
    assert planned[setup.raw1_item_id].order_type == PlannedOrderType.BUY.value
    # The rest of the tree is unchanged: sub 2x10=20, raw2 4x20=80.
    assert planned[setup.sub_assembly_item_id].quantity == Decimal(20)
    assert planned[setup.raw2_item_id].quantity == Decimal(80)


# --- cycle guard --------------------------------------------------------------


async def test_cyclic_bom_terminates_via_depth_cap(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """A constructed A↔B cyclic BOM does not infinite-loop: the level cap + already-netted guard
    terminate the explosion cleanly, producing a bounded plan."""
    from tests.modules.inventory.factories import (
        build_item,
        build_item_category,
        build_warehouse,
        seed_uom,
    )
    from tests.modules.manufacturing.factories import build_bom, build_bom_component

    ea_obj = await seed_uom(db_session, tenant_a, "EA", "Each")
    ea = ea_obj.id
    category = await build_item_category(db_session, tenant_a, with_accounts=True, code="CY")
    item_a = await build_item(
        db_session, tenant_a, item_code="CYC-A", category_id=category.id, base_uom_id=ea,
        reorder_point=Decimal(1), reorder_quantity=Decimal(1),
    )
    item_b = await build_item(
        db_session, tenant_a, item_code="CYC-B", category_id=category.id, base_uom_id=ea,
    )
    await build_warehouse(db_session, tenant_a, code="WH-CY")
    # A ← B and B ← A (a cycle the masters allow across separate BOMs).
    bom_a = await build_bom(db_session, tenant_a, item_id=item_a.id, uom_id=ea, version="cy-a")
    await build_bom_component(
        db_session, tenant_a, bom_a.id, component_item_id=item_b.id, uom_id=ea,
        quantity_per=Decimal(1),
    )
    with tenant_context(tenant_a):
        await service.activate_bom(db_session, tenant_a, bom_a.id)
        await db_session.commit()
    bom_b = await build_bom(db_session, tenant_a, item_id=item_b.id, uom_id=ea, version="cy-b")
    await build_bom_component(
        db_session, tenant_a, bom_b.id, component_item_id=item_a.id, uom_id=ea,
        quantity_per=Decimal(1),
    )
    with tenant_context(tenant_a):
        await service.activate_bom(db_session, tenant_a, bom_b.id)
        await db_session.commit()

    # The run must terminate (not hang) and produce a bounded number of planned orders.
    run = await run_mrp(db_session, tenant_a)
    with tenant_context(tenant_a):
        count = (
            await db_session.execute(
                select(func.count()).select_from(PlannedOrder).where(
                    PlannedOrder.tenant_id == tenant_a, PlannedOrder.mrp_run_id == run.id
                )
            )
        ).scalar_one()
    # A and B are each netted once (the already-netted guard collapses the cycle); never unbounded.
    assert 0 < count <= MRP_MAX_EXPLOSION_LEVELS
