"""THE BOOKING GATE (PLAN 20.2, spec Q3): the per-date room-type allotment counter, and the one
helper every counter touch in the module routes through.

Its own file, not part of the reservation service, for the reason ``pacing.py`` is not part of
``reservations.py``: it is its own aggregate (STRUCTURE §3), every writer in the phase goes through
it, and the reservation document consumes it exactly as the order ticket consumes ``availability``.
One pattern, now four counters.

**Copied in shape from ``inventory/service/stock_quants.apply_bin_delta``** (D-020/D-036), which is
what Q3 names: rows locked ``with_for_update``, a missing row upserted ON THE LOCK, a pre-flight
refusal BEFORE any write, and a portable CHECK pair as the DB backstop. Two things differ, and both
are stated where they are decided:

1. **A missing row means DEFAULT supply, not zero.** ``rooms_sellable`` is seeded from a live COUNT
   of the type's rooms that are not ``HOUSEKEEPING_UNSELLABLE``, so a date outside whatever grid a
   property has materialised is bookable, not silently sold out. Absence of a counter is absence of
   a BOOKING, never absence of a room.
2. **A stay is many nights, so there is a LOCK ORDER** — where a bin delta is one row. Every row a
   call touches is locked in ONE ascending ``stay_date`` pass, so two overlapping multi-night
   bookings can never take the same pair of rows in opposite orders and deadlock (D-020/D-036's
   deterministic-order rule, which the stock engine follows for its two-quant transfer).

The gate is a COUNTER and not an interval lock, and that is Q3's central finding: an
``EXCLUDE USING gist`` over a daterange is PostgreSQL-only, which would leave the SQLite suite
(D-003) unable to exercise the invariant the money path depends on.
"""

from __future__ import annotations

import uuid
from collections import Counter
from collections.abc import Awaitable, Callable, Collection, Mapping
from datetime import date

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationFailedError
from app.modules.hospitality.constants import (
    DEFAULT_OVERBOOKING_LIMIT,
    HOUSEKEEPING_UNSELLABLE,
)
from app.modules.hospitality.models import Room, RoomTypeInventory

_UNSELLABLE_VALUES = tuple(status.value for status in HOUSEKEEPING_UNSELLABLE)


class RoomTypeSoldOutError(ValidationFailedError):
    """No room of this type is left to sell on that night (422 ``hospitality.room_type_sold_out``).

    A NORMAL ANSWER, not an error state — "we are full on the 14th" is what a booking system says
    most of the time, and the website turns it into an offer of another date or another room type.
    ``details`` names the ONE night that refused rather than the whole stay, because that is what a
    guest can act on: a 5-night stay blocked by a single sold-out Saturday is re-bookable around it.

    This is the pre-flight half of the rule; ``CHECK (rooms_sold <= rooms_sellable +
    overbooking_limit)`` on ``hsp_room_type_inventory`` is the backstop that fires if it is ever
    bypassed. It is ALSO what refuses a room being taken OUT_OF_ORDER on a night already sold to the
    last room: Atlas has no walk-the-guest flow, so recording an oversell nothing can resolve is
    worse than telling the manager which nights to move first.
    """

    def __init__(self, *, room_type_id: uuid.UUID, row: RoomTypeInventory, requested: int) -> None:
        super().__init__(
            message="This room type has no room left to sell on that night",
            code="hospitality.room_type_sold_out",
            details={
                "room_type_id": str(room_type_id),
                "stay_date": row.stay_date.isoformat(),
                "requested": str(requested),
                "available": str(row.rooms_sellable + row.overbooking_limit - row.rooms_sold),
                "rooms_sellable": str(row.rooms_sellable),
                "rooms_sold": str(row.rooms_sold),
                "overbooking_limit": str(row.overbooking_limit),
            },
        )


def stay_nights(arrival_date: date, departure_date: date) -> list[date]:
    """The nights a stay actually SLEEPS: ``[arrival, departure)``, ascending.

    The departure date is never one of them, which is the whole of back-to-back availability — a
    guest leaving on the 5th and another arriving on the 5th buy different nights of the same room,
    and no interval arithmetic is needed to see it. Public because the reservation service, the
    counter and (Task 7) the night audit must all agree on which nights a stay is, and three
    spellings of a half-open range is how they stop agreeing.
    """
    return [
        date.fromordinal(day)
        for day in range(arrival_date.toordinal(), departure_date.toordinal())
    ]


