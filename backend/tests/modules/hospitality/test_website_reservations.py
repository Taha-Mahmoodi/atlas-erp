"""The property's WEBSITE booking tables over the Phase 18 machine credential (Phase 21 Task 4).

Driven over HTTP against the real app, because everything being proven here is a boundary property:
the D-069 scope the key carries, the D-013 replay, the conditional GET, and the shape of the answer
a full slot gives back. The pacing rules themselves are proven at the service level in
``test_table_reservations.py``; re-asserting them through the wire would test the same thing twice.

The fixture mints its OWN credential rather than reusing ``website_api``: a reservation references
no item, no price and no stock, so the priced kitchen that fixture builds would be setup this
surface never touches — and the point of two keys here is the WIDTH of each, which is easier to read
when each is minted with exactly the scopes its test argues about.
"""

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import utcnow
from app.core.tenancy import tenant_context
from app.modules.hospitality.constants import (
    HOSPITALITY_MENU_READ,
    HOSPITALITY_RESERVATION_BOOK,
)
from app.modules.hospitality.service import pacing
from tests.conftest import QueryCounter, assert_query_budget
from tests.modules.hospitality.factories import HospitalityPrincipal, mint_website_key


@dataclass(frozen=True)
class ReservationWebsite:
    """A website client holding ONLY ``hospitality.reservation.book``, plus a second credential on
    the same user narrowed to the menu read — the two widths the D-069 tests compare."""

    client: AsyncClient
    tenant_id: uuid.UUID
    menu_only_key: str


@pytest.fixture
async def reservation_site(
    client: AsyncClient,
    db_session: AsyncSession,
    hospitality_user_factory: Callable[..., Awaitable[HospitalityPrincipal]],
) -> AsyncIterator[ReservationWebsite]:
    principal = await hospitality_user_factory(slug="rsv-web", email="web@rsv-web.test")
    book_only = await mint_website_key(
        db_session, principal, name="bookings", scopes=[HOSPITALITY_RESERVATION_BOOK]
    )
    menu_only = await mint_website_key(
        db_session, principal, name="menu", scopes=[HOSPITALITY_MENU_READ]
    )
    client.headers["Authorization"] = f"Bearer {book_only}"
    yield ReservationWebsite(
        client=client, tenant_id=principal.tenant_id, menu_only_key=menu_only
    )


def a_service_date(days_ahead: int = 1) -> date:
    return utcnow().date() + timedelta(days=days_ahead)


def slot_at(service_date: date, hour: int, minute: int = 0) -> str:
    """A slot instant in the WIRE spelling — Pydantic renders UTC as ``...Z``, and both the grid's
    ``slot_start`` and the 422's ``alternatives`` must use it, or a website comparing the two
    against each other never matches an instant to itself."""
    return (
        datetime.combine(service_date, time(hour, minute), tzinfo=UTC)
        .isoformat()
        .replace("+00:00", "Z")
    )


def booking(service_date: date, hour: int = 19, party_size: int = 2) -> dict[str, object]:
    return {
        "service_date": service_date.isoformat(),
        "slot_start": slot_at(service_date, hour),
        "party_size": party_size,
        "guest_name": "Nakamura",
        "guest_contact": "nakamura@example.test",
    }


# --- The grid read ------------------------------------------------------------


