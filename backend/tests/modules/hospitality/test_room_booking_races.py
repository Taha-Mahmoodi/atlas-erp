"""The booking under CONCURRENCY (PLAN 20.2, spec Q3). FOUR locks are exercised here and no two of
them cover the same race:

- the RESERVATION row, taken ``with_for_update`` by every transition path, which is what stops one
  booking being confirmed (or cancelled) twice by two requests that both read it TENTATIVE;
- the ROOM row, taken by check-in and by BOTH writers of the room's own state, which is what stops
  two guests being handed one key and what stops one room being taken off its type's supply twice;
- the ROOM TYPE row — taken by ``allotment`` itself, SHARE when moving ``rooms_sold`` and EXCLUSIVE
  when moving ``rooms_sellable`` — which is what stops a night materialising from a room count a
  concurrent closure has already invalidated; and
- the per-night ALLOTMENT rows, taken ascending, which is what stops two DIFFERENT bookings
  overselling one night.

The order is **reservation → room → room type → nights ascending**, every writer takes a
subsequence of it, and the paths × locks table is in ``docs/modules/hospitality.md``.

Three of the four exist because a review round found a path that had skipped one — each time one
call site further over than the round before. The static census that catches the NEXT such path is
``test_allotment_lock_discipline.py``; these are the runtime proof that each lock is the right one.

**These are ``-m pg`` tests, and that is the point.** ``with_for_update`` is a NO-OP on SQLite
(D-003/D-020, the ``inv_stock_quants`` precedent), so a gated race there shows a lost update that
PostgreSQL — the runtime engine — does not have. The engine-independent halves (a sold-out night
refuses, a cancel restores, a missing row upserts) are covered in ``test_room_reservations.py``;
what has an EXACT answer only on the engine that takes the lock is asserted here.

**The night must be MATERIALISED first — except in the one test that is about materialising it.**
PR #201's lesson, restated for this counter: on an EMPTY night two racers collide on
``uq_hsp_room_type_inventory_...`` instead, PostgreSQL serializes them there, and the test passes
with ``with_for_update`` DELETED — proving the constraint rather than the mechanism. So every race
here books the night once and commits first, and
``test_two_bookings_of_one_unmaterialised_night_both_land`` deliberately does the opposite, because
the upsert-on-lock recovery is exactly the branch that index conflict drives.

Everything runs on REAL concurrent tasks — separate ``AsyncSession``s over one Postgres engine,
driven through ``asyncio.gather`` — never sequential calls narrating a race. ``interleaved`` holds
each party at a call it cannot avoid until both have got there; whether it gates before or after
that call is decided per race by which side of the lock the window has to open on, and the rule is
the same either way: never hold a gate across a lock the other party is blocked on.
"""

import asyncio
import contextlib
import os
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.core.db import build_session_factory
from app.core.events import run_in_uow
from app.core.exceptions import ConflictError, ValidationFailedError
from app.core.models import utcnow
from app.core.tenancy import system_context, tenant_context
from app.modules.admin.models import Tenant
from app.modules.hospitality.constants import HousekeepingStatus
from app.modules.hospitality.models import Room, RoomReservation, RoomTypeInventory
from app.modules.hospitality.rooms_schemas import (
    RatePlanCreate,
    RoomCreate,
    RoomReservationAmend,
    RoomTypeCreate,
    RoomUpdate,
)
from app.modules.hospitality.rooms_schemas import RoomReservationCreate as BookingCreate
from app.modules.hospitality.service import (
    allotment,
    rate_plans,
    room_reservations,
    room_stays,
    rooms,
)

_URL = os.environ.get("ATLAS_DATABASE_URL", "")

# A gated party waits at most this long for the other; a hang is a bug in the test, not a pass.
GATE_TIMEOUT = 5.0

# Every race here is two parties; the pool is warmed to exactly that (see the ``factory`` fixture).
RACERS = 2

# Every table these races touch, plus the tenant root they hang off. TRUNCATE rather than a per-test
# schema: the pg job runs against one migrated database (the test_reservation_pacing_races
# precedent, which is also where this file's harness comes from).
_TABLES = (
    "hsp_room_reservations, hsp_room_type_inventory, hsp_rate_plans, hsp_rooms, "
    "hsp_room_types, core_audit_log, core_doc_links, core_documents, "
    "core_number_sequences, adm_tenants"
)


@pytest.fixture
async def pg_engine() -> AsyncIterator[AsyncEngine]:
    """A real Postgres engine for the -m pg variant; skipped on the SQLite run."""
    if not _URL.startswith("postgresql"):
        pytest.skip("pg-marked test requires a PostgreSQL ATLAS_DATABASE_URL")
    engine = create_async_engine(_URL)
    async with engine.begin() as conn:
        await conn.exec_driver_sql(f"TRUNCATE {_TABLES} RESTART IDENTITY CASCADE")
    yield engine
    await engine.dispose()


@pytest.fixture
async def pg_tenant(pg_engine: AsyncEngine) -> uuid.UUID:
    """One tenant to sell rooms in. A room reservation references no item, no price list and no
    stock, so this is the entire fixture surface these races need."""
    async with build_session_factory(pg_engine)() as session:
        with system_context():
            tenant = Tenant(slug=f"rms-{uuid.uuid4().hex[:8]}", name="Allotment")
            session.add(tenant)
            await session.commit()
            return tenant.id


