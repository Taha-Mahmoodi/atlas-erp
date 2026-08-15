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
from datetime import UTC, datetime, time, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationFailedError
from app.core.models import utcnow
from app.core.tenancy import tenant_context
from app.modules.hospitality.constants import (
    DEFAULT_COVERS_MAX,
    DEFAULT_PARTIES_MAX,
)
from app.modules.hospitality.models import ServiceSlot
from app.modules.hospitality.service import pacing


def a_service_date(days_ahead: int = 1) -> "datetime.date":  # noqa: F821 - date via datetime
    """A bookable service date. Relative to today because the booking horizon is, so the suite does
    not rot the way a hard-coded 2026 date would."""
    return utcnow().date() + timedelta(days=days_ahead)


def slot_at(service_date: "datetime.date", hour: int, minute: int = 0) -> datetime:  # noqa: F821
    """A slot instant on ``service_date``. UTC, because that is what the settings' service window is
    expressed in — Atlas stores no per-tenant timezone."""
    return datetime.combine(service_date, time(hour, minute), tzinfo=UTC)


async def stored_slot(
    session: AsyncSession, tenant_id: uuid.UUID, service_date: "datetime.date"  # noqa: F821
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
