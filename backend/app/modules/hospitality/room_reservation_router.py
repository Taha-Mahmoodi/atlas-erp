"""The room-reservation HTTP surface (PLAN 20.2) — the desk's book and the property's website.

A FIFTH hospitality router on the same ``/api/v1/hospitality`` prefix (the ``menu_router`` /
``reservation_router`` / ``rooms_router`` precedent, D-030/D-031), because ``rooms_router.py`` is at
368 lines against the STRUCTURE §8.4 cap and the booking is a different document family from the
masters it sells.

**Two ``APIRouter``s in one file, unlike the table booking's two files.** The split that matters is
by PRINCIPAL and it is preserved — the website router mounts its own guard and its own D-013
namespace — but the website's whole surface here is ONE route that shares ``_create`` with the
desk's, and a second file for it would be the same import list twice. Task 9 adds the
room-availability read to ``website_router.py`` where the other cacheable guest reads already live.

**Paths.** ``/room-reservations`` for the desk, ``/website/room-reservations`` for the website —
the same noun on both, because a room reservation is one concept and STRUCTURE §7's terminology lock
does not let the website surface invent a second word for it. The prefix segment is what keeps the
two apart on one mount prefix; the table booking got away with two different nouns only because
Phase 21's staff route was already at the short ``/reservations``.

Thin by construction: every route is a guard, a uow and a schema. Which moves are legal, and which
of them touch the allotment counter, live in ``service/room_reservations.py`` so the desk and the
website cannot disagree.
"""

import uuid
from collections.abc import Awaitable, Callable
from datetime import date

from fastapi import APIRouter, Depends

from app.core.deps import CurrentUserDep, SessionDep
from app.core.events import run_in_uow
from app.core.idempotency import Idempotent, IdempotentDep
from app.core.pagination import CursorParams, cursor_params, map_page
from app.core.rbac import require_permission
from app.core.schemas import Page
from app.modules.hospitality.constants import (
    HOSPITALITY_ROOM_RESERVATION_BOOK,
    HOSPITALITY_ROOM_RESERVATION_MANAGE,
    HOSPITALITY_ROOM_RESERVATION_READ,
    RoomReservationStatus,
)
from app.modules.hospitality.models import RoomReservation
from app.modules.hospitality.rooms_schemas import (
    RoomCheckIn,
    RoomReservationAmend,
    RoomReservationCreate,
    RoomReservationRead,
)
from app.modules.hospitality.service import room_reservations, room_stays

router = APIRouter(prefix="/api/v1/hospitality", tags=["hospitality-rooms"])
website_router = APIRouter(prefix="/api/v1/hospitality", tags=["hospitality-website"])

CursorParamsDep = Depends(cursor_params)
_ReadGuard = Depends(require_permission(HOSPITALITY_ROOM_RESERVATION_READ))
_ManageGuard = Depends(require_permission(HOSPITALITY_ROOM_RESERVATION_MANAGE))
_BookGuard = Depends(require_permission(HOSPITALITY_ROOM_RESERVATION_BOOK))
# D-013 on the two creates, in SEPARATE namespaces: a website replay must never collide with a
# desk's, and the two are different requests even at the same key (the table booking's precedent).
_DeskIdempotentDep = Depends(Idempotent("hospitality.room_reservation.create"))
_WebsiteIdempotentDep = Depends(Idempotent("hospitality.room_reservation.book"))

Transition = Callable[[SessionDep, uuid.UUID, uuid.UUID], Awaitable[RoomReservation]]


async def _create(
    session: SessionDep,
    tenant_id: uuid.UUID,
    payload: RoomReservationCreate,
    idem: IdempotentDep,
) -> RoomReservationRead:
    """Take one booking and capture it for D-013 replay. Shared by both surfaces — "one gate, every
    writer" applied one step earlier: the desk and the website must create the same TENTATIVE
    document, or confirming a website booking would be a different code path from confirming a
    phone one."""
    holder: dict[str, RoomReservationRead] = {}

    async def work() -> None:
        reservation = await room_reservations.create_room_reservation(session, tenant_id, payload)
        await session.refresh(reservation)
        holder["read"] = await idem.capture(
            RoomReservationRead.model_validate(reservation), status_code=201
        )

    await run_in_uow(session, work)
    return holder["read"]