async def test_the_grid_offers_every_slot_of_the_service(
    reservation_site: ReservationWebsite,
) -> None:
    """A property that has never configured anything still answers: the grid is the code defaults'
    11:00-23:00 in quarter-hours, all bookable, because no slot row exists and absence means the
    room is free (finding 3)."""
    service_date = a_service_date()
    response = await reservation_site.client.get(
        "/api/v1/hospitality/reservation-availability",
        params={"service_date": service_date.isoformat(), "party_size": 2},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["party_size"] == 2
    assert len(body["slots"]) == 48
    assert all(slot["bookable"] for slot in body["slots"])
    assert body["slots"][0]["slot_start"] == slot_at(service_date, 11)


async def test_the_grid_read_stays_within_three_queries(
    reservation_site: ReservationWebsite, query_counter: Callable[[], QueryCounter]
) -> None:
    """PERFORMANCE §2, and the reason the counters are read set-based: the auth principal, the
    settings row and ONE read of the night's materialised slots. A per-slot lookup would be 96
    statements on a 24-hour service, which is the shape Q3 names as the trap."""
    service_date = a_service_date()
    await assert_query_budget(
        reservation_site.client,
        query_counter,
        "/api/v1/hospitality/reservation-availability"
        f"?service_date={service_date.isoformat()}&party_size=2",
    )


async def test_a_party_the_property_does_not_seat_is_told_so(
    reservation_site: ReservationWebsite,
) -> None:
    """A grid of forty-eight ``false`` would read as "we are fully booked all night"; the honest
    answer is that a party of fifty is not something this room seats at all."""
    service_date = a_service_date()
    response = await reservation_site.client.get(
        "/api/v1/hospitality/reservation-availability",
        params={"service_date": service_date.isoformat(), "party_size": 50},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "hospitality.party_size_not_accepted"


async def test_the_grid_etag_holds_still_until_a_booking_lands(
    reservation_site: ReservationWebsite,
) -> None:
    """The validator has to move when the answer moves and not before, or the website either serves
    a sold-out slot from cache or re-fetches the whole grid on every page view."""
    service_date = a_service_date()
    url = "/api/v1/hospitality/reservation-availability"
    params = {"service_date": service_date.isoformat(), "party_size": 2}

    first = await reservation_site.client.get(url, params=params)
    etag = first.headers["ETag"]
    assert (await reservation_site.client.get(url, params=params)).headers["ETag"] == etag
    revalidated = await reservation_site.client.get(
        url, params=params, headers={"If-None-Match": etag}
    )
    assert revalidated.status_code == 304
    assert revalidated.content == b""

    booked = await reservation_site.client.post(
        "/api/v1/hospitality/table-reservations",
        json=booking(service_date),
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert booked.status_code == 201, booked.text
    assert (await reservation_site.client.get(url, params=params)).headers["ETag"] != etag


async def test_widening_capacity_moves_the_grid_etag_with_no_slot_row_touched(
    reservation_site: ReservationWebsite, db_session: AsyncSession
) -> None:
    """The lying-validator case (D-073, one table over): a manager changing the DEFAULTS changes
    what every unmaterialised slot answers while ``hsp_service_slots`` holds perfectly still. A
    validator computed from the counters alone would serve a 304 asserting the old capacity."""
    service_date = a_service_date()
    url = "/api/v1/hospitality/reservation-availability"
    params = {"service_date": service_date.isoformat(), "party_size": 8}

    before = await reservation_site.client.get(url, params=params)
    assert all(slot["bookable"] for slot in before.json()["slots"])

    with tenant_context(reservation_site.tenant_id):
        await pacing.set_settings(
            db_session,
            reservation_site.tenant_id,
            pacing.ResolvedSettings(default_covers_max=4),
        )
        await db_session.commit()

    after = await reservation_site.client.get(url, params=params)
    assert after.headers["ETag"] != before.headers["ETag"]
    assert not any(slot["bookable"] for slot in after.json()["slots"])


async def test_a_slot_out_of_parties_is_unbookable_even_with_covers_to_spare(
    reservation_site: ReservationWebsite, db_session: AsyncSession
) -> None:
    """The grid must honour BOTH ceilings. A room with thirty-eight covers free and no table left
    to turn is not bookable, and a website told otherwise sends a guest to a 422 at the last step —
    the pass, not the dining room, is what is full."""
    service_date = a_service_date()
    with tenant_context(reservation_site.tenant_id):
        await pacing.set_settings(
            db_session,
            reservation_site.tenant_id,
            pacing.ResolvedSettings(default_covers_max=40, default_parties_max=1),
        )
        await db_session.commit()
    booked = await reservation_site.client.post(
        "/api/v1/hospitality/table-reservations",
        json=booking(service_date, party_size=2),
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert booked.status_code == 201, booked.text

    grid = await reservation_site.client.get(
        "/api/v1/hospitality/reservation-availability",
        params={"service_date": service_date.isoformat(), "party_size": 2},
    )
    at_seven = next(
        slot for slot in grid.json()["slots"] if slot["slot_start"] == slot_at(service_date, 19)
    )
    assert at_seven["bookable"] is False


# --- Booking ------------------------------------------------------------------


async def test_a_website_booking_is_confirmed_and_numbered(
    reservation_site: ReservationWebsite,
) -> None:
    """Passing the gate IS the confirmation — there is no held-pending-approval state to poll."""
    service_date = a_service_date()
    response = await reservation_site.client.post(
        "/api/v1/hospitality/table-reservations",
        json=booking(service_date, party_size=4),
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "CONFIRMED"
    assert body["reservation_number"].startswith("RSV-")
    assert body["party_size"] == 4


async def test_a_replayed_booking_returns_the_original_reservation(
    reservation_site: ReservationWebsite, db_session: AsyncSession
) -> None:
    """D-013, and this endpoint needs it most: a website retries a timed-out submit with the same
    key forever, and a second attempt must return the first booking rather than take the covers
    twice and seat one guest at two tables.

    Eight covers on the slot and a party of four, so the counter is the assertion: after the replay
    another four must still fit. A replay that ran the gate again would have filled the slot.
    """
    service_date = a_service_date()
    with tenant_context(reservation_site.tenant_id):
        await pacing.set_settings(
            db_session,
            reservation_site.tenant_id,
            pacing.ResolvedSettings(default_covers_max=8),
        )
        await db_session.commit()
    key = str(uuid.uuid4())
    payload = booking(service_date, party_size=4)

    first = await reservation_site.client.post(
        "/api/v1/hospitality/table-reservations", json=payload, headers={"Idempotency-Key": key}
    )
    replay = await reservation_site.client.post(
        "/api/v1/hospitality/table-reservations", json=payload, headers={"Idempotency-Key": key}
    )
    assert first.status_code == replay.status_code == 201
    assert replay.json()["id"] == first.json()["id"]
    assert replay.headers.get("Idempotency-Replayed") == "true"

    grid = await reservation_site.client.get(
        "/api/v1/hospitality/reservation-availability",
        params={"service_date": service_date.isoformat(), "party_size": 4},
    )
    at_seven = next(
        slot for slot in grid.json()["slots"] if slot["slot_start"] == slot_at(service_date, 19)
    )
    assert at_seven["bookable"] is True, "the replay burned a second four covers"


async def test_a_full_slot_answers_with_the_nearest_alternatives(
    reservation_site: ReservationWebsite, db_session: AsyncSession
) -> None:
    """"We are full at 19:00" is a NORMAL answer, and the useful half of it is what else is free.

    The alternatives ride the refusal so the website can offer "19:15 or 19:45 instead" without a
    second round trip — and they are computed after the uow rolled back, so the slot this very
    request materialised cannot report itself as free.
    """
    service_date = a_service_date()
    with tenant_context(reservation_site.tenant_id):
        await pacing.set_settings(
            db_session,
            reservation_site.tenant_id,
            pacing.ResolvedSettings(default_covers_max=4),
        )
        await db_session.commit()

    accepted = await reservation_site.client.post(
        "/api/v1/hospitality/table-reservations",
        json=booking(service_date, party_size=4),
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert accepted.status_code == 201, accepted.text

    refused = await reservation_site.client.post(
        "/api/v1/hospitality/table-reservations",
        json=booking(service_date, party_size=2),
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert refused.status_code == 422, refused.text
    error = refused.json()["error"]
    assert error["code"] == "hospitality.slot_full"
    assert error["details"]["limit"] == "covers"
    alternatives = error["details"]["alternatives"]
    assert slot_at(service_date, 19) not in alternatives
    assert slot_at(service_date, 19, 15) in alternatives


async def test_a_booking_body_carrying_an_unknown_field_is_rejected(
    reservation_site: ReservationWebsite,
) -> None:
    """``extra="forbid"``, the ``WebsiteOrderLine`` argument: a website that sends a field we ignore
    believes it set something, and a silent 201 at different terms is the worst of both worlds."""
    service_date = a_service_date()
    response = await reservation_site.client.post(
        "/api/v1/hospitality/table-reservations",
        json=booking(service_date) | {"table_code": "T12"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert response.status_code == 422, response.text


# --- Cancelling on the guest's behalf -----------------------------------------


async def test_cancelling_before_the_slot_frees_the_table_again(
    reservation_site: ReservationWebsite, db_session: AsyncSession
) -> None:
    """The website cancels for its guest (Q1: whose booking it is, is the website's problem), and
    the covers go back on sale — which is the whole reason a cancellation is a transition rather
    than a delete."""
    service_date = a_service_date()
    with tenant_context(reservation_site.tenant_id):
        await pacing.set_settings(
            db_session,
            reservation_site.tenant_id,
            pacing.ResolvedSettings(default_covers_max=4),
        )
        await db_session.commit()
    booked = await reservation_site.client.post(
        "/api/v1/hospitality/table-reservations",
        json=booking(service_date, party_size=4),
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert booked.status_code == 201, booked.text

    cancelled = await reservation_site.client.post(
        f"/api/v1/hospitality/table-reservations/{booked.json()['id']}/cancel"
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "CANCELLED"

    grid = await reservation_site.client.get(
        "/api/v1/hospitality/reservation-availability",
        params={"service_date": service_date.isoformat(), "party_size": 4},
    )
    at_seven = next(
        slot for slot in grid.json()["slots"] if slot["slot_start"] == slot_at(service_date, 19)
    )
    assert at_seven["bookable"] is True


async def test_cancelling_an_unknown_reservation_is_a_404(
    reservation_site: ReservationWebsite,
) -> None:
    """Not a 500, and not a silent 200: a website holding a stale id must be told plainly."""
    response = await reservation_site.client.post(
        f"/api/v1/hospitality/table-reservations/{uuid.uuid4()}/cancel"
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "hospitality.reservation_not_found"


# --- D-069: the key is exactly as wide as its job -----------------------------


async def test_a_booking_key_cannot_read_the_book_or_the_kitchen(
    reservation_site: ReservationWebsite,
) -> None:
    """The narrowing proof. A credential scoped to ``hospitality.reservation.book`` may take
    bookings and nothing else.

    The BOOK is the one that matters and is asserted first: ``GET /reservations`` returns every
    guest's name and contact detail for the night, and the whole reason ``.book`` is a third key
    rather than an alias for ``.read`` is that a leaked website key must not be a guest list
    (D-069/D-070). The kitchen's open checks are the second thing it cannot walk out with.
    """
    book = await reservation_site.client.get("/api/v1/hospitality/reservations")
    assert book.status_code == 403
    response = await reservation_site.client.get("/api/v1/hospitality/tickets")
    assert response.status_code == 403


async def test_a_menu_key_cannot_book_a_table(
    reservation_site: ReservationWebsite,
) -> None:
    """And the reverse: the key the property's menu page already holds gains nothing from Phase 21.
    A new scope only widens the credentials that are explicitly minted with it."""
    reservation_site.client.headers["Authorization"] = (
        f"Bearer {reservation_site.menu_only_key}"
    )
    response = await reservation_site.client.post(
        "/api/v1/hospitality/table-reservations",
        json=booking(a_service_date()),
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert response.status_code == 403
