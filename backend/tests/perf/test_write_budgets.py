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
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import run_in_uow
from app.core.tenancy import tenant_context
from app.main import register_event_handlers
from app.modules.hospitality.constants import AvailabilityState
from app.modules.hospitality.service import availability, tickets
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

# Phase 21's ratchet, pinned BEFORE the feature it bounds (the same reason the two above were):
# the availability burn shipped per-row once and only a flatness assertion caught it.
#
# A booking touches EXACTLY ONE ``hsp_service_slots`` counter row — the Q3 pacing model — so its
# cost must not move with the party size (one row, one integer, whether it is a deuce or a
# sixteen-top) nor with how full the night already is (the other 47 slots are never read). MEASURED
# on this branch at 15 statements for a booking that materialises its slot row: the settings read,
# the locked slot SELECT + its INSERT, the document registry INSERT + read-back, the sequence
# ensure/claim, the reservation INSERT, the registry status UPDATE and the D-010 audit rows.
# Headroom for incidental growth only — a ceiling that grows with the book is a per-reservation
# scan of the night, which is the grid-maintenance trap Q3 warns about.
TABLE_BOOKING_CEILING = 22

# The service window a tenant that has never configured one books inside (constants.DEFAULT_*), and
# the grid step. Spelled here rather than imported so the ratchet keeps measuring the same shape
# even if a default moves — a settings change must not silently re-point what this test books.
_RATCHET_SERVICE_OPEN = time(11, 0)
_RATCHET_SLOT_MINUTES = 15


def _slot_at(service_date: date, index: int) -> datetime:
    """The ``index``-th 15-minute slot of ``service_date``'s service, as the UTC instant the
    booking gate keys on."""
    return datetime.combine(service_date, _RATCHET_SERVICE_OPEN, tzinfo=UTC) + timedelta(
        minutes=_RATCHET_SLOT_MINUTES * index
    )


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


@pytest.mark.skip(reason="Phase 21 Task 3")
async def test_booking_a_table_is_flat_in_party_size_and_book_depth(
    db_session: AsyncSession,
    tenant_a: uuid.UUID,
    query_counter: Callable[[], QueryCounter],
) -> None:
    """A deuce on a dead Tuesday and an eight-top on a night already holding fifty covers cost the
    SAME number of statements.

    Q3's whole argument for pacing-by-slot over pacing-by-table is that availability is ONE counter
    row per (service_date, slot_start): the gate locks that row, reads two integers and writes two
    integers, and never looks at the other slots or at the reservations already in the book. Two
    shapes would break that and neither has a behavioural symptom — a gate that re-counted the
    night's reservations to derive ``covers_booked`` (O(book depth) on the request a guest waits
    on), and a per-cover write of any kind (O(party size)). Asserting EQUALITY rather than only the
    ceiling is what catches them: a ceiling alone is satisfied by a shape that still grows.

    Both measured bookings materialise their own slot row, so the two counts differ in nothing but
    party size and how full the night is. The imports are local because this test is written before
    the module it measures exists (Task 1 pins the ratchet's shape; Task 3 un-skips it).
    """
    from app.modules.hospitality.reservation_schemas import TableReservationCreate

    from app.modules.hospitality.service import reservations

    quiet_night = datetime.now(UTC).date() + timedelta(days=1)
    busy_night = quiet_night + timedelta(days=1)

    async def book(service_date: date, index: int, party_size: int) -> None:
        await reservations.create_reservation(
            db_session,
            tenant_a,
            TableReservationCreate(
                service_date=service_date,
                slot_start=_slot_at(service_date, index),
                party_size=party_size,
                guest_name="Ratchet",
            ),
        )

    with query_counter() as quiet, tenant_context(tenant_a):
        await run_in_uow(db_session, lambda: book(quiet_night, 0, 2))

    # Fifty reservations across the first half of the busy night's grid — two to a slot, so the
    # book is deep without any slot reaching the default party cap. The measured booking then lands
    # on slot 40, which no earlier booking has touched: identical work to the quiet night's.
    for reservation in range(50):
        with tenant_context(tenant_a):
            await run_in_uow(db_session, lambda index=reservation: book(busy_night, index // 2, 2))

    with query_counter() as busy, tenant_context(tenant_a):
        await run_in_uow(db_session, lambda: book(busy_night, 40, 8))

    assert busy.count == quiet.count, (
        f"booking cost {quiet.count} statements for a party of 2 on an empty night and "
        f"{busy.count} for a party of 8 on a night holding 50 reservations — the pacing gate "
        "scales with the party or with the book:\n" + "\n".join(busy.statements)
    )
    assert busy.count <= TABLE_BOOKING_CEILING, (
        f"booking a table now costs {busy.count} statements "
        f"(ceiling {TABLE_BOOKING_CEILING}):\n" + "\n".join(busy.statements)
    )
    print(f"\n[perf] booking a table (party 8, 50 already in the book): {busy.count} statements")
