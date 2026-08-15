"""Reservation PACING (Phase 21, spec Q3): the property's settings, the service grid they describe,
and the slot counter that gates every booking.

Its own file, not part of ``reservations.py``: its own aggregate (STRUCTURE §3, one file per
aggregate, each <400 lines), which every writer in the phase goes through — the reservation document
consumes it exactly as the order ticket consumes ``availability``.

**The gate is a counter, not a table.** OpenTable and Resy both cap COVERS PER 15-MINUTE SLOT and
leave the physical table a revisable soft assignment a human makes at seating, so the unit of
availability is one ``hsp_service_slots`` row per ``(service_date, slot_start)`` — locked
``with_for_update`` in the booking transaction, refused pre-flight, with a portable CHECK pair as
the backstop. That is ``inventory/service/stock_quants.apply_bin_delta`` in shape (D-020/D-036),
deliberately: one pattern, three counters.

**A missing slot row means DEFAULT capacity, not zero** — the one place this differs from a stock
quant, where absence means nothing on hand. Capacity is standing config, so the row is materialised
LAZILY by the first booking's upsert-on-lock; pre-creating the grid would be 96 rows a night per
property, forever, for nights nobody books. WHETHER a cancellation releases is the reservation's
decision (the counter only means something before the slot starts); only the release lives here.

Times are UTC throughout: Atlas stores no per-tenant timezone, so a slot is an INSTANT and the
service window is a pair of UTC times on the settings row; the property's website converts.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import as_utc
from app.core.exceptions import ValidationFailedError
from app.core.models import utcnow
from app.modules.hospitality.constants import (
    DEFAULT_BOOKING_HORIZON_DAYS,
    DEFAULT_COVERS_MAX,
    DEFAULT_MAX_PARTY,
    DEFAULT_MIN_PARTY,
    DEFAULT_PARTIES_MAX,
    DEFAULT_SERVICE_CLOSE,
    DEFAULT_SERVICE_OPEN,
    SLOT_MINUTES,
)
from app.modules.hospitality.models import ReservationSettings, ServiceSlot


class SlotFullError(ValidationFailedError):
    """The slot cannot take this party (422 ``hospitality.slot_full``).

    A NORMAL ANSWER, not an error state — "we are full at 19:30" is what a booking system says most
    of the time, and the website surface turns it into an offer of the nearest alternatives.
    ``details`` names WHICH ceiling was hit because the two mean different things to a host:
    covers-full is a full room, parties-full is a kitchen that cannot fire more tables at once, and
    the second is often relieved by a slot fifteen minutes away. The pre-flight half of the pacing
    rule; ``CHECK (covers_booked <= covers_max)`` is the backstop.
    """

    def __init__(
        self, *, slot: ServiceSlot, limit: str, requested: int, available: int
    ) -> None:
        super().__init__(
            message=f"This service slot has no {limit} left for that booking",
            code="hospitality.slot_full",
            details={
                "service_date": slot.service_date.isoformat(),
                "slot_start": as_utc(slot.slot_start).isoformat(),
                "limit": limit,
                "requested": str(requested),
                "available": str(available),
            },
        )


@dataclass(frozen=True)
class ResolvedSettings:
    """The property's pacing configuration with defaults already applied — what every caller reads
    instead of the nullable row, so "this tenant never configured reservations" is answered once.
    Frozen and detached from the ORM, so it survives a commit.

    ``version`` is the stored row's ``updated_at`` in microseconds ("" when there is no row); the
    slot-grid read folds it into that endpoint's validator, because a manager widening
    ``default_covers_max`` changes what the grid says without touching a slot row — a validator
    over ``hsp_service_slots`` alone would hold still through it (D-073's lying validator).
    """

    service_open: time = DEFAULT_SERVICE_OPEN
    service_close: time = DEFAULT_SERVICE_CLOSE
    default_covers_max: int = DEFAULT_COVERS_MAX
    default_parties_max: int = DEFAULT_PARTIES_MAX
    min_party: int = DEFAULT_MIN_PARTY
    max_party: int = DEFAULT_MAX_PARTY
    booking_horizon_days: int = DEFAULT_BOOKING_HORIZON_DAYS
    version: str = ""


# Every stored setting, named ONCE: the dataclass above mirrors these columns, ``resolve_settings``
# reads them off the row and ``set_settings`` writes them back, so adding a setting is one edit
# here instead of three parallel lists that drift. ``version`` is excluded — it is derived.
_SETTING_FIELDS = tuple(
    name for name in ResolvedSettings.__dataclass_fields__ if name != "version"
)
# The answer for a tenant with no settings row. Shared frozen instance.
_DEFAULTS = ResolvedSettings()


def resolve_settings(row: ReservationSettings | None) -> ResolvedSettings:
    """What a stored settings row — or its absence — means. Public because the staff settings
    endpoint renders the same answer it just wrote, and the two must agree."""
    if row is None:
        return _DEFAULTS
    return ResolvedSettings(
        version=str(int(as_utc(row.updated_at).timestamp() * 1_000_000)),
        **{name: getattr(row, name) for name in _SETTING_FIELDS},
    )


async def _settings_row(
    session: AsyncSession, tenant_id: uuid.UUID, *, lock: bool = False
) -> ReservationSettings | None:
    stmt = select(ReservationSettings).where(ReservationSettings.tenant_id == tenant_id)
    if lock:
        stmt = stmt.with_for_update()
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_settings(session: AsyncSession, tenant_id: uuid.UUID) -> ResolvedSettings:
    """The tenant's pacing configuration in ONE statement, defaults applied."""
    return resolve_settings(await _settings_row(session, tenant_id))


async def set_settings(
    session: AsyncSession, tenant_id: uuid.UUID, desired: ResolvedSettings
) -> ResolvedSettings:
    """Write the property's pacing configuration, replacing whatever was there.

    Upsert-on-lock with a SAVEPOINT, the ``availability._insert_or_reload`` idiom: the locked read
    locks NOTHING when the row does not exist, so two managers saving in the same second both read
    None and both INSERT, and the one-row-per-tenant constraint rejects the loser with an
    IntegrityError the API would surface as a 500. Rolling back and re-reading the winner under the
    lock makes it last-write-wins — the contract a replacing write already has. ``desired.version``
    is ignored: it is a read-side stamp, not a stored column.
    """
    row = await _settings_row(session, tenant_id, lock=True)
    if row is None:
        savepoint = await session.begin_nested()
        row = ReservationSettings(tenant_id=tenant_id)
        session.add(row)
        try:
            await session.flush()
        except IntegrityError:
            await savepoint.rollback()
            winner = await _settings_row(session, tenant_id, lock=True)
            if winner is None:  # not the uniqueness conflict this exists for — re-raise it
                raise
            row = winner
    for name in _SETTING_FIELDS:
        setattr(row, name, getattr(desired, name))
    await session.flush()
    return resolve_settings(row)


# --- The service grid ---------------------------------------------------------
def service_window(settings: ResolvedSettings, service_date: date) -> tuple[datetime, datetime]:
    """The UTC instants a service date opens and closes. A close at or before the open means the
    service runs PAST MIDNIGHT and the window rolls into the next calendar day — a late bar is the
    ordinary case, and the reason ``service_date`` is a business date separate from the instant."""
    opens_at = datetime.combine(service_date, settings.service_open, tzinfo=UTC)
    closes_at = datetime.combine(service_date, settings.service_close, tzinfo=UTC)
    if closes_at <= opens_at:
        closes_at += timedelta(days=1)
    return opens_at, closes_at


def slot_times(settings: ResolvedSettings, service_date: date) -> list[datetime]:
    """Every bookable slot instant of one service, ``SLOT_MINUTES`` apart. The last slot starts
    STRICTLY BEFORE close: a party seated exactly at closing time is not a service."""
    opens_at, closes_at = service_window(settings, service_date)
    step = timedelta(minutes=SLOT_MINUTES)
    slots: list[datetime] = []
    at = opens_at
    while at < closes_at:
        slots.append(at)
        at += step
    return slots


def require_slot_on_grid(
    settings: ResolvedSettings, service_date: date, slot_start: datetime
) -> None:
    """The slot must be one the service actually OFFERS: on the grid, and inside the window.

    Shared by the booking gate and the manager's override, because a time ``slot_times`` never emits
    is a slot nothing can render and nothing can book — an override written against 03:07 on a room
    that opens at 11:00 would answer 200 while closing nothing, and its junk counter row would then
    sit in every subsequent grid read of that date.

    Alignment before the window, so an off-grid time is named as such rather than as "outside
    service hours", which would send a caller looking at the wrong setting. Every real UTC offset
    is a whole number of quarter-hours, so a local :15 is always a UTC :00/:15/:30/:45.
    """
    if slot_start.minute % SLOT_MINUTES or slot_start.second or slot_start.microsecond:
        raise ValidationFailedError(
            message=f"A reservation slot must start on a {SLOT_MINUTES}-minute boundary",
            code="hospitality.slot_not_aligned",
            details={"slot_start": slot_start.isoformat(), "slot_minutes": str(SLOT_MINUTES)},
        )
    opens_at, closes_at = service_window(settings, service_date)
    if not opens_at <= slot_start < closes_at:
        raise ValidationFailedError(
            message="That time is outside the property's service hours for this date",
            code="hospitality.outside_service_hours",
            details={"opens_at": opens_at.isoformat(), "closes_at": closes_at.isoformat()},
        )


def require_bookable_slot(
    settings: ResolvedSettings,
    service_date: date,
    slot_start: datetime,
    party_size: int,
    *,
    now: datetime | None = None,
) -> None:
    """Everything that must hold before the counter is consulted, in the order a caller can act on:
    the party first (a host can offer to split it), then the date, then the time.

    Each refusal carries its own code because each has a different remedy at the website's end —
    "we do not seat parties that size", "we are not taking bookings that far out", "we are not open
    then" — and one generic code would make all three read as "try again".
    """
    if not settings.min_party <= party_size <= settings.max_party:
        raise ValidationFailedError(
            message=f"This property books parties of {settings.min_party}-{settings.max_party}",
            code="hospitality.party_size_not_accepted",
            details={
                "party_size": str(party_size),
                "min_party": str(settings.min_party),
                "max_party": str(settings.max_party),
            },
        )
    now = now or utcnow()
    today = now.date()
    # The floor is the earliest service whose window has NOT ALREADY CLOSED, not the UTC calendar
    # date — the two differ for every service that crosses UTC midnight, which is every dinner
    # service in the Americas (22:00-05:00 UTC is 18:00-01:00 in New York). Tonight's service has
    # service_date = D; the moment UTC ticks over to D+1 a calendar floor refuses D, while the
    # window check below refuses D+1 for the very same slot — so NO date at all would book the
    # service currently being run, every night, from UTC midnight until close.
    yesterday = today - timedelta(days=1)
    earliest = yesterday if service_window(settings, yesterday)[1] > now else today
    horizon = today + timedelta(days=settings.booking_horizon_days)
    if not earliest <= service_date <= horizon:
        # ONE code for both ends: a date in the past and a date past the horizon are the same
        # answer to a caller ("not that day"); splitting them invents a code nothing branches on.
        raise ValidationFailedError(
            message="That service date is outside the property's booking window",
            code="hospitality.outside_booking_window",
            details={"from": earliest.isoformat(), "to": horizon.isoformat()},
        )
    require_slot_on_grid(settings, service_date, slot_start)


# --- The pacing counter -------------------------------------------------------
async def _locked_slot(
    session: AsyncSession, tenant_id: uuid.UUID, service_date: date, slot_start: datetime
) -> ServiceSlot | None:
    """The slot's counter row FOR UPDATE, or None if nobody has booked it yet. The row lock
    serializes concurrent bookings on Postgres; SQLite omits FOR UPDATE as a no-op (D-003/D-020,
    the ``inv_stock_quants`` precedent) and its single-writer lock serializes instead."""
    stmt = (
        select(ServiceSlot)
        .where(
            ServiceSlot.tenant_id == tenant_id,
            ServiceSlot.service_date == service_date,
            ServiceSlot.slot_start == slot_start,
        )
        .with_for_update()
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _slot_for_update(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    service_date: date,
    slot_start: datetime,
    settings: ResolvedSettings,
) -> ServiceSlot:
    """The slot's counter row FOR UPDATE, materialised from the settings defaults if this is the
    first booking against it (finding 3: a missing row means DEFAULT capacity, never zero).

    The SAVEPOINT is not optional. ``_locked_slot`` locks nothing when the row does not exist, so
    two parties booking the same empty slot in the same second both read None and both INSERT — the
    unique constraint rejects the loser with an IntegrityError, a 500 on the guest's booking.
    Re-reading the winner UNDER THE LOCK is the fix ``_insert_or_reload`` already made for two staff
    86-ing one dish, and it is portable (D-003) where ON CONFLICT would not be."""
    slot = await _locked_slot(session, tenant_id, service_date, slot_start)
    if slot is not None:
        return slot
    savepoint = await session.begin_nested()
    slot = ServiceSlot(
        tenant_id=tenant_id,
        service_date=service_date,
        slot_start=slot_start,
        covers_booked=0,
        covers_max=settings.default_covers_max,
        parties_booked=0,
        parties_max=settings.default_parties_max,
    )
    session.add(slot)
    try:
        await session.flush()
    except IntegrityError:
        await savepoint.rollback()
        winner = await _locked_slot(session, tenant_id, service_date, slot_start)
        if winner is None:  # not the uniqueness conflict this exists for — re-raise it
            raise
        return winner
    return slot


async def book_into_slot(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    service_date: date,
    slot_start: datetime,
    covers: int,
    *,
    parties: int = 1,
    settings: ResolvedSettings,
) -> ServiceSlot:
    """THE GATE. Take ``covers`` and ``parties`` out of the slot's capacity, or refuse.

    ``parties=0`` is how a party that GREW takes only the extra covers: it is already counted as one
    party, and a release-then-rebook pair would let 8 growing to 9 fail on a slot that has exactly
    the room for it.

    Single-slot by construction: a booking consumes its ARRIVAL slot only (the OpenTable
    semantics), so unlike the stock engine's two-quant transfer there is no lock ordering to get
    wrong and no deadlock shape to avoid; a long meal spanning slots is out of scope, recorded
    rather than half-built. Refuses BEFORE mutating anything, so a caller's promise that a refusal
    leaves the book untouched holds without depending on the rollback. ``settings`` is passed in
    rather than read here because every caller has already read it to validate the request — one
    statement per booking, not two."""
    slot = await _slot_for_update(session, tenant_id, service_date, slot_start, settings)
    for limit, requested, booked, ceiling in (
        ("covers", covers, slot.covers_booked, slot.covers_max),
        ("parties", parties, slot.parties_booked, slot.parties_max),
    ):
        if booked + requested > ceiling:
            raise SlotFullError(
                slot=slot, limit=limit, requested=requested, available=ceiling - booked
            )
    slot.covers_booked += covers
    slot.parties_booked += parties
    await session.flush()
    return slot


async def release_from_slot(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    service_date: date,
    slot_start: datetime,
    covers: int,
    *,
    parties: int = 1,
) -> None:
    """Give ``covers`` and ``parties`` back to the slot — the inverse of :func:`book_into_slot`.

    A no-op when no counter row exists: the only way to reach that is a slot nothing was ever booked
    into, and inventing a row to decrement would materialise capacity for a night nobody booked.
    Floors at zero rather than refusing, because a release is always driven by a reservation already
    being cancelled or moved and a cancellation that 500s leaves a guest holding a table they told
    you they did not want. The floor is unreachable through this module's own paths (a reservation
    releases exactly what it booked, once, guarded by its status transition) and
    ``CHECK (covers_booked >= 0)`` stands behind it."""
    slot = await _locked_slot(session, tenant_id, service_date, slot_start)
    if slot is None:
        return
    slot.covers_booked = max(0, slot.covers_booked - covers)
    slot.parties_booked = max(0, slot.parties_booked - parties)
    await session.flush()


async def override_slot(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    service_date: date,
    slot_start: datetime,
    *,
    covers_max: int,
    parties_max: int,
    settings: ResolvedSettings,
) -> ServiceSlot:
    """A manager's capacity override for ONE slot — including ``covers_max = 0``, which is how a
    slot is CLOSED (a private event, a short-staffed shift, a boiler failure). An override BELOW
    what is already booked is REFUSED, not clamped: clamping would either silently drop guests
    already holding a confirmed booking, or leave the row violating its own CHECK and surface as a
    500 on the manager's next save. The refusal names both numbers so the manager can decide whom
    to call.

    The slot has to be one the service OFFERS, exactly as a booking's does: without that check a
    manager "closing" 03:07 gets a 200 and closes nothing, because the grid read never renders a
    time ``slot_times`` does not emit and the booking gate would refuse it anyway."""
    require_slot_on_grid(settings, service_date, slot_start)
    slot = await _slot_for_update(session, tenant_id, service_date, slot_start, settings)
    if covers_max < slot.covers_booked or parties_max < slot.parties_booked:
        raise ValidationFailedError(
            message="That capacity is below what this slot has already taken",
            code="hospitality.slot_override_below_booked",
            details={
                "covers_booked": str(slot.covers_booked),
                "parties_booked": str(slot.parties_booked),
                "covers_max": str(covers_max),
                "parties_max": str(parties_max),
            },
        )
    slot.covers_max = covers_max
    slot.parties_max = parties_max
    await session.flush()
    return slot
