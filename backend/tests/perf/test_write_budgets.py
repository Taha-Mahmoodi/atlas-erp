"""Write-path statement budgets (Phase 19 ratchet).

PERFORMANCE §2's <=3 rule is a LIST-ENDPOINT rule (tests/conftest.py:149-171) and
tests/perf/test_budgets.py times only read paths, so nothing has ever bounded a WRITE. Q4 of
docs/research/hospitality-industry-plan.md measured one ingredient ISSUE move and the whole
Phase 19 design turns on that number, so it gets a ceiling here before the feature lands.

These are CEILINGS, not targets. A number moving down is good and the ceiling should follow it
down; a number moving up is a regression that must be explained in the PR that causes it.

Deliberately NOT marked ``perf``: the perf marker is for wall-clock budgets, which are excluded
from the blocking CI job (``-m "not pg and not perf"``) because timings are machine-dependent. A
statement count is deterministic, so this ratchet runs in the DEFAULT suite where it can actually
block a regression.
"""

import uuid
from collections.abc import Callable
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import run_in_uow
from app.core.tenancy import tenant_context
from app.main import register_event_handlers
from app.modules.hospitality.constants import AvailabilityState
from app.modules.hospitality.service import availability, depletion, tickets
from app.modules.inventory import service
from app.modules.inventory.constants import MoveType
from app.modules.inventory.schemas import StockMoveCreate
from tests.conftest import QueryCounter
from tests.modules.hospitality.factories import build_kitchen, build_open_ticket
from tests.modules.inventory.factories import build_stock, build_stock_setup

# Measured on this branch at 38 statements, confirming Q4's number exactly. Headroom for
# incidental growth, not for a design that multiplies the count.
STOCK_MOVE_ISSUE_CEILING = 45

# The OTHER half of the same argument: what the guest's request costs once depletion is off it.
# MEASURED at 10 statements for an 8-dish ticket exploding to 12 distinct ingredients — against
# 12 x 38 = 456 if those ingredients were issued inline. Headroom for incidental growth only: any
# ceiling near the per-ingredient cost means depletion has moved back onto the sale.
#
# Two more shapes measured against this same ceiling, both flat in the ticket's size:
#   * every dish carrying a LIMITED countdown costs 12 — the burn's one locked read and its one
#     batched UPDATE, whatever the line count (it was 10 + 2 PER LINE until the burn was batched);
#   * the count rises by ONE per DEPLETE_MAX_COMPONENTS_PER_JOB distinct ingredients, because each
#     chunk is its own job INSERT (12 statements at 120 distinct ingredients). That is the chunking
#     working as designed, and the only axis on this path that is not flat.
FIRED_TICKET_CEILING = 14

# The OTHER end of that trade: what the guest's request handed to the background runner actually
# costs. Nothing in tests/perf/ executed the depletion JOB before, so P0's re-run guard
# (items_already_moved_for_document) landed on an unmeasured path — and the two ceilings above
# could never have moved whatever it cost, because neither runs this code.
#
# MEASURED at 123 statements for a 3-ingredient chunk, i.e. the 38-per-ingredient unit above plus a
# small fixed part. The ceiling is the weaker half of this test; the RATCHET is the assertion that
# the guard's read appears exactly ONCE, because the property P0 claims is "one query per JOB, not
# per move" and a guard that drifted inside the per-ingredient loop would still look linear.
DEPLETION_JOB_CEILING = 140


