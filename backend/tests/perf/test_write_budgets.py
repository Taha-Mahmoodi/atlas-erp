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

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import run_in_uow
from app.core.tenancy import tenant_context
from app.main import register_event_handlers
from app.modules.finance.receivables_schemas import (
    CustomerInvoiceCreate,
    CustomerInvoiceLineCreate,
    CustomerReceiptCreate,
    ReceiptAllocationCreate,
)
from app.modules.finance.service import customer_invoices, customer_receipts
from app.modules.hospitality.constants import AvailabilityState
from app.modules.hospitality.reservation_schemas import TableReservationCreate
from app.modules.hospitality.rooms_schemas import (
    RatePlanCreate,
    RoomCreate,
    RoomReservationCreate,
    RoomTypeCreate,
)
from app.modules.hospitality.service import (
    availability,
    depletion,
    rate_plans,
    reservations,
    room_reservations,
    rooms,
    tickets,
)
from app.modules.inventory import service
from app.modules.inventory.constants import MoveType
from app.modules.inventory.schemas import StockMoveCreate
from tests.conftest import QueryCounter
from tests.modules.finance.factories import build_ar_setup
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

# Phase 21's ratchet, pinned BEFORE the feature it bounds (the same reason the two above were):
# the availability burn shipped per-row once and only a flatness assertion caught it.
#
# A booking touches EXACTLY ONE ``hsp_service_slots`` counter row — the Q3 pacing model — so its
# cost must not move with the party size (one row, one integer, whether it is a deuce or a
# sixteen-top) nor with how full the night already is (the other 47 slots are never read). MEASURED
# on this branch at 12 statements for a booking that materialises its slot row: the settings read,
# the locked slot SELECT + its INSERT + the counter UPDATE, the document registry INSERT +
# read-back, the sequence read and claim, the reservation INSERT, its D-010 audit row and the
# registry status UPDATE. Headroom for incidental growth only — a ceiling that grows with the book
# means a per-reservation scan of the night, the grid-maintenance trap Q3 warns about.
#
# The very FIRST booking in a tenant costs 2 more (``ensure_sequence`` bootstrapping the RSV- row),
# which is a one-time cost per tenant and identical on ``create_ticket``; the test warms it so the
# two measurements differ in nothing but party size and book depth.
TABLE_BOOKING_CEILING = 16

# Phase 20 Task 1's ratchet on the SHIPPED AR money path, pinned before Task 2 (PLAN 20.4) widens
# the receipt. See the test's docstring for what the measured number is made of.
AR_ROUND_TRIP_CEILING = 85