class _Gate:
    """Release every party only once ``parties`` DISTINCT callers have arrived (the
    ``test_availability_races`` shape: not ``asyncio.Barrier``, because a caller may reach the gated
    read twice and a barrier would then wait forever for a party already through).

    **Opening the gate is not enough; every party has to have RESUMED past it.** ``Event.set()``
    only makes the waiters runnable — the last arriver keeps the event loop and can run its whole
    transaction to COMMIT before a waiter's ``wait_for`` is scheduled back on. The loser then reads
    committed state and answers correctly for the wrong reason, so the race under test never happens
    and the test passes with the lock DELETED. That is not hypothetical: the cancellation race
    below passed its own mutation exactly this way, on the same harness that made the confirmation
    race fail. So the last party out yields until ``_passed`` reaches ``parties``, which costs a few
    event loop turns and makes the window deterministic instead of a bet on how fast Postgres is.
    """

    def __init__(self, parties: int) -> None:
        self._parties = parties
        self._arrived: set[int] = set()
        self._passed = 0
        self._open = asyncio.Event()

    async def arrive(self, key: int) -> None:
        if self._open.is_set():
            return
        self._arrived.add(key)
        if len(self._arrived) >= self._parties:
            self._open.set()
        else:
            await asyncio.wait_for(self._open.wait(), timeout=GATE_TIMEOUT)
        self._passed += 1
        deadline = time.monotonic() + GATE_TIMEOUT
        while self._passed < self._parties:
            if time.monotonic() > deadline:  # pragma: no cover - a hang is a bug in the test
                raise TimeoutError("a party was released but never resumed past the gate")
            await asyncio.sleep(0)


@contextlib.asynccontextmanager
async def interleaved(
    *targets: tuple[object, str], parties: int = 2, before: bool = False
) -> AsyncIterator[None]:
    """Hold each session at one of the named ``(module, function)`` calls until ``parties`` sessions
    have reached it, so both racers are genuinely inside the window.

    ``before=False`` (the default) gates AFTER the call returns, and the targets are then reads
    taken before the allotment's ``with_for_update``. ``before=True`` gates BEFORE the call, and is
    what a race on ONE row needs: ``get_room_reservation(for_update=True)`` is itself the lock, so
    gating after it would leave the winner waiting at a gate the loser can only reach through the
    very lock the winner holds — a hang, not a race.

    Either way the gate is never held across a lock this test's other party is blocked on.
    """
    gate = _Gate(parties)
    originals = [(module, name, getattr(module, name)) for module, name in targets]

    def _wrap(real: Callable[..., Awaitable[object]]) -> Callable[..., Awaitable[object]]:
        async def _gated(session: AsyncSession, *args: object, **kwargs: object) -> object:
            if before:
                await gate.arrive(id(session))
                return await real(session, *args, **kwargs)
            result = await real(session, *args, **kwargs)
            await gate.arrive(id(session))
            return result

        return _gated

    for module, name, real in originals:
        setattr(module, name, _wrap(real))
    try:
        yield
    finally:
        for module, name, real in originals:
            setattr(module, name, real)


@pytest.fixture
async def factory(pg_engine: AsyncEngine) -> Callable[[], AsyncSession]:
    """A factory for INDEPENDENT sessions — one per concurrent actor, the way two web workers each
    hold their own connection — over a pool WARMED to ``RACERS`` live connections.

    The warm-up is not tidiness, it is the difference between a race and a coincidence. A session
    that finds the pool empty pays a fresh TCP connect plus asyncpg's startup and auth — about
    fifteen milliseconds — and a racer paying that INSIDE the gated window issues its read after its
    opponent has already committed. It then answers 409 for the wrong reason and the test passes
    with the lock deleted. That is how the cancellation race below survived its own mutation: the
    gate released both parties within twenty microseconds of each other, and one of them then spent
    fifteen milliseconds dialling Postgres. Real web workers hold warm connections, so this is also
    the more faithful shape.
    """
    make = build_session_factory(pg_engine)

    async def _touch() -> None:
        async with make() as session:
            await session.execute(text("SELECT 1"))

    await asyncio.gather(*(_touch() for _ in range(RACERS)))
    return make


async def _seed_property(
    factory: Callable[[], AsyncSession], tenant_id: uuid.UUID, *, rooms_count: int
) -> tuple[uuid.UUID, uuid.UUID]:
    """One room type with ``rooms_count`` rooms and a rate plan, committed. Returns
    ``(room_type_id, rate_plan_id)``."""
    async with factory() as session:
        with tenant_context(tenant_id):
            room_type = await rooms.create_room_type(
                session, tenant_id, RoomTypeCreate(code="DBL", name="Double", base_capacity=2)
            )
            plan = await rate_plans.create_rate_plan(
                session,
                tenant_id,
                RatePlanCreate(
                    code="BAR",
                    name="Best available",
                    room_type_id=room_type.id,
                    nightly_amount=Decimal("150.00"),
                    currency_code="USD",
                    valid_from=date(2020, 1, 1),
                ),
            )
            for index in range(rooms_count):
                await rooms.create_room(
                    session,
                    tenant_id,
                    RoomCreate(room_number=f"3{index:02d}", room_type_id=room_type.id),
                )
            await session.commit()
            return room_type.id, plan.id


async def _book_and_confirm(
    factory: Callable[[], AsyncSession],
    tenant_id: uuid.UUID,
    room_type_id: uuid.UUID,
    rate_plan_id: uuid.UUID,
    arrival: date,
    nights: int,
    guest: str,
) -> str:
    """Take a booking and confirm it, each in its own session and uow, reporting the outcome as a
    string so ``gather`` can collect both racers without one failure hiding the other's.

    The CREATE is committed separately and the CONFIRM is the raced call: creating touches no
    counter, so racing it would race nothing at all.
    """
    taken: dict[str, uuid.UUID] = {}

    async def create() -> None:
        booking = await room_reservations.create_room_reservation(
            session,
            tenant_id,
            BookingCreate(
                room_type_id=room_type_id,
                rate_plan_id=rate_plan_id,
                arrival_date=arrival,
                departure_date=arrival + timedelta(days=nights),
                party_size=2,
                guest_name=guest,
            ),
        )
        taken["id"] = booking.id

    async with factory() as session:
        try:
            with tenant_context(tenant_id):
                await run_in_uow(session, create)
                await run_in_uow(
                    session,
                    lambda: room_reservations.confirm_room_reservation(
                        session, tenant_id, taken["id"]
                    ),
                )
            return "confirmed"
        except ValidationFailedError as exc:
            return f"refused:{exc.code}"


