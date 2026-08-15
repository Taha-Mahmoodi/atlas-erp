"""The reservation HTTP surface (Phase 21): the property's WEBSITE and the staff BOOK.

A sibling router file rather than more of ``router.py`` / ``website_router.py``, the
``finance/ap_router.py`` precedent (D-030/D-031) — those two are already near STRUCTURE §8.4's
400-line cap, and reservations are a whole second document family. Both routers live HERE, in one
file, because they are two views of ONE surface and every rule they share (the gate, the counter,
the transition table) is one import away from both; ``industry/router.py`` already ships two
``APIRouter``s in a file for the same reason.

**Two principals, two widths (D-069).** ``website_router`` is what the property's own website calls
under a machine credential scoped to ``hospitality.reservation.book`` and NOTHING else: it can ask
what is bookable, book, and cancel on a guest's behalf. It cannot read the book — that is
``hospitality.reservation.read``, which is every guest's name and phone number for the night, and a
leaked website key must not be a guest list. Q1's boundary holds throughout: the website has already
authenticated its guest and owns notification, and Atlas exposes tenant-scoped operations.

**422 ``hospitality.slot_full`` is a NORMAL ANSWER on the booking route**, not an error state, and
it carries the nearest bookable alternatives so the website can offer "19:15 or 19:45 instead"
without a second round trip. The alternatives are computed AFTER the uow has rolled back, from the
committed state, so a slot the refused booking had just materialised cannot report itself as free.
"""

import uuid
from collections.abc import Awaitable, Callable
from datetime import date, datetime

from fastapi import APIRouter, Depends, Query, Request, Response

from app.core.auth import as_utc
from app.core.conditional import check_not_modified, request_fingerprint
from app.core.deps import CurrentUserDep, SessionDep
from app.core.events import run_in_uow
from app.core.exceptions import ValidationFailedError
from app.core.idempotency import Idempotent, IdempotentDep
from app.core.rbac import require_permission
from app.modules.hospitality import queries
from app.modules.hospitality.constants import HOSPITALITY_RESERVATION_BOOK
from app.modules.hospitality.models import ServiceSlot, TableReservation
from app.modules.hospitality.reservation_schemas import (
    ReservationAvailabilityRead,
    SlotOfferRead,
    TableReservationCreate,
    TableReservationRead,
)
from app.modules.hospitality.service import pacing, reservations

website_router = APIRouter(prefix="/api/v1/hospitality", tags=["hospitality-website"])

_BookGuard = Depends(require_permission(HOSPITALITY_RESERVATION_BOOK))
# Its own D-013 namespace, distinct from the staff booking route: a website replay must never
# collide with a host's, and the two are different requests even at the same key.
_WebsiteBookIdempotentDep = Depends(Idempotent("hospitality.table_reservation.book"))

# The grid is fast-changing state, exactly like the 86 board: a stale "bookable" sells a table that
# is gone, so it is never served without asking. ``stale-if-error`` fails OPEN for five minutes,
# which is the same trade Q6 makes for availability — a booking Atlas then refuses is a normal
# restaurant apology; a booking form that will not load is lost revenue.
GRID_CACHE_CONTROL = "no-cache, must-revalidate, stale-if-error=300"


def _offers(
    settings: pacing.ResolvedSettings,
    counters: dict[datetime, ServiceSlot],
    service_date: date,
    party_size: int,
) -> list[SlotOfferRead]:
    """Overlay the materialised counters onto the settings grid — finding 3 rendered.

    A slot with no row is bookable against the DEFAULTS (absence means the room is free, not that it
    is closed); a slot with a row is bookable if this party still fits under both of its ceilings.
    Pure, and driven by data both callers already hold, so the 422's alternatives and the grid read
    can never disagree about what is free.
    """
    offers: list[SlotOfferRead] = []
    for at in pacing.slot_times(settings, service_date):
        slot = counters.get(at)
        if slot is None:
            bookable = (
                party_size <= settings.default_covers_max and settings.default_parties_max >= 1
            )
        else:
            bookable = (
                slot.covers_booked + party_size <= slot.covers_max
                and slot.parties_booked < slot.parties_max
            )
        offers.append(SlotOfferRead(slot_start=at, bookable=bookable))
    return offers


