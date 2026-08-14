"""ATLAS NEVER REFUSES SERVICE — the adversarial half of Q4 (PLAN 19 Task 5).

``test_depletion.py`` pins the ONE stock-out Q4 names (an ingredient with no stock anywhere).
This module hunts every OTHER way a depletion problem could reach the guest, because Q4's claim is
not "a missing bin does not block the guest", it is that a *depletion problem* never does — and
restaurant theoretical stock being permanently 2-5% wrong is only the most common cause, not the
only one:

* a component with SOME stock but not enough (``InsufficientStockError`` from ``apply_bin_delta``);
* a component whose item category has no GL accounts wired (``costing.py`` ``_category_accounts``);
* a fire dated into a CLOSED fiscal period (``journal.py`` post-time period check);
* a component that is itself 86'd on the menu;
* a dish whose BOM is DRAFT, not ACTIVE;
* a dish with no BOM at all and no stock of its own.

Every one of those is a hard 422 somewhere in inventory or finance. The assertion in each test is
the same two-part one: the ticket reaches SENT_TO_KITCHEN (and can still be SETTLED), and the
failure is on a FAILED job row.

The second half of the trade is the last two tests: a failure that no one can attribute to a ticket
is not "recorded", it is lost. Q4's concession is bought with VISIBILITY, so what a reader can
actually see through ``GET /api/v1/jobs`` is asserted here too.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.db import build_session_factory
from app.core.events import run_in_uow
from app.core.jobs import Job, JobStatus, schedule_job, wait_for_jobs
from app.core.tenancy import tenant_context
from app.main import register_event_handlers
from app.modules.finance import queries as finance_queries
from app.modules.finance.service import periods as period_service
from app.modules.hospitality.constants import (
    DEPLETE_TICKET_JOB,
    AvailabilityState,
    OrderTicketStatus,
)
from app.modules.hospitality.service import availability, depletion, tickets
from tests.modules.hospitality.factories import build_dish, build_kitchen, build_open_ticket
from tests.modules.inventory.factories import build_item, build_item_category
from tests.modules.manufacturing.factories import build_bom, build_bom_component

pytestmark = pytest.mark.asyncio


@pytest.fixture
def job_factory(db_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """The per-test engine's sessionmaker — what ``get_session_factory`` hands the router."""
    return build_session_factory(db_engine)


async def _fire_and_drain(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    ticket_id: uuid.UUID,
    factory: async_sessionmaker[AsyncSession],
) -> None:
    """The router contract exactly: fire inside one uow, schedule the submitted depletion jobs
    strictly after it commits, then let the runner finish."""
    with tenant_context(tenant_id):
        await run_in_uow(session, lambda: tickets.fire_ticket(session, tenant_id, ticket_id))
    for job_id in depletion.take_depletion_jobs(session):
        schedule_job(job_id, factory)
    await wait_for_jobs()


async def _depletion_jobs(session: AsyncSession, tenant_id: uuid.UUID) -> list[Job]:
    session.expire_all()
    with tenant_context(tenant_id):
        rows = await session.execute(
            select(Job).where(Job.job_type == DEPLETE_TICKET_JOB).order_by(Job.created_at)
        )
        return list(rows.scalars().all())


async def _assert_guest_was_served(
    session: AsyncSession, tenant_id: uuid.UUID, ticket_id: uuid.UUID
) -> list[Job]:
    """The invariant under test everywhere in this module: the kitchen got the ticket, the check
    can still be closed, and whatever went wrong is on a FAILED job and not on the guest."""
    session.expire_all()
    with tenant_context(tenant_id):
        ticket = await tickets.get_ticket(session, tenant_id, ticket_id)
        assert ticket.status == OrderTicketStatus.SENT_TO_KITCHEN.value
        for status in (
            OrderTicketStatus.IN_PREP,
            OrderTicketStatus.READY,
            OrderTicketStatus.SERVED,
        ):
            await run_in_uow(
                session, lambda s=status: tickets.advance_ticket(session, tenant_id, ticket_id, s)
            )
        await run_in_uow(session, lambda: tickets.settle_ticket(session, tenant_id, ticket_id))
        ticket = await tickets.get_ticket(session, tenant_id, ticket_id)
        assert ticket.status == OrderTicketStatus.SETTLED.value, "the guest could not pay"
    return await _depletion_jobs(session, tenant_id)


