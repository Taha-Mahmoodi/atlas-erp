"""Adversarial: can a real ticket shape still breach ``MAX_DISPATCHES_PER_UOW`` (core/events.py)?

``test_depletion.py`` shows the happy path stays under the cap. This file attacks it. It MEASURES
the dispatch count instead of trusting the arithmetic in
``constants.DEPLETE_MAX_COMPONENTS_PER_JOB`` ("one ISSUE move costs exactly ONE dispatch ... 49
components COMPLETE and 50 FAIL"), and drives the shapes that could get past aggregation: dishes
sharing NO ingredients, a NESTED BOM, a ticket edited and re-fired, several tickets in ONE uow.

``_dispatch_probe`` counts what ``_drain_and_dispatch`` invokes, not moves or jobs, because the cap
is spent on HANDLER INVOCATIONS: a future second subscriber on ``StockValued`` — or a first one on
``JournalEntryPosted``, which the COGS handler publishes into an empty registry today — doubles the
real cost without changing one component count, and these tests fail the moment it does.
"""

import uuid
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core import events as events_module
from app.core.db import build_session_factory
from app.core.events import MAX_DISPATCHES_PER_UOW, run_in_uow
from app.core.exceptions import ConflictError
from app.core.jobs import Job, JobStatus, schedule_job, wait_for_jobs
from app.core.tenancy import tenant_context
from app.main import register_event_handlers
from app.modules.hospitality.constants import DEPLETE_MAX_COMPONENTS_PER_JOB, DEPLETE_TICKET_JOB
from app.modules.hospitality.schemas import OrderTicketLineCreate
from app.modules.hospitality.service import depletion, tickets
from tests.modules.hospitality.factories import build_dish, build_kitchen, build_open_ticket
from tests.modules.inventory.factories import build_item, build_stock


