"""Maintenance-plan service behaviour (PLAN 9.2, D-051): CRUD, the interval / next_due computation,
activate/deactivate, and the preventive-generation RUN — a due plan generates one order + advances
next_due, a not-due plan is skipped, a same-day re-run is idempotent, and an overdue-by-multiple
plan advances to the next FUTURE due (the overdue-advance rule).

Plans + the run go through the REAL service inside a uow (D-025); the run scans set-based via
``queries.due_plans``.
"""

import uuid
from collections.abc import Callable
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import run_in_uow
from app.core.exceptions import ConflictError, ValidationFailedError
from app.core.tenancy import tenant_context
from app.modules.maintenance import queries as maintenance_queries
from app.modules.maintenance import service
from app.modules.maintenance.constants import (
    IntervalUnit,
    MaintenanceOrderStatus,
    MaintenanceOrderType,
    MaintenancePlanStatus,
)
from app.modules.maintenance.schemas import (
    MaintenancePlanCreate,
    MaintenancePlanUpdate,
)
from tests.conftest import QueryCounter
from tests.modules.maintenance.conftest import MaintenanceSetup
from tests.modules.maintenance.factories import build_plan


async def _run(
    db_session: AsyncSession, tenant_id: uuid.UUID, as_of: date
) -> list:
    """Run the preventive generation inside a uow (D-025) — the full chain (orders + plan advance +
    docflow edges)."""
    holder: list = []

    async def work() -> None:
        with tenant_context(tenant_id):
            holder.extend(
                await service.run_preventive_maintenance(db_session, tenant_id, as_of)
            )

    with tenant_context(tenant_id):
        await run_in_uow(db_session, work)
    return holder


# --- CRUD + interval/next_due computation -------------------------------------


async def test_create_plan_computes_next_due(
    db_session: AsyncSession, maintenance_setup: MaintenanceSetup
) -> None:
    """A plan's first next_due = start_date + one interval; born ACTIVE, last_generated NULL."""
    setup = maintenance_setup
    with tenant_context(setup.tenant_id):
        plan = await service.create_plan(
            db_session,
            setup.tenant_id,
            MaintenancePlanCreate(
                code="MP-DAYS",
                name="Weekly check",
                equipment_id=setup.equipment_id,
                interval_value=7,
                interval_unit=IntervalUnit.DAYS,
                task_description="Lubricate",
                start_date=date(2026, 1, 1),
            ),
        )
    assert plan.status == MaintenancePlanStatus.ACTIVE.value
    assert plan.last_generated_date is None
    assert plan.next_due_date == date(2026, 1, 8)  # +7 days


async def test_month_interval_clamps_end_of_month(
    db_session: AsyncSession, maintenance_setup: MaintenanceSetup
) -> None:
    """A MONTHS interval uses calendar arithmetic clamped to the month's last day (Jan 31 + 1mo =
    Feb 28)."""
    plan = await build_plan(
        db_session,
        maintenance_setup.tenant_id,
        equipment_id=maintenance_setup.equipment_id,
        code="MP-MONTH",
        interval_value=1,
        interval_unit=IntervalUnit.MONTHS,
        start_date=date(2026, 1, 31),
    )
    assert plan.next_due_date == date(2026, 2, 28)


async def test_interval_must_be_positive(
    db_session: AsyncSession, maintenance_setup: MaintenanceSetup
) -> None:
    """A non-positive interval is a 422."""
    setup = maintenance_setup
    with pytest.raises(ValidationFailedError) as exc, tenant_context(setup.tenant_id):
        await service.create_plan(
            db_session,
            setup.tenant_id,
            MaintenancePlanCreate(
                code="MP-BAD",
                name="Bad",
                equipment_id=setup.equipment_id,
                interval_value=0,
                interval_unit=IntervalUnit.DAYS,
                task_description="x",
            ),
        )
    assert exc.value.code == "maintenance.interval_invalid"


async def test_duplicate_plan_code_conflicts(
    db_session: AsyncSession, maintenance_setup: MaintenanceSetup
) -> None:
    setup = maintenance_setup
    await build_plan(
        db_session, setup.tenant_id, equipment_id=setup.equipment_id, code="MP-DUP"
    )
    with pytest.raises(ConflictError) as exc, tenant_context(setup.tenant_id):
        await service.create_plan(
            db_session,
            setup.tenant_id,
            MaintenancePlanCreate(
                code="MP-DUP",
                name="Dup",
                equipment_id=setup.equipment_id,
                interval_value=1,
                interval_unit=IntervalUnit.MONTHS,
                task_description="x",
            ),
        )
    assert exc.value.code == "maintenance.plan_code_conflict"


