"""Service-level MRP planning tests (PLAN 8.3, D-049): the rough capacity check, planned-order
conversion (MAKE → production order; BUY → requisition via the event), firm/cancel + regeneration,
and the set-based query budget + tenant isolation.

Split from test_mrp.py (the demand/supply/explosion engine proofs) at the 400-line file cap
(STRUCTURE §8.4). The run is driven through the real service inside a uow (D-025) via the shared
helper.
"""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import run_in_uow
from app.core.tenancy import tenant_context
from app.modules.manufacturing import service
from app.modules.manufacturing.constants import PlannedOrderStatus
from app.modules.manufacturing.models import MrpRun, PlannedOrder, ProductionOrder
from app.modules.procurement.models import PurchaseRequisition
from tests.conftest import QueryCounter
from tests.modules.manufacturing._mrp_shared import RUN_DATE, planned_by_item, run_mrp
from tests.modules.manufacturing.mrp_factories import MrpSetup, build_mrp_setup


@pytest.fixture
async def mrp_setup(db_session: AsyncSession, tenant_a: uuid.UUID) -> MrpSetup:
    """A tenant wired with a confirmed undelivered sales order, a multi-level BOM, a routing, and a
    vendor — real demand + supply for the MRP run to net + explode."""
    return await build_mrp_setup(db_session, tenant_a)


# --- rough capacity check -----------------------------------------------------