def _grid_etag(
    tenant_id: uuid.UUID,
    settings: pacing.ResolvedSettings,
    counters: dict[datetime, ServiceSlot],
    fingerprint: str,
) -> str:
    """The grid's weak validator, computed from rows the request has ALREADY loaded.

    Deliberately not ``collection_etag`` (D-035), which every other conditional read in Atlas uses.
    That helper issues its own aggregate SELECT, and this endpoint's body needs both the settings
    row and the day's counters — a fourth statement would put the 200 path over PERFORMANCE §2's
    ≤3. Computing ``(count, max updated_at)`` from the loaded rows is the same signal for free, and
    NARROWER: it moves only when THIS service date changes, where the table-wide aggregate would
    invalidate every night whenever any night was booked.

    ``settings.version`` is the third component and is not optional: a manager widening
    ``default_covers_max`` changes what an unmaterialised slot answers without touching a single
    counter row, and a validator blind to it would serve a 304 asserting the old capacity (D-073's
    lying validator, one table over). The tenant component makes a cross-tenant match impossible
    even in theory, and the request fingerprint pins the date and party size the body was built for.
    """
    newest = max(
        (int(as_utc(slot.updated_at).timestamp() * 1_000_000) for slot in counters.values()),
        default=0,
    )
    return (
        f'W/"{len(counters)}-{newest}-{settings.version}-{tenant_id.hex[:8]}-{fingerprint}"'
    )


async def _read_grid(
    session: SessionDep, tenant_id: uuid.UUID, service_date: date, party_size: int
) -> tuple[pacing.ResolvedSettings, dict[datetime, ServiceSlot], list[SlotOfferRead]]:
    """The two statements behind every availability answer: the settings row and the day's
    counters. Validates the party size and the date against the booking window first, so a request
    for a party the property does not seat is told so rather than handed a grid of ``false``."""
    settings = await pacing.get_settings(session, tenant_id)
    grid = pacing.slot_times(settings, service_date)
    # The first slot is aligned and in-window by construction, so this validates exactly the two
    # things a whole-day question can get wrong: the party size and the date.
    pacing.require_bookable_slot(settings, service_date, grid[0], party_size)
    counters = await queries.slot_counters(session, tenant_id, service_date)
    return settings, counters, _offers(settings, counters, service_date, party_size)


# --- The property's website ---------------------------------------------------


@website_router.get(
    "/reservation-availability",
    response_model=ReservationAvailabilityRead,
    dependencies=[_BookGuard],
)
async def read_reservation_availability(
    request: Request,
    response: Response,
    current: CurrentUserDep,
    session: SessionDep,
    service_date: date,
    party_size: int = Query(ge=1),
) -> ReservationAvailabilityRead | Response:
    """What a party of this size can book on this date — the whole day's grid, one boolean a slot.

    THREE statements flat (PERFORMANCE §2): the auth principal, the settings row, and one set-based
    read of the night's materialised counters. Never a query per slot — a 24-hour service is 96
    slots, and the per-slot shape is the failure Q3 names.

    Conditional GET (D-035 in spirit): the validator is built from the rows this request already
    loaded rather than from a separate aggregate, because a fourth statement would breach the
    budget. See ``_grid_etag`` for why the settings stamp is part of it.
    """
    response.headers["Cache-Control"] = GRID_CACHE_CONTROL
    settings, counters, offers = await _read_grid(
        session, current.tenant_id, service_date, party_size
    )
    etag = _grid_etag(
        current.tenant_id,
        settings,
        counters,
        request_fingerprint(None, 0, service_date, party_size),
    )
    if check_not_modified(request, etag):
        return Response(
            status_code=304, headers={"ETag": etag, "Cache-Control": GRID_CACHE_CONTROL}
        )
    response.headers["ETag"] = etag
    return ReservationAvailabilityRead(
        service_date=service_date, party_size=party_size, slots=offers
    )


