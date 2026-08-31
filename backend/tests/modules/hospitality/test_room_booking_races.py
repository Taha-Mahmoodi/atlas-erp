"""The allotment counter under CONCURRENCY (PLAN 20.2, spec Q3): two guests racing the last room,
and two multi-night stays racing each other's nights.

**These are ``-m pg`` tests, and that is the point.** ``with_for_update`` is a NO-OP on SQLite
(D-003/D-020, the ``inv_stock_quants`` precedent), so a gated race there shows a lost update that
PostgreSQL — the runtime engine — does not have. The engine-independent halves (a sold-out night
refuses, a cancel restores, a missing row upserts) are covered in ``test_room_reservations.py``;
what has an EXACT answer only on the engine that takes the lock is asserted here.

**The row must be MATERIALISED first.** PR #201's lesson, restated for this counter: on an EMPTY
night the two racers collide on ``uq_hsp_room_type_inventory_...`` instead, PostgreSQL serializes
them on the unique index, and the test passes with ``with_for_update`` DELETED — proving the
constraint rather than the mechanism. Every race below therefore books the night once, commits, and
only then opens the window.

Everything runs on REAL concurrent tasks — separate ``AsyncSession``s over one Postgres engine,
driven through ``asyncio.gather`` — never sequential calls narrating a race. ``interleaved`` holds
each party inside a read it cannot avoid until both have got there, and it gates BEFORE the locked
allotment read, never inside it: a gate held while one task owns the row lock would simply deadlock
the other against it.
"""

import asyncio
import contextlib
import os
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.core.db import build_session_factory
from app.core.events import run_in_uow
from app.core.exceptions import ValidationFailedError
from app.core.models import utcnow
from app.core.tenancy import system_context, tenant_context
from app.modules.admin.models import Tenant
from app.modules.hospitality.models import RoomReservation, RoomTypeInventory
from app.modules.hospitality.rooms_schemas import (
    RatePlanCreate,
    RoomCreate,
    RoomReservationAmend,
    RoomTypeCreate,
)
from app.modules.hospitality.rooms_schemas import RoomReservationCreate as BookingCreate
from app.modules.hospitality.service import rate_plans, room_reservations, rooms

_URL = os.environ.get("ATLAS_DATABASE_URL", "")

# A gated party waits at most this long for the other; a hang is a bug in the test, not a pass.
GATE_TIMEOUT = 5.0

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
    read twice and a barrier would then wait forever for a party already through)."""

    def __init__(self, parties: int) -> None:
        self._parties = parties
        self._arrived: set[int] = set()
        self._open = asyncio.Event()

    async def arrive(self, key: int) -> None:
        if self._open.is_set():
            return
        self._arrived.add(key)
        if len(self._arrived) >= self._parties:
            self._open.set()
            return
        await asyncio.wait_for(self._open.wait(), timeout=GATE_TIMEOUT)


@contextlib.asynccontextmanager
async def interleaved(*targets: tuple[object, str], parties: int = 2) -> AsyncIterator[None]:
    """Hold each session inside one of the named ``(module, function)`` reads until ``parties``
    sessions have passed one of them, so both racers are genuinely inside the window.

    The targets are always reads taken BEFORE the allotment's ``with_for_update``: the booking's
    room-type load, the amend's reservation load. Gating inside the locked read instead would have
    one task holding the row lock while it waits for a task blocked on that very lock.
    """
    gate = _Gate(parties)
    originals = [(module, name, getattr(module, name)) for module, name in targets]

    def _wrap(real: Callable[..., Awaitable[object]]) -> Callable[..., Awaitable[object]]:
        async def _gated(session: AsyncSession, *args: object, **kwargs: object) -> object:
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
def factory(pg_engine: AsyncEngine) -> Callable[[], AsyncSession]:
    """A factory for INDEPENDENT sessions — one per concurrent actor, the way two web workers each
    hold their own connection."""
    return build_session_factory(pg_engine)


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
async def test_two_multi_night_bookings_lock_dates_in_the_same_order(
    pg_engine: AsyncEngine, pg_tenant: uuid.UUID, factory: Callable[[], AsyncSession]
) -> None:
    """THE DEADLOCK TEST (D-020/D-036). Two overlapping multi-night stays confirm at the same
    instant, and both finish.

    Each stay locks several allotment rows in one transaction. If the pass were not sorted — if it
    followed, say, the order the caller supplied the dates in, or a set's iteration order — one task
    could hold the 4th while waiting for the 3rd and the other hold the 3rd while waiting for the
    4th, and PostgreSQL would break the cycle by killing one with a deadlock error. That reaches a
    receptionist as a 500 on a booking that was perfectly legal, and it is intermittent, so it would
    be found in production rather than here.

    The overlapping nights are MATERIALISED FIRST so both racers are locking existing rows, which is
    where a lock-order bug actually bites; an unmaterialised night has no row to take out of order.
    Two rooms of supply so neither stay refuses — the assertion is that both COMPLETE, and a
    deadlock would surface as one of them raising rather than as a sold-out answer.
    """
    first_night = _tomorrow()
    room_type_id, rate_plan_id = await _seed_property(factory, pg_tenant, rooms_count=3)
    # Materialise nights 0..4 by confirming a five-night stay and then cancelling it: the rows exist
    # holding zero, so the racers below lock REAL rows (which is where a lock-order bug bites) and
    # neither is refused. Through the public path, so nothing here can materialise a shape the
    # booking gate would not.
    await _book_and_confirm(
        factory, pg_tenant, room_type_id, rate_plan_id, first_night, 5, "Grid maker"
    )
    async with factory() as session:
        with tenant_context(pg_tenant):
            grid_maker = (await session.execute(select(RoomReservation))).scalars().one()
            await run_in_uow(
                session,
                lambda: room_reservations.cancel_room_reservation(
                    session, pg_tenant, grid_maker.id
                ),
            )
            await session.commit()
    assert set((await _sold(pg_engine, pg_tenant, room_type_id)).values()) == {0}

    async with interleaved((room_reservations, "get_room_reservation")):
        results = await asyncio.wait_for(
            asyncio.gather(
                _book_and_confirm(
                    factory, pg_tenant, room_type_id, rate_plan_id, first_night, 4, "Ascending"
                ),
                _book_and_confirm(
                    factory,
                    pg_tenant,
                    room_type_id,
                    rate_plan_id,
                    first_night + timedelta(days=1),
                    4,
                    "Overlapping",
                ),
            ),
            timeout=GATE_TIMEOUT * 3,
        )

    assert results == ["confirmed", "confirmed"], results
    sold = await _sold(pg_engine, pg_tenant, room_type_id)
    assert sold[first_night] == 1
    assert sold[first_night + timedelta(days=1)] == 2
    assert sold[first_night + timedelta(days=4)] == 1


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