async def _take_booking(
    factory: Callable[[], AsyncSession],
    tenant_id: uuid.UUID,
    room_type_id: uuid.UUID,
    rate_plan_id: uuid.UUID,
    arrival: date,
    nights: int,
    guest: str,
) -> uuid.UUID:
    """One TENTATIVE booking, committed. Creating touches no counter, so it is never the raced
    half — it exists so the transition that IS raced has a document to move."""
    taken: dict[str, uuid.UUID] = {}

    async def create() -> None:
        booking = await room_reservations.create_room_reservation(
            session,
            tenant_id,
            BookingCreate(
                room_type_id=room_type_id,
                rate_plan_id=rate_plan_id,
                arrival_date=arrival,
                departure_date=arrival + timedelta(days=nights),
                party_size=2,
                guest_name=guest,
            ),
        )
        taken["id"] = booking.id

    async with factory() as session:
        with tenant_context(tenant_id):
            await run_in_uow(session, create)
        return taken["id"]


async def _move(
    factory: Callable[[], AsyncSession],
    tenant_id: uuid.UUID,
    reservation_id: uuid.UUID,
    action: Callable[..., Awaitable[object]],
    label: str,
) -> str:
    """One transition on ONE booking, in its own session and uow, reporting the outcome as a string
    so ``gather`` collects both racers without one failure hiding the other's. A 409 is reported
    rather than raised because on the paths raced below it is the CORRECT answer for the loser."""
    async with factory() as session:
        try:
            with tenant_context(tenant_id):
                await run_in_uow(
                    session, lambda: action(session, tenant_id, reservation_id)
                )
            return label
        except ConflictError as exc:
            return f"conflict:{exc.code}"
        except ValidationFailedError as exc:
            return f"refused:{exc.code}"


async def _room_ids(
    factory: Callable[[], AsyncSession], tenant_id: uuid.UUID
) -> list[uuid.UUID]:
    """The property's physical rooms in number order. ``_seed_property`` returns only the two ids a
    booking needs; the occupancy race is the one test that has to name a ROOM."""
    async with factory() as session:
        with tenant_context(tenant_id):
            return list(
                (await session.execute(select(Room.id).order_by(Room.room_number))).scalars()
            )


def _into(room_id: uuid.UUID) -> Callable[..., Awaitable[object]]:
    """``check_in_room_reservation`` bound to one room, so it has ``_move``'s three-argument shape.
    """

    async def action(
        session: AsyncSession, tenant_id: uuid.UUID, reservation_id: uuid.UUID
    ) -> object:
        return await room_stays.check_in_room_reservation(
            session, tenant_id, reservation_id, room_id
        )

    return action


async def _sold(
    pg_engine: AsyncEngine, tenant_id: uuid.UUID, room_type_id: uuid.UUID
) -> dict[date, int]:
    async with build_session_factory(pg_engine)() as session:
        with tenant_context(tenant_id):
            rows = (
                await session.execute(
                    select(RoomTypeInventory).where(
                        RoomTypeInventory.room_type_id == room_type_id
                    )
                )
            ).scalars()
            return {row.stay_date: row.rooms_sold for row in rows}


def _tomorrow() -> date:
    return utcnow().date() + timedelta(days=1)


@pytest.mark.pg
async def test_two_concurrent_bookings_of_the_last_room_serialize(
    pg_engine: AsyncEngine, pg_tenant: uuid.UUID, factory: Callable[[], AsyncSession]
) -> None:
    """A two-room property with one room already sold, and two guests confirming at the same
    instant. EXACTLY ONE gets it; the loser gets ``hospitality.room_type_sold_out``.

    This is the whole reason the counter row is LOCKED and not merely CHECKed. Without the row lock
    both confirmations read ``rooms_sold = 1``, both pass their pre-flight against
    ``rooms_sellable = 2``, and the property sells three rooms it does not have — and the CHECK does
    not fire either, because each write on its own is legal. The oversell is silent, and the only
    thing that prevents it is the second confirmation re-reading the counter UNDER the lock and
    refusing, which is the answer a website can turn into "the 15th instead?".

    The night is MATERIALISED FIRST, deliberately (PR #201's lesson). On an empty night the two
    racers collide on the unique index instead and PostgreSQL serializes them there, so the test
    would pass with ``with_for_update`` deleted — proving the constraint, not the mechanism.
    """
    arrival = _tomorrow()
    room_type_id, rate_plan_id = await _seed_property(factory, pg_tenant, rooms_count=2)
    assert (
        await _book_and_confirm(
            factory, pg_tenant, room_type_id, rate_plan_id, arrival, 1, "Already in"
        )
        == "confirmed"
    )
    assert await _sold(pg_engine, pg_tenant, room_type_id) == {arrival: 1}

    # Gate on the CONFIRM's own first read, not the create's: the two calls run in separate
    # transactions, and a gate the create had already opened would leave the confirmations to
    # interleave by luck — which is how a race test comes to pass with the lock deleted.
    async with interleaved((room_reservations, "get_room_reservation")):
        results = await asyncio.wait_for(
            asyncio.gather(
                _book_and_confirm(
                    factory, pg_tenant, room_type_id, rate_plan_id, arrival, 1, "Adeyemi"
                ),
                _book_and_confirm(
                    factory, pg_tenant, room_type_id, rate_plan_id, arrival, 1, "Bianchi"
                ),
            ),
            timeout=GATE_TIMEOUT * 3,
        )

    assert sorted(results) == ["confirmed", "refused:hospitality.room_type_sold_out"], results
    assert await _sold(pg_engine, pg_tenant, room_type_id) == {arrival: 2}


