"""The booking gate and the room-reservation document (PLAN 20.2, spec Q3).

The transition/counter matrix is the point of this file. Every row of it is a NAMED test, because
the rules are not derivable from each other and three of them are the exact opposite of the
restaurant's rules one file over:

    confirm     takes one room-night per night of the stay, or refuses
    cancel      gives every night back, whenever it happens
    no-show     gives NOTHING back — the difference from the restaurant, and D-087
    date change decrements the old nights and increments the new in ONE transaction
    OUT_OF_ORDER lowers rooms_sellable on the future nights, and coming back raises it

``test_a_hotel_no_show_keeps_the_night_while_the_restaurant_gives_covers_back`` drives BOTH modules
in one test on purpose: the two rules look like an inconsistency, and the cheapest "cleanup"
somebody could make later is to unify them. That test is what fails when they do.

The row lock is NOT what these tests exercise — ``with_for_update`` is a no-op on SQLite (D-003), so
the mechanism is pinned in ``test_room_booking_races.py`` under ``-m pg``. What is pinned here is
engine-independent: the arithmetic, the refusals and the transition table.
"""

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import CheckConstraint, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import run_in_uow
from app.core.exceptions import ConflictError, ValidationFailedError
from app.core.models import utcnow
from app.core.tenancy import tenant_context
from app.modules.hospitality.constants import (
    HOSPITALITY_ROOM_RESERVATION_BOOK,
    HOSPITALITY_ROOM_RESERVATION_READ,
    HousekeepingStatus,
    ReservationStatus,
    RoomReservationStatus,
)
from app.modules.hospitality.models import RoomReservation, RoomTypeInventory
from app.modules.hospitality.reservation_schemas import TableReservationCreate
from app.modules.hospitality.rooms_schemas import (
    RatePlanCreate,
    RoomCreate,
    RoomReservationAmend,
    RoomReservationCreate,
    RoomTypeCreate,
    RoomUpdate,
)
from app.modules.hospitality.service import (
    allotment,
    rate_plans,
    reservations,
    room_reservations,
    room_stays,
    rooms,
)
from tests.modules.hospitality.conftest import RoomsApi

BOOKINGS_URL = "/api/v1/hospitality/room-reservations"
WEBSITE_BOOKINGS_URL = "/api/v1/hospitality/website/room-reservations"

RoomsApiFactory = Callable[..., Awaitable[RoomsApi]]


@pytest.fixture
def arrival() -> date:
    """A stay that starts tomorrow, so ``adjust_sellable``'s "future nights only" rule can be
    exercised without today's date being the boundary under test."""
    return utcnow().date() + timedelta(days=1)


class Property:
    """One room type, its rate plan, and N physical rooms — the smallest thing that can be booked.

    Ids, not ORM objects: these tests commit repeatedly and an expired instance fails on attribute
    access (the ``make_dish`` argument in conftest).
    """

    def __init__(self, room_type_id: uuid.UUID, rate_plan_id: uuid.UUID, room_ids: list[uuid.UUID]):
        self.room_type_id = room_type_id
        self.rate_plan_id = rate_plan_id
        self.room_ids = room_ids


async def build_property(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    rooms_count: int = 2,
    capacity: int = 2,
    code: str = "DBL",
    floor: str = "10",
) -> Property:
    """Seed a room type, a rate plan that prices it, and ``rooms_count`` rooms, through the REAL
    services under the tenant context (D-025), so tenancy stamping and audit fire as in production.

    ``code``/``floor`` exist so a test can build a SECOND sellable type in the same property — what
    a room moving between types needs, since both counters have to be materialised to be watched.
    Room numbers are unique per tenant, so the two types cannot share a floor prefix.
    """
    with tenant_context(tenant_id):
        room_type = await rooms.create_room_type(
            session, tenant_id, RoomTypeCreate(code=code, name=code, base_capacity=capacity)
        )
        plan = await rate_plans.create_rate_plan(
            session,
            tenant_id,
            RatePlanCreate(
                code=f"BAR-{code}",
                name="Best available",
                room_type_id=room_type.id,
                nightly_amount=Decimal("120.00"),
                currency_code="USD",
                valid_from=date(2020, 1, 1),
            ),
        )
        room_ids = [
            (
                await rooms.create_room(
                    session,
                    tenant_id,
                    RoomCreate(room_number=f"{floor}{index}", room_type_id=room_type.id),
                )
            ).id
            for index in range(rooms_count)
        ]
        await session.commit()
        return Property(room_type.id, plan.id, room_ids)


async def book(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    prop: Property,
    arrival_date: date,
    nights: int,
    *,
    party_size: int = 2,
    guest_name: str = "Okonjo",
) -> uuid.UUID:
    """Take one TENTATIVE booking and return its id."""
    with tenant_context(tenant_id):
        reservation = await room_reservations.create_room_reservation(
            session,
            tenant_id,
            RoomReservationCreate(
                room_type_id=prop.room_type_id,
                rate_plan_id=prop.rate_plan_id,
                arrival_date=arrival_date,
                departure_date=arrival_date + timedelta(days=nights),
                party_size=party_size,
                guest_name=guest_name,
            ),
        )
        await session.commit()
        return reservation.id


async def counters(
    session: AsyncSession, tenant_id: uuid.UUID, room_type_id: uuid.UUID
) -> dict[date, tuple[int, int, int]]:
    """Every materialised night for a room type as
    ``{stay_date: (rooms_sold, rooms_sellable, overbooking_limit)}``."""
    session.expire_all()
    with tenant_context(tenant_id):
        rows = (
            await session.execute(
                select(RoomTypeInventory).where(RoomTypeInventory.room_type_id == room_type_id)
            )
        ).scalars()
        return {
            row.stay_date: (row.rooms_sold, row.rooms_sellable, row.overbooking_limit)
            for row in rows
        }


async def move(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    reservation_id: uuid.UUID,
    action: Callable[..., Awaitable[Any]],
    *args: Any,
) -> Any:
    """Run one transition in its own uow, the way the router does."""
    with tenant_context(tenant_id):
        result = await run_in_uow(
            session, lambda: action(session, tenant_id, reservation_id, *args)
        )
        await session.commit()
        return result


# --- The counter arithmetic, transition by transition -------------------------


async def test_confirming_a_stay_takes_one_room_night_per_night(
    db_session: AsyncSession, tenant_a: uuid.UUID, arrival: date
) -> None:
    """A three-night stay takes exactly three room-nights, one per night slept, and the DEPARTURE
    date is not one of them.

    The half-open range is the whole of back-to-back availability: a guest leaving on the 5th and
    another arriving on the 5th buy different nights of the same room. Selling the departure night
    would make a two-room property refuse its second guest for no reason at all.
    """
    prop = await build_property(db_session, tenant_a, rooms_count=2)
    reservation_id = await book(db_session, tenant_a, prop, arrival, 3)

    await move(db_session, tenant_a, reservation_id, room_reservations.confirm_room_reservation)

    rows = await counters(db_session, tenant_a, prop.room_type_id)
    assert sorted(rows) == [arrival + timedelta(days=n) for n in range(3)]
    assert all(sold == 1 and sellable == 2 for sold, sellable, _ in rows.values()), rows
    assert arrival + timedelta(days=3) not in rows