async def test_capacity_load_flags_overloaded_work_center(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """Planned production loads the routing's work centre; a load above available minutes over the
    horizon flags ``is_overloaded``. Available = 8h × 100% × 30d × 60 = 14400 min; a setup of 60 +
    run 2000 × 10 = 20060 min overloads it."""
    setup = await build_mrp_setup(
        db_session, tenant_a, sales_quantity="10",
        routing_setup_minutes=Decimal(60), routing_run_minutes=Decimal(2000),
    )
    run = await run_mrp(db_session, tenant_a)
    with tenant_context(tenant_a):
        loads = await service.capacity_for_run(db_session, tenant_a, run.id)
    assert len(loads) == 1
    load = loads[0]
    assert load.work_center_id == setup.work_center_id
    assert load.planned_load_minutes == Decimal(20060)  # 60 + 2000 × 10
    assert load.available_minutes == Decimal(14400)
    assert load.is_overloaded is True
    assert load.utilization_percent > Decimal(100)


async def test_capacity_load_not_overloaded_under_available(
    db_session: AsyncSession, mrp_setup: MrpSetup
) -> None:
    """A modest load (160 min) is well under the 14400-min available → not overloaded."""
    setup = mrp_setup
    run = await run_mrp(db_session, setup.tenant_id)
    with tenant_context(setup.tenant_id):
        loads = await service.capacity_for_run(db_session, setup.tenant_id, run.id)
    assert len(loads) == 1
    assert loads[0].planned_load_minutes == Decimal(160)  # 60 + 10 × 10
    assert loads[0].is_overloaded is False


# --- conversion ---------------------------------------------------------------


async def test_convert_make_planned_order_creates_production_order(
    db_session: AsyncSession, mrp_setup: MrpSetup
) -> None:
    """Converting a MAKE planned order creates a real production order (docflow planned → order)."""
    setup = mrp_setup
    run = await run_mrp(db_session, setup.tenant_id)
    planned = await planned_by_item(db_session, setup.tenant_id, run.id)
    finished_planned_id = planned[setup.finished_item_id].id

    holder: dict[str, uuid.UUID | None] = {}

    async def work() -> None:
        with tenant_context(setup.tenant_id):
            order = await service.convert_planned_order(
                db_session, setup.tenant_id, finished_planned_id,
                warehouse_id=setup.warehouse_id,
            )
            holder["converted_document_id"] = order.converted_document_id

    with tenant_context(setup.tenant_id):
        await run_in_uow(db_session, work)
        converted = await service.get_planned_order(
            db_session, setup.tenant_id, finished_planned_id
        )
    assert converted.status == PlannedOrderStatus.CONVERTED.value
    assert holder["converted_document_id"] is not None
    with tenant_context(setup.tenant_id):
        order_count = (
            await db_session.execute(
                select(func.count()).select_from(ProductionOrder).where(
                    ProductionOrder.tenant_id == setup.tenant_id,
                    ProductionOrder.item_id == setup.finished_item_id,
                )
            )
        ).scalar_one()
    assert order_count == 1


async def test_convert_buy_planned_order_creates_requisition(
    db_session: AsyncSession, mrp_setup: MrpSetup
) -> None:
    """Converting a BUY planned order publishes the event procurement handles → a DRAFT requisition
    is created in the same transaction (the §5-clean cross-module write)."""
    setup = mrp_setup
    run = await run_mrp(db_session, setup.tenant_id)
    planned = await planned_by_item(db_session, setup.tenant_id, run.id)
    raw1_planned_id = planned[setup.raw1_item_id].id

    async def work() -> None:
        with tenant_context(setup.tenant_id):
            await service.convert_planned_order(db_session, setup.tenant_id, raw1_planned_id)

    with tenant_context(setup.tenant_id):
        await run_in_uow(db_session, work)
        req_count = (
            await db_session.execute(
                select(func.count()).select_from(PurchaseRequisition).where(
                    PurchaseRequisition.tenant_id == setup.tenant_id
                )
            )
        ).scalar_one()
        converted = await service.get_planned_order(db_session, setup.tenant_id, raw1_planned_id)
    assert converted.status == PlannedOrderStatus.CONVERTED.value
    assert req_count == 1


# --- firm / cancel + regeneration --------------------------------------------


async def test_firmed_planned_order_survives_rerun_and_nets_as_supply(
    db_session: AsyncSession, mrp_setup: MrpSetup
) -> None:
    """A FIRMED planned order survives a re-run (regeneration deletes only PLANNED rows) and nets as
    supply so a fresh run does not re-propose its quantity."""
    setup = mrp_setup
    run1 = await run_mrp(db_session, setup.tenant_id)
    planned = await planned_by_item(db_session, setup.tenant_id, run1.id)
    raw1_id = planned[setup.raw1_item_id].id

    async def firm() -> None:
        with tenant_context(setup.tenant_id):
            await service.firm_planned_order(db_session, setup.tenant_id, raw1_id)

    with tenant_context(setup.tenant_id):
        await run_in_uow(db_session, firm)

    run2 = await run_mrp(db_session, setup.tenant_id)
    planned2 = await planned_by_item(db_session, setup.tenant_id, run2.id)
    # The FIRMED raw1 (30) survives + nets as supply → the fresh run raises NO new raw1 planned
    # order (demand 30 - firmed supply 30 = 0).
    assert setup.raw1_item_id not in planned2
    with tenant_context(setup.tenant_id):
        firmed = await service.get_planned_order(db_session, setup.tenant_id, raw1_id)
    assert firmed.status == PlannedOrderStatus.FIRMED.value


async def test_rerun_regenerates_planned_rows(
    db_session: AsyncSession, mrp_setup: MrpSetup
) -> None:
    """A second run deletes the prior PLANNED rows and writes a fresh plan (regeneration policy)."""
    setup = mrp_setup
    run1 = await run_mrp(db_session, setup.tenant_id)
    run2 = await run_mrp(db_session, setup.tenant_id)
    assert run1.id != run2.id
    with tenant_context(setup.tenant_id):
        run1_rows = (
            await db_session.execute(
                select(func.count()).select_from(PlannedOrder).where(
                    PlannedOrder.tenant_id == setup.tenant_id,
                    PlannedOrder.mrp_run_id == run1.id,
                )
            )
        ).scalar_one()
    assert run1_rows == 0


# --- query budget + tenant isolation -----------------------------------------


async def test_run_is_set_based_no_per_item_n_plus_one(
    db_session: AsyncSession, db_engine, mrp_setup: MrpSetup
) -> None:
    """The run's query count is BOUNDED (set-based): it does NOT scale per planned item. A 4-item
    multi-level plan must stay well under a generous ceiling — the gather phase is a bounded number
    of reads and the explosion is in-memory (HEED #53: assert no N+1)."""
    setup = mrp_setup
    counter = QueryCounter(db_engine.sync_engine)

    async def work() -> None:
        with tenant_context(setup.tenant_id):
            await service.run_mrp(db_session, setup.tenant_id, RUN_DATE)

    with tenant_context(setup.tenant_id), counter:
        await run_in_uow(db_session, work)
    # A per-item N+1 would balloon; a bounded set-based run stays modest (far below per-item).
    assert counter.count < 60, "\n".join(counter.statements)


async def test_tenant_isolation_on_runs(
    db_session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """Tenant B cannot see tenant A's run (D-007)."""
    setup_a = await build_mrp_setup(db_session, tenant_a, sales_quantity="10")
    run_a = await run_mrp(db_session, tenant_a)
    assert run_a.tenant_id == setup_a.tenant_id
    with tenant_context(tenant_b):
        rows = (
            await db_session.execute(select(MrpRun).where(MrpRun.id == run_a.id))
        ).scalars().all()
    assert rows == []