@pytest.mark.pg
async def test_two_concurrent_confirmations_of_one_booking_take_the_nights_once(
    pg_engine: AsyncEngine, pg_tenant: uuid.UUID, factory: Callable[[], AsyncSession]
) -> None:
    """A DOUBLE-CLICKED Confirm button. The nights are taken ONCE and the loser gets 409.

    This is the race the allotment row lock does NOT cover, because the two racers agree about the
    counter and disagree about nothing: both read the SAME reservation as TENTATIVE under READ
    COMMITTED, both pass ``require_transition``, and then both serialize perfectly correctly on the
    allotment row and BOTH increment it. One booking, two room-nights taken. The CHECK does not fire
    either — each write is legal on its own — and the corruption is PERMANENT, because the later
    cancel releases one night and the counter keeps the other forever, so the property starts
    refusing room-nights it can honour.

    What prevents it is ``get_room_reservation(for_update=True)``: the reservation row is the OUTER
    lock, taken before the allotment pass, so the loser's re-read happens under it and sees
    CONFIRMED. Delete the ``with_for_update`` there and this test reports
    ``["confirmed", "confirmed"]`` with ``rooms_sold == 2``.

    The gate is taken BEFORE that locked read, not after: gating after it would park the winner at a
    gate the loser can only reach by acquiring the very lock the winner holds.
    """
    arrival = _tomorrow()
    room_type_id, rate_plan_id = await _seed_property(factory, pg_tenant, rooms_count=5)
    booking_id = await _take_booking(
        factory, pg_tenant, room_type_id, rate_plan_id, arrival, 1, "Double clicker"
    )

    async with interleaved((room_reservations, "get_room_reservation"), before=True):
        results = await asyncio.wait_for(
            asyncio.gather(
                _move(
                    factory,
                    pg_tenant,
                    booking_id,
                    room_reservations.confirm_room_reservation,
                    "confirmed",
                ),
                _move(
                    factory,
                    pg_tenant,
                    booking_id,
                    room_reservations.confirm_room_reservation,
                    "confirmed",
                ),
            ),
            timeout=GATE_TIMEOUT * 3,
        )

    assert sorted(results) == [
        "confirmed",
        "conflict:hospitality.room_reservation_not_transitionable",
    ], results
    assert await _sold(pg_engine, pg_tenant, room_type_id) == {arrival: 1}


@pytest.mark.pg
async def test_two_concurrent_cancellations_of_one_booking_release_the_nights_once(
    pg_engine: AsyncEngine, pg_tenant: uuid.UUID, factory: Callable[[], AsyncSession]
) -> None:
    """The same shape on the way out, and it is worse: a double release is SILENT.

    ``adjust_allotment`` floors a release at zero rather than refusing, which is right for a
    cancellation driven by a guest who has already said no — but it means an unserialized double
    cancel of one booking gives back a night the property never took, on a counter that then reads
    perfectly plausible. Here a SECOND booking holds the same night, so the double release is
    visible as an arithmetic error rather than being swallowed by the floor: one cancel must leave
    ``rooms_sold == 1``, and two would leave 0 while a confirmed guest still holds the room.
    """
    arrival = _tomorrow()
    room_type_id, rate_plan_id = await _seed_property(factory, pg_tenant, rooms_count=5)
    assert (
        await _book_and_confirm(
            factory, pg_tenant, room_type_id, rate_plan_id, arrival, 1, "Staying"
        )
        == "confirmed"
    )
    booking_id = await _take_booking(
        factory, pg_tenant, room_type_id, rate_plan_id, arrival, 1, "Leaving"
    )
    assert (
        await _move(
            factory, pg_tenant, booking_id, room_reservations.confirm_room_reservation, "confirmed"
        )
        == "confirmed"
    )
    assert await _sold(pg_engine, pg_tenant, room_type_id) == {arrival: 2}

    async with interleaved((room_reservations, "get_room_reservation"), before=True):
        results = await asyncio.wait_for(
            asyncio.gather(
                _move(
                    factory,
                    pg_tenant,
                    booking_id,
                    room_reservations.cancel_room_reservation,
                    "cancelled",
                ),
                _move(
                    factory,
                    pg_tenant,
                    booking_id,
                    room_reservations.cancel_room_reservation,
                    "cancelled",
                ),
            ),
            timeout=GATE_TIMEOUT * 3,
        )

    assert sorted(results) == [
        "cancelled",
        "conflict:hospitality.room_reservation_not_transitionable",
    ], results
    assert await _sold(pg_engine, pg_tenant, room_type_id) == {arrival: 1}


@pytest.mark.pg
async def test_two_bookings_of_one_unmaterialised_night_both_land(
    pg_engine: AsyncEngine, pg_tenant: uuid.UUID, factory: Callable[[], AsyncSession]
) -> None:
    """The UPSERT-ON-LOCK branch, which is the one place in the gate a lock locks nothing.

    ``_locked_row`` returns None when the row does not exist, and a ``FOR UPDATE`` over no rows
    takes no lock at all — so two guests confirming the FIRST booking of a night both read None and
    both INSERT. The unique constraint rejects the loser, and without
    ``_row_for_update``'s SAVEPOINT-and-reload that IntegrityError is a 500 on somebody's booking
    rather than a booking. This is the ONE race that must be run on an UNMATERIALISED night —
    every other race in this file materialises first, precisely to avoid resolving on this index.

    Both bookings must LAND (five rooms of supply): the loser's recovery is to re-read the winner's
    row under the lock and take its night from there, so the correct end state is two rooms sold on
    a night nothing had ever booked.
    """
    arrival = _tomorrow()
    room_type_id, rate_plan_id = await _seed_property(factory, pg_tenant, rooms_count=5)
    assert await _sold(pg_engine, pg_tenant, room_type_id) == {}
    first = await _take_booking(
        factory, pg_tenant, room_type_id, rate_plan_id, arrival, 1, "Adeyemi"
    )
    second = await _take_booking(
        factory, pg_tenant, room_type_id, rate_plan_id, arrival, 1, "Bianchi"
    )

    async with interleaved((room_reservations, "get_room_reservation")):
        results = await asyncio.wait_for(
            asyncio.gather(
                _move(
                    factory,
                    pg_tenant,
                    first,
                    room_reservations.confirm_room_reservation,
                    "confirmed",
                ),
                _move(
                    factory,
                    pg_tenant,
                    second,
                    room_reservations.confirm_room_reservation,
                    "confirmed",
                ),
            ),
            timeout=GATE_TIMEOUT * 3,
        )

    assert results == ["confirmed", "confirmed"], results
    assert await _sold(pg_engine, pg_tenant, room_type_id) == {arrival: 2}