async def test_a_tentative_booking_holds_no_room_night(
    db_session: AsyncSession, tenant_a: uuid.UUID, arrival: date
) -> None:
    """Taking the booking materialises NOTHING. A hotel enquiry is not a sale, so a property that
    took ten unconfirmed website requests for its last room has still sold zero — the counter is
    only touched by ``/confirm``. (The restaurant is the other way round: passing the pacing gate IS
    the confirmation, D-077.)"""
    prop = await build_property(db_session, tenant_a)
    await book(db_session, tenant_a, prop, arrival, 2)
    assert await counters(db_session, tenant_a, prop.room_type_id) == {}


async def test_cancelling_a_confirmed_stay_gives_every_night_back(
    db_session: AsyncSession, tenant_a: uuid.UUID, arrival: date
) -> None:
    """A cancel returns all N nights, so the room is back on sale within the second.

    Unlike the restaurant there is no "too late" cut-off: a room-night cancelled at any point before
    it is slept is genuinely resellable, and the row stays materialised at zero rather than being
    deleted, so the night's ``rooms_sellable`` snapshot survives.
    """
    prop = await build_property(db_session, tenant_a, rooms_count=1)
    reservation_id = await book(db_session, tenant_a, prop, arrival, 2)
    await move(db_session, tenant_a, reservation_id, room_reservations.confirm_room_reservation)

    await move(db_session, tenant_a, reservation_id, room_reservations.cancel_room_reservation)

    rows = await counters(db_session, tenant_a, prop.room_type_id)
    assert [sold for sold, _, _ in rows.values()] == [0, 0], rows


async def test_cancelling_a_tentative_booking_releases_nothing(
    db_session: AsyncSession, tenant_a: uuid.UUID, arrival: date
) -> None:
    """A booking that never took a night cannot give one back. Releasing unconditionally would push
    ``rooms_sold`` below what confirmed guests hold — a phantom room the property would then sell
    twice, and the CHECK would not catch it because a decrement is legal on its own."""
    prop = await build_property(db_session, tenant_a, rooms_count=1)
    held = await book(db_session, tenant_a, prop, arrival, 1, guest_name="Holder")
    await move(db_session, tenant_a, held, room_reservations.confirm_room_reservation)
    enquiry = await book(db_session, tenant_a, prop, arrival, 1, guest_name="Enquiry")

    await move(db_session, tenant_a, enquiry, room_reservations.cancel_room_reservation)

    assert await counters(db_session, tenant_a, prop.room_type_id) == {arrival: (1, 1, 0)}


async def test_a_hotel_no_show_keeps_the_night_while_the_restaurant_gives_covers_back(
    db_session: AsyncSession, tenant_a: uuid.UUID, arrival: date
) -> None:
    """THE RULE THAT MUST NOT BE UNIFIED (D-087). Both modules are driven here on purpose.

    A hotel no-show keeps its room-night: the room stood empty and unsellable all night, so there is
    nothing to resell, and the property's protection against that loss is the ``overbooking_limit``
    it sold into in advance — releasing here would spend that buffer twice. A restaurant no-show
    recorded BEFORE the slot releases its covers, because the table can still be turned.

    Written as one test rather than two so the asymmetry is visible in a single failure. Anybody who
    "cleans up" the inconsistency by making the two agree breaks this, whichever way they go.
    """
    prop = await build_property(db_session, tenant_a, rooms_count=1)
    room_booking = await book(db_session, tenant_a, prop, arrival, 1)
    await move(db_session, tenant_a, room_booking, room_reservations.confirm_room_reservation)

    service_date = utcnow().date() + timedelta(days=1)
    slot_start = datetime.combine(service_date, time(19, 0), tzinfo=UTC)
    with tenant_context(tenant_a):
        table = await reservations.create_reservation(
            db_session,
            tenant_a,
            TableReservationCreate(
                service_date=service_date,
                slot_start=slot_start,
                party_size=4,
                guest_name="Bianchi",
            ),
        )
        await db_session.commit()

    await move(db_session, tenant_a, room_booking, room_reservations.mark_room_no_show)
    with tenant_context(tenant_a):
        await run_in_uow(
            db_session, lambda: reservations.mark_no_show(db_session, tenant_a, table.id)
        )
        await db_session.commit()

    assert await counters(db_session, tenant_a, prop.room_type_id) == {arrival: (1, 1, 0)}, (
        "a hotel no-show must NOT give its room-night back — the overbooking buffer already paid"
    )
    from app.modules.hospitality.models import ServiceSlot

    db_session.expire_all()
    with tenant_context(tenant_a):
        slot = (
            await db_session.execute(
                select(ServiceSlot).where(ServiceSlot.service_date == service_date)
            )
        ).scalar_one()
    assert slot.covers_booked == 0, (
        "a restaurant no-show BEFORE the slot must give its covers back — the table can still turn"
    )


async def test_a_date_change_moves_both_night_sets_in_one_transaction(
    db_session: AsyncSession, tenant_a: uuid.UUID, arrival: date
) -> None:
    """Shifting a confirmed stay by two days releases the nights it leaves and takes the ones it
    arrives on, with the overlap NETTING to zero.

    The netting is what lets a full hotel shift a booking by a day at all: a release-then-rebook
    pair would hand the overlap back and then fail to retake it if somebody else got there first —
    and on a one-room property, "somebody else" is any concurrent booking at all.
    """
    prop = await build_property(db_session, tenant_a, rooms_count=1)
    reservation_id = await book(db_session, tenant_a, prop, arrival, 3)
    await move(db_session, tenant_a, reservation_id, room_reservations.confirm_room_reservation)

    moved_to = arrival + timedelta(days=2)
    await move(
        db_session,
        tenant_a,
        reservation_id,
        room_reservations.amend_room_reservation,
        RoomReservationAmend(
            arrival_date=moved_to, departure_date=moved_to + timedelta(days=3)
        ),
    )

    rows = await counters(db_session, tenant_a, prop.room_type_id)
    assert {night: sold for night, (sold, _, _) in rows.items()} == {
        arrival: 0,
        arrival + timedelta(days=1): 0,
        moved_to: 1,
        moved_to + timedelta(days=1): 1,
        moved_to + timedelta(days=2): 1,
    }, rows