async def _book(
    session: SessionDep,
    tenant_id: uuid.UUID,
    payload: TableReservationCreate,
    idem: IdempotentDep,
) -> TableReservationRead:
    """Run one booking through the gate and capture it for D-013 replay.

    Shared by both surfaces, because "one gate, every writer" is the availability module's lesson:
    a host taking a phone booking and a guest booking online must decrement the same counter, or the
    room is sold twice by two code paths that each believe they are correct.
    """
    holder: dict[str, TableReservationRead] = {}

    async def work() -> None:
        reservation = await reservations.create_reservation(session, tenant_id, payload)
        await session.refresh(reservation)
        holder["read"] = await idem.capture(
            TableReservationRead.model_validate(reservation), status_code=201
        )

    await run_in_uow(session, work)
    return holder["read"]


async def _transition(
    session: SessionDep,
    tenant_id: uuid.UUID,
    reservation_id: uuid.UUID,
    action: Callable[[SessionDep, uuid.UUID, uuid.UUID], Awaitable[TableReservation]],
) -> TableReservationRead:
    """Run one lifecycle move in its own uow and render the result. Every transition route is this
    plus a guard, which is what keeps the HTTP layer thin (STRUCTURE §3) — the rules, including
    which moves are legal and which touch the counter, live in the service."""
    holder: dict[str, TableReservationRead] = {}

    async def work() -> None:
        reservation = await action(session, tenant_id, reservation_id)
        await session.refresh(reservation)
        holder["read"] = TableReservationRead.model_validate(reservation)

    await run_in_uow(session, work)
    return holder["read"]


@website_router.post(
    "/table-reservations",
    response_model=TableReservationRead,
    status_code=201,
    dependencies=[_BookGuard],
)
async def book_table_from_website(
    payload: TableReservationCreate,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _WebsiteBookIdempotentDep,
) -> TableReservationRead:
    """Book a table on a guest's behalf.

    IDEMPOTENT (D-013): a website retries a timed-out submit with the same key forever, and a second
    attempt must return the first booking rather than take the covers twice. A 409
    ``idempotency.in_progress`` means RETRY LATER WITH THE SAME KEY — minting a new key on a 409 is
    exactly how the duplicate this mechanism prevents gets created.

    A FULL SLOT IS A NORMAL ANSWER. The 422 is re-raised carrying ``alternatives``: the nearest
    bookable slots for this party on this date, computed after the uow rolled back so the slot this
    very request may have materialised cannot report itself as free.
    """
    try:
        return await _book(session, current.tenant_id, payload, idem)
    except ValidationFailedError as exc:
        if exc.code != "hospitality.slot_full":
            raise
        _, _, offers = await _read_grid(
            session, current.tenant_id, payload.service_date, payload.party_size
        )
        raise ValidationFailedError(
            message=exc.message,
            code=exc.code,
            details=exc.details
            | {
                # Rendered THROUGH the schema, not with ``isoformat()``: the grid emits Pydantic's
                # ``...Z`` spelling and a website comparing these strings against slots it already
                # holds must not be handed ``+00:00`` for the same instant.
                "alternatives": [
                    offer.model_dump(mode="json")["slot_start"]
                    for offer in offers
                    if offer.bookable
                ]
            },
        ) from exc


@website_router.post(
    "/table-reservations/{reservation_id}/cancel",
    response_model=TableReservationRead,
    dependencies=[_BookGuard],
)
async def cancel_reservation_from_website(
    reservation_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> TableReservationRead:
    """Cancel on the guest's behalf, releasing the covers if the slot has not started (finding 4).

    WHICH guest may cancel WHICH booking is the website's problem, not Atlas's — Q1's boundary: the
    website authenticates its guest and calls a tenant-scoped operation under its own credential.
    Refused once the party is SEATED (409): they are at the table, and the correction wanted then is
    on their check.

    No idempotency key: cancelling creates no document, and the transition table already rejects a
    second attempt with 409 ``hospitality.reservation_not_transitionable`` (the ``/settle``
    precedent).
    """
    return await _transition(
        session, current.tenant_id, reservation_id, reservations.cancel_reservation
    )
