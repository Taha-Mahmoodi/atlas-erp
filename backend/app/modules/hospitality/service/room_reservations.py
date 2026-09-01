"""The ROOM reservation document and its lifecycle (PLAN 20.2, spec Q3).

Named ``room_reservations`` and not ``reservations`` because ``service/reservations.py`` next door
is the RESTAURANT's table booking: that one holds a 15-minute pacing slot, this one holds a
room-night allotment, and they share a word and nothing else.

An ordinary D-012 document — numbered ``RMR-`` at creation like the order ticket and the table
booking, because the number is the confirmation reference the guest is given before anything is
sold. What is specific to a HOTEL is where the counter moves:

    create                          TENTATIVE, counter UNTOUCHED
    CONFIRMED                       rooms_sold += 1 on every night of the stay
    CANCELLED (from CONFIRMED)      release every night
    CANCELLED (from TENTATIVE)      nothing — it never took them
    NO_SHOW                         NOTHING RELEASED
    CHECKED_IN / CHECKED_OUT        nothing — the nights are consumed, not re-sold
    date change                     release the old nights, take the new, ONE locked pass

**NO_SHOW releasing nothing is the rule that differs from the restaurant** (D-087): a table
no-showed before its slot is still resellable, a room that stood empty all night is not, and what
pays for that loss is the ``overbooking_limit`` the property sold into in advance.
``test_a_hotel_no_show_keeps_the_night_while_the_restaurant_gives_covers_back`` fails on a merge.

Every counter touch goes through ``allotment.adjust_allotment``: a desk booking, a website booking
and a manager's move must all touch the SAME row, or the room is sold twice by two paths that each
believe they are correct.

**Arrival and departure live in ``room_stays.py``**, which this file reached the STRUCTURE §8.4 cap
by holding. The seam is the BOOK against the OCCUPANCY: what is sold and whether it can be is here,
which physical room the guest is in is there. :func:`get_room_reservation`,
:func:`require_transition` and :func:`apply_transition` are public because that file shares them —
two spellings of "is this move legal" is how the desk and the front desk stop agreeing.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.numbering import claim_number, ensure_sequence
from app.core.pagination import DEFAULT_LIMIT, OrderKey, SortDirection, filter_fingerprint, paginate
from app.core.schemas import Page
from app.modules.hospitality.constants import (
    ROOM_RESERVATION_DOC_TYPE,
    ROOM_RESERVATION_FLOW,
    ROOM_RESERVATION_HOLDS_ALLOTMENT,
    ROOM_RESERVATION_NUMBER_PADDING,
    ROOM_RESERVATION_NUMBER_PREFIX,
    ROOM_RESERVATION_SEQUENCE_NAME,
    RoomReservationStatus,
)
from app.modules.hospitality.models import RoomReservation
from app.modules.hospitality.rooms_schemas import RoomReservationAmend, RoomReservationCreate
from app.modules.hospitality.service import allotment, rate_plans, rooms


async def get_room_reservation(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    reservation_id: uuid.UUID,
    *,
    for_update: bool = False,
) -> RoomReservation:
    """The booking, or 404 ``hospitality.room_reservation_not_found`` — including for another
    tenant's id, which is what stops a desk reading somebody else's arrivals.

    **``for_update=True`` on EVERY transition path, and it is the OUTER lock.** The status is read
    in Python and the counter is guarded by ``hsp_room_type_inventory`` row locks, so without this
    two concurrent confirmations of ONE booking (a double-clicked Confirm button IS two concurrent
    requests) both read TENTATIVE under READ COMMITTED, then serialize perfectly correctly on the
    allotment row and BOTH increment it. ``require_transition`` cannot stop that: it has already run
    on a stale read. The counter is then permanently overstated — the later cancel gives back one
    night, not two — and the property starts refusing room-nights it can honour.

    Reservation FIRST, allotment rows second, so the lock order stays deterministic (D-020/D-036).

    ``populate_existing`` is a GUARD, not the mechanism, and nothing needs it TODAY: every request
    has its own session and this is its first load of the row, so deleting it leaves the whole suite
    (races included) green. It stays because the factory is ``expire_on_commit=False``, so the first
    caller that reads this booking and THEN locks it in one session would be handed the identity
    map's pre-lock copy — Task 5's folio is that caller waiting to happen.

    Reads (``GET``, the arrivals book) pass ``for_update=False`` and take no lock at all — a desk
    refreshing the book must not queue behind a confirmation.
    """
    stmt = select(RoomReservation).where(
        RoomReservation.id == reservation_id, RoomReservation.tenant_id == tenant_id
    )
    if for_update:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    reservation = (await session.execute(stmt)).scalar_one_or_none()
    if reservation is None:
        raise NotFoundError(
            message="Room reservation not found",
            code="hospitality.room_reservation_not_found",
        )
    return reservation


def require_transition(
    reservation: RoomReservation, to_status: RoomReservationStatus
) -> RoomReservationStatus:
    """The lifecycle rule, read off ``ROOM_RESERVATION_FLOW``, returning the current status."""
    current = RoomReservationStatus(reservation.status)
    if to_status not in ROOM_RESERVATION_FLOW[current]:
        raise ConflictError(
            message=f"A room reservation cannot move from {current.value} to {to_status.value}",
            code="hospitality.room_reservation_not_transitionable",
            details={
                "reservation_id": str(reservation.id),
                "status": current.value,
                "requested_status": to_status.value,
            },
        )
    return current


async def apply_transition(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    reservation: RoomReservation,
    to_status: RoomReservationStatus,
) -> None:
    """Move the booking and mirror the state onto its registry row so the document-flow viewer and
    the book never disagree (D-012) — the ``reservations._apply_transition`` shape."""
    reservation.status = to_status.value
    await session.flush()
    await docflow.set_document_status(
        session, tenant_id, reservation.document_id, status=to_status.value
    )


def _nights(reservation: RoomReservation) -> list[date]:
    """The nights this booking sleeps — ``[arrival, departure)``, ascending."""
    return allotment.stay_nights(reservation.arrival_date, reservation.departure_date)


def _holds_allotment(reservation: RoomReservation) -> bool:
    """Whether this booking's nights are ON the counter — written once, so cancel and amend cannot
    drift about what "still owns its nights" means."""
    return RoomReservationStatus(reservation.status) in ROOM_RESERVATION_HOLDS_ALLOTMENT


async def _require_bookable_stay(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    room_type_id: uuid.UUID,
    rate_plan_id: uuid.UUID,
    party_size: int,
    arrival_date: date,
    departure_date: date,
) -> None:
    """Everything a request can get wrong before any night is looked at — ONE function, called by
    both the create and the amend, because two copies of "is this bookable" is how two paths stop
    agreeing. The rate plan must price THIS room type: without the check a suite sells at a single's
    rate through a copy-pasted id, and Task 7's night audit posts that rate every night of the stay.
    """
    if departure_date <= arrival_date:
        raise ValidationFailedError(
            message="A stay must cover at least one night",
            code="hospitality.stay_range_invalid",
            details={
                "arrival_date": arrival_date.isoformat(),
                "departure_date": departure_date.isoformat(),
            },
        )
    room_type = await rooms.get_room_type(session, tenant_id, room_type_id)
    plan = await rate_plans.get_rate_plan(session, tenant_id, rate_plan_id)
    if plan.room_type_id != room_type_id:
        raise ValidationFailedError(
            message="That rate plan does not price this room type",
            code="hospitality.rate_plan_room_type_mismatch",
            details={"rate_plan_id": str(rate_plan_id), "room_type_id": str(room_type_id)},
        )
    if party_size > room_type.base_capacity:
        raise ValidationFailedError(
            message=f"A {room_type.code} sleeps {room_type.base_capacity}",
            code="hospitality.party_size_exceeds_capacity",
            details={
                "party_size": str(party_size),
                "base_capacity": str(room_type.base_capacity),
            },
        )


async def create_room_reservation(
    session: AsyncSession, tenant_id: uuid.UUID, payload: RoomReservationCreate
) -> RoomReservation:
    """Take a booking. It starts TENTATIVE and touches NO counter.

    A hotel enquiry is not a sale: a website booking with no deposit and a corporate hold are both
    real, and both must reach the desk before a room is given away for them.
    :func:`confirm_room_reservation` is where the gate runs — the opposite of the restaurant, where
    passing the pacing gate IS the confirmation (D-077), and deliberately so.
    """
    await _require_bookable_stay(
        session,
        tenant_id,
        room_type_id=payload.room_type_id,
        rate_plan_id=payload.rate_plan_id,
        party_size=payload.party_size,
        arrival_date=payload.arrival_date,
        departure_date=payload.departure_date,
    )

    reservation_id = uuid.uuid4()
    document = await docflow.register_document(
        session,
        tenant_id,
        ROOM_RESERVATION_DOC_TYPE,
        reservation_id,
        doc_number=None,
        status=RoomReservationStatus.TENTATIVE.value,
    )
    await ensure_sequence(
        session,
        tenant_id,
        ROOM_RESERVATION_SEQUENCE_NAME,
        ROOM_RESERVATION_NUMBER_PREFIX,
        ROOM_RESERVATION_NUMBER_PADDING,
        year_reset=True,
    )
    number = await claim_number(
        session, tenant_id, ROOM_RESERVATION_SEQUENCE_NAME, on_date=payload.arrival_date
    )
    reservation = RoomReservation(
        id=reservation_id,
        tenant_id=tenant_id,
        document_id=document.id,
        reservation_number=number,
        status=RoomReservationStatus.TENTATIVE.value,
        room_type_id=payload.room_type_id,
        rate_plan_id=payload.rate_plan_id,
        arrival_date=payload.arrival_date,
        departure_date=payload.departure_date,
        party_size=payload.party_size,
        guest_name=payload.guest_name,
        guest_contact=payload.guest_contact,
        notes=payload.notes,
    )
    session.add(reservation)
    await session.flush()
    await docflow.set_document_status(
        session,
        tenant_id,
        document.id,
        doc_number=number,
        status=RoomReservationStatus.TENTATIVE.value,
    )
    return reservation


async def confirm_room_reservation(
    session: AsyncSession, tenant_id: uuid.UUID, reservation_id: uuid.UUID
) -> RoomReservation:
    """Sell the stay: take one room of the type out of EVERY night, or refuse.

    **The counter touch is the FIRST write in the transaction**, before the status moves and the
    registry row is rewritten — a refusal that has already rewritten a document status has to be
    unwound. It refuses before mutating anything, so a sold-out Saturday leaves this TENTATIVE.
    """
    reservation = await get_room_reservation(session, tenant_id, reservation_id, for_update=True)
    require_transition(reservation, RoomReservationStatus.CONFIRMED)
    await allotment.adjust_allotment(
        session, tenant_id, reservation.room_type_id, _nights(reservation), 1
    )
    await apply_transition(session, tenant_id, reservation, RoomReservationStatus.CONFIRMED)
    return reservation


async def cancel_room_reservation(
    session: AsyncSession, tenant_id: uuid.UUID, reservation_id: uuid.UUID
) -> RoomReservation:
    """Call the stay off, giving every night back if it was holding them. No "too late to release"
    cut-off, unlike the restaurant: a room-night cancelled before it is slept is genuinely
    resellable. A TENTATIVE booking releases nothing — it never took anything. Refused once the
    guest is CHECKED_IN: the correction wanted then is on their folio."""
    reservation = await get_room_reservation(session, tenant_id, reservation_id, for_update=True)
    require_transition(reservation, RoomReservationStatus.CANCELLED)
    if _holds_allotment(reservation):
        await allotment.adjust_allotment(
            session, tenant_id, reservation.room_type_id, _nights(reservation), -1
        )
    await apply_transition(session, tenant_id, reservation, RoomReservationStatus.CANCELLED)
    return reservation


async def mark_room_no_show(
    session: AsyncSession, tenant_id: uuid.UUID, reservation_id: uuid.UUID
) -> RoomReservation:
    """They never arrived. **NOTHING IS RELEASED**: the room stood empty and unsellable all night,
    so there is no night left to give back, and what pays for that loss is the ``overbooking_limit``
    the property sold into in advance. The one transition where the hotel and the restaurant
    deliberately disagree (D-087)."""
    reservation = await get_room_reservation(session, tenant_id, reservation_id, for_update=True)
    require_transition(reservation, RoomReservationStatus.NO_SHOW)
    await apply_transition(session, tenant_id, reservation, RoomReservationStatus.NO_SHOW)
    return reservation


async def amend_room_reservation(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    reservation_id: uuid.UUID,
    payload: RoomReservationAmend,
) -> RoomReservation:
    """Move a stay — different dates, a different party — the commonest thing a desk does after
    taking a booking.

    Not after check-in (the guest is in the room). TENTATIVE holds nothing, so an amend is then a
    plain field update; CONFIRMED releases the old nights and takes the new **in one call**, so both
    row sets are locked in ONE ascending pass. Two calls would be two passes and two lock orders —
    the deadlock D-020/D-036 forbids, reaching a receptionist as a 500 rather than a 409.

    Nights the stay KEEPS net to zero and are neither re-checked nor re-written, so a full hotel can
    still shift a booking by a day. Changing the ROOM TYPE is deliberately not offered: it is two
    counters rather than one and it re-prices the stay, so it is a cancel and a re-book.
    """
    reservation = await get_room_reservation(session, tenant_id, reservation_id, for_update=True)
    current = RoomReservationStatus(reservation.status)
    if current not in (RoomReservationStatus.TENTATIVE, RoomReservationStatus.CONFIRMED):
        raise ConflictError(
            message=f"A {current.value} room reservation cannot be amended",
            code="hospitality.room_reservation_not_transitionable",
            details={"reservation_id": str(reservation_id), "status": current.value},
        )
    new_party = payload.party_size or reservation.party_size
    new_arrival = payload.arrival_date or reservation.arrival_date
    new_departure = payload.departure_date or reservation.departure_date
    await _require_bookable_stay(
        session,
        tenant_id,
        room_type_id=reservation.room_type_id,
        rate_plan_id=reservation.rate_plan_id,
        party_size=new_party,
        arrival_date=new_arrival,
        departure_date=new_departure,
    )
    if _holds_allotment(reservation):
        await allotment.adjust_allotment(
            session,
            tenant_id,
            reservation.room_type_id,
            allotment.stay_nights(new_arrival, new_departure),
            1,
            released_dates=_nights(reservation),
        )
    reservation.party_size = new_party
    reservation.arrival_date = new_arrival
    reservation.departure_date = new_departure
    await session.flush()
    return reservation


async def list_room_reservations(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    status: RoomReservationStatus | None = None,
    arriving_from: date | None = None,
    arriving_to: date | None = None,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Page[RoomReservation]:
    """The arrivals book, in arrival order (D-014 keyset, never OFFSET).

    ONE statement whatever the property's size (PERFORMANCE §2): both filters are served by the
    tenant-leading indexes on the model and nothing is loaded per row. The arrival window is the
    filter the desk uses, and what keeps the read bounded on three years of history.
    """
    stmt = select(RoomReservation).where(RoomReservation.tenant_id == tenant_id)
    if status is not None:
        stmt = stmt.where(RoomReservation.status == status.value)
    if arriving_from is not None:
        stmt = stmt.where(RoomReservation.arrival_date >= arriving_from)
    if arriving_to is not None:
        stmt = stmt.where(RoomReservation.arrival_date <= arriving_to)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(RoomReservation.arrival_date, SortDirection.ASC)],
        pk=RoomReservation.id,
        cursor=cursor,
        limit=limit,
        filters=filter_fingerprint(status, arriving_from, arriving_to),
    )