async def _transition(
    session: SessionDep, tenant_id: uuid.UUID, reservation_id: uuid.UUID, action: Transition
) -> RoomReservationRead:
    """Run one lifecycle move in its own uow and render the result. Every transition route is this
    plus a guard, which is what keeps the HTTP layer thin (STRUCTURE §3)."""
    holder: dict[str, RoomReservationRead] = {}

    async def work() -> None:
        reservation = await action(session, tenant_id, reservation_id)
        await session.refresh(reservation)
        holder["read"] = RoomReservationRead.model_validate(reservation)

    await run_in_uow(session, work)
    return holder["read"]


# --- The desk -----------------------------------------------------------------


@router.get(
    "/room-reservations", response_model=Page[RoomReservationRead], dependencies=[_ReadGuard]
)
async def list_room_reservations(
    current: CurrentUserDep,
    session: SessionDep,
    status: RoomReservationStatus | None = None,
    arriving_from: date | None = None,
    arriving_to: date | None = None,
    params: CursorParams = CursorParamsDep,
) -> Page[RoomReservationRead]:
    """The arrivals book, in arrival order (D-014 keyset, never OFFSET). The date window is the
    filter the desk actually uses and what keeps the read bounded on years of history."""
    page = await room_reservations.list_room_reservations(
        session,
        current.tenant_id,
        status=status,
        arriving_from=arriving_from,
        arriving_to=arriving_to,
        cursor=params.cursor,
        limit=params.limit,
    )
    return map_page(page, RoomReservationRead)