@pytest.mark.pg
async def test_two_multi_night_bookings_lock_dates_in_the_same_order(
    pg_engine: AsyncEngine, pg_tenant: uuid.UUID, factory: Callable[[], AsyncSession]
) -> None:
    """THE DEADLOCK TEST (D-020/D-036), and it is rigged so a genuine reversal expresses itself.

    A confirmation and a DATE CHANGE race the same four nights. That pairing is the point: two plain
    confirmations both walk their nights in the order ``_nights()`` produced them, so no ordering
    bug can express itself between them and the test cannot fail from the defect it names. The date
    change is the one caller whose UNION is naturally out of order — ``adjust_allotment`` counts the
    NEW nights first and the RELEASED ones second, so a move from the low pair onto the high pair
    enumerates ``d2, d3, d0, d1`` while the confirmation enumerates ``d0, d1, d2, d3``.

    ``apply_allotment_deltas``'s ``sorted()`` is the ONLY thing that reconciles them. Delete it and
    this test deadlocks for real: the confirmation takes ``d0``, the amend takes ``d2``, then each
    reaches for the row the other is holding. PostgreSQL breaks the cycle by aborting one, and the
    survivor's partner raises a ``DeadlockDetected`` that no service code catches — the intermittent
    500 on a perfectly legal booking that would otherwise be found in production.

    **The gate is on ``apply_allotment_deltas`` itself, and it has to be.** Gating on the
    reservation read instead leaves the amend to pay two extra round trips
    (``_require_bookable_stay`` reloads the room type and the rate plan) before its first night
    lock, by which time the confirmation holds ALL FOUR rows and there is no cycle left to form —
    the test then passes with ``sorted()`` deleted, proving nothing. Released side by side at the
    lock pass, the two interleave one row per round trip and the cycle closes on the third.

    The nights are MATERIALISED FIRST so both racers lock existing rows; an unmaterialised night has
    no row to take out of order. Three rooms of supply so neither is refused: the assertion is that
    both COMPLETE, and a deadlock surfaces as a raise rather than as a sold-out answer.
    """
    d0 = _tomorrow()
    d2 = d0 + timedelta(days=2)
    room_type_id, rate_plan_id = await _seed_property(factory, pg_tenant, rooms_count=3)
    # Materialise d0..d3 by confirming a four-night stay and cancelling it, through the public path
    # so nothing here can materialise a shape the gate would not.
    grid_id = await _take_booking(
        factory, pg_tenant, room_type_id, rate_plan_id, d0, 4, "Grid maker"
    )
    assert (
        await _move(
            factory, pg_tenant, grid_id, room_reservations.confirm_room_reservation, "confirmed"
        )
        == "confirmed"
    )
    assert (
        await _move(
            factory, pg_tenant, grid_id, room_reservations.cancel_room_reservation, "cancelled"
        )
        == "cancelled"
    )
    assert set((await _sold(pg_engine, pg_tenant, room_type_id)).values()) == {0}

    # The mover holds d0+d1 and will be moved onto d2+d3, so its lock pass takes the HIGH nights
    # first and the low ones second — the reversal a plain confirmation cannot produce.
    mover_id = await _take_booking(
        factory, pg_tenant, room_type_id, rate_plan_id, d0, 2, "Mover"
    )
    assert (
        await _move(
            factory, pg_tenant, mover_id, room_reservations.confirm_room_reservation, "confirmed"
        )
        == "confirmed"
    )
    stayer_id = await _take_booking(
        factory, pg_tenant, room_type_id, rate_plan_id, d0, 4, "Ascending"
    )

    async def amend() -> str:
        async with factory() as session:
            with tenant_context(pg_tenant):
                await run_in_uow(
                    session,
                    lambda: room_reservations.amend_room_reservation(
                        session,
                        pg_tenant,
                        mover_id,
                        RoomReservationAmend(
                            arrival_date=d2, departure_date=d2 + timedelta(days=2)
                        ),
                    ),
                )
            return "moved"

    async with interleaved((allotment, "apply_allotment_deltas"), before=True):
        results = await asyncio.wait_for(
            asyncio.gather(
                _move(
                    factory,
                    pg_tenant,
                    stayer_id,
                    room_reservations.confirm_room_reservation,
                    "confirmed",
                ),
                amend(),
            ),
            timeout=GATE_TIMEOUT * 3,
        )

    assert sorted(results) == ["confirmed", "moved"], results
    sold = await _sold(pg_engine, pg_tenant, room_type_id)
    # The stayer holds all four nights; the mover has left d0/d1 and taken d2/d3.
    assert [sold[d0 + timedelta(days=night)] for night in range(4)] == [1, 1, 2, 2], sold