async def _sellable_rooms(
    session: AsyncSession, tenant_id: uuid.UUID, room_type_id: uuid.UUID
) -> int:
    """How many physical rooms of this type could be sold TODAY — the seed a new counter row is
    born with (finding: a missing row means default supply, not zero).

    Counts against ``HOUSEKEEPING_UNSELLABLE`` rather than naming OUT_OF_ORDER, so this and
    ``rooms.set_housekeeping_status``'s hook read the SAME set. A set each of them derived for
    itself is exactly how an oversell gets in (D-085).
    """
    stmt = select(func.count(Room.id)).where(
        Room.tenant_id == tenant_id,
        Room.room_type_id == room_type_id,
        Room.housekeeping_status.not_in(_UNSELLABLE_VALUES),
    )
    return int((await session.execute(stmt)).scalar_one())


async def _locked_row(
    session: AsyncSession, tenant_id: uuid.UUID, room_type_id: uuid.UUID, stay_date: date
) -> RoomTypeInventory | None:
    """One night's counter row FOR UPDATE, or None if nobody has booked that night yet.

    The row lock serializes concurrent bookings on PostgreSQL; SQLite omits FOR UPDATE as a no-op
    (D-003/D-020, the ``inv_stock_quants`` precedent) and its single-writer lock serializes instead.
    """
    stmt = (
        select(RoomTypeInventory)
        .where(
            RoomTypeInventory.tenant_id == tenant_id,
            RoomTypeInventory.room_type_id == room_type_id,
            RoomTypeInventory.stay_date == stay_date,
        )
        .with_for_update()
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _row_for_update(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    room_type_id: uuid.UUID,
    stay_date: date,
    seed: Callable[[], Awaitable[int]],
) -> RoomTypeInventory:
    """One night's counter row FOR UPDATE, materialised from the live room count if this is the
    first booking against that night.

    ``seed`` is called only when a row really is missing, so a stay whose nights are all
    materialised pays no COUNT at all and a 14-night stay pays exactly one (the caller memoises it):
    the supply of a room type does not vary night to night at materialisation time.

    The SAVEPOINT is not optional. ``_locked_row`` locks NOTHING when the row does not exist, so two
    guests booking the same untouched night in the same second both read None and both INSERT — the
    unique constraint rejects the loser with an IntegrityError, a 500 on somebody's booking.
    Re-reading the winner UNDER THE LOCK is the fix ``pacing._slot_for_update`` and
    ``availability._insert_or_reload`` already made, and it is portable (D-003) where
    ``ON CONFLICT`` would not be.
    """
    row = await _locked_row(session, tenant_id, room_type_id, stay_date)
    if row is not None:
        return row
    savepoint = await session.begin_nested()
    row = RoomTypeInventory(
        tenant_id=tenant_id,
        room_type_id=room_type_id,
        stay_date=stay_date,
        rooms_sellable=await seed(),
        rooms_sold=0,
        overbooking_limit=DEFAULT_OVERBOOKING_LIMIT,
    )
    session.add(row)
    try:
        await session.flush()
    except IntegrityError:
        await savepoint.rollback()
        winner = await _locked_row(session, tenant_id, room_type_id, stay_date)
        if winner is None:  # not the uniqueness conflict this exists for — re-raise it
            raise
        return winner
    return row


async def adjust_allotment(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    room_type_id: uuid.UUID,
    stay_dates: Collection[date],
    delta: int,
    *,
    released_dates: Collection[date] = (),
) -> None:
    """THE GATE, and the ONE function that ever moves ``rooms_sold``.

    Takes ``delta`` rooms of ``room_type_id`` out of every night in ``stay_dates``, and gives one
    back on every night in ``released_dates``. Refuses with :class:`RoomTypeSoldOutError` if any
    single night would be sold past ``rooms_sellable + overbooking_limit``.

    **Why a date change passes both sets to ONE call** rather than calling this twice. Every row is
    locked in a single ascending ``stay_date`` pass over the UNION, so two desks each moving a stay
    onto the other's dates cannot take the same two rows in opposite orders. Two calls would take
    two passes, and the second pass can start below where the first ended — the deadlock shape
    D-020/D-036 forbids, and one that reaches a receptionist as a 500 rather than a 409.
    ``released_dates`` is therefore only meaningful alongside a positive ``delta``: it is the other
    half of a move, not a release in its own right (a plain release is ``delta = -1``).

    THREE PHASES, in this order, and the order is the contract:

    1. **Lock** every night ascending, materialising a missing row from the live room count.
    2. **Check** every night. Refusing before any counter has moved is what lets a caller promise
       that a refused booking leaves the book exactly as it was, without depending on the rollback.
    3. **Apply**, in one flush.

    Overlapping dates NET OUT: a stay moved from the 3rd-6th to the 4th-7th touches the 4th and 5th
    with a delta of zero, so it neither re-checks nor re-writes nights it already holds — a full
    hotel can still shift a stay by one day.

    A release FLOORS at zero rather than refusing, the ``pacing.release_from_slot`` argument: a
    release is always driven by a booking already being cancelled or moved, and a cancellation that
    500s leaves a guest holding a room they told you they did not want. The floor is unreachable
    through this module's own paths (a booking releases exactly what it took, once, guarded by its
    status transition) and ``CHECK (rooms_sold >= 0)`` stands behind it.
    """
    deltas: Counter[date] = Counter()
    for stay_date in stay_dates:
        deltas[stay_date] += delta
    for stay_date in released_dates:
        deltas[stay_date] -= delta
    await apply_allotment_deltas(session, tenant_id, room_type_id, deltas)


async def apply_allotment_deltas(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    room_type_id: uuid.UUID,
    deltas: Mapping[date, int],
) -> None:
    """:func:`adjust_allotment`'s three phases over an already-netted per-night delta map.

    Separate only because ``adjust_allotment`` is the vocabulary every caller speaks (nights and a
    signed count) while this is the shape the lock pass needs. Nothing outside this module calls it.
    """
    wanted = sorted(stay_date for stay_date, moved in deltas.items() if moved)
    if not wanted:
        return

    # ONE count for the whole call, memoised, and paid only if a night really is missing.
    cached: list[int] = []

    async def seed() -> int:
        if not cached:
            cached.append(await _sellable_rooms(session, tenant_id, room_type_id))
        return cached[0]

    # PHASE 1 — lock ascending. ``wanted`` is sorted, and that sort IS the deadlock guarantee.
    rows = [
        (
            await _row_for_update(session, tenant_id, room_type_id, stay_date, seed),
            deltas[stay_date],
        )
        for stay_date in wanted
    ]

    # PHASE 2 — check every night before ANY counter moves.
    for row, moved in rows:
        if moved > 0 and row.rooms_sold + moved > row.rooms_sellable + row.overbooking_limit:
            raise RoomTypeSoldOutError(room_type_id=room_type_id, row=row, requested=moved)

    # PHASE 3 — apply.
    for row, moved in rows:
        row.rooms_sold = max(0, row.rooms_sold + moved)
    await session.flush()


async def adjust_sellable(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    room_type_id: uuid.UUID,
    delta: int,
    *,
    on_or_after: date,
) -> None:
    """Move ``rooms_sellable`` by ``delta`` on every ALREADY-MATERIALISED night from ``on_or_after``
    — what a room going OUT_OF_ORDER (and coming back) does to what the property can sell.

    **Only materialised rows, deliberately.** A night with no counter row is seeded from a live
    COUNT the moment somebody books it (:func:`_sellable_rooms`), and that count already reflects
    the room's new status — so materialising the property's whole horizon here to write a number
    that would be recomputed anyway is the grid-maintenance cost Q3 rejects. Past nights are left
    alone for the same reason the restaurant's counter stops mattering after the slot: they are
    history, and rewriting what a sold-out Tuesday could have held changes nothing and lies about
    the past.

    Refuses rather than breaching the CHECK. Taking the last sellable room out of service on a night
    that is fully sold is a genuine oversell, and Atlas has no walk-the-guest flow to resolve one —
    so the manager is told which night to move a booking off first, instead of the row being pushed
    past ``CHECK (rooms_sold <= rooms_sellable + overbooking_limit)`` into a 500 on the housekeeping
    board. Rows are locked ascending, the same order every booking takes them in.

    ONE UPDATE whatever the horizon (PERFORMANCE §2), the ``availability.decrement_remaining_many``
    shape: a property with a year of materialised nights must not pay 365 statements for one boiler
    failure. ``synchronize_session`` is off and the loaded rows are expired instead — nothing on
    this path reads them again.
    """
    if delta == 0:
        return
    stmt = (
        select(RoomTypeInventory)
        .where(
            RoomTypeInventory.tenant_id == tenant_id,
            RoomTypeInventory.room_type_id == room_type_id,
            RoomTypeInventory.stay_date >= on_or_after,
        )
        .order_by(RoomTypeInventory.stay_date)
        .with_for_update()
    )
    rows = list((await session.execute(stmt)).scalars())
    if not rows:
        return
    for row in rows:
        if row.rooms_sold > row.rooms_sellable + delta + row.overbooking_limit:
            raise RoomTypeSoldOutError(room_type_id=room_type_id, row=row, requested=-delta)
    await session.execute(
        update(RoomTypeInventory)
        .where(RoomTypeInventory.id.in_([row.id for row in rows]))
        .values(rooms_sellable=RoomTypeInventory.rooms_sellable + delta)
        .execution_options(synchronize_session=False)
    )
    for row in rows:
        session.expire(row)