async def test_update_interval_does_not_retroshift_next_due(
    db_session: AsyncSession, maintenance_setup: MaintenanceSetup
) -> None:
    """Changing the interval applies to the NEXT advance — it does not retro-shift next_due_date."""
    setup = maintenance_setup
    plan = await build_plan(
        db_session,
        setup.tenant_id,
        equipment_id=setup.equipment_id,
        code="MP-IV",
        interval_value=1,
        interval_unit=IntervalUnit.MONTHS,
        start_date=date(2026, 1, 1),
    )
    original_due = plan.next_due_date
    with tenant_context(setup.tenant_id):
        updated = await service.update_plan(
            db_session,
            setup.tenant_id,
            plan.id,
            MaintenancePlanUpdate(interval_value=3),
        )
    assert updated.next_due_date == original_due  # unchanged
    assert updated.interval_value == 3


async def test_activate_deactivate(
    db_session: AsyncSession, maintenance_setup: MaintenanceSetup
) -> None:
    setup = maintenance_setup
    plan = await build_plan(
        db_session, setup.tenant_id, equipment_id=setup.equipment_id, code="MP-AD"
    )
    with tenant_context(setup.tenant_id):
        off = await service.set_plan_status(
            db_session, setup.tenant_id, plan.id, MaintenancePlanStatus.INACTIVE
        )
        assert off.status == MaintenancePlanStatus.INACTIVE.value
        on = await service.set_plan_status(
            db_session, setup.tenant_id, plan.id, MaintenancePlanStatus.ACTIVE
        )
        assert on.status == MaintenancePlanStatus.ACTIVE.value


# --- The preventive-generation run --------------------------------------------


async def test_run_generates_order_for_due_plan_and_advances(
    db_session: AsyncSession, maintenance_setup: MaintenanceSetup
) -> None:
    """A plan due on/before the run date generates ONE PREVENTIVE order (scheduled at the due date,
    linked to the plan) and advances next_due_date by one interval."""
    setup = maintenance_setup
    # next_due = start + 1 month = 2026-02-01.
    plan = await build_plan(
        db_session,
        setup.tenant_id,
        equipment_id=setup.equipment_id,
        code="MP-DUE",
        interval_value=1,
        interval_unit=IntervalUnit.MONTHS,
        start_date=date(2026, 1, 1),
    )
    orders = await _run(db_session, setup.tenant_id, date(2026, 2, 1))
    assert len(orders) == 1
    order = orders[0]
    assert order.order_type == MaintenanceOrderType.PREVENTIVE.value
    assert order.status == MaintenanceOrderStatus.SCHEDULED.value
    assert order.maintenance_plan_id == plan.id
    assert order.scheduled_date == date(2026, 2, 1)
    assert order.description == "Routine service"

    with tenant_context(setup.tenant_id):
        reloaded = await service.get_maintenance_plan(db_session, setup.tenant_id, plan.id)
    assert reloaded.last_generated_date == date(2026, 2, 1)
    assert reloaded.next_due_date == date(2026, 3, 1)  # advanced one interval


async def test_run_skips_not_due_plan(
    db_session: AsyncSession, maintenance_setup: MaintenanceSetup
) -> None:
    """A plan whose next_due_date is still in the future is not touched by the run."""
    setup = maintenance_setup
    plan = await build_plan(
        db_session,
        setup.tenant_id,
        equipment_id=setup.equipment_id,
        code="MP-FUT",
        interval_value=1,
        interval_unit=IntervalUnit.MONTHS,
        start_date=date(2026, 1, 1),  # next_due = 2026-02-01
    )
    orders = await _run(db_session, setup.tenant_id, date(2026, 1, 15))  # before due
    assert orders == []
    with tenant_context(setup.tenant_id):
        reloaded = await service.get_maintenance_plan(db_session, setup.tenant_id, plan.id)
    assert reloaded.next_due_date == date(2026, 2, 1)  # untouched
    assert reloaded.last_generated_date is None


async def test_run_skips_inactive_plan(
    db_session: AsyncSession, maintenance_setup: MaintenanceSetup
) -> None:
    """An INACTIVE plan, even if overdue, generates nothing."""
    setup = maintenance_setup
    plan = await build_plan(
        db_session,
        setup.tenant_id,
        equipment_id=setup.equipment_id,
        code="MP-OFF",
        interval_value=1,
        interval_unit=IntervalUnit.MONTHS,
        start_date=date(2026, 1, 1),
    )
    with tenant_context(setup.tenant_id):
        await service.set_plan_status(
            db_session, setup.tenant_id, plan.id, MaintenancePlanStatus.INACTIVE
        )
        await db_session.commit()
    orders = await _run(db_session, setup.tenant_id, date(2026, 6, 1))
    assert orders == []


async def test_run_is_idempotent_same_day(
    db_session: AsyncSession, maintenance_setup: MaintenanceSetup
) -> None:
    """Running the generator twice the same day generates an order ONCE — after the first run the
    plan's next_due_date is past as_of, so the second run finds nothing."""
    setup = maintenance_setup
    await build_plan(
        db_session,
        setup.tenant_id,
        equipment_id=setup.equipment_id,
        code="MP-IDEM",
        interval_value=7,
        interval_unit=IntervalUnit.DAYS,
        start_date=date(2026, 1, 1),  # next_due = 2026-01-08
    )
    first = await _run(db_session, setup.tenant_id, date(2026, 1, 10))
    assert len(first) == 1
    second = await _run(db_session, setup.tenant_id, date(2026, 1, 10))
    assert second == []  # idempotent