@pytest.mark.pg
async def test_a_date_change_and_a_booking_racing_one_night_never_tear_the_counter(
    pg_engine: AsyncEngine, pg_tenant: uuid.UUID, factory: Callable[[], AsyncSession]
) -> None:
    """A desk moving a stay onto a night at the same instant a guest books that night.

    Both writers compute their new value from a counter they read, so an unserialized pair loses one
    of the two updates and the property is left holding either a room it has not sold or one it has
    sold twice. The row lock is what orders them; the CHECK pair is only a backstop, and a backstop
    turns a torn counter into a 500 rather than into a correct number. So the exact end state is
    what is asserted.

    Three rooms of supply, so neither writer is refused and the ONLY thing under test is the
    arithmetic surviving the race.
    """
    first_night = _tomorrow()
    target = first_night + timedelta(days=2)
    room_type_id, rate_plan_id = await _seed_property(factory, pg_tenant, rooms_count=3)
    assert (
        await _book_and_confirm(
            factory, pg_tenant, room_type_id, rate_plan_id, first_night, 1, "Mover"
        )
        == "confirmed"
    )
    async with factory() as session:
        with tenant_context(pg_tenant):
            moving_id = (await session.execute(select(RoomReservation))).scalars().one().id
    assert (
        await _book_and_confirm(
            factory, pg_tenant, room_type_id, rate_plan_id, target, 1, "Sitting"
        )
        == "confirmed"
    )

    async def amend() -> str:
        async with factory() as session:
            with tenant_context(pg_tenant):
                await run_in_uow(
                    session,
                    lambda: room_reservations.amend_room_reservation(
                        session,
                        pg_tenant,
                        moving_id,
                        RoomReservationAmend(
                            arrival_date=target, departure_date=target + timedelta(days=1)
                        ),
                    ),
                )
            return "moved"

    async with interleaved((room_reservations, "get_room_reservation")):
        results = await asyncio.wait_for(
            asyncio.gather(
                _book_and_confirm(
                    factory, pg_tenant, room_type_id, rate_plan_id, target, 1, "Arriving"
                ),
                amend(),
            ),
            timeout=GATE_TIMEOUT * 3,
        )

    assert sorted(results) == ["confirmed", "moved"], results
    sold = await _sold(pg_engine, pg_tenant, room_type_id)
    assert sold[first_night] == 0, sold
    assert sold[target] == 3, sold


@pytest.mark.pg
async def test_two_guests_cannot_be_checked_into_one_room_at_the_same_instant(
    pg_engine: AsyncEngine, pg_tenant: uuid.UUID, factory: Callable[[], AsyncSession]
) -> None:
    """TWO DIFFERENT bookings, ONE room, and the reservation lock cannot help.

    Every other race in this file is two writers arguing over one row. This one is two writers on
    two DIFFERENT reservation rows, so each takes its own ``with_for_update`` uncontested and both
    reach the occupancy read believing 101 is empty. What serializes them is the third lock in the
    module: ``rooms.get_room(..., for_update=True)``. Take it away and both pass the read, both
    write ``room_id``, and the partial unique index
    ``uq_hsp_room_reservations_tenant_id_room_id_checked_in`` catches the loser as a raw
    IntegrityError — the invariant holds, but a receptionist gets a 500 on a legal check-in instead
    of "101 is still occupied by RMR-...". The index is the backstop; the room lock is what makes
    the friendly answer trustworthy, and this test tells the two apart by asserting the CODE.

    The gate opens BEFORE ``get_room`` — that call is the lock, so gating after it would park the
    winner at a gate the loser can only reach through the lock the winner holds.
    """
    arrival = _tomorrow()
    room_type_id, rate_plan_id = await _seed_property(factory, pg_tenant, rooms_count=2)
    rooms_available = await _room_ids(factory, pg_tenant)
    bookings = []
    for guest in ("Adeyemi", "Bianchi"):
        booking_id = await _take_booking(
            factory, pg_tenant, room_type_id, rate_plan_id, arrival, 1, guest
        )
        assert (
            await _move(
                factory,
                pg_tenant,
                booking_id,
                room_reservations.confirm_room_reservation,
                "confirmed",
            )
            == "confirmed"
        )
        bookings.append(booking_id)
    assert await _sold(pg_engine, pg_tenant, room_type_id) == {arrival: 2}

    async with interleaved((rooms, "get_room"), before=True):
        results = await asyncio.wait_for(
            asyncio.gather(
                *(
                    _move(
                        factory,
                        pg_tenant,
                        booking_id,
                        _into(rooms_available[0]),
                        "checked_in",
                    )
                    for booking_id in bookings
                )
            ),
            timeout=GATE_TIMEOUT * 3,
        )

    assert sorted(results) == ["checked_in", "conflict:hospitality.room_occupied"], results
    # Exactly one guest is in 101, and the other still holds its night — free to be given 102.
    async with factory() as session:
        with tenant_context(pg_tenant):
            occupants = list(
                (
                    await session.execute(
                        select(RoomReservation.status).where(
                            RoomReservation.room_id == rooms_available[0]
                        )
                    )
                )
                .scalars()
                .all()
            )
    assert occupants == ["CHECKED_IN"]
    assert await _sold(pg_engine, pg_tenant, room_type_id) == {arrival: 2}


async def _sellable(
    pg_engine: AsyncEngine, tenant_id: uuid.UUID, room_type_id: uuid.UUID
) -> dict[date, int]:
    """``rooms_sellable`` per materialised night — the SUPPLY half of the counter, which the three
    races below are about and the six above never move."""
    async with build_session_factory(pg_engine)() as session:
        with tenant_context(tenant_id):
            rows = (
                await session.execute(
                    select(RoomTypeInventory).where(
                        RoomTypeInventory.room_type_id == room_type_id
                    )
                )
            ).scalars()
            return {row.stay_date: row.rooms_sellable for row in rows}


async def _second_room_type(
    factory: Callable[[], AsyncSession], tenant_id: uuid.UUID
) -> uuid.UUID:
    """A SGL for a room to be moved onto. ``_seed_property`` sells one type; a room move needs two.
    """
    async with factory() as session:
        with tenant_context(tenant_id):
            room_type = await rooms.create_room_type(
                session, tenant_id, RoomTypeCreate(code="SGL", name="Single", base_capacity=1)
            )
            await session.commit()
            return room_type.id