# --- Depletion problems that must land on the JOB, never on the guest ---------


async def test_a_partial_stock_out_does_not_block_the_guest(
    db_session: AsyncSession,
    tenant_a: uuid.UUID,
    job_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The 2-5% variance case Q4 actually describes: the storeroom SAYS it has beef, just not
    enough. ``issue_bins_for_items`` happily returns the bin (on_hand > 0) so hospitality's own
    out-of-stock guard never fires — the refusal comes from ``apply_bin_delta`` deep in the move,
    which is a different code path from the empty-bin one ``test_depletion.py`` pins."""
    register_event_handlers()
    kitchen = await build_kitchen(
        db_session, tenant_a, {"DISH-STEAK": {"ING-BEEF": Decimal(20)}}, stock=Decimal(5)
    )
    ticket_id = await build_open_ticket(db_session, tenant_a, [(kitchen.dishes["DISH-STEAK"], "1")])

    await _fire_and_drain(db_session, tenant_a, ticket_id, job_factory)

    jobs = await _assert_guest_was_served(db_session, tenant_a, ticket_id)
    assert [job.status for job in jobs] == [JobStatus.FAILED.value]


async def test_an_unwired_gl_category_does_not_block_the_guest(
    db_session: AsyncSession,
    tenant_a: uuid.UUID,
    job_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A brand-new ingredient filed under a category nobody wired accounts to.
    ``_category_accounts`` raises ``inventory.category_accounts_unwired`` when the COGS journal has
    nowhere to land — a BOOKKEEPING gap, not a stock one, and it must never be the reason a guest
    cannot order."""
    register_event_handlers()
    kitchen = await build_kitchen(db_session, tenant_a, {"DISH-SOUP": {"ING-ONION": Decimal(1)}})
    unwired = await build_item_category(
        db_session, tenant_a, code="CAT-NOGL", name="Unwired", with_accounts=False
    )
    truffle = await build_item(
        db_session,
        tenant_a,
        item_code="ING-TRUFFLE",
        category_id=unwired.id,
        base_uom_id=kitchen.setup.base_uom_id,
    )
    # Stock it, so the failure is UNAMBIGUOUSLY the GL wiring and not a missing bin. Seeding a
    # RECEIPT for an unwired category is refused for the same reason, so the quant is written
    # straight into the projection the issue path reads.
    await _seed_quant(db_session, tenant_a, truffle.id, kitchen.setup.bin_a_id, Decimal(10))
    dish_id = await build_dish(
        db_session,
        tenant_a,
        kitchen.setup,
        item_code="DISH-TRUFFLE",
        recipe={truffle.id: Decimal(1)},
    )
    ticket_id = await build_open_ticket(db_session, tenant_a, [(dish_id, "1")])

    await _fire_and_drain(db_session, tenant_a, ticket_id, job_factory)

    jobs = await _assert_guest_was_served(db_session, tenant_a, ticket_id)
    assert [job.status for job in jobs] == [JobStatus.FAILED.value]


async def _seed_quant(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    item_id: uuid.UUID,
    bin_id: uuid.UUID,
    quantity: Decimal,
) -> None:
    """On-hand for an item whose category has NO GL accounts — a RECEIPT would be refused by the
    same guard the test is aiming at, so the maintained projection (D-036) is written directly."""
    from app.modules.inventory.models import StockQuant

    with tenant_context(tenant_id):
        session.add(
            StockQuant(
                tenant_id=tenant_id, item_id=item_id, bin_id=bin_id, on_hand_qty=quantity
            )
        )
        await session.commit()


async def test_a_closed_fiscal_period_does_not_block_the_guest(
    db_session: AsyncSession,
    tenant_a: uuid.UUID,
    job_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Month-end. The accountant closed the period this evening's service falls in, and the COGS
    journal the ISSUE move posts is rejected with ``finance.period_closed``. The kitchen has no
    idea the books closed and the guest is already eating."""
    register_event_handlers()
    kitchen = await build_kitchen(db_session, tenant_a, {"DISH-SOUP": {"ING-ONION": Decimal(1)}})
    ticket_id = await build_open_ticket(db_session, tenant_a, [(kitchen.dishes["DISH-SOUP"], "1")])
    with tenant_context(tenant_a):
        period = await finance_queries.find_period_for_date(db_session, tenant_a, date.today())
        assert period is not None, "the kitchen factory seeds FY2026; today must fall in it"
        await run_in_uow(
            db_session, lambda: period_service.close_period(db_session, tenant_a, period.id)
        )

    await _fire_and_drain(db_session, tenant_a, ticket_id, job_factory)

    jobs = await _assert_guest_was_served(db_session, tenant_a, ticket_id)
    assert [job.status for job in jobs] == [JobStatus.FAILED.value]


async def test_an_86d_ingredient_does_not_block_its_dish(
    db_session: AsyncSession,
    tenant_a: uuid.UUID,
    job_factory: async_sessionmaker[AsyncSession],
) -> None:
    """86-ing is a MENU statement, not a stock one. A cook who 86s the onion has said "stop selling
    onions", not "stop selling every dish that contains one" — the fire check reads the ticket's
    LINE items only, and the depletion must still run."""
    register_event_handlers()
    kitchen = await build_kitchen(db_session, tenant_a, {"DISH-SOUP": {"ING-ONION": Decimal(1)}})
    with tenant_context(tenant_a):
        await run_in_uow(
            db_session,
            lambda: availability.set_availability(
                db_session,
                tenant_a,
                kitchen.ingredients["ING-ONION"],
                state=AvailabilityState.EIGHTY_SIXED,
                reason="out of onions",
            ),
        )
    ticket_id = await build_open_ticket(db_session, tenant_a, [(kitchen.dishes["DISH-SOUP"], "1")])

    await _fire_and_drain(db_session, tenant_a, ticket_id, job_factory)

    jobs = await _assert_guest_was_served(db_session, tenant_a, ticket_id)
    assert [job.status for job in jobs] == [JobStatus.COMPLETED.value], (
        f"an 86'd COMPONENT must not fail the depletion: {[job.error for job in jobs]}"
    )


async def test_a_draft_bom_does_not_block_the_guest(
    db_session: AsyncSession,
    tenant_a: uuid.UUID,
    job_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A chef entered tonight's special's recipe but never activated it. ``active_boms_for_items``
    filters on ACTIVE, so the dish looks recipe-less and depletes ITSELF — a dish item nobody
    stocks. Wrong in the books, but the guest still gets dinner."""
    register_event_handlers()
    kitchen = await build_kitchen(db_session, tenant_a, {"DISH-SOUP": {"ING-ONION": Decimal(1)}})
    special = await build_item(
        db_session,
        tenant_a,
        item_code="DISH-SPECIAL",
        category_id=kitchen.setup.category_id,
        base_uom_id=kitchen.setup.base_uom_id,
    )
    draft = await build_bom(
        db_session, tenant_a, item_id=special.id, uom_id=kitchen.setup.base_uom_id, name="special"
    )
    await build_bom_component(
        db_session,
        tenant_a,
        draft.id,
        component_item_id=kitchen.ingredients["ING-ONION"],
        uom_id=kitchen.setup.base_uom_id,
        quantity_per=Decimal(1),
    )  # deliberately NOT activated
    ticket_id = await build_open_ticket(db_session, tenant_a, [(special.id, "1")])

    await _fire_and_drain(db_session, tenant_a, ticket_id, job_factory)

    jobs = await _assert_guest_was_served(db_session, tenant_a, ticket_id)
    assert [job.status for job in jobs] == [JobStatus.FAILED.value]


async def test_a_dish_with_no_bom_and_no_stock_does_not_block_the_guest(
    db_session: AsyncSession,
    tenant_a: uuid.UUID,
    job_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The bottled beer nobody ever received into the storeroom. ``aggregate_components`` makes a
    recipe-less dish deplete itself, which for an unstocked item is a guaranteed depletion failure
    — and one a property hits on its FIRST order of a newly listed drink."""
    register_event_handlers()
    kitchen = await build_kitchen(db_session, tenant_a, {"BEV-BEER": {}})
    ticket_id = await build_open_ticket(db_session, tenant_a, [(kitchen.dishes["BEV-BEER"], "2")])

    await _fire_and_drain(db_session, tenant_a, ticket_id, job_factory)

    jobs = await _assert_guest_was_served(db_session, tenant_a, ticket_id)
    assert [job.status for job in jobs] == [JobStatus.FAILED.value]


# --- Over the wire: the website is the guest ----------------------------------


async def test_the_website_order_survives_a_phantom_stock_out(
    website_api,  # noqa: ANN001 - the fixture's dataclass, typed in conftest
    db_session: AsyncSession,
) -> None:
    """The guest-facing surface, end to end. PASTA takes 2 TOMATO and the storeroom holds 10, so a
    6-plate web order needs 12 — a stock-out that has to come back 201 with a ticket number, not a
    422 or a 500. This is the exact request Q4 says must never be refused."""
    response = await website_api.client.post(
        "/api/v1/hospitality/orders",
        headers={"Idempotency-Key": "web-phantom-stock-out"},
        json={
            "table_code": "WEB",
            "lines": [{"item_id": str(website_api.kitchen.dishes["PASTA"]), "quantity": "6"}],
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["status"] == OrderTicketStatus.SENT_TO_KITCHEN.value
    await wait_for_jobs()
    jobs = await _depletion_jobs(db_session, website_api.tenant_id)
    assert [job.status for job in jobs] == [JobStatus.FAILED.value]


# --- The other side of the trade: is the failure findable? --------------------


async def test_a_failed_depletion_is_attributable_to_its_ticket(
    db_session: AsyncSession,
    tenant_a: uuid.UUID,
    job_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Q4 buys the guest's dinner with a QUIET failure, and the price is that the failure has to be
    LOUD somewhere. ``core/jobs`` records only ``str(exc)`` — an AtlasError's ``code`` and
    ``details`` are dropped — so a failure raised inside inventory or finance says "The posting date
    is not within an open fiscal period" and names neither the ticket nor the ingredient. Every
    depletion failure must carry its ticket in the recorded error, whichever module raised it."""
    register_event_handlers()
    kitchen = await build_kitchen(
        db_session, tenant_a, {"DISH-STEAK": {"ING-BEEF": Decimal(20)}}, stock=Decimal(5)
    )
    ticket_id = await build_open_ticket(db_session, tenant_a, [(kitchen.dishes["DISH-STEAK"], "1")])

    await _fire_and_drain(db_session, tenant_a, ticket_id, job_factory)

    jobs = await _depletion_jobs(db_session, tenant_a)
    assert [job.status for job in jobs] == [JobStatus.FAILED.value]
    error = jobs[0].error or ""
    assert str(ticket_id) in error, (
        f"a FAILED depletion nobody can trace to a ticket is a LOST failure, not a recorded "
        f"one: {error!r}"
    )
    assert str(kitchen.ingredients["ING-BEEF"]) in error, (
        f"the failure must name the ingredient a human has to go count: {error!r}"
    )


async def test_a_failed_depletion_is_visible_to_the_property_over_http(
    hospitality_api,  # noqa: ANN001 - the fixture's dataclass, typed in conftest
    db_session: AsyncSession,
) -> None:
    """The only surface a restaurant actually has: ``GET /api/v1/jobs?status=FAILED``. STEAK needs
    20 BEEF and the kitchen holds 10, so firing it must return 200 to the terminal and leave a
    FAILED row whose error identifies the check the manager has to go re-count against."""
    client: AsyncClient = hospitality_api.client
    created = await client.post(
        "/api/v1/hospitality/tickets",
        headers={"Idempotency-Key": "steak-check"},
        json={
            "table_code": "12",
            "guest_count": 2,
            "lines": [
                {
                    "item_id": str(hospitality_api.kitchen.dishes["STEAK"]),
                    "quantity": "1",
                    "unit_price": "44.00",
                }
            ],
        },
    )
    assert created.status_code == 201, created.text
    ticket = created.json()

    fired = await client.post(
        f"/api/v1/hospitality/tickets/{ticket['id']}/fire",
        headers={"Idempotency-Key": "steak-fire"},
    )
    assert fired.status_code == 200, fired.text
    await wait_for_jobs()

    listed = await client.get("/api/v1/jobs", params={"status": JobStatus.FAILED.value})
    assert listed.status_code == 200, listed.text
    rows = [row for row in listed.json()["items"] if row["job_type"] == DEPLETE_TICKET_JOB]
    assert len(rows) == 1, "the failure must be findable through the tenant's own job list"
    assert ticket["id"] in (rows[0]["error"] or ""), (
        f"the FAILED job must name the ticket: {rows[0]['error']!r}"
    )