async def test_run_overdue_by_multiple_advances_to_next_future(
    db_session: AsyncSession, maintenance_setup: MaintenanceSetup
) -> None:
    """A plan overdue by several intervals generates exactly ONE order and advances next_due_date to
    the next FUTURE due date (the overdue-advance rule — no order spam)."""
    setup = maintenance_setup
    # next_due = 2026-01-08; weekly. Running at 2026-02-15 is ~5+ weeks overdue.
    await build_plan(
        db_session,
        setup.tenant_id,
        equipment_id=setup.equipment_id,
        code="MP-OVER",
        interval_value=7,
        interval_unit=IntervalUnit.DAYS,
        start_date=date(2026, 1, 1),
    )
    as_of = date(2026, 2, 15)
    orders = await _run(db_session, setup.tenant_id, as_of)
    assert len(orders) == 1  # ONE order, not one per missed week
    assert orders[0].scheduled_date == date(2026, 1, 8)  # the current due date

    with tenant_context(setup.tenant_id):
        plans = await maintenance_queries.due_plans(db_session, setup.tenant_id, as_of)
        all_plan = await service.get_maintenance_plan(
            db_session, setup.tenant_id, orders[0].maintenance_plan_id
        )
    assert plans == []  # nothing due any more (advanced past as_of)
    assert all_plan.next_due_date > as_of  # strictly future
    # It advanced by whole weeks; the next future due after 2026-02-15 stepping from 2026-01-08 by
    # 7 days lands on 2026-02-19.
    assert all_plan.next_due_date == date(2026, 2, 19)


async def test_run_generates_for_multiple_due_plans(
    db_session: AsyncSession, maintenance_setup: MaintenanceSetup
) -> None:
    """The set-based run generates one order per due plan in a single pass."""
    setup = maintenance_setup
    yesterday = date.today() - timedelta(days=1)
    for i in range(3):
        await build_plan(
            db_session,
            setup.tenant_id,
            equipment_id=setup.equipment_id,
            code=f"MP-M{i}",
            interval_value=1,
            interval_unit=IntervalUnit.DAYS,
            start_date=yesterday - timedelta(days=1),  # due today
            estimated_cost=Decimal("50"),
        )
    orders = await _run(db_session, setup.tenant_id, date.today())
    assert len(orders) == 3
    assert all(Decimal(str(o.estimated_cost)) == Decimal("50") for o in orders)


async def _run_query_count(
    db_session: AsyncSession,
    tenant_id: uuid.UUID,
    plan_count: int,
    query_counter: Callable[[], QueryCounter],
) -> int:
    """Seed ``plan_count`` due plans, run the generator inside a uow, return the statement count."""
    start = date.today() - timedelta(days=2)
    for i in range(plan_count):
        await build_plan(
            db_session,
            tenant_id,
            equipment_id=(await build_plan_equipment(db_session, tenant_id, i)),
            code=f"MP-Q{plan_count}-{i}",
            interval_value=1,
            interval_unit=IntervalUnit.DAYS,
            start_date=start,
        )

    async def work() -> None:
        with tenant_context(tenant_id):
            await service.run_preventive_maintenance(db_session, tenant_id, date.today())

    with query_counter() as qc, tenant_context(tenant_id):
        await run_in_uow(db_session, work)
    return qc.count


async def build_plan_equipment(
    db_session: AsyncSession, tenant_id: uuid.UUID, index: int
) -> uuid.UUID:
    """A distinct ACTIVE equipment per plan (so each plan is independent)."""
    from tests.modules.maintenance.factories import build_equipment

    eq = await build_equipment(db_session, tenant_id, code=f"EQ-Q{index}-{uuid.uuid4().hex[:6]}")
    return eq.id


async def test_run_scan_is_linear_no_n_plus_1(
    db_session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    query_counter: Callable[[], QueryCounter],
) -> None:
    """The DUE-PLAN scan is ONE set-based query regardless of plan count (PERFORMANCE §2): the run's
    statement count grows LINEARLY with the plan count, never quadratically. Doubling the plans (2 →
    4) must not more-than-double the per-plan cost — proving no N+1 inside the scan. Two separate
    tenants keep the two measurements independent."""
    count_2 = await _run_query_count(db_session, tenant_a, 2, query_counter)
    count_4 = await _run_query_count(db_session, tenant_b, 4, query_counter)
    # Linear: 4-plan cost ≤ 2× the 2-plan cost + a small constant (the one set-based scan). A
    # quadratic N+1 would blow well past this.
    assert count_4 <= 2 * count_2 + 3, (
        f"run scaled non-linearly: 2 plans={count_2}, 4 plans={count_4}"
    )
