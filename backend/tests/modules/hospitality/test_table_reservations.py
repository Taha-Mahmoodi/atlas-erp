"""Table reservations (Phase 21, spec Q3): the pacing settings, the slot counter that gates every
booking, and the reservation document's lifecycle.

Everything here runs through the REAL service under the tenant context (D-025), because the rules
being proven are service rules — the HTTP layer is thin by construction and is exercised in
``test_staff_reservations.py`` / ``test_website_reservations.py``.

The counter half comes first: a property's capacity is standing config, so the interesting cases
are all about what an ABSENT row means (default capacity, materialised lazily) versus what a
present one means, and about which refusals are pre-flight rather than constraint violations.
"""

import uuid
from datetime import UTC, date, datetime, time, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.core.exceptions import ConflictError, ValidationFailedError
from app.core.models import utcnow
from app.core.tenancy import tenant_context
from app.modules.hospitality.constants import (
    DEFAULT_COVERS_MAX,
    DEFAULT_PARTIES_MAX,
    ReservationStatus,
)
from app.modules.hospitality.models import ServiceSlot, TableReservation
from app.modules.hospitality.reservation_schemas import TableReservationCreate
from app.modules.hospitality.service import pacing, reservations, tickets


def a_service_date(days_ahead: int = 1) -> date:
    """A bookable service date. Relative to today because the booking horizon is, so the suite does
    not rot the way a hard-coded 2026 date would."""
    return utcnow().date() + timedelta(days=days_ahead)


def slot_at(service_date: date, hour: int, minute: int = 0) -> datetime:
    """A slot instant on ``service_date``. UTC, because that is what the settings' service window is
    expressed in — Atlas stores no per-tenant timezone."""
    return datetime.combine(service_date, time(hour, minute), tzinfo=UTC)


async def stored_slot(
    session: AsyncSession, tenant_id: uuid.UUID, service_date: date
) -> ServiceSlot | None:
    """The one materialised counter row for a service date, or None — what "lazily materialised"
    is actually asserted against."""
    session.expire_all()
    with tenant_context(tenant_id):
        return (
            await session.execute(
                select(ServiceSlot).where(ServiceSlot.service_date == service_date)
            )
        ).scalar_one_or_none()


# --- Settings: absence is the default -----------------------------------------