# PLAN 20.2's ratchet, and the shape it pins is FLATNESS-EXCEPT-FOR-NIGHTS.
#
# Confirming a stay is the one write in this phase whose cost is legitimately linear: one
# ``hsp_room_type_inventory`` row per night slept, locked and updated. Everything else — the
# document read, the transition check, the status write and its registry mirror — is fixed. So the
# ratchet asserts the DIFFERENCE between a 14-night and a 3-night confirmation is exactly eleven
# nights' worth, which is what catches the two shapes that have no behavioural symptom: a gate that
# re-counted the property's rooms per night (``_sellable_rooms`` inside the loop rather than
# memoised across it) and a per-night document or reservation read. A ceiling alone is satisfied by
# a shape that still grows the wrong way — the Phase 19 lesson from ``test_firing_does_not_scale``.
#
# MEASURED on this branch: a 3-night confirmation costs 12 statements — the reservation load, the
# room COUNT that seeds a new night's supply (ONE per call, not one per night), three locked
# SELECT + INSERT pairs, the counter UPDATE, the status write, and the registry read + UPDATE — and
# each further night costs exactly 2 more (its locked SELECT and its INSERT; the UPDATEs batch).
# 14 nights therefore costs 34. Both measurements run after the tenant's RMR- sequence exists, so
# they differ in nothing but the number of nights.
ROOM_BOOKING_CEILING = 16
ROOM_BOOKING_PER_NIGHT = 2

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

    Both measured bookings materialise their own slot row and both run after the tenant's RSV-
    sequence exists, so the two counts differ in nothing but party size and how full the night is.
    """
    warm_up_night = datetime.now(UTC).date() + timedelta(days=1)
    quiet_night = warm_up_night + timedelta(days=1)
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

    # The tenant's RSV- sequence row is created by its FIRST booking (``ensure_sequence``), a
    # one-time 2-statement cost that would otherwise land on the quiet measurement alone and read
    # as the busy night being cheaper.
    with tenant_context(tenant_a):
        await run_in_uow(db_session, lambda: book(warm_up_night, 0, 2))

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


async def test_an_invoice_to_cleared_receipt_round_trip_stays_within_its_ceiling(
    db_session: AsyncSession,
    tenant_a: uuid.UUID,
    query_counter: Callable[[], QueryCounter],
) -> None:
    """The order-to-cash money path end to end: create + post one customer invoice, then clear it
    in full with a customer receipt.

    Pinned BEFORE Phase 20 Task 2 (PLAN 20.4) widens ``CustomerReceipt`` into an unapplied/
    on-account receipt, because that task rewrites the receipt's validation spine and its journal
    build on a SHIPPED, seeded path. Its own tests will prove the new behaviour; nothing would
    prove the ALLOCATED path still costs what it costs, and an extra per-allocation read or a
    re-read of the invoice's control line is invisible to every behavioural test.

    MEASURED on this branch at 75 statements for a one-line, tax-free invoice cleared by a
    single-allocation receipt: the two documents' registry INSERTs and read-backs, both gapless
    sequences bootstrapped and claimed (INV- and RCT- — a one-time-per-tenant cost this round trip
    deliberately includes, since the seed pays it once per tenant too), the two journal entries
    with their lines and posting reads, the invoice INSERT + audit row, the receipt's frozen-rate
    read of the AR control line (D-019), the allocation INSERT, the open-amount UPDATE and the
    three docflow links. Headroom for incidental growth only.

    Nothing subscribes to ``CustomerInvoicePosted`` or ``CustomerReceiptPosted`` today, so this is
    the cost of the write itself. The real registry is installed anyway (the sibling ISSUE ratchet's
    house rule: the autouse ``clear_event_subscriptions`` empties the bus, so a service-level test
    that does not re-register measures a write with ZERO handlers FOREVER, and a Phase 20
    folio/deposit handler on ``CustomerReceiptPosted`` would land outside this ceiling instead of
    inside it, which is where it should be argued for).
    """
    register_event_handlers()
    setup = await build_ar_setup(db_session, tenant_a)
    partner_id = uuid.uuid4()
    holder: dict[str, uuid.UUID] = {}

    async def bill() -> None:
        invoice = await customer_invoices.create_customer_invoice(
            db_session,
            tenant_a,
            CustomerInvoiceCreate(
                partner_id=partner_id,
                partner_name="Globex Inc",
                invoice_date=date(2026, 3, 1),
                due_date=date(2026, 3, 31),
                currency_code="USD",
                ar_account_id=setup.accounts["1200"],
                description="Consulting services",
                lines=[
                    CustomerInvoiceLineCreate(
                        account_id=setup.accounts["4000"], net_amount=Decimal("100.00")
                    )
                ],
            ),
        )
        await customer_invoices.post_customer_invoice(db_session, tenant_a, invoice.id)
        holder["invoice_id"] = invoice.id

    async def receive() -> None:
        await customer_receipts.create_and_post_receipt(
            db_session,
            tenant_a,
            CustomerReceiptCreate(
                partner_id=partner_id,
                partner_name="Globex Inc",
                receipt_date=date(2026, 3, 15),
                currency_code="USD",
                bank_account_id=setup.accounts["1000"],
                amount=Decimal("100.00"),
                allocations=[
                    ReceiptAllocationCreate(
                        invoice_id=holder["invoice_id"], amount=Decimal("100.00")
                    )
                ],
            ),
        )

    with query_counter() as counted, tenant_context(tenant_a):
        await run_in_uow(db_session, bill)
        await run_in_uow(db_session, receive)

    assert counted.count <= AR_ROUND_TRIP_CEILING, (
        f"one invoice -> receipt -> cleared round trip now costs {counted.count} statements "
        f"(ceiling {AR_ROUND_TRIP_CEILING}); this is the shipped AR money path Phase 20 Task 2 "
        "rewrites:\n" + "\n".join(counted.statements)
    )
    print(f"\n[perf] invoice -> receipt -> cleared round trip: {counted.count} statements")


async def test_confirming_a_stay_costs_the_same_plus_exactly_its_nights(
    db_session: AsyncSession,
    tenant_a: uuid.UUID,
    query_counter: Callable[[], QueryCounter],
) -> None:
    """A 3-night booking and a 14-night booking differ by EXACTLY eleven nights of counter rows.

    Q3's argument for a per-date counter over an interval lock is that a stay's cost is one row per
    night and nothing else: the gate locks those rows, reads three integers each and writes one, and
    never looks at the property's other room types, at its other nights, or at the bookings already
    in the book. Two shapes would break that and NEITHER has a behavioural symptom — a gate that
    re-counted ``hsp_rooms`` per night to seed ``rooms_sellable`` (O(nights) COUNTs on the request a
    guest waits on), and a per-night reservation or document read. Asserting the DIFFERENCE rather
    than only the ceiling is what catches them: a ceiling alone is satisfied by a shape that still
    grows the wrong way.

    Both bookings are created and committed first, so only the CONFIRM — the counter touch — is
    measured, and both run after the tenant's RMR- sequence exists.
    """
    register_event_handlers()
    with tenant_context(tenant_a):
        room_type = await rooms.create_room_type(
            db_session, tenant_a, RoomTypeCreate(code="DBL", name="Double", base_capacity=2)
        )
        plan = await rate_plans.create_rate_plan(
            db_session,
            tenant_a,
            RatePlanCreate(
                code="BAR",
                name="Best available",
                room_type_id=room_type.id,
                nightly_amount=Decimal("120.00"),
                currency_code="USD",
                valid_from=date(2020, 1, 1),
            ),
        )
        for index in range(4):
            await rooms.create_room(
                db_session,
                tenant_a,
                RoomCreate(room_number=f"4{index:02d}", room_type_id=room_type.id),
            )
        await db_session.commit()

    taken: dict[str, uuid.UUID] = {}

    async def take(arrival: date, nights: int) -> uuid.UUID:
        async def work() -> None:
            booking = await room_reservations.create_room_reservation(
                db_session,
                tenant_a,
                RoomReservationCreate(
                    room_type_id=room_type.id,
                    rate_plan_id=plan.id,
                    arrival_date=arrival,
                    departure_date=arrival + timedelta(days=nights),
                    party_size=2,
                    guest_name="Ratchet",
                ),
            )
            taken["id"] = booking.id

        with tenant_context(tenant_a):
            await run_in_uow(db_session, work)
            await db_session.commit()
            return taken["id"]

    async def confirm(booking_id: uuid.UUID) -> None:
        with tenant_context(tenant_a):
            await run_in_uow(
                db_session,
                lambda: room_reservations.confirm_room_reservation(
                    db_session, tenant_a, booking_id
                ),
            )
            await db_session.commit()

    base = datetime.now(UTC).date() + timedelta(days=1)
    # The tenant's RMR- sequence row is created by its FIRST booking (``ensure_sequence``), a
    # one-time cost that would otherwise land on whichever measurement ran first.
    await confirm(await take(base, 1))

    short_id = await take(base + timedelta(days=10), 3)
    long_id = await take(base + timedelta(days=40), 14)
    with query_counter() as short, tenant_context(tenant_a):
        await confirm(short_id)
    with query_counter() as long, tenant_context(tenant_a):
        await confirm(long_id)

    assert long.count - short.count == 11 * ROOM_BOOKING_PER_NIGHT, (
        f"a 3-night confirmation cost {short.count} statements and a 14-night one {long.count} — "
        f"the difference is not the {ROOM_BOOKING_PER_NIGHT} statements a night should cost, so "
        "the gate scales on some other axis:\n" + "\n".join(long.statements)
    )
    assert short.count <= ROOM_BOOKING_CEILING, (
        f"confirming a 3-night stay now costs {short.count} statements "
        f"(ceiling {ROOM_BOOKING_CEILING}):\n" + "\n".join(short.statements)
    )
    print(
        f"\n[perf] confirming a stay: {short.count} statements for 3 nights, "
        f"{long.count} for 14"
    )