async def test_a_date_change_locks_every_night_of_both_sets_in_one_ascending_pass(
    db_session: AsyncSession,
    tenant_a: uuid.UUID,
    arrival: date,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The DEADLOCK GUARANTEE, asserted directly on the order the rows are taken in.

    A move touches two sets of nights, and it is the only call in this module that does. If the pass
    followed the sets rather than the calendar — new nights first, then the released ones, which is
    the order they are handed in — a stay moved LATER would lock its high nights before its low
    ones. A concurrent booking ascending over the same span then holds one of the pair and waits for
    the other, and PostgreSQL breaks the cycle by killing one transaction: a 500 on a booking that
    was perfectly legal, intermittent, and found in production rather than here (D-020/D-036 is the
    rule; the stock engine's two-quant transfer follows it for the same reason).

    Asserted white-box on ``_locked_row`` because the order is invisible in every outcome — the end
    state is identical whichever way the rows were taken — and because a real deadlock needs two
    racers holding opposite halves, which no test can schedule reliably. ``test_room_booking_races``
    proves the lock is TAKEN; this proves it is taken in the one order that cannot deadlock.
    """
    prop = await build_property(db_session, tenant_a, rooms_count=2)
    reservation_id = await book(db_session, tenant_a, prop, arrival, 3)
    await move(db_session, tenant_a, reservation_id, room_reservations.confirm_room_reservation)

    locked: list[date] = []
    real = allotment._locked_row

    async def spy(session: Any, tenant_id: Any, room_type_id: Any, stay_date: date) -> Any:
        locked.append(stay_date)
        return await real(session, tenant_id, room_type_id, stay_date)

    monkeypatch.setattr(allotment, "_locked_row", spy)
    moved_to = arrival + timedelta(days=2)
    await move(
        db_session,
        tenant_a,
        reservation_id,
        room_reservations.amend_room_reservation,
        RoomReservationAmend(
            arrival_date=moved_to, departure_date=moved_to + timedelta(days=3)
        ),
    )

    assert locked == sorted(locked), (
        f"the move locked nights in {locked} — not ascending, so two concurrent movers can take "
        "the same pair of rows in opposite orders and deadlock"
    )
    # Every night of the union exactly once, and the ONE night the stay keeps (arrival + 2, where
    # the old and new ranges overlap) is not locked at all: it nets to a delta of zero, which is
    # what lets a full hotel shift a booking by a day.
    assert locked == [
        arrival,
        arrival + timedelta(days=1),
        arrival + timedelta(days=3),
        arrival + timedelta(days=4),
    ]


async def test_a_date_change_into_a_full_night_refuses_and_changes_nothing(
    db_session: AsyncSession, tenant_a: uuid.UUID, arrival: date
) -> None:
    """A move whose destination is sold out leaves the ORIGINAL stay exactly as it was.

    ``adjust_allotment`` locks every night of both sets, checks them all, and only then writes — so
    the guest keeps the room they had rather than being dropped into the gap between a release and a
    failed re-take.
    """
    prop = await build_property(db_session, tenant_a, rooms_count=1)
    blocked_night = arrival + timedelta(days=5)
    other = await book(db_session, tenant_a, prop, blocked_night, 1, guest_name="Sitting tenant")
    await move(db_session, tenant_a, other, room_reservations.confirm_room_reservation)
    mine = await book(db_session, tenant_a, prop, arrival, 1)
    await move(db_session, tenant_a, mine, room_reservations.confirm_room_reservation)

    with pytest.raises(ValidationFailedError) as excinfo:
        await move(
            db_session,
            tenant_a,
            mine,
            room_reservations.amend_room_reservation,
            RoomReservationAmend(
                arrival_date=blocked_night, departure_date=blocked_night + timedelta(days=1)
            ),
        )
    assert excinfo.value.code == "hospitality.room_type_sold_out"
    assert excinfo.value.details["stay_date"] == blocked_night.isoformat()

    await db_session.rollback()
    rows = await counters(db_session, tenant_a, prop.room_type_id)
    assert rows[arrival][0] == 1 and rows[blocked_night][0] == 1, rows
    with tenant_context(tenant_a):
        still = await room_reservations.get_room_reservation(db_session, tenant_a, mine)
        assert still.arrival_date == arrival


# --- The gate refuses -------------------------------------------------------------


async def test_confirming_past_the_supply_refuses_with_room_type_sold_out(
    db_session: AsyncSession, tenant_a: uuid.UUID, arrival: date
) -> None:
    """Two rooms, two confirmed stays, a third asking for the same night: 422 naming the night.

    The pre-flight refusal is what a website turns into "the 14th is full, try the 15th", and it
    fires BEFORE the CHECK — a caller who reached the CHECK would get a 500 instead of an answer.
    """
    prop = await build_property(db_session, tenant_a, rooms_count=2)
    for index in range(2):
        held = await book(db_session, tenant_a, prop, arrival, 1, guest_name=f"Guest {index}")
        await move(db_session, tenant_a, held, room_reservations.confirm_room_reservation)
    third = await book(db_session, tenant_a, prop, arrival, 1, guest_name="Third")

    with pytest.raises(ValidationFailedError) as excinfo:
        await move(db_session, tenant_a, third, room_reservations.confirm_room_reservation)

    assert excinfo.value.code == "hospitality.room_type_sold_out"
    assert excinfo.value.details["stay_date"] == arrival.isoformat()
    assert excinfo.value.details["available"] == "0"
    await db_session.rollback()
    with tenant_context(tenant_a):
        refused = await room_reservations.get_room_reservation(db_session, tenant_a, third)
        assert refused.status == RoomReservationStatus.TENTATIVE.value


async def test_a_confirmation_takes_the_allotment_lock_before_any_other_write(
    db_session: AsyncSession,
    tenant_a: uuid.UUID,
    arrival: date,
    query_counter: Callable[..., Any],
) -> None:
    """The counter row is read (and on PostgreSQL locked) as the FIRST touch of
    ``hsp_room_type_inventory`` in the transaction, and BEFORE the booking's own status write.

    Q3 asks for the lock as the first write in the ``run_in_uow`` body, and the reason is the shape
    of what comes after it: a confirmation that had already rewritten the reservation row and its
    ``core_documents`` mirror before consulting the counter would hold those rows' locks for the
    whole of the allotment pass, so every concurrent transition of ANY booking would queue behind a
    guest's availability check. Ordering is invisible to an outcome assertion — the uow rolls back
    either way — so it is asserted on the statement log, which is the only place it shows.

    ``with_for_update`` itself is a no-op on SQLite (D-003), so what is pinned here is the ORDER;
    that the clause is present and serializing is ``test_room_booking_races.py``'s job under -m pg.
    """
    prop = await build_property(db_session, tenant_a, rooms_count=2)
    reservation_id = await book(db_session, tenant_a, prop, arrival, 2)

    with query_counter() as counted:
        await move(db_session, tenant_a, reservation_id, room_reservations.confirm_room_reservation)

    def first_touching(table: str) -> int:
        for index, statement in enumerate(counted.statements):
            if table in statement:
                return index
        raise AssertionError(f"no statement touched {table}:\n" + "\n".join(counted.statements))

    def first_write(table: str) -> int:
        for index, statement in enumerate(counted.statements):
            if table in statement and statement.lstrip().upper().startswith(("UPDATE", "INSERT")):
                return index
        raise AssertionError(f"nothing wrote {table}:\n" + "\n".join(counted.statements))

    assert first_touching("hsp_room_type_inventory") < first_write("hsp_room_reservations"), (
        "the allotment row must be taken before the booking's own row is written:\n"
        + "\n".join(counted.statements)
    )
    assert first_touching("hsp_room_type_inventory") < first_write("core_documents"), (
        "the allotment row must be taken before the D-012 registry mirror is rewritten:\n"
        + "\n".join(counted.statements)
    )


async def test_a_missing_allotment_row_upserts_rather_than_reading_zero(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """Q3's named hidden cost: a date outside the materialised grid must not silently refuse.

    Nothing pre-creates allotment rows — a grid would be one row per room type per night forever,
    for nights nobody books — so EVERY first booking of a night reads no row at all. If absence read
    as "nothing on sale" (the ``StockQuant`` meaning, where a missing quant really is zero on hand)
    the property could never take a booking, and a property that materialised a 90-day grid could
    never take one on day 91. Absence of a counter is absence of a BOOKING, never absence of a room.
    """
    prop = await build_property(db_session, tenant_a, rooms_count=3)
    far_future = utcnow().date() + timedelta(days=400)
    reservation_id = await book(db_session, tenant_a, prop, far_future, 1)

    await move(db_session, tenant_a, reservation_id, room_reservations.confirm_room_reservation)

    assert await counters(db_session, tenant_a, prop.room_type_id) == {far_future: (1, 3, 0)}


async def test_the_overbooking_limit_is_what_sells_past_the_supply(
    db_session: AsyncSession, tenant_a: uuid.UUID, arrival: date
) -> None:
    """A one-room property with a buffer of one sells two nights, and refuses the third.

    ``overbooking_limit`` is the whole reason a no-show releases nothing: it is the property's
    advance sale against the guests who will not turn up, so it has to be spendable exactly once.
    Zero by default — overbooking is a decision, not an accident.
    """
    prop = await build_property(db_session, tenant_a, rooms_count=1)
    first = await book(db_session, tenant_a, prop, arrival, 1, guest_name="First")
    await move(db_session, tenant_a, first, room_reservations.confirm_room_reservation)
    with tenant_context(tenant_a):
        row = (
            await db_session.execute(
                select(RoomTypeInventory).where(RoomTypeInventory.stay_date == arrival)
            )
        ).scalar_one()
        row.overbooking_limit = 1
        await db_session.commit()

    second = await book(db_session, tenant_a, prop, arrival, 1, guest_name="Second")
    await move(db_session, tenant_a, second, room_reservations.confirm_room_reservation)
    third = await book(db_session, tenant_a, prop, arrival, 1, guest_name="Third")
    with pytest.raises(ValidationFailedError) as excinfo:
        await move(db_session, tenant_a, third, room_reservations.confirm_room_reservation)

    assert excinfo.value.code == "hospitality.room_type_sold_out"
    await db_session.rollback()
    assert (await counters(db_session, tenant_a, prop.room_type_id))[arrival] == (2, 1, 1)


# --- Housekeeping moves the supply (D-085) ------------------------------------


async def test_taking_a_room_out_of_order_lowers_sellable_on_future_nights_and_restores_it(
    db_session: AsyncSession, tenant_a: uuid.UUID, arrival: date
) -> None:
    """OUT_OF_ORDER is the one housekeeping state with a revenue consequence, and the counter has to
    move with it — through ``set_housekeeping_status``, the column's single writer (D-085).

    Only MATERIALISED future nights are rewritten: a night nobody has booked is seeded from a live
    room count when somebody does, so materialising the horizon here would write a number that gets
    recomputed anyway. Coming back raises the same rows, so a boiler fixed the next morning restores
    exactly the supply it took.
    """
    prop = await build_property(db_session, tenant_a, rooms_count=3)
    reservation_id = await book(db_session, tenant_a, prop, arrival, 2)
    await move(db_session, tenant_a, reservation_id, room_reservations.confirm_room_reservation)

    with tenant_context(tenant_a):
        await run_in_uow(
            db_session,
            lambda: rooms.set_housekeeping_status(
                db_session, tenant_a, prop.room_ids[0], HousekeepingStatus.OUT_OF_ORDER
            ),
        )
        await db_session.commit()
    assert [sellable for _, sellable, _ in (
        await counters(db_session, tenant_a, prop.room_type_id)
    ).values()] == [2, 2]

    with tenant_context(tenant_a):
        await run_in_uow(
            db_session,
            lambda: rooms.set_housekeeping_status(
                db_session, tenant_a, prop.room_ids[0], HousekeepingStatus.DIRTY
            ),
        )
        await db_session.commit()
    assert [sellable for _, sellable, _ in (
        await counters(db_session, tenant_a, prop.room_type_id)
    ).values()] == [3, 3]


async def test_an_ordinary_housekeeping_move_does_not_touch_the_counter(
    db_session: AsyncSession, tenant_a: uuid.UUID, arrival: date
) -> None:
    """DIRTY -> IN_PROGRESS -> CLEAN is the whole of an ordinary day and sells nothing differently.

    Only the crossing into or out of ``HOUSEKEEPING_UNSELLABLE`` counts. A hook that fired on every
    move would rewrite the property's whole future allotment dozens of times a morning, and
    ``rooms_sellable`` would drift by exactly the number of rooms serviced.
    """
    prop = await build_property(db_session, tenant_a, rooms_count=2)
    reservation_id = await book(db_session, tenant_a, prop, arrival, 1)
    await move(db_session, tenant_a, reservation_id, room_reservations.confirm_room_reservation)

    for status in (HousekeepingStatus.IN_PROGRESS, HousekeepingStatus.CLEAN):
        with tenant_context(tenant_a):
            await run_in_uow(
                db_session,
                lambda s=status: rooms.set_housekeeping_status(
                    db_session, tenant_a, prop.room_ids[0], s
                ),
            )
            await db_session.commit()

    assert await counters(db_session, tenant_a, prop.room_type_id) == {arrival: (1, 2, 0)}


async def test_taking_the_last_sellable_room_off_a_sold_out_night_refuses(
    db_session: AsyncSession, tenant_a: uuid.UUID, arrival: date
) -> None:
    """A one-room property whose only night is sold cannot put that room out of order.

    Allowing it would push the row past ``CHECK (rooms_sold <= rooms_sellable + overbooking_limit)``
    and surface as a 500 on the housekeeping board; recording the oversell instead would leave a
    guest booked into a room the property cannot give them, and Atlas has no walk-the-guest flow to
    resolve one. So the manager is told which night to move a booking off first, and the room's
    status is left exactly as it was.
    """
    prop = await build_property(db_session, tenant_a, rooms_count=1)
    reservation_id = await book(db_session, tenant_a, prop, arrival, 1)
    await move(db_session, tenant_a, reservation_id, room_reservations.confirm_room_reservation)

    with pytest.raises(ValidationFailedError) as excinfo, tenant_context(tenant_a):
        await run_in_uow(
            db_session,
            lambda: rooms.set_housekeeping_status(
                db_session, tenant_a, prop.room_ids[0], HousekeepingStatus.OUT_OF_ORDER
            ),
        )
    assert excinfo.value.code == "hospitality.room_type_sold_out"

    await db_session.rollback()
    with tenant_context(tenant_a):
        room = await rooms.get_room(db_session, tenant_a, prop.room_ids[0])
        assert room.housekeeping_status == HousekeepingStatus.DIRTY.value


async def test_moving_a_room_to_another_type_moves_the_sellable_count_on_both(
    db_session: AsyncSession, tenant_a: uuid.UUID, arrival: date
) -> None:
    """The SECOND axis that changes supply, and the one that had no hook.

    D-085 gave ``housekeeping_status`` a single writer so the counter could hang off it.
    ``RoomUpdate.room_type_id`` is a shipped, documented field that changes the same fact and went
    straight to ``setattr``. Without the hook the losing type's already-materialised nights keep
    counting a room the type no longer has — ``rooms_sellable`` overstating physical supply, which
    is a SILENT oversell: the gate then confirms a stay for a room that does not exist, and the walk
    happens at check-in.

    Both counters must move, so both are materialised first. DBL holds two rooms and one sold night;
    SGL holds one room and one sold night. Moving 101 out of DBL and into SGL leaves DBL sellable 1
    (which is what it physically has) and SGL sellable 2.
    """
    dbl = await build_property(db_session, tenant_a, rooms_count=2, code="DBL", floor="10")
    sgl = await build_property(db_session, tenant_a, rooms_count=1, code="SGL", floor="20")
    for prop in (dbl, sgl):
        booking = await book(db_session, tenant_a, prop, arrival, 1)
        await move(db_session, tenant_a, booking, room_reservations.confirm_room_reservation)
    assert await counters(db_session, tenant_a, dbl.room_type_id) == {arrival: (1, 2, 0)}
    assert await counters(db_session, tenant_a, sgl.room_type_id) == {arrival: (1, 1, 0)}

    with tenant_context(tenant_a):
        await run_in_uow(
            db_session,
            lambda: rooms.update_room(
                db_session, tenant_a, dbl.room_ids[0], RoomUpdate(room_type_id=sgl.room_type_id)
            ),
        )
        await db_session.commit()

    assert await counters(db_session, tenant_a, dbl.room_type_id) == {arrival: (1, 1, 0)}
    assert await counters(db_session, tenant_a, sgl.room_type_id) == {arrival: (1, 2, 0)}


async def test_moving_the_last_sellable_room_out_of_a_sold_out_type_refuses(
    db_session: AsyncSession, tenant_a: uuid.UUID, arrival: date
) -> None:
    """A move that would leave the losing type oversold on a future night is REFUSED, exactly as
    taking that room OUT_OF_ORDER would be — the same helper, the same argument. Atlas has no
    walk-the-guest flow, so the manager is told which night to move a booking off first, and the
    room stays on the type it was on."""
    dbl = await build_property(db_session, tenant_a, rooms_count=1, code="DBL", floor="10")
    sgl = await build_property(db_session, tenant_a, rooms_count=1, code="SGL", floor="20")
    booking = await book(db_session, tenant_a, dbl, arrival, 1)
    await move(db_session, tenant_a, booking, room_reservations.confirm_room_reservation)

    with pytest.raises(ValidationFailedError) as excinfo, tenant_context(tenant_a):
        await run_in_uow(
            db_session,
            lambda: rooms.update_room(
                db_session, tenant_a, dbl.room_ids[0], RoomUpdate(room_type_id=sgl.room_type_id)
            ),
        )
    assert excinfo.value.code == "hospitality.room_type_sold_out"

    await db_session.rollback()
    with tenant_context(tenant_a):
        room = await rooms.get_room(db_session, tenant_a, dbl.room_ids[0])
        assert room.room_type_id == dbl.room_type_id
    assert await counters(db_session, tenant_a, dbl.room_type_id) == {arrival: (1, 1, 0)}


async def test_moving_an_out_of_order_room_between_types_moves_neither_counter(
    db_session: AsyncSession, tenant_a: uuid.UUID, arrival: date
) -> None:
    """A room in ``HOUSEKEEPING_UNSELLABLE`` is supply for NEITHER type, so moving it changes
    nothing on either counter — the same set ``allotment`` seeds a new night from, read once. A hook
    that fired unconditionally would decrement a type that was never counting the room."""
    dbl = await build_property(db_session, tenant_a, rooms_count=2, code="DBL", floor="10")
    sgl = await build_property(db_session, tenant_a, rooms_count=1, code="SGL", floor="20")
    for prop in (dbl, sgl):
        booking = await book(db_session, tenant_a, prop, arrival, 1)
        await move(db_session, tenant_a, booking, room_reservations.confirm_room_reservation)
    with tenant_context(tenant_a):
        await run_in_uow(
            db_session,
            lambda: rooms.set_housekeeping_status(
                db_session, tenant_a, dbl.room_ids[0], HousekeepingStatus.OUT_OF_ORDER
            ),
        )
        await db_session.commit()
    before = (
        await counters(db_session, tenant_a, dbl.room_type_id),
        await counters(db_session, tenant_a, sgl.room_type_id),
    )

    with tenant_context(tenant_a):
        await run_in_uow(
            db_session,
            lambda: rooms.update_room(
                db_session, tenant_a, dbl.room_ids[0], RoomUpdate(room_type_id=sgl.room_type_id)
            ),
        )
        await db_session.commit()

    assert (
        await counters(db_session, tenant_a, dbl.room_type_id),
        await counters(db_session, tenant_a, sgl.room_type_id),
    ) == before


async def test_the_supply_hook_leaves_already_slept_nights_alone(
    db_session: AsyncSession, tenant_a: uuid.UUID, arrival: date
) -> None:
    """``adjust_sellable``'s ``on_or_after`` is a real boundary, not decoration.

    A night in the past is history: rewriting what a sold-out Tuesday could have held changes
    nothing anybody can sell and lies about the past, and on a property with three years of
    materialised nights it is also the difference between a bounded UPDATE and an unbounded one.
    Widening the filter to every materialised night leaves every other hospitality test green,
    which is exactly why this one exists.
    """
    # Off ``date.today()`` and not off the ``arrival`` fixture: ``adjust_sellable``'s boundary is
    # the LOCAL today and the fixture is built from ``utcnow()``, so a machine behind UTC in the
    # small hours would otherwise put this night exactly ON the boundary it is meant to be under.
    slept = date.today() - timedelta(days=1)
    prop = await build_property(db_session, tenant_a, rooms_count=3)
    for night in (slept, arrival):
        booking = await book(db_session, tenant_a, prop, night, 1)
        await move(db_session, tenant_a, booking, room_reservations.confirm_room_reservation)
    assert await counters(db_session, tenant_a, prop.room_type_id) == {
        slept: (1, 3, 0),
        arrival: (1, 3, 0),
    }

    with tenant_context(tenant_a):
        await run_in_uow(
            db_session,
            lambda: rooms.set_housekeeping_status(
                db_session, tenant_a, prop.room_ids[0], HousekeepingStatus.OUT_OF_ORDER
            ),
        )
        await db_session.commit()

    assert await counters(db_session, tenant_a, prop.room_type_id) == {
        slept: (1, 3, 0),  # already slept — untouched
        arrival: (1, 2, 0),  # still sellable — one room fewer
    }


# --- The document: numbering, transitions and check-in ------------------------


async def test_the_booking_is_a_numbered_document_from_the_moment_it_is_tentative(
    db_session: AsyncSession, tenant_a: uuid.UUID, arrival: date
) -> None:
    """RMR- at creation, not at confirmation: the number is the reference the website shows the
    guest and the desk searches on, so it exists before the sale does. Distinct from the table
    booking's RSV- series, because a guest quoting a number is quoting exactly one document."""
    prop = await build_property(db_session, tenant_a)
    reservation_id = await book(db_session, tenant_a, prop, arrival, 1)

    with tenant_context(tenant_a):
        reservation = await room_reservations.get_room_reservation(
            db_session, tenant_a, reservation_id
        )
    assert reservation.reservation_number.startswith("RMR-")
    assert reservation.status == RoomReservationStatus.TENTATIVE.value
    assert reservation.document_id is not None


async def test_a_checked_in_stay_cannot_be_cancelled(
    db_session: AsyncSession, tenant_a: uuid.UUID, arrival: date
) -> None:
    """The guest is in the room; the correction wanted then is on their folio, not on the booking.
    ``ROOM_RESERVATION_FLOW`` is what says so, so the desk endpoint and the website endpoint cannot
    disagree about it."""
    prop = await build_property(db_session, tenant_a)
    reservation_id = await book(db_session, tenant_a, prop, arrival, 1)
    await move(db_session, tenant_a, reservation_id, room_reservations.confirm_room_reservation)
    await move(
        db_session,
        tenant_a,
        reservation_id,
        room_stays.check_in_room_reservation,
        prop.room_ids[0],
    )

    with pytest.raises(ConflictError) as excinfo:
        await move(db_session, tenant_a, reservation_id, room_reservations.cancel_room_reservation)
    assert excinfo.value.code == "hospitality.room_reservation_not_transitionable"


async def test_check_in_refuses_an_out_of_order_room(
    db_session: AsyncSession, tenant_a: uuid.UUID, arrival: date
) -> None:
    """Assigning a guest to a room that is off sale is the walk the refusals exist to prevent."""
    prop = await build_property(db_session, tenant_a, rooms_count=2)
    reservation_id = await book(db_session, tenant_a, prop, arrival, 1)
    await move(db_session, tenant_a, reservation_id, room_reservations.confirm_room_reservation)
    with tenant_context(tenant_a):
        await run_in_uow(
            db_session,
            lambda: rooms.set_housekeeping_status(
                db_session, tenant_a, prop.room_ids[0], HousekeepingStatus.OUT_OF_ORDER
            ),
        )
        await db_session.commit()

    with pytest.raises(ValidationFailedError) as excinfo:
        await move(
            db_session,
            tenant_a,
            reservation_id,
            room_stays.check_in_room_reservation,
            prop.room_ids[0],
        )
    assert excinfo.value.code == "hospitality.room_not_sellable"


async def test_two_guests_cannot_be_checked_into_the_same_room(
    db_session: AsyncSession, tenant_a: uuid.UUID, arrival: date
) -> None:
    """A guest walking into an occupied room, which nothing above check-in prevents.

    The allotment counter sells a room TYPE, so two confirmed doubles on one night are a perfectly
    correct book on a two-room property — which physical room each gets is a check-in decision. The
    type check and the housekeeping check both pass for the second guest, so without an occupancy
    refusal the desk hands out the same key twice. 409 rather than 422: the room is in a state that
    forbids the move, like every other ``*_not_transitionable``.

    The partial unique index is the backstop under the read, and the end state is what says the two
    are not the same guard: the refused booking is still CONFIRMED, still holding its night, and
    free to be given a different room — or the same one once the first guest leaves.
    """
    prop = await build_property(db_session, tenant_a, rooms_count=2)
    first = await book(db_session, tenant_a, prop, arrival, 1, guest_name="First")
    second = await book(db_session, tenant_a, prop, arrival, 1, guest_name="Second")
    for booking in (first, second):
        await move(db_session, tenant_a, booking, room_reservations.confirm_room_reservation)
    await move(db_session, tenant_a, first, room_stays.check_in_room_reservation, prop.room_ids[0])

    with pytest.raises(ConflictError) as excinfo:
        await move(
            db_session, tenant_a, second, room_stays.check_in_room_reservation, prop.room_ids[0]
        )
    assert excinfo.value.code == "hospitality.room_occupied"

    await db_session.rollback()
    with tenant_context(tenant_a):
        held = await room_reservations.get_room_reservation(db_session, tenant_a, second)
        assert held.status == RoomReservationStatus.CONFIRMED.value
        assert held.room_id is None

    await move(db_session, tenant_a, first, room_stays.check_out_room_reservation)
    await move(db_session, tenant_a, second, room_stays.check_in_room_reservation, prop.room_ids[0])
    with tenant_context(tenant_a):
        moved_in = await room_reservations.get_room_reservation(db_session, tenant_a, second)
        assert moved_in.room_id == prop.room_ids[0]


async def test_a_rate_plan_for_another_room_type_is_refused(
    db_session: AsyncSession, tenant_a: uuid.UUID, arrival: date
) -> None:
    """A suite must not sell at a single's rate through a copy-pasted id: the night audit would post
    that rate as revenue every night of the stay, a money bug with no symptom until month end."""
    prop = await build_property(db_session, tenant_a)
    with tenant_context(tenant_a):
        suite = await rooms.create_room_type(
            db_session, tenant_a, RoomTypeCreate(code="SUI", name="Suite", base_capacity=4)
        )
        await db_session.commit()

    with pytest.raises(ValidationFailedError) as excinfo, tenant_context(tenant_a):
        await room_reservations.create_room_reservation(
            db_session,
            tenant_a,
            RoomReservationCreate(
                room_type_id=suite.id,
                rate_plan_id=prop.rate_plan_id,
                arrival_date=arrival,
                departure_date=arrival + timedelta(days=1),
                party_size=2,
                guest_name="Mismatch",
            ),
        )
    assert excinfo.value.code == "hospitality.rate_plan_room_type_mismatch"


async def test_a_party_larger_than_the_type_sleeps_is_refused(
    db_session: AsyncSession, tenant_a: uuid.UUID, arrival: date
) -> None:
    """``base_capacity`` is what a room type sleeps as standard, and it is what the booking is
    validated against — extra beds are a rate question this phase does not model."""
    prop = await build_property(db_session, tenant_a, capacity=2)
    with pytest.raises(ValidationFailedError) as excinfo:
        await book(db_session, tenant_a, prop, arrival, 1, party_size=5)
    assert excinfo.value.code == "hospitality.party_size_exceeds_capacity"


async def test_a_stay_that_sleeps_no_night_is_refused(
    db_session: AsyncSession, tenant_a: uuid.UUID, arrival: date
) -> None:
    """Departure on the arrival date is a booking for nobody, occupying a room somebody else could
    have had. Refused with a reason rather than reaching the CHECK as a 500."""
    prop = await build_property(db_session, tenant_a)
    with pytest.raises(ValidationFailedError) as excinfo, tenant_context(tenant_a):
        await room_reservations.create_room_reservation(
            db_session,
            tenant_a,
            RoomReservationCreate(
                room_type_id=prop.room_type_id,
                rate_plan_id=prop.rate_plan_id,
                arrival_date=arrival,
                departure_date=arrival,
                party_size=2,
                guest_name="Zero nights",
            ),
        )
    assert excinfo.value.code == "hospitality.stay_range_invalid"


async def test_stay_nights_is_the_half_open_range() -> None:
    """The one arithmetic every consumer of the counter shares, pinned directly: three calendar days
    apart is three nights, and the departure date is never one of them."""
    start = date(2026, 9, 3)
    assert allotment.stay_nights(start, date(2026, 9, 6)) == [
        date(2026, 9, 3),
        date(2026, 9, 4),
        date(2026, 9, 5),
    ]
    assert allotment.stay_nights(start, start) == []


# --- The HTTP surface ---------------------------------------------------------


async def api_property(client: AsyncClient, *, rooms_count: int = 2) -> dict[str, Any]:
    """Seed a bookable property over the wire, so the endpoints are driven exactly as a client
    would."""
    response = await client.post(
        "/api/v1/hospitality/room-types",
        json={"code": "DBL", "name": "Double", "base_capacity": 2},
    )
    assert response.status_code == 201, response.text
    room_type_id = response.json()["id"]
    response = await client.post(
        "/api/v1/hospitality/rate-plans",
        json={
            "code": "BAR",
            "name": "Best available",
            "room_type_id": room_type_id,
            "nightly_amount": "120.00",
            "currency_code": "USD",
            "valid_from": "2020-01-01",
        },
    )
    assert response.status_code == 201, response.text
    rate_plan_id = response.json()["id"]
    room_ids = []
    for index in range(rooms_count):
        created = await client.post(
            "/api/v1/hospitality/rooms",
            json={"room_number": f"20{index}", "room_type_id": room_type_id},
        )
        assert created.status_code == 201, created.text
        room_ids.append(created.json()["id"])
    return {"room_type_id": room_type_id, "rate_plan_id": rate_plan_id, "room_ids": room_ids}


def booking_body(prop: dict[str, Any], arrival_date: date, nights: int = 1) -> dict[str, Any]:
    return {
        "room_type_id": prop["room_type_id"],
        "rate_plan_id": prop["rate_plan_id"],
        "arrival_date": arrival_date.isoformat(),
        "departure_date": (arrival_date + timedelta(days=nights)).isoformat(),
        "party_size": 2,
        "guest_name": "Okonjo",
    }


async def test_the_desk_can_take_confirm_and_check_in_a_booking_over_the_wire(
    rooms_api: RoomsApi, arrival: date
) -> None:
    """The whole desk path end to end, because the transitions are what a receptionist actually
    does and a router that renders the wrong state is invisible to a service-level test."""
    prop = await api_property(rooms_api.client)
    created = await rooms_api.client.post(
        BOOKINGS_URL, json=booking_body(prop, arrival), headers={"Idempotency-Key": "desk-1"}
    )
    assert created.status_code == 201, created.text
    assert created.json()["status"] == RoomReservationStatus.TENTATIVE.value
    booking_id = created.json()["id"]

    confirmed = await rooms_api.client.post(f"{BOOKINGS_URL}/{booking_id}/confirm")
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == RoomReservationStatus.CONFIRMED.value

    checked_in = await rooms_api.client.post(
        f"{BOOKINGS_URL}/{booking_id}/check-in", json={"room_id": prop["room_ids"][0]}
    )
    assert checked_in.status_code == 200, checked_in.text
    assert checked_in.json()["room_id"] == prop["room_ids"][0]

    checked_out = await rooms_api.client.post(f"{BOOKINGS_URL}/{booking_id}/check-out")
    assert checked_out.json()["status"] == RoomReservationStatus.CHECKED_OUT.value


async def test_replaying_a_booking_key_returns_the_first_booking(
    rooms_api: RoomsApi, arrival: date
) -> None:
    """D-013: the booking registers a numbered document, so a retried submit must return the first
    one rather than burn a second RMR- number on a guest who asked once."""
    prop = await api_property(rooms_api.client)
    body = booking_body(prop, arrival)
    first = await rooms_api.client.post(
        BOOKINGS_URL, json=body, headers={"Idempotency-Key": "retry-me"}
    )
    second = await rooms_api.client.post(
        BOOKINGS_URL, json=body, headers={"Idempotency-Key": "retry-me"}
    )
    assert first.status_code == 201 and second.status_code == 201, second.text
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["reservation_number"] == second.json()["reservation_number"]


async def test_a_website_replay_returns_its_first_booking_and_never_the_desks(
    rooms_api: RoomsApi, arrival: date
) -> None:
    """D-013 on the WEBSITE create, and the separate-namespace claim under it.

    The website is the surface that actually retries: a guest's browser resubmits a timed-out form,
    and a second RMR- document for one guest who asked once is the duplicate the key exists to
    prevent. The desk create is replayed by the test above; this replays the route that needs it
    most, and the one whose principal cannot fix a duplicate afterwards.

    The namespaces are ``hospitality.room_reservation.create`` and ``...book`` — DIFFERENT keys, so
    the SAME ``Idempotency-Key`` on the two surfaces is two requests and must produce two bookings.
    One shared namespace would have a website's "1" hand a desk clerk the website's booking, or the
    reverse: a replay is only ever a replay of the same request.
    """
    prop = await api_property(rooms_api.client)
    body = booking_body(prop, arrival)
    first = await rooms_api.client.post(
        WEBSITE_BOOKINGS_URL, json=body, headers={"Idempotency-Key": "same-key"}
    )
    replay = await rooms_api.client.post(
        WEBSITE_BOOKINGS_URL, json=body, headers={"Idempotency-Key": "same-key"}
    )
    assert first.status_code == 201 and replay.status_code == 201, replay.text
    assert first.json()["id"] == replay.json()["id"]
    assert first.json()["reservation_number"] == replay.json()["reservation_number"]

    desk = await rooms_api.client.post(
        BOOKINGS_URL, json=body, headers={"Idempotency-Key": "same-key"}
    )
    assert desk.status_code == 201, desk.text
    assert desk.json()["id"] != first.json()["id"]
    assert desk.json()["reservation_number"] != first.json()["reservation_number"]


async def test_the_arrivals_list_is_paginated_and_costs_at_most_three_queries(
    rooms_api: RoomsApi, arrival: date, query_counter: Callable[..., Any]
) -> None:
    """PERFORMANCE §2/§6: the desk's book is a list endpoint, so it is keyset-paginated and flat in
    the number of bookings. Measured WARM, after the D-009 RBAC cache is hot."""
    prop = await api_property(rooms_api.client)
    for index in range(6):
        body = booking_body(prop, arrival + timedelta(days=index))
        response = await rooms_api.client.post(
            BOOKINGS_URL, json=body, headers={"Idempotency-Key": f"list-{index}"}
        )
        assert response.status_code == 201, response.text

    await rooms_api.client.get(BOOKINGS_URL, params={"limit": 2})
    with query_counter() as counted:
        page = await rooms_api.client.get(BOOKINGS_URL, params={"limit": 2})
    assert page.status_code == 200, page.text
    assert len(page.json()["items"]) == 2
    assert page.json()["next_cursor"]
    assert counted.count <= 3, counted.statements


async def test_a_website_key_may_book_but_never_confirm_or_read_the_book(
    rooms_api_factory: RoomsApiFactory,
) -> None:
    """D-069's narrowing rule: ``room_reservation.book`` is the ONLY key the property's website
    holds, and it takes a TENTATIVE booking and stops there.

    Confirming is the counter touch and the sale, so an external client cannot reach it — a human
    (or, from Task 2, a recorded deposit) is what turns an enquiry into a room. Reading the book is
    every guest's name and phone number for the week, which a leaked website credential must never
    be. Both are asserted as 403s on the guard, so they hold before any row is looked at.
    """
    website = await rooms_api_factory(
        slug="hsp-site",
        email="site@hsp-site.test",
        keys=(HOSPITALITY_ROOM_RESERVATION_BOOK,),
    )
    somebody = uuid.uuid4()
    assert (await website.client.post(f"{BOOKINGS_URL}/{somebody}/confirm")).status_code == 403
    assert (await website.client.get(BOOKINGS_URL)).status_code == 403
    assert (await website.client.post(f"{BOOKINGS_URL}/{somebody}/cancel")).status_code == 403


async def test_the_desk_keys_are_split_between_reading_and_moving_a_booking(
    rooms_api_factory: RoomsApiFactory,
) -> None:
    """A reader of the arrivals book cannot confirm, check in or cancel — the read/manage split
    every other module uses, so a night porter can see who is arriving without being able to sell
    the last room."""
    reader = await rooms_api_factory(
        slug="hsp-reader",
        email="reader@hsp-reader.test",
        keys=(HOSPITALITY_ROOM_RESERVATION_READ,),
    )
    somebody = uuid.uuid4()
    assert (await reader.client.get(BOOKINGS_URL)).status_code == 200
    assert (await reader.client.post(f"{BOOKINGS_URL}/{somebody}/confirm")).status_code == 403
    assert (
        await reader.client.post(
            BOOKINGS_URL,
            json={
                "room_type_id": str(somebody),
                "rate_plan_id": str(somebody),
                "arrival_date": "2026-09-01",
                "departure_date": "2026-09-02",
                "party_size": 2,
                "guest_name": "Nope",
            },
        )
    ).status_code == 403


async def test_the_website_booking_comes_back_tentative_and_cannot_assert_a_status(
    rooms_api: RoomsApi, arrival: date
) -> None:
    """Q6's acknowledgment rule, copied from ``place_website_order``: an external client is told the
    state its booking is actually in, and a body that tries to assert one is REJECTED rather than
    silently ignored (``extra="forbid"``). A website that could set CONFIRMED would be selling rooms
    with no human in the loop."""
    prop = await api_property(rooms_api.client)
    booked = await rooms_api.client.post(
        WEBSITE_BOOKINGS_URL,
        json=booking_body(prop, arrival),
        headers={"Idempotency-Key": "site-1"},
    )
    assert booked.status_code == 201, booked.text
    assert booked.json()["status"] == RoomReservationStatus.TENTATIVE.value

    asserted = await rooms_api.client.post(
        WEBSITE_BOOKINGS_URL,
        json=booking_body(prop, arrival) | {"status": "CONFIRMED"},
        headers={"Idempotency-Key": "site-2"},
    )
    assert asserted.status_code == 422, asserted.text


def test_the_new_tables_emit_the_constraint_names_migration_0056_creates() -> None:
    """The NAMING_CONVENTION trap, pinned rather than remembered.

    ``Base.metadata``'s convention is ``ck_%(table_name)s_%(constraint_name)s``, and alembic's
    ``op.create_table`` builds its table on a BARE ``MetaData`` with no convention at all. So a
    ``ck_``-prefixed name on the model double-prefixes —
    ``ck_hsp_room_type_inventory_ck_hsp_room_type_inventory_sold_non_negative``, 71 chars — while
    the migration creates the 44-char literal. The two never match, and past PostgreSQL's 63-byte
    cap the model's half is machine-truncated on top of that.

    Autogenerate does not compare CHECK constraints, so the drift test cannot see this; the model is
    read against the migration's SOURCE instead, which is the only place the real DDL is written.
    Both tables' indexes go through the same check, which is what holds the new partial unique index
    on ``(tenant_id, room_id) WHERE status = 'CHECKED_IN'`` to one spelling.

    Scope: the 57 OTHER double-prefixed CHECK names already in ``Base.metadata`` are a
    platform-wide trap this PR does not rename (they are shipped tables), filed separately.
    """
    migration = (
        Path(__file__).resolve().parents[3] / "alembic/versions/0056_hsp_room_bookings.py"
    ).read_text()
    emitted = sorted(
        [
            str(constraint.name)
            for model in (RoomTypeInventory, RoomReservation)
            for constraint in model.__table__.constraints
            if isinstance(constraint, CheckConstraint)
        ]
        + [
            str(index.name)
            for model in (RoomTypeInventory, RoomReservation)
            for index in model.__table__.indexes
        ]
    )
    assert emitted, "the two tables declare CHECKs and indexes; reading none is the test failing"
    for name in emitted:
        assert len(name) <= 63, f"{name} is {len(name)} chars; PostgreSQL truncates past 63"
        assert name in migration, f"{name} is not what migration 0056 creates"


async def test_the_restaurant_reservation_status_enum_is_a_different_type(
    db_session: AsyncSession,
) -> None:
    """A guard against the two bookings' vocabularies being merged (the naming decision this phase
    records): the restaurant has SEATED/COMPLETED and no TENTATIVE, the hotel has CHECKED_IN/
    CHECKED_OUT and a TENTATIVE state, and neither set is a subset of the other."""
    assert {status.value for status in ReservationStatus} != {
        status.value for status in RoomReservationStatus
    }
    assert "TENTATIVE" not in {status.value for status in ReservationStatus}
    assert "SEATED" not in {status.value for status in RoomReservationStatus}
