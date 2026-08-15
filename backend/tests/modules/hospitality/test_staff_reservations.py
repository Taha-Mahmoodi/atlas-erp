"""The staff BOOK over HTTP (Phase 21 Task 5): take a booking, move it, seat it, close it out, and
set the room's capacity.

Boundary properties only — the guards, the pagination budget, the error codes a host actually sees.
The pacing rules and the transition/counter matrix are proven at the service level in
``test_table_reservations.py``; re-asserting them through the wire would test the same thing twice.

The principal is a full-rights staff JWT: ``create_hospitality_principal`` grants EVERY registered
``hospitality.*`` key, so the three Phase 21 permissions arrived in that grant automatically. The
narrower grants are requested explicitly, per test, which is what makes the 403s readable.
"""

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, date, datetime, time, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import utcnow
from app.modules.hospitality.constants import (
    HOSPITALITY_RESERVATION_BOOK,
    HOSPITALITY_RESERVATION_MANAGE,
    HOSPITALITY_RESERVATION_READ,
)
from tests.conftest import QueryCounter, assert_query_budget
from tests.modules.hospitality.factories import HospitalityPrincipal, mint_website_key


@pytest.fixture
async def book_client(
    client: AsyncClient,
    hospitality_user_factory: Callable[..., Awaitable[HospitalityPrincipal]],
) -> AsyncIterator[AsyncClient]:
    """A logged-in host holding every hospitality key. No kitchen is seeded: a reservation
    references no item, no price and no stock."""
    principal = await hospitality_user_factory(slug="hsp-book", email="host@hsp-book.test")
    yield await _logged_in(client, principal)


async def _logged_in(client: AsyncClient, principal: HospitalityPrincipal) -> AsyncClient:
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": principal.tenant_slug,
            "email": principal.email,
            "password": principal.password,
        },
    )
    assert response.status_code == 200, response.text
    client.headers["Authorization"] = f"Bearer {response.json()['access_token']}"
    return client


def a_service_date(days_ahead: int = 1) -> date:
    return utcnow().date() + timedelta(days=days_ahead)


def slot_at(service_date: date, hour: int, minute: int = 0) -> str:
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
        "guest_name": "Okonkwo",
    }