async def _change_room(
    factory: Callable[[], AsyncSession],
    tenant_id: uuid.UUID,
    room_id: uuid.UUID,
    payload: RoomUpdate,
    label: str,
) -> str:
    """One ``PATCH /rooms/{id}`` in its own session and uow, reporting the outcome as a string so
    ``gather`` collects both racers without one failure hiding the other's."""
    async with factory() as session:
        try:
            with tenant_context(tenant_id):
                await run_in_uow(
                    session, lambda: rooms.update_room(session, tenant_id, room_id, payload)
                )
            return label
        except ConflictError as exc:
            return f"conflict:{exc.code}"
        except ValidationFailedError as exc:
            return f"refused:{exc.code}"


async def _set_status(
    factory: Callable[[], AsyncSession],
    tenant_id: uuid.UUID,
    room_id: uuid.UUID,
    to_status: HousekeepingStatus,
    label: str,
) -> str:
    """One housekeeping move, same reporting shape as :func:`_change_room`."""
    async with factory() as session:
        try:
            with tenant_context(tenant_id):
                await run_in_uow(
                    session,
                    lambda: rooms.set_housekeeping_status(
                        session, tenant_id, room_id, to_status
                    ),
                )
            return label
        except ConflictError as exc:
            return f"conflict:{exc.code}"
        except ValidationFailedError as exc:
            return f"refused:{exc.code}"


@pytest.mark.pg
async def test_two_concurrent_moves_of_one_room_take_it_off_the_losing_type_once(
    pg_engine: AsyncEngine, pg_tenant: uuid.UUID, factory: Callable[[], AsyncSession]
) -> None:
    """TWO CONCURRENT ``PATCH /rooms/{id} {room_type_id: SGL}`` ON ONE ROOM. The losing type gives
    up the room ONCE.

    The supply half of the defect the reservation lock covers on the sold half, and it is a
    permanent UNDER-sell rather than an oversell. ``room.room_type_id`` decides the delta and it is
    read in Python, so two requests both see DBL, both compute a move, and both apply -1 to
    every materialised DBL night: three rooms become one, and the property then refuses two rooms a
    night it physically has, on every materialised night, FOREVER. Nothing notices — each write is
    legal on its own, both CHECKs hold, and the only symptom is bookings quietly turned away.

    ``rooms.get_room(..., for_update=True)`` is what prevents it: the loser re-reads the room under
    the lock, finds it already on SGL, and its move is the no-op it should be. Delete that
    ``for_update`` and this test reports ``rooms_sellable == 1`` on a night with three rooms.

    The night is MATERIALISED FIRST and holds a live booking, so the assertion is arithmetic on a
    real row rather than on a grid that does not exist yet.
    """
    arrival = _tomorrow()
    room_type_id, rate_plan_id = await _seed_property(factory, pg_tenant, rooms_count=3)
    single_id = await _second_room_type(factory, pg_tenant)
    assert (
        await _book_and_confirm(
            factory, pg_tenant, room_type_id, rate_plan_id, arrival, 1, "Sleeping"
        )
        == "confirmed"
    )
    assert await _sellable(pg_engine, pg_tenant, room_type_id) == {arrival: 3}
    assert await _sold(pg_engine, pg_tenant, room_type_id) == {arrival: 1}
    moving = (await _room_ids(factory, pg_tenant))[0]

    # BEFORE the read: ``get_room(for_update=True)`` IS the lock, so gating after it would park the
    # winner at a gate the loser can only reach through the lock the winner holds.
    async with interleaved((rooms, "get_room"), before=True):
        results = await asyncio.wait_for(
            asyncio.gather(
                *(
                    _change_room(
                        factory, pg_tenant, moving, RoomUpdate(room_type_id=single_id), "moved"
                    )
                    for _ in range(RACERS)
                )
            ),
            timeout=GATE_TIMEOUT * 3,
        )

    assert results == ["moved", "moved"], results
    assert await _sellable(pg_engine, pg_tenant, room_type_id) == {arrival: 2}, (
        "the losing type gave up the room twice"
    )
    assert await _sold(pg_engine, pg_tenant, room_type_id) == {arrival: 1}


@pytest.mark.pg
async def test_two_concurrent_housekeeping_moves_take_the_room_off_sale_once(
    pg_engine: AsyncEngine, pg_tenant: uuid.UUID, factory: Callable[[], AsyncSession]
) -> None:
    """TWO CONCURRENT ``OUT_OF_ORDER`` MOVES ON ONE ROOM. Supply drops by one, not two.

    Identical in shape to the room move above and to the double-clicked Confirm: the delta is
    derived from ``room.housekeeping_status``, read in Python, so two requests both see DIRTY, both
    cross into ``HOUSEKEEPING_UNSELLABLE``, and both take a room off every materialised night.
    ``HOUSEKEEPING_FLOW`` cannot stop it — like ``ROOM_RESERVATION_FLOW``, it has already run on a
    stale read.

    Under the room lock the loser re-reads OUT_OF_ORDER and the flow refuses it 409
    ``hospitality.room_not_transitionable`` (the only move out of OUT_OF_ORDER is DIRTY), which is
    both the correct answer and the proof the re-read happened. Delete the ``for_update`` and this
    reports two successes and ``rooms_sellable == 1``.
    """
    arrival = _tomorrow()
    room_type_id, rate_plan_id = await _seed_property(factory, pg_tenant, rooms_count=3)
    assert (
        await _book_and_confirm(
            factory, pg_tenant, room_type_id, rate_plan_id, arrival, 1, "Sleeping"
        )
        == "confirmed"
    )
    assert await _sellable(pg_engine, pg_tenant, room_type_id) == {arrival: 3}
    closing = (await _room_ids(factory, pg_tenant))[2]

    async with interleaved((rooms, "get_room"), before=True):
        results = await asyncio.wait_for(
            asyncio.gather(
                *(
                    _set_status(
                        factory, pg_tenant, closing, HousekeepingStatus.OUT_OF_ORDER, "closed"
                    )
                    for _ in range(RACERS)
                )
            ),
            timeout=GATE_TIMEOUT * 3,
        )

    assert sorted(results) == [
        "closed",
        "conflict:hospitality.room_not_transitionable",
    ], results
    assert await _sellable(pg_engine, pg_tenant, room_type_id) == {arrival: 2}


