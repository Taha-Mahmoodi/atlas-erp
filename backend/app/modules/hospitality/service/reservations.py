"""The table-reservation document and its lifecycle (Phase 21, spec Q3).

An ordinary D-012 document — it registers in ``core_documents`` and claims its gapless ``RSV-``
number at creation, exactly like an order ticket, because a reservation is referenceable by the
guest and the floor the instant it is confirmed. What is specific to a restaurant is WHERE the
counter moves, and that is the whole of finding 4:

    create (gate passes)                 covers += party, parties += 1
    CANCELLED / NO_SHOW before slot      both decrement
    CANCELLED / NO_SHOW at or after      nothing — there is nothing left to resell
    SEATED / COMPLETED                   nothing
    party-size change before slot_start  delta on covers, same locked row
    slot change before slot_start        release the old slot, book the new one, one transaction

That is SIMPLER than the hotel's rule, where a no-show deliberately keeps its count for the
overbooking buffer, and each row has its own named test so nobody unifies them later.

There is no TENTATIVE state: passing the pacing gate IS the confirmation (``ReservationStatus``),
which is why the gate runs inside the create transaction rather than behind it.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.core.auth import as_utc
from app.core.exceptions import ConflictError, NotFoundError
from app.core.models import utcnow
from app.core.numbering import claim_number, ensure_sequence
from app.modules.hospitality.constants import (
    RESERVATION_FLOW,
    RESERVATION_SEATED_AS_TICKET_LINK,
    TABLE_RESERVATION_DOC_TYPE,
    TABLE_RESERVATION_NUMBER_PADDING,
    TABLE_RESERVATION_NUMBER_PREFIX,
    TABLE_RESERVATION_SEQUENCE_NAME,
    ReservationStatus,
)
from app.modules.hospitality.models import TableReservation
from app.modules.hospitality.reservation_schemas import TableReservationCreate
from app.modules.hospitality.schemas import OrderTicketCreate
from app.modules.hospitality.service import pacing, tickets


async def get_reservation(
    session: AsyncSession, tenant_id: uuid.UUID, reservation_id: uuid.UUID
) -> TableReservation:
    """The reservation, or 404 ``hospitality.reservation_not_found``."""
    reservation = await session.get(TableReservation, reservation_id)
    if reservation is None or reservation.tenant_id != tenant_id:
        raise NotFoundError(
            message="Reservation not found", code="hospitality.reservation_not_found"
        )
    return reservation


def _require_transition(
    reservation: TableReservation, to_status: ReservationStatus
) -> ReservationStatus:
    """The lifecycle rule, read off ``RESERVATION_FLOW`` — a branching lifecycle has no "next state"
    arithmetic to lean on, unlike the ticket's straight line. Returns the current status so callers
    that need it do not re-parse the string."""
    current = ReservationStatus(reservation.status)
    if to_status not in RESERVATION_FLOW[current]:
        raise ConflictError(
            message=f"A reservation cannot move from {current.value} to {to_status.value}",
            code="hospitality.reservation_not_transitionable",
            details={
                "reservation_id": str(reservation.id),
                "status": current.value,
                "requested_status": to_status.value,
            },
        )
    return current


async def _apply_transition(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    reservation: TableReservation,
    to_status: ReservationStatus,
) -> None:
    """Move the reservation and mirror the state onto its registry row, so the document-flow viewer
    and the book never disagree (D-012) — the ``tickets._apply_transition`` shape."""
    reservation.status = to_status.value
    await session.flush()
    await docflow.set_document_status(
        session, tenant_id, reservation.document_id, status=to_status.value
    )


def _holds_capacity(reservation: TableReservation) -> bool:
    """Whether this reservation's covers are still worth giving back — finding 4's whole rule in one
    predicate, so "before the slot" is written once and cannot drift between cancel, no-show and
    amend.

    The counter only means something BEFORE the slot starts: after it, the covers cannot be resold
    to anybody, so releasing them would only invite a double-booking of a table that is already
    occupied (or, for a no-show, already lost)."""
    return utcnow() < as_utc(reservation.slot_start)


async def create_reservation(
    session: AsyncSession, tenant_id: uuid.UUID, payload: TableReservationCreate
) -> TableReservation:
    """Book a table: validate, pass the pacing gate, then register and number the document.

    ORDER MATTERS TWICE. The window checks run before the counter, so a request for 09:00 never
    materialises a slot row for a time the room does not sell. The counter runs before the NUMBER,
    because ``claim_number`` holds the tenant's sequence row lock until COMMIT by construction
    (D-012 gaplessness) and Q4 flags that lock as what serializes every other posting in the tenant
    — a refused booking must never have taken it. That is the same ordering ``create_ticket`` uses
    for its item validation, for the same reason.

    A slot earlier TODAY is bookable on purpose: a host taking a party that is walking in in ten
    minutes is an ordinary same-day booking, and the horizon rule already bounds the date.
    """
    settings = await pacing.get_settings(session, tenant_id)
    pacing.require_bookable_slot(
        settings, payload.service_date, payload.slot_start, payload.party_size
    )
    await pacing.book_into_slot(
        session,
        tenant_id,
        payload.service_date,
        payload.slot_start,
        payload.party_size,
        settings=settings,
    )

    reservation_id = uuid.uuid4()
    document = await docflow.register_document(
        session,
        tenant_id,
        TABLE_RESERVATION_DOC_TYPE,
        reservation_id,
        doc_number=None,
        status=ReservationStatus.CONFIRMED.value,
    )
    await ensure_sequence(
        session,
        tenant_id,
        TABLE_RESERVATION_SEQUENCE_NAME,
        TABLE_RESERVATION_NUMBER_PREFIX,
        TABLE_RESERVATION_NUMBER_PADDING,
        year_reset=True,
    )
    number = await claim_number(
        session, tenant_id, TABLE_RESERVATION_SEQUENCE_NAME, on_date=payload.service_date
    )
    reservation = TableReservation(
        id=reservation_id,
        tenant_id=tenant_id,
        document_id=document.id,
        reservation_number=number,
        status=ReservationStatus.CONFIRMED.value,
        service_date=payload.service_date,
        slot_start=payload.slot_start,
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
        status=ReservationStatus.CONFIRMED.value,
    )
    return reservation


async def amend_reservation(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    reservation_id: uuid.UUID,
    *,
    party_size: int | None = None,
    service_date: date | None = None,
    slot_start: datetime | None = None,
) -> TableReservation:
    """Move a booking: a different party size, a different time, or both — the single most common
    thing a host does after taking one.

    CONFIRMED only, and only while the slot has not started: once the party is seated (or the slot
    has gone) the counter no longer means anything and the change is a floor decision, not a booking
    one. Moving to a different slot RELEASES the old and BOOKS the new inside this transaction, so
    a full destination leaves the original booking exactly as it was rather than dropping the guest
    into a gap between two writes. Staying in the same slot takes the delta on the one locked row,
    which is why growing a party can be refused with ``hospitality.slot_full`` while shrinking one
    never is.
    """
    reservation = await get_reservation(session, tenant_id, reservation_id)
    if ReservationStatus(reservation.status) != ReservationStatus.CONFIRMED:
        raise ConflictError(
            message=f"A {reservation.status} reservation cannot be amended",
            code="hospitality.reservation_not_transitionable",
            details={"reservation_id": str(reservation_id), "status": reservation.status},
        )
    if not _holds_capacity(reservation):
        raise ConflictError(
            message="That service slot has already started",
            code="hospitality.reservation_slot_started",
            details={"reservation_id": str(reservation_id)},
        )

    new_party = party_size if party_size is not None else reservation.party_size
    new_date = service_date if service_date is not None else reservation.service_date
    new_slot = slot_start if slot_start is not None else as_utc(reservation.slot_start)
    settings = await pacing.get_settings(session, tenant_id)
    pacing.require_bookable_slot(settings, new_date, new_slot, new_party)

    old_key = (reservation.service_date, as_utc(reservation.slot_start))
    new_key = (new_date, new_slot)
    if old_key != new_key:
        # Two counter rows means a LOCK ORDER, the ``stock_quants.apply_bin_delta`` discipline
        # (D-036): both halves take their row ``with_for_update``, so they take them in key order
        # and two hosts swapping a pair of bookings between 19:00 and 20:00 cannot lock the same
        # pair in opposite orders. A deadlock there reaches the host as a 500, not as a 409.
        # Either order still leaves a full destination harmless: ``book_into_slot`` refuses before
        # mutating anything, so the original booking survives whichever half runs first.
        if old_key < new_key:
            await pacing.release_from_slot(
                session, tenant_id, *old_key, reservation.party_size
            )
            await pacing.book_into_slot(
                session, tenant_id, *new_key, new_party, settings=settings
            )
        else:
            await pacing.book_into_slot(
                session, tenant_id, *new_key, new_party, settings=settings
            )
            await pacing.release_from_slot(
                session, tenant_id, *old_key, reservation.party_size
            )
    elif (delta := new_party - reservation.party_size) > 0:
        # Same slot: take the DELTA on the one locked row, counting NO extra party (they are already
        # one booking). A release-then-rebook pair would let 8 growing to 9 fail on a slot with
        # exactly the room for it.
        await pacing.book_into_slot(
            session, tenant_id, new_date, new_slot, delta, parties=0, settings=settings
        )
    elif delta < 0:
        await pacing.release_from_slot(
            session, tenant_id, new_date, new_slot, -delta, parties=0
        )

    reservation.party_size = new_party
    reservation.service_date = new_date
    reservation.slot_start = new_slot
    await session.flush()
    return reservation


async def seat_reservation(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    reservation_id: uuid.UUID,
    *,
    table_code: str | None,
) -> TableReservation:
    """Sit the party down: mark SEATED and open the check they will order onto.

    The ticket is opened HERE rather than left to the server's terminal so the doc-flow edge exists
    from the moment the party sits — reservation -> ticket -> (Phase 20 folio line) is the chain a
    dispute is read from, and an edge written later is an edge somebody forgets. ``table_code`` is
    free text on the check, exactly as Phase 19 left it: which table is a human's revisable decision
    made at this moment, which is precisely why pacing does not gate on tables.

    NO COUNTER EFFECT. The covers were taken when the booking was confirmed; seating is the party
    arriving to use them, not a second claim. A walk-in needs nothing from this module at all — it
    is the ticket Phase 19 already creates.
    """
    reservation = await get_reservation(session, tenant_id, reservation_id)
    _require_transition(reservation, ReservationStatus.SEATED)
    ticket = await tickets.create_ticket(
        session,
        tenant_id,
        OrderTicketCreate(
            table_code=table_code,
            guest_count=reservation.party_size,
            opened_on=reservation.service_date,
            notes=f"Reservation {reservation.reservation_number} — {reservation.guest_name}",
        ),
    )
    reservation.ticket_id = ticket.id
    await _apply_transition(session, tenant_id, reservation, ReservationStatus.SEATED)
    await docflow.link_documents(
        session,
        tenant_id,
        reservation.document_id,
        ticket.document_id,
        RESERVATION_SEATED_AS_TICKET_LINK,
    )
    return reservation


async def cancel_reservation(
    session: AsyncSession, tenant_id: uuid.UUID, reservation_id: uuid.UUID
) -> TableReservation:
    """Call the booking off, giving the capacity back IF the slot has not started yet (finding 4).

    Refused once the party is SEATED: they are at the table eating, and the correction that is
    actually wanted then is on their check, not on a booking record. ``RESERVATION_FLOW`` is what
    says so, so the rule is stated once.
    """
    reservation = await get_reservation(session, tenant_id, reservation_id)
    _require_transition(reservation, ReservationStatus.CANCELLED)
    if _holds_capacity(reservation):
        await pacing.release_from_slot(
            session,
            tenant_id,
            reservation.service_date,
            as_utc(reservation.slot_start),
            reservation.party_size,
        )
    await _apply_transition(session, tenant_id, reservation, ReservationStatus.CANCELLED)
    return reservation


async def mark_no_show(
    session: AsyncSession, tenant_id: uuid.UUID, reservation_id: uuid.UUID
) -> TableReservation:
    """They never came. Bookkeeping at or after the slot, and a release before it (finding 4).

    A no-show is normally recorded at or after the slot, when the covers cannot be resold to
    anybody; giving them back would offer a table that has been standing empty for an hour and is
    about to turn. The difference from a cancellation is entirely that one arrives in time to be
    useful — which is exactly why an EARLY no-show (a host's mis-click on tomorrow's eight-top)
    must release like a cancel: NO_SHOW is terminal in ``RESERVATION_FLOW``, so covers stranded
    here have no transition left that could ever give them back, and the only remedy would be a
    manager raising ``covers_max`` on that one slot.
    """
    reservation = await get_reservation(session, tenant_id, reservation_id)
    _require_transition(reservation, ReservationStatus.NO_SHOW)
    if _holds_capacity(reservation):
        await pacing.release_from_slot(
            session,
            tenant_id,
            reservation.service_date,
            as_utc(reservation.slot_start),
            reservation.party_size,
        )
    await _apply_transition(session, tenant_id, reservation, ReservationStatus.NO_SHOW)
    return reservation


async def complete_reservation(
    session: AsyncSession, tenant_id: uuid.UUID, reservation_id: uuid.UUID
) -> TableReservation:
    """They ate and left (terminal). Bookkeeping only — the covers were spent when they sat."""
    reservation = await get_reservation(session, tenant_id, reservation_id)
    _require_transition(reservation, ReservationStatus.COMPLETED)
    await _apply_transition(session, tenant_id, reservation, ReservationStatus.COMPLETED)
    return reservation