@pytest.fixture
def job_factory(db_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """The session factory the job runner gets (tests/core/test_jobs.py precedent)."""
    return build_session_factory(db_engine)


@contextmanager
def _dispatch_probe(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    """One entry per handler invocation the bus makes — so ``len()`` IS the dispatch count the
    D-011 cap is spent on, and ``Counter`` says which event key spent it. Wraps
    ``events.handlers_for``, called once per drained event, AFTER ``register_event_handlers`` so
    bootstrap's ``not in handlers_for(...)`` guards never count."""
    dispatched: list[str] = []
    real = events_module.handlers_for

    def counting(event_key: str) -> tuple:
        handlers = real(event_key)
        dispatched.extend([event_key] * len(handlers))
        return handlers

    monkeypatch.setattr(events_module, "handlers_for", counting)
    yield dispatched


async def _fire(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    ticket_id: uuid.UUID,
    *,
    factory: async_sessionmaker[AsyncSession] | None = None,
) -> None:
    """The router contract: fire in one uow, then schedule the jobs strictly after it commits."""
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


# --- What one component actually costs ----------------------------------------


async def test_a_full_width_chunk_costs_one_dispatch_per_component_plus_one(
    db_session: AsyncSession,
    tenant_a: uuid.UUID,
    job_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The measurement ``DEPLETE_MAX_COMPONENTS_PER_JOB`` is derived from, re-measured here.

    A job at the FULL chunk width is the worst uow this phase can produce, because the fire's own
    uow costs one dispatch whatever the ticket looks like and every wider aggregate is split. Its
    cost must be exactly ``1 + components``: one ``TicketIngredientsConsumed`` -> the inventory
    handler, then one ``StockValued`` -> the finance COGS handler per ISSUE move.
    """
    register_event_handlers()
    codes = [f"ING-{index:03d}" for index in range(DEPLETE_MAX_COMPONENTS_PER_JOB)]
    kitchen = await build_kitchen(
        db_session, tenant_a, {"DISH-WIDE": {code: Decimal(1) for code in codes}}
    )
    ticket_id = await build_open_ticket(db_session, tenant_a, [(kitchen.dishes["DISH-WIDE"], "1")])

    with _dispatch_probe(monkeypatch) as probe:
        with tenant_context(tenant_a):
            await run_in_uow(
                db_session, lambda: tickets.fire_ticket(db_session, tenant_a, ticket_id)
            )
        fire_cost = len(probe)
        probe.clear()
        for job_id in depletion.take_depletion_jobs(db_session):
            schedule_job(job_id, job_factory)
        await wait_for_jobs()
        job_cost = len(probe)

    jobs = await _jobs(db_session, tenant_a)
    assert [job.status for job in jobs] == [JobStatus.COMPLETED.value], (
        f"a full-width chunk must complete: {[job.error for job in jobs]}"
    )
    assert fire_cost == 1, f"the fire's uow must cost one dispatch, measured {fire_cost}"
    assert job_cost == DEPLETE_MAX_COMPONENTS_PER_JOB + 1, (
        f"expected 1 + {DEPLETE_MAX_COMPONENTS_PER_JOB} dispatches, measured {job_cost}: "
        f"{Counter(probe)}"
    )
    assert job_cost < MAX_DISPATCHES_PER_UOW, (
        f"the worst uow this phase produces is {job_cost} of {MAX_DISPATCHES_PER_UOW} dispatches"
    )


async def test_the_chunk_width_is_what_keeps_the_cap_out_of_reach(
    db_session: AsyncSession,
    tenant_a: uuid.UUID,
    job_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prove the wall is REAL and that 40 is a measured margin, not decoration: widen the chunk to
    ``MAX_DISPATCHES_PER_UOW`` components and the very same ticket FAILS with
    ``events.cycle_detected``. If a later change made a component cost two dispatches, the shipped
    width of 40 would land exactly here — which is what the test above is guarding.
    """
    register_event_handlers()
    monkeypatch.setattr(
        depletion, "DEPLETE_MAX_COMPONENTS_PER_JOB", MAX_DISPATCHES_PER_UOW, raising=True
    )
    codes = [f"ING-{index:03d}" for index in range(MAX_DISPATCHES_PER_UOW)]
    kitchen = await build_kitchen(
        db_session, tenant_a, {"DISH-OVER": {code: Decimal(1) for code in codes}}
    )
    ticket_id = await build_open_ticket(db_session, tenant_a, [(kitchen.dishes["DISH-OVER"], "1")])

    await _fire(db_session, tenant_a, ticket_id, factory=job_factory)

    jobs = await _jobs(db_session, tenant_a)
    assert [job.status for job in jobs] == [JobStatus.FAILED.value]
    assert "events.cycle_detected" in (jobs[0].error or "") or "cap of" in (jobs[0].error or ""), (
        f"expected the D-011 cap, got {jobs[0].error}"
    )


# --- The shapes aggregation cannot help -----------------------------------------


async def test_eight_dishes_sharing_no_ingredients_split_instead_of_breaching(
    db_session: AsyncSession,
    tenant_a: uuid.UUID,
    job_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Q4's 8-top with the sharing removed: 8 dishes x 7 ingredients, DISJOINT, so aggregation
    collapses nothing and the raw 56 lines survive intact — six past the cap. Every job's uow must
    still measure under it, and the guest's fire must not raise."""
    register_event_handlers()
    recipes = {
        f"DISH-{dish:02d}": {f"ING-{dish:02d}-{slot}": Decimal(1) for slot in range(7)}
        for dish in range(8)
    }
    kitchen = await build_kitchen(db_session, tenant_a, recipes, stock=Decimal(500))
    ticket_id = await build_open_ticket(
        db_session, tenant_a, [(kitchen.dishes[code], "1") for code in recipes]
    )

    with tenant_context(tenant_a):
        components = await depletion.aggregate_components(db_session, tenant_a, ticket_id)
    assert len(components) == 56, "disjoint recipes must NOT collapse"
    assert len(components) > MAX_DISPATCHES_PER_UOW, "the un-chunked shape would breach the cap"

    with _dispatch_probe(monkeypatch) as probe:
        with tenant_context(tenant_a):
            await run_in_uow(
                db_session, lambda: tickets.fire_ticket(db_session, tenant_a, ticket_id)
            )
        worst = 0
        for job_id in depletion.take_depletion_jobs(db_session):
            probe.clear()
            schedule_job(job_id, job_factory)
            await wait_for_jobs()
            worst = max(worst, len(probe))

    jobs = await _jobs(db_session, tenant_a)
    assert [job.status for job in jobs] == [JobStatus.COMPLETED.value] * 2, (
        f"the depletion failed: {[job.error for job in jobs]}"
    )
    assert sum(job.result["component_count"] for job in jobs) == 56
    assert worst == DEPLETE_MAX_COMPONENTS_PER_JOB + 1, f"worst job uow measured {worst}"
    assert worst < MAX_DISPATCHES_PER_UOW


async def test_a_nested_bom_does_not_explode_past_the_chunk_the_submitter_counted(
    db_session: AsyncSession,
    tenant_a: uuid.UUID,
    job_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A sub-recipe is a stock item, not a second explosion level.

    The chunker counts the components ``aggregate_components`` returned; if the explosion were
    recursive, a sauce with 30 components inside a dish with 30 would issue 60 moves against a
    payload sized for 30. Single-level (matching ``create_production_order``) is what makes the
    chunk width a real bound — so pin it: the SAUCE item itself is issued, its own components are
    not, and the job's move count equals the payload's component count.
    """
    register_event_handlers()
    sub_codes = [f"ING-SUB-{index:02d}" for index in range(30)]
    kitchen = await build_kitchen(
        db_session,
        tenant_a,
        {"SAUCE": {code: Decimal(1) for code in sub_codes}},
        stock=Decimal(500),
    )
    top_codes = [f"ING-TOP-{index:02d}" for index in range(9)]
    tops: dict[str, uuid.UUID] = {}
    for code in top_codes:
        item = await build_item(
            db_session,
            tenant_a,
            item_code=code,
            category_id=kitchen.setup.category_id,
            base_uom_id=kitchen.setup.base_uom_id,
            name=code,
        )
        tops[code] = item.id
        await build_stock(db_session, tenant_a, item.id, kitchen.setup.bin_a_id, Decimal(500))
    # The prepped sauce is on the shelf: its own production order made it, which is exactly why the
    # explosion stops here rather than reaching through to the sauce's own components.
    await build_stock(
        db_session, tenant_a, kitchen.dishes["SAUCE"], kitchen.setup.bin_a_id, Decimal(500)
    )
    # SAUCE is a component of PLATE *and* a dish with its own ACTIVE BOM.
    plate_id = await build_dish(
        db_session,
        tenant_a,
        kitchen.setup,
        item_code="PLATE",
        recipe={kitchen.dishes["SAUCE"]: Decimal(2), **{tops[c]: Decimal(1) for c in top_codes}},
    )
    ticket_id = await build_open_ticket(db_session, tenant_a, [(plate_id, "1")])

    with tenant_context(tenant_a):
        components = await depletion.aggregate_components(db_session, tenant_a, ticket_id)
    by_item = {component.item_id: component.quantity for component in components}
    assert len(components) == 10, "the explosion must stop at one level"
    assert by_item[kitchen.dishes["SAUCE"]] == Decimal(2), "the sub-recipe issues as a stock item"
    assert kitchen.ingredients[sub_codes[0]] not in by_item

    await _fire(db_session, tenant_a, ticket_id, factory=job_factory)
    jobs = await _jobs(db_session, tenant_a)
    assert [job.status for job in jobs] == [JobStatus.COMPLETED.value], (
        f"the depletion failed: {[job.error for job in jobs]}"
    )
    assert jobs[0].result["component_count"] == 10


# --- Re-firing and multi-ticket units of work -----------------------------------


async def test_an_edited_ticket_cannot_be_re_fired_into_a_second_depletion(
    db_session: AsyncSession,
    tenant_a: uuid.UUID,
    job_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A second fire would submit a second depletion — doubling both the stock issue and the
    dispatch cost of the ticket. The lifecycle must refuse it, and a late line must be refused
    before it can widen an already-fired aggregate."""
    register_event_handlers()
    kitchen = await build_kitchen(
        db_session, tenant_a, {"DISH-SOUP": {"ING-ONION": Decimal(1)}}, stock=Decimal(100)
    )
    ticket_id = await build_open_ticket(db_session, tenant_a, [(kitchen.dishes["DISH-SOUP"], "1")])

    await _fire(db_session, tenant_a, ticket_id, factory=job_factory)
    assert len(await _jobs(db_session, tenant_a)) == 1

    with tenant_context(tenant_a), pytest.raises(ConflictError) as refire:
        await run_in_uow(db_session, lambda: tickets.fire_ticket(db_session, tenant_a, ticket_id))
    assert refire.value.code == "hospitality.ticket_transition_invalid"

    with tenant_context(tenant_a), pytest.raises(ConflictError) as late_line:
        await run_in_uow(
            db_session,
            lambda: tickets.add_lines(
                db_session,
                tenant_a,
                ticket_id,
                [
                    OrderTicketLineCreate(
                        item_id=kitchen.dishes["DISH-SOUP"],
                        quantity=Decimal(1),
                        unit_price=Decimal("9.00"),
                    )
                ],
            ),
        )
    assert late_line.value.code == "hospitality.ticket_not_open"
    assert len(await _jobs(db_session, tenant_a)) == 1, "a refused re-fire submits no second job"


async def test_firing_several_tickets_in_one_uow_costs_one_dispatch_each(
    db_session: AsyncSession, tenant_a: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The one shape whose dispatch cost scales with something a caller chooses.

    Explosion and issue both live in the JOB, so a fire costs exactly one dispatch however large the
    ticket — so a request may fire ``MAX_DISPATCHES_PER_UOW`` tickets before the cap bites. No
    endpoint fires more than one, so the bound is not reachable over the wire today; this pins the
    per-fire cost at one so a future kitchen-batch endpoint inherits a 50-ticket ceiling rather than
    a 50/n one.
    """
    register_event_handlers()
    kitchen = await build_kitchen(
        db_session,
        tenant_a,
        {"DISH-A": {f"ING-{index:02d}": Decimal(1) for index in range(12)}},
        stock=Decimal(500),
    )
    ticket_ids = [
        await build_open_ticket(db_session, tenant_a, [(kitchen.dishes["DISH-A"], "2")])
        for _ in range(3)
    ]

    async def fire_all() -> None:
        for ticket_id in ticket_ids:
            await tickets.fire_ticket(db_session, tenant_a, ticket_id)

    with _dispatch_probe(monkeypatch) as probe, tenant_context(tenant_a):
        await run_in_uow(db_session, fire_all)

    assert len(probe) == len(ticket_ids), f"a fire must cost one dispatch: {Counter(probe)}"
    assert len(depletion.take_depletion_jobs(db_session)) == len(ticket_ids)


# --- The collapse Q4 actually claims --------------------------------------------


async def test_a_four_dish_check_sharing_a_mirepoix_collapses_twenty_four_lines_to_twelve(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """Q4's own number: four dishes at six ingredients is 24 raw issue lines, and sharing
    onion/oil/salt/garlic must take it to ~12 distinct items. Asserted on the REAL explosion so the
    claim in the depletion module docstring cannot drift from what the code does."""
    register_event_handlers()
    shared = ["ING-ONION", "ING-OIL", "ING-SALT", "ING-GARLIC"]
    recipes = {
        f"DISH-{index}": {
            **{code: Decimal(1) for code in shared},
            f"ING-OWN-{index}A": Decimal(1),
            f"ING-OWN-{index}B": Decimal(2),
        }
        for index in range(4)
    }
    raw_lines = sum(len(recipe) for recipe in recipes.values())
    assert raw_lines == 24
    kitchen = await build_kitchen(db_session, tenant_a, recipes, stock=Decimal(200))
    ticket_id = await build_open_ticket(
        db_session, tenant_a, [(kitchen.dishes[code], "1") for code in recipes]
    )

    with tenant_context(tenant_a):
        components = await depletion.aggregate_components(db_session, tenant_a, ticket_id)

    by_item = {component.item_id: component.quantity for component in components}
    assert len(components) == 12, f"24 raw lines must collapse to 12, got {len(components)}"
    assert by_item[kitchen.ingredients["ING-ONION"]] == Decimal(4), "one demand, 4 dishes"
    assert by_item[kitchen.ingredients["ING-OWN-0B"]] == Decimal(2)

    # And the line count itself buys nothing: no schema caps ``lines``, but the aggregate is keyed
    # by ITEM, so 200 more covers of the same four dishes is still 12 components and still one job.
    banquet_id = await build_open_ticket(
        db_session, tenant_a, [(kitchen.dishes[code], "50") for code in recipes] * 50
    )
    with tenant_context(tenant_a):
        wide = await depletion.aggregate_components(db_session, tenant_a, banquet_id)
    assert len(wide) == 12, "an unbounded line count cannot widen the aggregate past the menu"
    assert len(depletion.job_payloads(banquet_id, wide, move_date=date(2026, 8, 14))) == 1