@pytest.mark.pg
async def test_a_night_materialising_after_a_closure_is_seeded_from_the_new_supply(
    pg_engine: AsyncEngine, pg_tenant: uuid.UUID, factory: Callable[[], AsyncSession]
) -> None:
    """THE SUPPLY GATE, half one: the CLOSURE reaches it first, so the count must wait for it.

    This is the one supply write no ROW lock can cover.

    ``adjust_sellable`` deliberately touches only MATERIALISED nights, because a night with no row
    is seeded from a live COUNT of the property's rooms the moment somebody books it. That COUNT is
    the third writer of ``rooms_sellable``, and the state deciding it is not one row but every
    ``hsp_rooms`` row of the type — so no ``for_update`` on a single row can order it against a room
    going out of service. A booking that counts BEFORE the closure commits materialises the night at
    the pre-closure supply, and ``adjust_sellable`` has already passed a row that did not exist: the
    night is permanently one room over, and the property oversells it.

    ``allotment._lock_room_type_supply`` is what orders the two — the ``hsp_room_types`` row, taken
    EXCLUSIVE by the supply change and SHARE by the booking gate, so the count and the change cannot
    interleave while two concurrent bookings of one type still run in parallel. Both orders give the
    same answer, and each order is a separate test because each proves a different half of the lock:
    here the closure gets there first, so the SHARE side is what has to wait. Delete the SHARE lock
    from ``apply_allotment_deltas`` and the night materialises at THREE on a property with two rooms
    left. The other half is the test below.

    The gate opens after the closure's ``adjust_sellable`` has run and before the booking's count,
    which is the exact window.
    """
    arrival = _tomorrow() + timedelta(days=7)
    room_type_id, rate_plan_id = await _seed_property(factory, pg_tenant, rooms_count=3)
    assert await _sellable(pg_engine, pg_tenant, room_type_id) == {}, "the night must be UNMADE"
    booking_id = await _take_booking(
        factory, pg_tenant, room_type_id, rate_plan_id, arrival, 1, "Arriving"
    )
    closing = (await _room_ids(factory, pg_tenant))[2]

    async with interleaved(
        (room_reservations, "get_room_reservation"), (allotment, "adjust_sellable")
    ):
        results = await asyncio.wait_for(
            asyncio.gather(
                _move(
                    factory,
                    pg_tenant,
                    booking_id,
                    room_reservations.confirm_room_reservation,
                    "confirmed",
                ),
                _set_status(
                    factory, pg_tenant, closing, HousekeepingStatus.OUT_OF_ORDER, "closed"
                ),
            ),
            timeout=GATE_TIMEOUT * 3,
        )

    assert sorted(results) == ["closed", "confirmed"], results
    assert await _sellable(pg_engine, pg_tenant, room_type_id) == {arrival: 2}, (
        "the night was seeded from a room count the closure had already invalidated"
    )
    assert await _sold(pg_engine, pg_tenant, room_type_id) == {arrival: 1}


@pytest.mark.pg
async def test_a_closure_racing_a_night_that_materialises_first_still_reaches_that_night(
    pg_engine: AsyncEngine, pg_tenant: uuid.UUID, factory: Callable[[], AsyncSession]
) -> None:
    """THE SUPPLY GATE, half two: the BOOKING reaches it first, so the closure must wait for it.

    The mirror of the test above, and it proves the other side of the same lock — a lock only orders
    anything if BOTH parties take it, so a test that fails when the SHARE half is deleted proves
    nothing about the EXCLUSIVE half.

    Here the booking materialises the night while the closure is still upstream. ``adjust_sellable``
    reaches only MATERIALISED rows, and an uncommitted INSERT is not one: without the EXCLUSIVE lock
    the closure's ``FOR UPDATE`` scan simply does not see the new night, decrements nothing, and
    leaves it holding three rooms on a property that has two — the room is out of service and the
    night still sells it. With the lock the closure blocks on ``hsp_room_types`` until the booking
    commits, then its scan finds the night and takes the room off it.

    The gate opens after the booking has INSERTED its night (``_row_for_update``) and after the
    closure has read its room, so the closure is released straight into the lock the booking holds.
    """
    arrival = _tomorrow() + timedelta(days=7)
    room_type_id, rate_plan_id = await _seed_property(factory, pg_tenant, rooms_count=3)
    assert await _sellable(pg_engine, pg_tenant, room_type_id) == {}, "the night must be UNMADE"
    booking_id = await _take_booking(
        factory, pg_tenant, room_type_id, rate_plan_id, arrival, 1, "Arriving"
    )
    closing = (await _room_ids(factory, pg_tenant))[2]

    async with interleaved((allotment, "_row_for_update"), (rooms, "get_room")):
        results = await asyncio.wait_for(
            asyncio.gather(
                _move(
                    factory,
                    pg_tenant,
                    booking_id,
                    room_reservations.confirm_room_reservation,
                    "confirmed",
                ),
                _set_status(
                    factory, pg_tenant, closing, HousekeepingStatus.OUT_OF_ORDER, "closed"
                ),
            ),
            timeout=GATE_TIMEOUT * 3,
        )

    assert sorted(results) == ["closed", "confirmed"], results
    assert await _sellable(pg_engine, pg_tenant, room_type_id) == {arrival: 2}, (
        "the closure never reached a night that materialised beside it"
    )
    assert await _sold(pg_engine, pg_tenant, room_type_id) == {arrival: 1}