async def take(client: AsyncClient, payload: dict[str, object]) -> dict[str, object]:
    response = await client.post(
        "/api/v1/hospitality/reservations",
        json=payload,
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert response.status_code == 201, response.text
    return response.json()


# --- The book -----------------------------------------------------------------


async def test_the_book_lists_a_service_in_slot_order(book_client: AsyncClient) -> None:
    """A host reads the book FORWARD through the evening, so the first page is the start of
    service — the opposite of the ticket list, which is a floor's most recent checks."""
    service_date = a_service_date()
    for hour in (21, 19, 20):
        await take(book_client, booking(service_date, hour=hour))

    response = await book_client.get(
        "/api/v1/hospitality/reservations", params={"service_date": service_date.isoformat()}
    )
    assert response.status_code == 200, response.text
    assert [row["slot_start"] for row in response.json()["items"]] == [
        slot_at(service_date, 19),
        slot_at(service_date, 20),
        slot_at(service_date, 21),
    ]


async def test_the_book_filters_by_status(book_client: AsyncClient) -> None:
    """"Who has not shown up?" is the filter a host uses at ten past eight."""
    service_date = a_service_date()
    stood_up = await take(book_client, booking(service_date, hour=19))
    await take(book_client, booking(service_date, hour=20))
    marked = await book_client.post(
        f"/api/v1/hospitality/reservations/{stood_up['id']}/no-show"
    )
    assert marked.status_code == 200, marked.text

    response = await book_client.get(
        "/api/v1/hospitality/reservations",
        params={"service_date": service_date.isoformat(), "status": "NO_SHOW"},
    )
    assert [row["id"] for row in response.json()["items"]] == [stood_up["id"]]


async def test_the_book_stays_within_its_query_budget(
    book_client: AsyncClient, query_counter: Callable[[], QueryCounter]
) -> None:
    """PERFORMANCE §2: the auth principal plus one keyset page, whatever the night's size."""
    service_date = a_service_date()
    for hour in range(18, 22):
        await take(book_client, booking(service_date, hour=hour))
    await assert_query_budget(
        book_client,
        query_counter,
        f"/api/v1/hospitality/reservations?service_date={service_date.isoformat()}",
    )


# --- Transitions over the wire ------------------------------------------------


async def test_a_host_seats_a_party_onto_a_linked_check(book_client: AsyncClient) -> None:
    """Seating opens the check and returns the reservation carrying its id, so the terminal can go
    straight to adding lines without a second lookup."""
    service_date = a_service_date()
    reservation = await take(book_client, booking(service_date, party_size=4))

    seated = await book_client.post(
        f"/api/v1/hospitality/reservations/{reservation['id']}/seat",
        json={"table_code": "T12"},
    )
    assert seated.status_code == 200, seated.text
    assert seated.json()["status"] == "SEATED"

    ticket = await book_client.get(
        f"/api/v1/hospitality/tickets/{seated.json()['ticket_id']}"
    )
    assert ticket.status_code == 200, ticket.text
    assert (ticket.json()["table_code"], ticket.json()["guest_count"]) == ("T12", 4)

    chain = await book_client.get(
        f"/api/v1/documents/{reservation['document_id']}/chain"
    )
    assert chain.status_code == 200, chain.text
    assert [edge["link_type"] for edge in chain.json()["edges"]] == ["seated_as"]


async def test_seating_a_cancelled_booking_is_refused(book_client: AsyncClient) -> None:
    """The transition table over the wire: a 409 naming the state it is in, not a 500 from a table
    that has nothing to seat."""
    service_date = a_service_date()
    reservation = await take(book_client, booking(service_date))
    await book_client.post(f"/api/v1/hospitality/reservations/{reservation['id']}/cancel")

    response = await book_client.post(
        f"/api/v1/hospitality/reservations/{reservation['id']}/seat", json={"table_code": "T1"}
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "hospitality.reservation_not_transitionable"


async def test_a_host_moves_a_booking_to_a_bigger_party_and_a_later_slot(
    book_client: AsyncClient,
) -> None:
    """The commonest call a restaurant takes after the booking itself. Omitted fields are
    unchanged, so correcting the party size does not mean retyping the time."""
    service_date = a_service_date()
    reservation = await take(book_client, booking(service_date, hour=19, party_size=2))

    response = await book_client.patch(
        f"/api/v1/hospitality/reservations/{reservation['id']}",
        json={"party_size": 6, "slot_start": slot_at(service_date, 20)},
    )
    assert response.status_code == 200, response.text
    assert response.json()["party_size"] == 6
    assert response.json()["slot_start"] == slot_at(service_date, 20)
    assert response.json()["service_date"] == service_date.isoformat()


async def test_a_seated_party_is_completed_not_cancelled(book_client: AsyncClient) -> None:
    """The end of the happy path, and the reason COMPLETED exists: clearing a party off tonight's
    book without recording that they never came."""
    service_date = a_service_date()
    reservation = await take(book_client, booking(service_date))
    await book_client.post(
        f"/api/v1/hospitality/reservations/{reservation['id']}/seat", json={"table_code": "T4"}
    )
    response = await book_client.post(
        f"/api/v1/hospitality/reservations/{reservation['id']}/complete"
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "COMPLETED"


# --- Capacity -----------------------------------------------------------------


async def test_settings_round_trip_and_carry_the_grid_step(book_client: AsyncClient) -> None:
    """A property that has never configured anything reads a complete answer, and the write
    replaces it wholesale. ``slot_minutes`` rides along so a client never hard-codes the grid."""
    unset = await book_client.get("/api/v1/hospitality/reservation-settings")
    assert unset.status_code == 200, unset.text
    assert unset.json()["slot_minutes"] == 15

    written = await book_client.put(
        "/api/v1/hospitality/reservation-settings",
        json={
            "service_open": "17:00:00",
            "service_close": "23:00:00",
            "default_covers_max": 60,
            "default_parties_max": 15,
            "min_party": 2,
            "max_party": 10,
            "booking_horizon_days": 60,
        },
    )
    assert written.status_code == 200, written.text
    reread = await book_client.get("/api/v1/hospitality/reservation-settings")
    assert reread.json()["default_covers_max"] == 60
    assert reread.json()["min_party"] == 2


async def test_settings_with_an_impossible_party_range_are_rejected(
    book_client: AsyncClient,
) -> None:
    """A range that admits nobody is a typo, and it comes back as a 422 body error rather than as an
    IntegrityError from the CHECK behind it."""
    response = await book_client.put(
        "/api/v1/hospitality/reservation-settings",
        json={
            "service_open": "17:00:00",
            "service_close": "23:00:00",
            "default_covers_max": 60,
            "default_parties_max": 15,
            "min_party": 10,
            "max_party": 2,
            "booking_horizon_days": 60,
        },
    )
    assert response.status_code == 422, response.text


async def test_a_manager_closes_one_slot(book_client: AsyncClient) -> None:
    """``covers_max = 0`` is the whole closure mechanism — a private event, a boiler failure — and
    the booking that follows is refused like any other full slot."""
    service_date = a_service_date()
    closed = await book_client.put(
        "/api/v1/hospitality/service-slots",
        json={
            "service_date": service_date.isoformat(),
            "slot_start": slot_at(service_date, 19),
            "covers_max": 0,
            "parties_max": 0,
        },
    )
    assert closed.status_code == 200, closed.text
    assert closed.json()["covers_max"] == 0

    refused = await book_client.post(
        "/api/v1/hospitality/reservations",
        json=booking(service_date, hour=19),
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert refused.status_code == 422, refused.text
    assert refused.json()["error"]["code"] == "hospitality.slot_full"


async def test_a_manager_cannot_cut_capacity_under_the_guests_already_holding_it(
    book_client: AsyncClient,
) -> None:
    """Refused, not clamped: the manager is shown the conflict and both numbers, and decides whom
    to call — rather than silently stranding a confirmed booking."""
    service_date = a_service_date()
    await take(book_client, booking(service_date, hour=19, party_size=8))

    response = await book_client.put(
        "/api/v1/hospitality/service-slots",
        json={
            "service_date": service_date.isoformat(),
            "slot_start": slot_at(service_date, 19),
            "covers_max": 4,
            "parties_max": 10,
        },
    )
    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] == "hospitality.slot_override_below_booked"
    assert error["details"]["covers_booked"] == "8"


# --- Permissions --------------------------------------------------------------


async def test_reading_the_book_needs_the_read_key(
    client: AsyncClient,
    hospitality_user_factory: Callable[..., Awaitable[HospitalityPrincipal]],
) -> None:
    """A principal that may change bookings is not automatically one that may read the whole
    night's guest list; the two keys are granted separately for exactly that reason."""
    principal = await hospitality_user_factory(
        slug="hsp-mgr", email="mgr@hsp-mgr.test", keys=(HOSPITALITY_RESERVATION_MANAGE,)
    )
    manage_only = await _logged_in(client, principal)
    assert (await manage_only.get("/api/v1/hospitality/reservations")).status_code == 403


async def test_changing_a_booking_needs_the_manage_key(
    client: AsyncClient,
    hospitality_user_factory: Callable[..., Awaitable[HospitalityPrincipal]],
) -> None:
    """And the reverse: a screen on the pass reads the book without being able to cancel anybody's
    table."""
    principal = await hospitality_user_factory(
        slug="hsp-pass", email="pass@hsp-pass.test", keys=(HOSPITALITY_RESERVATION_READ,)
    )
    read_only = await _logged_in(client, principal)
    response = await read_only.post(
        "/api/v1/hospitality/reservations",
        json=booking(a_service_date()),
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert response.status_code == 403


async def test_a_staff_booking_and_a_website_booking_share_one_counter(
    client: AsyncClient,
    db_session: AsyncSession,
    hospitality_user_factory: Callable[..., Awaitable[HospitalityPrincipal]],
) -> None:
    """One gate, every writer — the availability module's lesson. A phone booking that decremented
    a different counter from the website's would oversell the room from the one direction nobody
    watches, so the staff route is refused by exactly the slot the WEBSITE filled.

    The two surfaces are the point, so each booking really goes through its own: the first over the
    website's ``hospitality.reservation.book`` machine credential on ``/table-reservations``, the
    second over the host's JWT on ``/reservations``. Posting both through one router would pass
    identically if the website router were ever pointed at a second counter.
    """
    principal = await hospitality_user_factory(slug="hsp-both", email="host@hsp-both.test")
    staff = await _logged_in(client, principal)
    website_key = await mint_website_key(
        db_session, principal, name="bookings", scopes=[HOSPITALITY_RESERVATION_BOOK]
    )
    service_date = a_service_date()
    await staff.put(
        "/api/v1/hospitality/reservation-settings",
        json={
            "service_open": "11:00:00",
            "service_close": "23:00:00",
            "default_covers_max": 4,
            "default_parties_max": 12,
            "min_party": 1,
            "max_party": 12,
            "booking_horizon_days": 90,
        },
    )
    from_website = await client.post(
        "/api/v1/hospitality/table-reservations",
        json=booking(service_date, hour=19, party_size=4),
        headers={
            "Idempotency-Key": str(uuid.uuid4()),
            "Authorization": f"Bearer {website_key}",
        },
    )
    assert from_website.status_code == 201, from_website.text

    response = await staff.post(
        "/api/v1/hospitality/reservations",
        json=booking(service_date, hour=19, party_size=1),
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "hospitality.slot_full"