@router.get(
    "/room-reservations/{reservation_id}",
    response_model=RoomReservationRead,
    dependencies=[_ReadGuard],
)
async def read_room_reservation(
    reservation_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> RoomReservationRead:
    """One booking, or 404 — including for another tenant's id."""
    reservation = await room_reservations.get_room_reservation(
        session, current.tenant_id, reservation_id
    )
    return RoomReservationRead.model_validate(reservation)


@router.post(
    "/room-reservations",
    response_model=RoomReservationRead,
    status_code=201,
    dependencies=[_ManageGuard],
)
async def create_room_reservation(
    payload: RoomReservationCreate,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _DeskIdempotentDep,
) -> RoomReservationRead:
    """Take a booking over the phone. It starts TENTATIVE and holds no room-night; ``/confirm`` is
    the sale. IDEMPOTENT (D-013): the booking registers a numbered document, so a retried submit
    must return the first one rather than burn a second RMR- number."""
    return await _create(session, current.tenant_id, payload, idem)


@router.patch(
    "/room-reservations/{reservation_id}",
    response_model=RoomReservationRead,
    dependencies=[_ManageGuard],
)
async def amend_room_reservation(
    reservation_id: uuid.UUID,
    payload: RoomReservationAmend,
    current: CurrentUserDep,
    session: SessionDep,
) -> RoomReservationRead:
    """Move the dates or the party size. A CONFIRMED stay releases its old nights and takes the new
    ones in ONE locked pass; a full destination refuses and leaves the booking exactly as it was.

    No idempotency key: an amend creates no document, and replaying it lands on the same state —
    which is only true because the reservation row is taken ``with_for_update`` first, so two
    concurrent moves of one booking serialize instead of both releasing the same old nights."""
    holder: dict[str, RoomReservationRead] = {}

    async def work() -> None:
        reservation = await room_reservations.amend_room_reservation(
            session, current.tenant_id, reservation_id, payload
        )
        await session.refresh(reservation)
        holder["read"] = RoomReservationRead.model_validate(reservation)

    await run_in_uow(session, work)
    return holder["read"]


@router.post(
    "/room-reservations/{reservation_id}/confirm",
    response_model=RoomReservationRead,
    dependencies=[_ManageGuard],
)
async def confirm_room_reservation(
    reservation_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> RoomReservationRead:
    """Sell the stay. 422 ``hospitality.room_type_sold_out`` is a NORMAL ANSWER naming the night
    that refused, so the desk can offer around it.

    No idempotency key: the document already exists, and a second SEQUENTIAL attempt is rejected
    409 ``hospitality.room_reservation_not_transitionable`` by the transition table (the
    ``/settle`` precedent).

    **What makes a double-CLICK safe is the row lock, not that table.** A double-clicked Confirm
    button is two CONCURRENT requests, and the transition table is an in-Python read on whatever was
    loaded: under READ COMMITTED both racers see TENTATIVE, both pass it, and both then serialize
    perfectly correctly on the allotment row and BOTH take them — one booking, two room-nights, and
    a counter permanently overstated, because the later cancel gives back only one. So
    ``room_reservations.get_room_reservation`` takes the reservation ``with_for_update`` BEFORE the
    allotment pass, and the loser's re-read under that lock is what sees CONFIRMED and answers 409.
    Pinned by ``test_two_concurrent_confirmations_of_one_booking_take_the_nights_once`` (``-m pg``),
    which reports ``["confirmed", "confirmed"]`` with the lock deleted."""
    return await _transition(
        session,
        current.tenant_id,
        reservation_id,
        room_reservations.confirm_room_reservation,
    )


@router.post(
    "/room-reservations/{reservation_id}/check-in",
    response_model=RoomReservationRead,
    dependencies=[_ManageGuard],
)
async def check_in_room_reservation(
    reservation_id: uuid.UUID,
    payload: RoomCheckIn,
    current: CurrentUserDep,
    session: SessionDep,
) -> RoomReservationRead:
    """Put the guest in a physical room. The room must be of the booked type, not out of order, and
    **EMPTY** — 409 ``hospitality.room_occupied`` names the booking already in there. The counter is
    untouched, because the nights were taken at confirmation.

    Exclusivity starts here and nowhere earlier: the gate sells a room TYPE, so two confirmed
    doubles on one night are a correct book and this is the call that decides which of them gets
    101."""
    holder: dict[str, RoomReservationRead] = {}

    async def work() -> None:
        reservation = await room_stays.check_in_room_reservation(
            session, current.tenant_id, reservation_id, payload.room_id
        )
        await session.refresh(reservation)
        holder["read"] = RoomReservationRead.model_validate(reservation)

    await run_in_uow(session, work)
    return holder["read"]


@router.post(
    "/room-reservations/{reservation_id}/check-out",
    response_model=RoomReservationRead,
    dependencies=[_ManageGuard],
)
async def check_out_room_reservation(
    reservation_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> RoomReservationRead:
    """They slept and left. Terminal, and the counter is untouched — the nights were spent."""
    return await _transition(
        session,
        current.tenant_id,
        reservation_id,
        room_stays.check_out_room_reservation,
    )


@router.post(
    "/room-reservations/{reservation_id}/cancel",
    response_model=RoomReservationRead,
    dependencies=[_ManageGuard],
)
async def cancel_room_reservation(
    reservation_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> RoomReservationRead:
    """Call the stay off, releasing every night it was holding. A double-clicked Cancel releases
    them ONCE: the reservation row is taken ``with_for_update`` before the release, so the second
    request re-reads CANCELLED and answers 409 rather than double-releasing into the ``max(0, ...)``
    floor and silently putting a room back on sale that was never taken."""
    return await _transition(
        session, current.tenant_id, reservation_id, room_reservations.cancel_room_reservation
    )


@router.post(
    "/room-reservations/{reservation_id}/no-show",
    response_model=RoomReservationRead,
    dependencies=[_ManageGuard],
)
async def mark_room_no_show(
    reservation_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> RoomReservationRead:
    """They never arrived. **Releases NOTHING** — the room stood empty, and the loss is what
    ``overbooking_limit`` was sold against (D-087). Not the restaurant's rule, deliberately."""
    return await _transition(
        session, current.tenant_id, reservation_id, room_reservations.mark_room_no_show
    )


# --- The property's website ---------------------------------------------------


@website_router.post(
    "/website/room-reservations",
    response_model=RoomReservationRead,
    status_code=201,
    dependencies=[_BookGuard],
)
async def book_room_from_website(
    payload: RoomReservationCreate,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _WebsiteIdempotentDep,
) -> RoomReservationRead:
    """Take a booking on a guest's behalf. It comes back **TENTATIVE**, and that is the contract.

    An external client never silently skips a human check (Q6, the ``place_website_order``
    acknowledgment rule): the request shape has no ``status`` field and ``extra="forbid"`` REJECTS
    one, so a website cannot assert its booking into CONFIRMED, and ``room_reservation.book`` cannot
    reach ``/confirm`` either. What confirms a stay is a member of staff or (Task 2) a recorded
    deposit; taking payment on the booking is out until a payment provider exists. The response's
    ``status`` is authoritative so the website can say "we will confirm within the hour" rather than
    guess.

    IDEMPOTENT (D-013): a website retries a timed-out submit with the same key forever, and a second
    attempt must return the first booking rather than raise a second document. A 409
    ``idempotency.in_progress`` means RETRY LATER WITH THE SAME KEY — minting a new key on a 409 is
    exactly how the duplicate this mechanism prevents gets created.

    No room-nights are taken here, so there is no sold-out answer to give: the counter is consulted
    at confirmation. That is deliberate — a TENTATIVE booking a property later cannot honour is a
    phone call, while a website that could confirm would be selling rooms with no human in the loop.
    """
    return await _create(session, current.tenant_id, payload, idem)
