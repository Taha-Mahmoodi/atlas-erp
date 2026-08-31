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
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationFailedError
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
    arriving is the guest using them, not a second claim. The room must be of the booked TYPE and
    not in ``HOUSEKEEPING_UNSELLABLE``: the type check stops a double being handed a single."""
    reservation = await get_room_reservation(session, tenant_id, reservation_id)
    require_transition(reservation, RoomReservationStatus.CHECKED_IN)
    room = await rooms.get_room(session, tenant_id, room_id)
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
    reservation.room_id = room_id
    await apply_transition(session, tenant_id, reservation, RoomReservationStatus.CHECKED_IN)
    return reservation


async def check_out_room_reservation(
    session: AsyncSession, tenant_id: uuid.UUID, reservation_id: uuid.UUID
) -> RoomReservation:
    """They slept and left (terminal). Bookkeeping only — the nights were spent, not returned.
    The departure clean and the folio settlement are Task 5's, hung off this document id; neither is
    invented here, and neither would change the counter."""
    reservation = await get_room_reservation(session, tenant_id, reservation_id)
    require_transition(reservation, RoomReservationStatus.CHECKED_OUT)
    await apply_transition(session, tenant_id, reservation, RoomReservationStatus.CHECKED_OUT)
    return reservation