async def test_a_tenant_with_no_settings_row_reads_the_code_defaults(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """A property takes its first booking without being configured first.

    The MenuAvailability idiom one table over: the settings table holds OVERRIDES, so absence is a
    valid, complete answer rather than a "not set up yet" error. Without it, finding 3 has nowhere
    to get the default capacity a missing slot row is supposed to mean.
    """
    with tenant_context(tenant_a):
        settings = await pacing.get_settings(db_session, tenant_a)
    assert settings.default_covers_max == DEFAULT_COVERS_MAX
    assert settings.default_parties_max == DEFAULT_PARTIES_MAX
    assert settings.version == "", "an absent row has no version to validate a cached grid against"


async def test_saving_settings_twice_replaces_the_one_row(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """There is at most ONE settings row per tenant, and saving again edits it in place.

    A second row would make ``get_settings`` non-deterministic (``scalar_one_or_none`` would raise),
    which is why the table carries its own named UNIQUE(tenant_id) alongside the composite one.
    """
    with tenant_context(tenant_a):
        first = await pacing.set_settings(
            db_session, tenant_a, pacing.ResolvedSettings(default_covers_max=30)
        )
        second = await pacing.set_settings(
            db_session, tenant_a, pacing.ResolvedSettings(default_covers_max=50)
        )
        await db_session.commit()
        reread = await pacing.get_settings(db_session, tenant_a)

    assert (first.default_covers_max, second.default_covers_max) == (30, 50)
    assert reread.default_covers_max == 50
    assert reread.version != "", "a stored row must carry a version the grid's validator can move"


# --- The counter: a missing row means DEFAULT capacity ------------------------


async def test_the_first_booking_materialises_the_slot_from_the_settings_defaults(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """Finding 3, the one place this differs from a stock quant: NO ROW MEANS DEFAULT CAPACITY.

    A quant that does not exist means nothing on hand; a slot that does not exist means the whole
    room is free. So the first booking must both create the row AND seed it from settings — a
    materialisation that defaulted the caps to zero would refuse every first booking of every night.
    """
    service_date = a_service_date()
    with tenant_context(tenant_a):
        settings = await pacing.set_settings(
            db_session, tenant_a, pacing.ResolvedSettings(default_covers_max=12)
        )
        assert await stored_slot(db_session, tenant_a, service_date) is None

        slot = await pacing.book_into_slot(
            db_session, tenant_a, service_date, slot_at(service_date, 19), 4, settings=settings
        )
    assert (slot.covers_booked, slot.covers_max) == (4, 12)
    assert (slot.parties_booked, slot.parties_max) == (1, settings.default_parties_max)


async def test_a_second_booking_adds_to_the_same_counter_row(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """Two parties at 19:00 share ONE counter row — that is what makes the gate O(1) in the book's
    depth, and what the write-budget ratchet pins."""
    service_date = a_service_date()
    with tenant_context(tenant_a):
        settings = await pacing.get_settings(db_session, tenant_a)
        for covers in (4, 2):
            await pacing.book_into_slot(
                db_session,
                tenant_a,
                service_date,
                slot_at(service_date, 19),
                covers,
                settings=settings,
            )
        await db_session.commit()

    row = await stored_slot(db_session, tenant_a, service_date)
    assert row is not None
    assert (row.covers_booked, row.parties_booked) == (6, 2)


async def test_a_slot_with_no_covers_left_refuses_and_names_covers(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """The pre-flight refusal, and it says WHICH ceiling was hit.

    Covers-full is a full room; parties-full is a kitchen that cannot fire more tables at once, and
    the second is often relieved fifteen minutes away. A host given only "full" cannot tell the
    guest which of those it is, and the website cannot decide whether to offer a different size or a
    different time. The CHECK constraint would also stop the oversell, but as a 500.
    """
    service_date = a_service_date()
    with tenant_context(tenant_a):
        settings = await pacing.set_settings(
            db_session, tenant_a, pacing.ResolvedSettings(default_covers_max=6, max_party=8)
        )
        await pacing.book_into_slot(
            db_session, tenant_a, service_date, slot_at(service_date, 19), 4, settings=settings
        )
        with pytest.raises(ValidationFailedError) as excinfo:
            await pacing.book_into_slot(
                db_session, tenant_a, service_date, slot_at(service_date, 19), 3, settings=settings
            )
    assert excinfo.value.code == "hospitality.slot_full"
    assert excinfo.value.details["limit"] == "covers"
    assert excinfo.value.details["available"] == "2"


async def test_a_slot_with_no_parties_left_refuses_and_names_parties(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """The other ceiling: the room has covers to spare but the pass cannot fire another table."""
    service_date = a_service_date()
    with tenant_context(tenant_a):
        settings = await pacing.set_settings(
            db_session,
            tenant_a,
            pacing.ResolvedSettings(default_covers_max=100, default_parties_max=1),
        )
        await pacing.book_into_slot(
            db_session, tenant_a, service_date, slot_at(service_date, 19), 2, settings=settings
        )
        with pytest.raises(ValidationFailedError) as excinfo:
            await pacing.book_into_slot(
                db_session, tenant_a, service_date, slot_at(service_date, 19), 2, settings=settings
            )
    assert excinfo.value.code == "hospitality.slot_full"
    assert excinfo.value.details["limit"] == "parties"


async def test_releasing_gives_the_capacity_back_to_the_same_slot(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """The inverse of the gate: what a cancellation before the slot does to the counter."""
    service_date = a_service_date()
    with tenant_context(tenant_a):
        settings = await pacing.get_settings(db_session, tenant_a)
        await pacing.book_into_slot(
            db_session, tenant_a, service_date, slot_at(service_date, 19), 6, settings=settings
        )
        await pacing.release_from_slot(
            db_session, tenant_a, service_date, slot_at(service_date, 19), 6
        )
        await db_session.commit()

    row = await stored_slot(db_session, tenant_a, service_date)
    assert row is not None
    assert (row.covers_booked, row.parties_booked) == (0, 0)


async def test_releasing_a_slot_nobody_booked_is_a_no_op(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """A release must not MATERIALISE a row. Creating one to decrement would put capacity on the
    books for a night nobody booked — the grid-maintenance trap finding 3 exists to avoid — and it
    would have to be created at zero, which the CHECK then rejects."""
    service_date = a_service_date()
    with tenant_context(tenant_a):
        await pacing.release_from_slot(
            db_session, tenant_a, service_date, slot_at(service_date, 19), 4
        )
        await db_session.commit()
    assert await stored_slot(db_session, tenant_a, service_date) is None


# --- The manager's override ---------------------------------------------------


async def test_closing_a_slot_to_zero_covers_refuses_every_booking(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """``covers_max = 0`` is how a slot is CLOSED — a private event, a boiler failure. There is no
    separate is_closed flag, because a closed slot and a full slot answer a guest identically and a
    second spelling would be a second thing to keep in sync with the counter."""
    service_date = a_service_date()
    with tenant_context(tenant_a):
        settings = await pacing.get_settings(db_session, tenant_a)
        await pacing.override_slot(
            db_session,
            tenant_a,
            service_date,
            slot_at(service_date, 19),
            covers_max=0,
            parties_max=0,
            settings=settings,
        )
        with pytest.raises(ValidationFailedError) as excinfo:
            await pacing.book_into_slot(
                db_session, tenant_a, service_date, slot_at(service_date, 19), 2, settings=settings
            )
    assert excinfo.value.code == "hospitality.slot_full"


async def test_an_override_below_what_is_already_booked_is_refused_not_clamped(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """A manager cutting capacity under the guests already holding it must SEE the conflict.

    Clamping down would either silently strand confirmed bookings or leave the row violating
    ``CHECK (covers_booked <= covers_max)`` — a 500 on the next save, with no clue about which
    tables to call. The refusal carries both numbers so the manager can act.
    """
    service_date = a_service_date()
    with tenant_context(tenant_a):
        settings = await pacing.get_settings(db_session, tenant_a)
        await pacing.book_into_slot(
            db_session, tenant_a, service_date, slot_at(service_date, 19), 8, settings=settings
        )
        with pytest.raises(ValidationFailedError) as excinfo:
            await pacing.override_slot(
                db_session,
                tenant_a,
                service_date,
                slot_at(service_date, 19),
                covers_max=4,
                parties_max=10,
                settings=settings,
            )
    assert excinfo.value.code == "hospitality.slot_override_below_booked"
    assert excinfo.value.details["covers_booked"] == "8"


# --- What may be asked for at all ---------------------------------------------


async def test_a_time_outside_the_service_window_is_refused(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """09:00 on a property that opens at 11:00 is not a booking, it is a mistake — and it must be
    refused BEFORE the counter, or the slot row is materialised for a time the room never sells."""
    service_date = a_service_date()
    settings = pacing.ResolvedSettings(service_open=time(11, 0), service_close=time(23, 0))
    with pytest.raises(ValidationFailedError) as excinfo:
        pacing.require_bookable_slot(settings, service_date, slot_at(service_date, 9), 2)
    assert excinfo.value.code == "hospitality.outside_service_hours"


async def test_a_late_service_running_past_midnight_still_accepts_its_own_slots(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """A bar open 18:00-02:00 is the ordinary case, not a misconfiguration: a close at or before the
    open rolls the window into the next calendar day, which is exactly why ``service_date`` is a
    BUSINESS date and not the calendar date of the slot's own instant."""
    service_date = a_service_date()
    settings = pacing.ResolvedSettings(service_open=time(18, 0), service_close=time(2, 0))
    pacing.require_bookable_slot(
        settings, service_date, slot_at(service_date + timedelta(days=1), 1), 2
    )
    with pytest.raises(ValidationFailedError) as excinfo:
        pacing.require_bookable_slot(
            settings, service_date, slot_at(service_date + timedelta(days=1), 3), 2
        )
    assert excinfo.value.code == "hospitality.outside_service_hours"


async def test_a_date_past_the_booking_horizon_is_refused(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """Its own code, not "slot full": the remedy is "come back nearer the time", and a website that
    saw a generic refusal would offer alternatives that are equally unbookable."""
    settings = pacing.ResolvedSettings(booking_horizon_days=30)
    far = a_service_date(days_ahead=31)
    with pytest.raises(ValidationFailedError) as excinfo:
        pacing.require_bookable_slot(settings, far, slot_at(far, 19), 2)
    assert excinfo.value.code == "hospitality.outside_booking_window"


async def test_a_date_in_the_past_is_refused_by_the_same_window_rule(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """The other end of the same window. Yesterday is not bookable, and the counter must never
    materialise a row for a service that has already happened."""
    yesterday = a_service_date(days_ahead=-1)
    with pytest.raises(ValidationFailedError) as excinfo:
        pacing.require_bookable_slot(
            pacing.ResolvedSettings(), yesterday, slot_at(yesterday, 19), 2
        )
    assert excinfo.value.code == "hospitality.outside_booking_window"


async def test_a_slot_off_the_fifteen_minute_grid_is_refused(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """19:07 is not a slot. Accepting it would create a counter row nothing else can ever find —
    the grid read enumerates quarter-hours — so those covers would be held against a slot the
    availability answer never mentions, and the room would be quietly oversold."""
    service_date = a_service_date()
    with pytest.raises(ValidationFailedError) as excinfo:
        pacing.require_bookable_slot(
            pacing.ResolvedSettings(), service_date, slot_at(service_date, 19, 7), 2
        )
    assert excinfo.value.code == "hospitality.slot_not_aligned"


async def test_a_party_outside_the_configured_size_range_is_refused(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """"We do not seat twenty" is a different answer from "we are full", and a host can act on it
    (split the party, offer the private room) while a generic refusal reads as "try again"."""
    service_date = a_service_date()
    settings = pacing.ResolvedSettings(min_party=2, max_party=8)
    with pytest.raises(ValidationFailedError) as excinfo:
        pacing.require_bookable_slot(settings, service_date, slot_at(service_date, 19), 20)
    assert excinfo.value.code == "hospitality.party_size_not_accepted"
    assert excinfo.value.details["max_party"] == "8"


async def test_the_service_grid_is_quarter_hours_between_open_and_close(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """The grid the availability read enumerates, and the last slot starts STRICTLY before close: a
    party seated exactly at closing time is not a service."""
    service_date = a_service_date()
    settings = pacing.ResolvedSettings(service_open=time(18, 0), service_close=time(19, 0))
    assert pacing.slot_times(settings, service_date) == [
        slot_at(service_date, 18, 0),
        slot_at(service_date, 18, 15),
        slot_at(service_date, 18, 30),
        slot_at(service_date, 18, 45),
    ]


# --- The reservation document: the transition/counter matrix (finding 4) ------


async def book(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    service_date: date | None = None,
    slot_start: datetime | None = None,
    party_size: int = 4,
) -> TableReservation:
    """One confirmed booking through the real service, committed."""
    service_date = service_date or a_service_date()
    with tenant_context(tenant_id):
        reservation = await reservations.create_reservation(
            session,
            tenant_id,
            TableReservationCreate(
                service_date=service_date,
                slot_start=slot_start or slot_at(service_date, 19),
                party_size=party_size,
                guest_name="Okonkwo",
                guest_contact="+44 7700 900000",
            ),
        )
        await session.commit()
        return reservation


def a_slot_that_has_already_started() -> datetime:
    """The most recent quarter-hour boundary — always today's UTC date and never in the future, so a
    reservation made against it is one whose slot has come and gone."""
    now = utcnow()
    return now.replace(minute=now.minute - now.minute % 15, second=0, microsecond=0)


async def counters(
    session: AsyncSession, tenant_id: uuid.UUID, service_date: date
) -> tuple[int, int]:
    """``(covers_booked, parties_booked)`` for the service date's single slot row."""
    row = await stored_slot(session, tenant_id, service_date)
    assert row is not None, "the booking should have materialised a counter row"
    return row.covers_booked, row.parties_booked


async def slot_rows(
    session: AsyncSession, tenant_id: uuid.UUID, service_date: date
) -> dict[int, tuple[int, int]]:
    """Every counter row of a service date, keyed by the slot's UTC hour — what a test asserts
    against when a booking has moved BETWEEN slots and both ends have to be checked."""
    session.expire_all()
    with tenant_context(tenant_id):
        found = (
            await session.execute(
                select(ServiceSlot).where(ServiceSlot.service_date == service_date)
            )
        ).scalars()
        return {row.slot_start.hour: (row.covers_booked, row.parties_booked) for row in found}


async def test_confirming_a_booking_takes_its_covers_and_one_party(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """Row 1 of the matrix, and the reason there is no TENTATIVE state: passing the gate IS the
    confirmation, so the counter and the document move in the same transaction."""
    reservation = await book(db_session, tenant_a, party_size=4)
    assert reservation.status == ReservationStatus.CONFIRMED
    assert reservation.reservation_number.startswith("RSV-")
    assert await counters(db_session, tenant_a, reservation.service_date) == (4, 1)


async def test_cancelling_before_the_slot_gives_the_capacity_back(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """Row 2. The table can still be resold, so it must be — this is the whole point of tracking
    cancellations rather than just deleting the booking."""
    reservation = await book(db_session, tenant_a, party_size=4)
    with tenant_context(tenant_a):
        await reservations.cancel_reservation(db_session, tenant_a, reservation.id)
        await db_session.commit()
    assert await counters(db_session, tenant_a, reservation.service_date) == (0, 0)


async def test_cancelling_after_the_slot_has_started_releases_nothing(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """Row 3. Once the slot has begun there is nothing left to resell, so the counter is frozen: a
    release here would offer a table that is already occupied or already lost.

    The 24-hour service window is what makes a slot earlier TODAY bookable — which is also the real
    same-day case (a host taking a party that is walking in in ten minutes).
    """
    with tenant_context(tenant_a):
        await pacing.set_settings(
            db_session,
            tenant_a,
            pacing.ResolvedSettings(service_open=time(0, 0), service_close=time(0, 0)),
        )
        await db_session.commit()
    started = a_slot_that_has_already_started()
    reservation = await book(
        db_session, tenant_a, service_date=started.date(), slot_start=started, party_size=4
    )
    with tenant_context(tenant_a):
        await reservations.cancel_reservation(db_session, tenant_a, reservation.id)
        await db_session.commit()
    assert await counters(db_session, tenant_a, reservation.service_date) == (4, 1)


async def test_a_no_show_releases_nothing(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """Row 3 again, by the other door — and the rule that must NOT be unified with the hotel's.

    A no-show is bookkeeping: it says the covers were wasted, not that they became available. This
    is deliberately simpler than Phase 20's rooms, where a no-show keeps its count to feed the
    overbooking buffer; here there is no buffer and no time left to sell into.
    """
    reservation = await book(db_session, tenant_a, party_size=4)
    with tenant_context(tenant_a):
        await reservations.mark_no_show(db_session, tenant_a, reservation.id)
        await db_session.commit()
    assert reservation.status == ReservationStatus.NO_SHOW
    assert await counters(db_session, tenant_a, reservation.service_date) == (4, 1)


async def test_seating_and_completing_leave_the_counter_alone(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """Rows 4 and 5. The covers were taken when the booking was confirmed; the party arriving to use
    them is not a second claim, and neither is their leaving."""
    reservation = await book(db_session, tenant_a, party_size=4)
    with tenant_context(tenant_a):
        await reservations.seat_reservation(
            db_session, tenant_a, reservation.id, table_code="T12"
        )
        await reservations.complete_reservation(db_session, tenant_a, reservation.id)
        await db_session.commit()
    assert reservation.status == ReservationStatus.COMPLETED
    assert await counters(db_session, tenant_a, reservation.service_date) == (4, 1)


async def test_growing_a_party_takes_only_the_extra_covers(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """Row 6. Two becoming four is the commonest change a host makes, and it must take the DELTA on
    the same locked row: counting a second party would exhaust ``parties_max`` with phantom tables,
    and a release-then-rebook pair would fail on a slot with exactly the room for the bigger party.
    """
    reservation = await book(db_session, tenant_a, party_size=2)
    with tenant_context(tenant_a):
        await reservations.amend_reservation(
            db_session, tenant_a, reservation.id, party_size=4
        )
        await db_session.commit()
    assert await counters(db_session, tenant_a, reservation.service_date) == (4, 1)


async def test_shrinking_a_party_gives_the_difference_back(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """Row 6 downward. Six becoming two frees four covers for the night, and still exactly one
    party — the table has not gone away."""
    reservation = await book(db_session, tenant_a, party_size=6)
    with tenant_context(tenant_a):
        await reservations.amend_reservation(
            db_session, tenant_a, reservation.id, party_size=2
        )
        await db_session.commit()
    assert await counters(db_session, tenant_a, reservation.service_date) == (2, 1)


async def test_moving_a_booking_to_another_slot_releases_the_old_and_books_the_new(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """Row 7, in ONE transaction. Two separate calls would leave a window in which the guest holds
    neither slot, and a full destination would strand them there."""
    service_date = a_service_date()
    reservation = await book(
        db_session, tenant_a, service_date=service_date, slot_start=slot_at(service_date, 19)
    )
    with tenant_context(tenant_a):
        await reservations.amend_reservation(
            db_session, tenant_a, reservation.id, slot_start=slot_at(service_date, 20)
        )
        await db_session.commit()

    by_hour = await slot_rows(db_session, tenant_a, service_date)
    assert by_hour[19] == (0, 0)
    assert by_hour[20] == (4, 1)


async def test_a_move_into_a_full_slot_leaves_the_original_booking_intact(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """The reason row 7 is one transaction and not two calls: the destination refusing must roll the
    release back, or a host trying to help a guest loses the booking they already had."""
    service_date = a_service_date()
    with tenant_context(tenant_a):
        await pacing.set_settings(
            db_session, tenant_a, pacing.ResolvedSettings(default_covers_max=6)
        )
        await db_session.commit()
    # The id is captured BEFORE the rollback below: a rollback expires every loaded instance, and
    # reading an attribute back off one afterwards is a lazy refresh, which async SQLAlchemy cannot
    # do outside an await.
    reservation_id = (
        await book(
            db_session,
            tenant_a,
            service_date=service_date,
            slot_start=slot_at(service_date, 19),
            party_size=4,
        )
    ).id
    await book(
        db_session,
        tenant_a,
        service_date=service_date,
        slot_start=slot_at(service_date, 20),
        party_size=4,
    )

    with pytest.raises(ValidationFailedError) as excinfo, tenant_context(tenant_a):
        await reservations.amend_reservation(
            db_session, tenant_a, reservation_id, slot_start=slot_at(service_date, 20)
        )
    assert excinfo.value.code == "hospitality.slot_full"
    await db_session.rollback()

    with tenant_context(tenant_a):
        held = await reservations.get_reservation(db_session, tenant_a, reservation_id)
        assert held.status == ReservationStatus.CONFIRMED
    by_hour = await slot_rows(db_session, tenant_a, service_date)
    assert by_hour[19] == (4, 1)
    assert by_hour[20] == (4, 1)


# --- Seating, and the chain it writes -----------------------------------------


async def test_seating_opens_a_ticket_linked_to_the_reservation(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """The reservation -> ticket edge is written AT SEATING, not left to the terminal: it is the
    chain a dispute is read from, and an edge written later is an edge somebody forgets. The check
    carries the party as its guest count and the host's free-text table."""
    reservation = await book(db_session, tenant_a, party_size=5)
    with tenant_context(tenant_a):
        await reservations.seat_reservation(
            db_session, tenant_a, reservation.id, table_code="T12"
        )
        await db_session.commit()
        ticket = await tickets.get_ticket(db_session, tenant_a, reservation.ticket_id)
        chain = await docflow.get_document_chain(db_session, tenant_a, reservation.document_id)

    assert reservation.status == ReservationStatus.SEATED
    assert (ticket.table_code, ticket.guest_count) == ("T12", 5)
    assert {node.doc_type for node in chain.nodes} == {
        "hospitality.table_reservation",
        "hospitality.order_ticket",
    }
    assert [edge.link_type for edge in chain.edges] == ["seated_as"]


# --- Illegal transitions ------------------------------------------------------


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("cancel_reservation", "cancel_reservation"),
        ("mark_no_show", "cancel_reservation"),
        ("cancel_reservation", "seat_reservation"),
        ("mark_no_show", "seat_reservation"),
    ],
)
async def test_a_terminal_reservation_cannot_be_moved_again(
    db_session: AsyncSession, tenant_a: uuid.UUID, first: str, second: str
) -> None:
    """CANCELLED and NO_SHOW are terminal, and the second attempt must be a clean 409 rather than a
    second counter effect — a cancel that ran twice would hand the same covers back twice and
    oversell the night."""
    reservation = await book(db_session, tenant_a, party_size=4)
    kwargs = {"table_code": "T1"} if second == "seat_reservation" else {}
    with tenant_context(tenant_a):
        await getattr(reservations, first)(db_session, tenant_a, reservation.id)
        with pytest.raises(ConflictError) as excinfo:
            await getattr(reservations, second)(db_session, tenant_a, reservation.id, **kwargs)
    assert excinfo.value.code == "hospitality.reservation_not_transitionable"


async def test_a_seated_party_cannot_be_cancelled(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """They are at the table eating. The correction that is actually wanted is on their check, and
    cancelling here would also release covers the room is currently using."""
    reservation = await book(db_session, tenant_a, party_size=4)
    with tenant_context(tenant_a):
        await reservations.seat_reservation(db_session, tenant_a, reservation.id, table_code="T3")
        with pytest.raises(ConflictError) as excinfo:
            await reservations.cancel_reservation(db_session, tenant_a, reservation.id)
    assert excinfo.value.code == "hospitality.reservation_not_transitionable"


async def test_a_booking_whose_slot_has_started_cannot_be_amended(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """Moving a booking is a counter operation, and the counter has stopped meaning anything. What
    a host actually wants at that point is to seat them, or to mark the no-show."""
    with tenant_context(tenant_a):
        await pacing.set_settings(
            db_session,
            tenant_a,
            pacing.ResolvedSettings(service_open=time(0, 0), service_close=time(0, 0)),
        )
        await db_session.commit()
    started = a_slot_that_has_already_started()
    reservation = await book(
        db_session, tenant_a, service_date=started.date(), slot_start=started
    )
    with pytest.raises(ConflictError) as excinfo, tenant_context(tenant_a):
        await reservations.amend_reservation(
            db_session, tenant_a, reservation.id, party_size=6
        )
    assert excinfo.value.code == "hospitality.reservation_slot_started"


async def test_a_naive_slot_start_is_rejected_at_the_wire(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """The slot instant is half of the counter's unique key, and the two engines disagree about
    offsets — SQLite writes the wall clock it is handed, PostgreSQL converts to UTC. A datetime with
    no offset is therefore ambiguous in a way that silently splits one slot's counter in two, so it
    is refused rather than guessed at."""
    service_date = a_service_date()
    with pytest.raises(ValueError, match="UTC offset"):
        TableReservationCreate(
            service_date=service_date,
            slot_start=datetime.combine(service_date, time(19, 0)),
            party_size=2,
            guest_name="Naive",
        )


async def test_an_offset_slot_start_is_normalised_to_the_same_utc_counter(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """19:00+02:00 and 17:00Z are the same instant and must be the same counter row — otherwise a
    website in Berlin and a terminal in the dining room each fill their own copy of the slot."""
    service_date = a_service_date()
    berlin = TableReservationCreate(
        service_date=service_date,
        slot_start=datetime.combine(service_date, time(19, 0), tzinfo=timezone(timedelta(hours=2))),
        party_size=2,
        guest_name="Berlin",
    )
    assert berlin.slot_start == slot_at(service_date, 17)
