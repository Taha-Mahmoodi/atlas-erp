"""Ingredient depletion (PLAN 19 Task 5, spec Q4): aggregated, backgrounded, fired at send-to-
kitchen.

Q4 measured the obvious implementation and it fails three ways, so all three are pinned here:

1. **``MAX_DISPATCHES_PER_UOW = 50`` counts handler INVOCATIONS** (``core/events.py``), so a
   56-line ticket — an 8-top ordering 8 dishes at 7 ingredients — raises ``EventCycleError`` →
   HTTP 500 *while the guest waits to pay*. Aggregating components across ticket lines collapses
   that to ~12 distinct items, and backgrounding moves even those out of the request. The job
   itself runs inside ``run_in_uow`` too, so the cap applies there as well and the aggregate is
   chunked at a MEASURED ceiling rather than trusted to stay small.
2. **A phantom stock-out must never refuse service.** Restaurant theoretical stock is known to be
   2-5% wrong by the industry's own benchmark, and D-011 rolls a whole uow back on
   ``InsufficientStockError``. The ticket therefore fires and the FAILED job carries the problem.
3. **The job row commits with the fire**, so a D-013 replay returns the same job rather than
   depleting twice.

Everything runs through the REAL services inside a uow (D-025/D-011) and through the REAL job
runner, so the transaction boundary under test is the production one.
"""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.db import build_session_factory
from app.core.events import MAX_DISPATCHES_PER_UOW, run_in_uow
from app.core.jobs import Job, JobStatus, schedule_job, wait_for_jobs
from app.core.tenancy import tenant_context
from app.main import register_event_handlers
from app.modules.hospitality.constants import (
    DEPLETE_MAX_COMPONENTS_PER_JOB,
    DEPLETE_TICKET_JOB,
    OrderTicketStatus,
)
from app.modules.hospitality.service import depletion, tickets
from app.modules.inventory import queries as inventory_queries
from tests.modules.hospitality.factories import build_kitchen, build_open_ticket