async def test_single_ingredient_issue_move_stays_within_its_ceiling(
    db_session: AsyncSession,
    tenant_a: uuid.UUID,
    query_counter: Callable[[], QueryCounter],
) -> None:
    """One ISSUE move through the real write path: create_move (validation, docflow, gapless
    number, quant delta, costing) plus the D-011 dispatch of StockValued into the finance COGS
    handler, all inside one uow. That is the unit a fired restaurant ticket multiplies by every
    distinct component, which is why Phase 19 aggregates components and backgrounds depletion
    instead of issuing one move per ticket line inline.
    """
    # The app factory subscribes the inventory->finance COGS handler; the autouse
    # clear_event_subscriptions fixture wipes it, so a service-level test must re-register or it
    # measures a write that never posts its journal (tests/modules/inventory/conftest.py:32-41).
    register_event_handlers()
    setup = await build_stock_setup(db_session, tenant_a)
    await build_stock(db_session, tenant_a, setup.item_id, setup.bin_a_id, Decimal("100"))
    payload = StockMoveCreate(
        move_type=MoveType.ISSUE,
        item_id=setup.item_id,
        quantity=Decimal("1"),
        from_bin_id=setup.bin_a_id,
    )

    async def issue() -> None:
        with tenant_context(tenant_a):
            await service.create_move(db_session, tenant_a, payload)

    with query_counter() as counted, tenant_context(tenant_a):
        await run_in_uow(db_session, issue)

    assert counted.count <= STOCK_MOVE_ISSUE_CEILING, (
        f"one ingredient issue now costs {counted.count} statements "
        f"(ceiling {STOCK_MOVE_ISSUE_CEILING}); a rise here multiplies by every component on "
        "every ticket:\n" + "\n".join(counted.statements)
    )
    print(f"\n[perf] single ingredient ISSUE move: {counted.count} statements")


async def test_firing_a_ticket_stays_within_its_ceiling(
    db_session: AsyncSession,
    tenant_a: uuid.UUID,
    query_counter: Callable[[], QueryCounter],
) -> None:
    """Firing a ticket is the request a guest and a server actually wait on, and Phase 19's whole
    claim is that it stays CHEAP AND FLAT while the expensive part (38 statements per ingredient)
    moves into a background job.

    An 8-dish ticket exploding to 12 distinct ingredients costs 10 statements: the availability
    read, the ticket UPDATE + its audit row, the docflow status, the recipe explosion's three
    reads and the job INSERT. The ceiling sits an order of magnitude under the 456 those same 12
    ingredients would cost issued inline, so it also enforces the flatness claim — a count that
    grows with the ingredient count cannot stay under it. A regression here means depletion has
    crept back onto the sale (Q4), the exact failure this phase exists to prevent, and no
    behavioural test would notice.
    """
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

    async def fire() -> None:
        await tickets.fire_ticket(db_session, tenant_a, ticket_id)

    with query_counter() as counted, tenant_context(tenant_a):
        await run_in_uow(db_session, fire)

    assert counted.count <= FIRED_TICKET_CEILING, (
        f"firing an 8-dish ticket now costs {counted.count} statements "
        f"(ceiling {FIRED_TICKET_CEILING}); if depletion has moved back onto the sale this is "
        "where it shows:\n" + "\n".join(counted.statements)
    )
    print(f"\n[perf] firing an 8-dish / 12-ingredient ticket: {counted.count} statements")


