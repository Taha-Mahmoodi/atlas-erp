"""ARRIVAL AND DEPARTURE: putting a guest into a physical room and taking them out again
(PLAN 20.2).

Split out of ``room_reservations.py`` for the reason ``rate_plans.py`` was split out of ``rooms.py``
— that file reached the STRUCTURE §8.4 cap and this is a real aggregate rather than an arithmetic
half. The seam: ``room_reservations.py`` owns the BOOK (what is sold, and the allotment counter that
says whether it can be), and this file owns the OCCUPANCY (which physical room the guest is in). It
is the only place in the phase that reads ``Room`` or writes ``RoomReservation.room_id``, and it is
where Task 5's folio hangs — a folio opens at check-in and settles at check-out.

**Neither transition touches the allotment counter**, and that is the rule the file exists to state:
the nights were taken at confirmation, so arriving is the guest USING them and leaving is the guest
having SPENT them. A second counter touch on either would sell the same night twice.

What arrival DOES own is EXCLUSIVITY. The counter sells a room TYPE, so two confirmed doubles are a
correct book and nothing before this file decides which physical room either of them gets; the one
place that fact becomes exclusive is here, and it is held by a read plus a partial unique index on
``(tenant_id, room_id) WHERE status = 'CHECKED_IN'``.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ValidationFailedError
from app.modules.hospitality.constants import (
    HOUSEKEEPING_UNSELLABLE,
    HousekeepingStatus,
    RoomReservationStatus,
)
from app.modules.hospitality.models import RoomReservation
from app.modules.hospitality.service import rooms
from app.modules.hospitality.service.room_reservations import (
    apply_transition,
    get_room_reservation,
    require_transition,
)


async def check_in_room_reservation(
    session: AsyncSession, tenant_id: uuid.UUID, reservation_id: uuid.UUID, room_id: uuid.UUID
) -> RoomReservation:
    """Put the guest in a physical room. NO COUNTER EFFECT — the nights were taken at confirmation;
    arriving is the guest using them, not a second claim.

    THREE refusals, and the third is the one a guest actually feels: the room must be of the booked
    TYPE (so a double is not handed a single), it must not be in ``HOUSEKEEPING_UNSELLABLE``, and
    **it must be EMPTY**. Nothing above this makes a room exclusive — the allotment counter sells
    the TYPE, so two confirmed doubles are a correct book and it is check-in that decides which of
    them gets 101 — so without the occupancy read a desk hands two guests the same key and the
    second walks in on the first.

    Both halves are needed and neither is redundant. The read gives a readable 409
    ``hospitality.room_occupied`` naming the booking already in there; the partial unique index
    ``uq_hsp_room_reservations_tenant_id_room_id_checked_in`` is the backstop that holds if some
    later path writes ``room_id`` without coming through here. What makes the READ trustworthy under
    concurrency is the ``for_update`` on the room: two receptionists checking two different guests
    into 101 at the same instant serialize on that row, so the loser's read sees the winner and
    answers 409 rather than reaching the index as a 500.
    """
    reservation = await get_room_reservation(session, tenant_id, reservation_id, for_update=True)
    require_transition(reservation, RoomReservationStatus.CHECKED_IN)
    room = await rooms.get_room(session, tenant_id, room_id, for_update=True)
    if room.room_type_id != reservation.room_type_id:
        raise ValidationFailedError(
            message="That room is not of the booked room type",
            code="hospitality.room_type_mismatch",
            details={"room_id": str(room_id), "room_type_id": str(reservation.room_type_id)},
        )
    if HousekeepingStatus(room.housekeeping_status) in HOUSEKEEPING_UNSELLABLE:
        raise ValidationFailedError(
            message=f"Room {room.room_number} is not sellable",
            code="hospitality.room_not_sellable",
            details={
                "room_id": str(room_id),
                "housekeeping_status": room.housekeeping_status,
            },
        )
    occupant = (
        (
            await session.execute(
                select(RoomReservation.reservation_number).where(
                    RoomReservation.tenant_id == tenant_id,
                    RoomReservation.room_id == room_id,
                    RoomReservation.status == RoomReservationStatus.CHECKED_IN.value,
                )
            )
        )
        .scalars()
        .first()
    )
    if occupant is not None:
        raise ConflictError(
            message=f"Room {room.room_number} is still occupied by {occupant}",
            code="hospitality.room_occupied",
            details={"room_id": str(room_id), "occupied_by": occupant},
        )
    reservation.room_id = room_id
    await apply_transition(session, tenant_id, reservation, RoomReservationStatus.CHECKED_IN)
    return reservation


async def check_out_room_reservation(
    session: AsyncSession, tenant_id: uuid.UUID, reservation_id: uuid.UUID
) -> RoomReservation:
    """They slept and left (terminal). Bookkeeping only — the nights were spent, not returned.
    The departure clean and the folio settlement are Task 5's, hung off this document id; neither is
    invented here, and neither would change the counter."""
    reservation = await get_room_reservation(session, tenant_id, reservation_id, for_update=True)
    require_transition(reservation, RoomReservationStatus.CHECKED_OUT)
    await apply_transition(session, tenant_id, reservation, RoomReservationStatus.CHECKED_OUT)
    return reservation