@pytest.fixture
def job_factory(db_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """The factory the job runner gets — the per-test engine's sessionmaker, mirroring what the
    ``get_session_factory`` dependency hands a router (tests/core/test_jobs.py precedent)."""
    return build_session_factory(db_engine)


async def _fire(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    ticket_id: uuid.UUID,
    *,
    factory: async_sessionmaker[AsyncSession] | None = None,
) -> None:
    """Fire inside one uow, then schedule + drain the depletion jobs it submitted — exactly the
    router contract Task 6/7 implement (submit inside the uow, schedule strictly after commit)."""
    with tenant_context(tenant_id):
        await run_in_uow(session, lambda: tickets.fire_ticket(session, tenant_id, ticket_id))
    if factory is not None:
        for job_id in depletion.take_depletion_jobs(session):
            schedule_job(job_id, factory)
        await wait_for_jobs()


async def _jobs(session: AsyncSession, tenant_id: uuid.UUID) -> list[Job]:
    session.expire_all()
    with tenant_context(tenant_id):
        rows = await session.execute(
            select(Job).where(Job.job_type == DEPLETE_TICKET_JOB).order_by(Job.created_at)
        )
        return list(rows.scalars().all())


# --- Aggregation --------------------------------------------------------------


async def test_components_are_aggregated_across_lines(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """Q4: without this a 4-dish check is ~24 issue lines; with it, ~12 distinct items. Four dishes
    sharing an onion must produce ONE onion demand, not four."""
    register_event_handlers()
    kitchen = await build_kitchen(
        db_session,
        tenant_a,
        {
            "DISH-SOUP": {"ING-ONION": Decimal(1), "ING-STOCK": Decimal(2)},
            "DISH-STEW": {"ING-ONION": Decimal(1), "ING-BEEF": Decimal(3)},
        },
    )
    ticket_id = await build_open_ticket(
        db_session,
        tenant_a,
        [(kitchen.dishes["DISH-SOUP"], "3"), (kitchen.dishes["DISH-STEW"], "1")],
    )

    with tenant_context(tenant_a):
        components = await depletion.aggregate_components(db_session, tenant_a, ticket_id)

    by_item = {component.item_id: component.quantity for component in components}
    assert len(components) == 3, "shared ingredients must collapse to one component each"
    assert by_item[kitchen.ingredients["ING-ONION"]] == Decimal(4)  # 3 soups + 1 stew
    assert by_item[kitchen.ingredients["ING-STOCK"]] == Decimal(6)
    assert by_item[kitchen.ingredients["ING-BEEF"]] == Decimal(3)


async def test_a_dish_with_no_recipe_depletes_itself(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """A bottled beer is a sellable inventory item with no recipe. Treating "no BOM" as "nothing to
    deplete" would make its stock never move — silently wrong, and Q4's whole concession rests on
    depletion failures being VISIBLE rather than silent."""
    register_event_handlers()
    kitchen = await build_kitchen(db_session, tenant_a, {"BEV-BEER": {}})
    ticket_id = await build_open_ticket(db_session, tenant_a, [(kitchen.dishes["BEV-BEER"], "2")])

    with tenant_context(tenant_a):
        components = await depletion.aggregate_components(db_session, tenant_a, ticket_id)

    assert [(c.item_id, c.quantity) for c in components] == [
        (kitchen.dishes["BEV-BEER"], Decimal(2))
    ]


# --- The depletion itself -----------------------------------------------------


async def test_firing_depletes_the_aggregated_ingredients_off_request(
    db_session: AsyncSession,
    tenant_a: uuid.UUID,
    job_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The whole path: fire submits a job, the runner issues ONE move per distinct component at the
    aggregated quantity, and on-hand falls. Stock is untouched inside the fire's transaction."""
    register_event_handlers()
    kitchen = await build_kitchen(
        db_session,
        tenant_a,
        {
            "DISH-SOUP": {"ING-ONION": Decimal(1), "ING-STOCK": Decimal(2)},
            "DISH-STEW": {"ING-ONION": Decimal(1)},
        },
        stock=Decimal(100),
    )
    ticket_id = await build_open_ticket(
        db_session,
        tenant_a,
        [(kitchen.dishes["DISH-SOUP"], "3"), (kitchen.dishes["DISH-STEW"], "1")],
    )

    with tenant_context(tenant_a):
        await run_in_uow(db_session, lambda: tickets.fire_ticket(db_session, tenant_a, ticket_id))
        # Depletion is NOT in the sale's transaction (Q4), so nothing has moved yet.
        assert await inventory_queries.total_on_hand(
            db_session, tenant_a, kitchen.ingredients["ING-ONION"]
        ) == Decimal(100)

    for job_id in depletion.take_depletion_jobs(db_session):
        schedule_job(job_id, job_factory)
    await wait_for_jobs()

    jobs = await _jobs(db_session, tenant_a)
    assert [job.status for job in jobs] == [JobStatus.COMPLETED.value]
    assert jobs[0].result["component_count"] == 2
    with tenant_context(tenant_a):
        assert await inventory_queries.total_on_hand(
            db_session, tenant_a, kitchen.ingredients["ING-ONION"]
        ) == Decimal(96)
        assert await inventory_queries.total_on_hand(
            db_session, tenant_a, kitchen.ingredients["ING-STOCK"]
        ) == Decimal(94)


async def test_a_large_ticket_does_not_hit_the_dispatch_ceiling(
    db_session: AsyncSession,
    tenant_a: uuid.UUID,
    job_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Q4's wall: an 8-top ordering 8 dishes at 7 ingredients is 56 raw issue lines, and
    MAX_DISPATCHES_PER_UOW=50 counts handler invocations, so the un-aggregated version is an HTTP
    500 at the table. Aggregation collapses it under the cap and backgrounding takes it off the
    request — the fire must not raise and the depletion must COMPLETE."""
    register_event_handlers()
    pool = [f"ING-{index:02d}" for index in range(12)]
    recipes = {
        f"DISH-{dish:02d}": {pool[(dish + offset) % len(pool)]: Decimal(1) for offset in range(7)}
        for dish in range(8)
    }
    kitchen = await build_kitchen(db_session, tenant_a, recipes, stock=Decimal(500))
    ticket_id = await build_open_ticket(
        db_session, tenant_a, [(kitchen.dishes[code], "1") for code in recipes]
    )

    await _fire(db_session, tenant_a, ticket_id, factory=job_factory)

    jobs = await _jobs(db_session, tenant_a)
    assert [job.status for job in jobs] == [JobStatus.COMPLETED.value], (
        f"the depletion failed: {[job.error for job in jobs]}"
    )
    assert jobs[0].result["component_count"] == len(pool)
    assert len(pool) < MAX_DISPATCHES_PER_UOW, "aggregation must stay under the D-011 cap"


async def test_a_missing_ingredient_does_not_block_the_guest(
    db_session: AsyncSession,
    tenant_a: uuid.UUID,
    job_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Restaurant theoretical stock is 2-5% wrong by the industry's own benchmark, so a phantom
    stock-out must never refuse service. The ticket fires and reaches the kitchen; the FAILED job
    row is where the problem is recorded (Q4's traded concession, Task 8's DECISIONS entry)."""
    register_event_handlers()
    kitchen = await build_kitchen(
        db_session,
        tenant_a,
        {"DISH-SALAD": {"ING-FETA": Decimal(1)}},
        unstocked=frozenset({"ING-FETA"}),
    )
    ticket_id = await build_open_ticket(db_session, tenant_a, [(kitchen.dishes["DISH-SALAD"], "1")])

    await _fire(db_session, tenant_a, ticket_id, factory=job_factory)

    db_session.expire_all()
    with tenant_context(tenant_a):
        ticket = await tickets.get_ticket(db_session, tenant_a, ticket_id)
        assert ticket.status == OrderTicketStatus.SENT_TO_KITCHEN.value
    jobs = await _jobs(db_session, tenant_a)
    assert [job.status for job in jobs] == [JobStatus.FAILED.value]
    assert str(kitchen.ingredients["ING-FETA"]) in (jobs[0].error or "")


async def test_depletion_job_is_submitted_in_the_same_uow_as_the_fire(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """D-013 rests on this: the PENDING row and the fire commit together, so a replayed request
    returns the SAME job id instead of depleting twice. If the fire's transaction rolls back, no
    job row may survive it."""
    register_event_handlers()
    kitchen = await build_kitchen(db_session, tenant_a, {"DISH-SOUP": {"ING-ONION": Decimal(1)}})
    ticket_id = await build_open_ticket(db_session, tenant_a, [(kitchen.dishes["DISH-SOUP"], "1")])

    async def fire_then_fail() -> None:
        await tickets.fire_ticket(db_session, tenant_a, ticket_id)
        raise RuntimeError("the request died after the fire")

    with tenant_context(tenant_a), pytest.raises(RuntimeError):
        await run_in_uow(db_session, fire_then_fail)
    assert await _jobs(db_session, tenant_a) == []

    await _fire(db_session, tenant_a, ticket_id)
    assert len(await _jobs(db_session, tenant_a)) == 1


async def test_a_ticket_beyond_the_component_ceiling_splits_into_several_jobs(
    db_session: AsyncSession,
    tenant_a: uuid.UUID,
    job_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The residual risk the plan names: an extreme ticket could approach MAX_DISPATCHES_PER_UOW
    even after aggregation, and backgrounding alone does NOT fix it — the job runs inside
    ``run_in_uow`` too, so the cap applies there as well (measured: 49 components COMPLETE, 50
    FAIL with EventCycleError). Chunking at ``DEPLETE_MAX_COMPONENTS_PER_JOB`` puts the wall out
    of reach, and a FULL-WIDTH chunk must actually run — if a future handler adds a second
    dispatch per move, this is what catches it."""
    register_event_handlers()
    count = DEPLETE_MAX_COMPONENTS_PER_JOB + 3
    codes = [f"ING-{index:03d}" for index in range(count)]
    kitchen = await build_kitchen(
        db_session, tenant_a, {"DISH-BANQUET": {code: Decimal(1) for code in codes}}
    )
    ticket_id = await build_open_ticket(
        db_session, tenant_a, [(kitchen.dishes["DISH-BANQUET"], "1")]
    )

    await _fire(db_session, tenant_a, ticket_id, factory=job_factory)

    jobs = await _jobs(db_session, tenant_a)
    assert len(jobs) == 2
    assert sum(job.result["component_count"] for job in jobs) == count
    assert max(job.result["component_count"] for job in jobs) == DEPLETE_MAX_COMPONENTS_PER_JOB
    assert [job.status for job in jobs] == [JobStatus.COMPLETED.value] * 2, (
        f"a full-width chunk must complete: {[job.error for job in jobs]}"
    )