async def test_firing_does_not_scale_with_countdown_lines(
    db_session: AsyncSession,
    tenant_a: uuid.UUID,
    query_counter: Callable[[], QueryCounter],
) -> None:
    """The SAME flatness claim, on the branch the test above never enters: a ticket whose dishes
    all carry a LIMITED countdown.

    ``fire_ticket`` burns a countdown per LINE, and a burn that reads its row one item at a time is
    an N+1 on the path a guest waits on — the shape PERFORMANCE §2 bans, on a WRITE where the
    list-endpoint rule does not reach. Neither schema caps ``lines`` (``OrderTicketCreate``,
    ``WebsiteOrderCreate``), so the multiplier is the caller's, not ours: an 86-board-heavy property
    running specials with counts is exactly the tenant that gets there.

    Asserting EQUALITY between 2 lines and 24, not just the ceiling, is the point — a ceiling alone
    would be satisfied by a shape that still grows one query per line up to it.
    """
    register_event_handlers()
    recipes = {f"DISH-{index:02d}": {"ONION": Decimal(1)} for index in range(24)}
    kitchen = await build_kitchen(db_session, tenant_a, recipes, stock=Decimal(5000))
    codes = sorted(recipes)
    with tenant_context(tenant_a):
        for code in codes:
            await availability.set_availability(
                db_session,
                tenant_a,
                kitchen.dishes[code],
                state=AvailabilityState.LIMITED,
                remaining_qty=Decimal(1000),
            )
        await db_session.commit()

    counts: dict[int, int] = {}
    for line_count in (2, 24):
        ticket_id = await build_open_ticket(
            db_session, tenant_a, [(kitchen.dishes[code], "1") for code in codes[:line_count]]
        )

        async def fire(ticket_id: uuid.UUID = ticket_id) -> None:
            await tickets.fire_ticket(db_session, tenant_a, ticket_id)

        with query_counter() as counted, tenant_context(tenant_a):
            await run_in_uow(db_session, fire)
        counts[line_count] = counted.count
        print(f"\n[perf] firing a {line_count}-line all-countdown ticket: {counted.count}")

    assert counts[24] == counts[2], (
        f"firing cost {counts[2]} statements for 2 countdown lines and {counts[24]} for 24 — the "
        "countdown burn scales with the ticket"
    )
    assert counts[24] <= FIRED_TICKET_CEILING, (
        f"firing a 24-line countdown ticket costs {counts[24]} statements "
        f"(ceiling {FIRED_TICKET_CEILING})"
    )


async def test_the_depletion_job_pays_for_its_rerun_guard_once_per_job(
    db_session: AsyncSession,
    tenant_a: uuid.UUID,
    query_counter: Callable[[], QueryCounter],
) -> None:
    """The depletion JOB, which is where the fired ticket's real cost went and where P0's re-run
    guard actually runs.

    ``issue_ticket_ingredients`` asks ``items_already_moved_for_document`` which items this ticket
    has already issued, so the sweeper can re-dispatch a dead depletion without double-posting
    COGS. That read is deliberately hoisted OUT of the ingredient loop — one query per job, not one
    per move — and that is exactly the kind of property that decays silently: moving it inside the
    loop keeps every behavioural test green and every count still linear, it just multiplies by the
    chunk size (up to ``DEPLETE_MAX_COMPONENTS_PER_JOB``). So the count of guard reads is asserted
    EXACTLY, not the total alone.
    """
    register_event_handlers()
    kitchen = await build_kitchen(
        db_session,
        tenant_a,
        {"BURGER": {"BUN": Decimal(2), "PATTY": Decimal(1), "ONION": Decimal(1)}},
        stock=Decimal(500),
    )
    ticket_id = await build_open_ticket(db_session, tenant_a, [(kitchen.dishes["BURGER"], "1")])
    with tenant_context(tenant_a):
        components = await depletion.aggregate_components(db_session, tenant_a, ticket_id)
    payload = depletion.job_payloads(ticket_id, components, move_date=date(2026, 3, 2))[0]
    assert len(components) == 3, "the guard's cost is only observable over several ingredients"

    async def deplete() -> None:
        await depletion.deplete_ticket_job(db_session, tenant_a, payload)

    with query_counter() as counted, tenant_context(tenant_a):
        await run_in_uow(db_session, deplete)

    # The guard's shape, and only it: the moved-item ids read through the ticket's outgoing doc
    # links. Ordinary per-move link INSERTs and their ORM refreshes also touch core_doc_links, so
    # both halves of the join have to be named.
    guard_reads = [
        sql
        for sql in counted.statements
        if "inv_stock_moves.item_id" in sql and "core_doc_links" in sql
    ]
    assert len(guard_reads) == 1, (
        f"the re-run guard ran {len(guard_reads)} times for a 3-ingredient chunk; it must be one "
        "read per JOB, not one per move:\n" + "\n".join(guard_reads)
    )
    assert counted.count <= DEPLETION_JOB_CEILING, (
        f"depleting a 3-ingredient chunk now costs {counted.count} statements "
        f"(ceiling {DEPLETION_JOB_CEILING}):\n" + "\n".join(counted.statements)
    )
    print(f"\n[perf] depletion job, 3 ingredients: {counted.count} statements")
