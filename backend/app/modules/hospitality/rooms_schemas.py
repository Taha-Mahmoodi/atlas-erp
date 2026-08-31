"""Wire shapes for the HOTEL side of hospitality: the rooms masters and the housekeeping board
(PLAN 20.1), and the room reservation the booking gate sells (PLAN 20.2).

A SIBLING of ``schemas.py``/``menu_schemas.py``/``reservation_schemas.py``, the
``finance/payables_schemas.py`` precedent (D-030/D-031): the hotel side is a third document family
in a module whose ``schemas.py`` is already at 297 lines, and folding it in puts that file over the
STRUCTURE §8.4 cap.

``extra="forbid"`` on every request shape, and it does real work here rather than being a habit:
``RoomUpdate`` deliberately has NO ``housekeeping_status`` field, so a client that tries to move a
room's condition through the master PATCH is REFUSED rather than silently ignored. That column has
exactly one writer (``service/rooms.set_housekeeping_status``) because Phase 20 Task 4 hangs the
per-date allotment counter off it, and a second writer would be an oversell nothing tests.
"""

import uuid
from datetime import date
from decimal import Decimal

from pydantic import ConfigDict, Field

from app.core.schemas import ApiModel
from app.modules.hospitality.constants import (
    HousekeepingStatus,
    HousekeepingTaskStatus,
    HousekeepingTrigger,
    RoomReservationStatus,
)


class RoomTypeCreate(ApiModel):
    """A new unit of sale. ``code`` is user-supplied and unique per tenant (the ``item_code``
    shape) — a master carries a code, not a gapless document number."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=200)
    base_capacity: int = Field(gt=0)


class RoomTypeUpdate(ApiModel):
    """Rename or re-capacity a type. ``code`` is immutable and absent: rate plans, rooms and
    (Task 4) allotment rows all refer to the type by id, but humans refer to it by code, and a
    renamed code makes every printed rate sheet and every export wrong."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    base_capacity: int | None = Field(default=None, gt=0)


class RoomTypeRead(ApiModel):
    id: uuid.UUID
    code: str
    name: str
    base_capacity: int


class RoomCreate(ApiModel):
    """A physical room. No ``housekeeping_status``: a room nobody has made up starts DIRTY, and
    moving it is the transition endpoint's job."""

    model_config = ConfigDict(extra="forbid")

    room_number: str = Field(min_length=1, max_length=20)
    room_type_id: uuid.UUID


class RoomUpdate(ApiModel):
    """Renumber a room or move it to another type. NOT the housekeeping status — see the module
    docstring: one writer, because Task 4's counter hangs off it."""

    model_config = ConfigDict(extra="forbid")

    room_number: str | None = Field(default=None, min_length=1, max_length=20)
    room_type_id: uuid.UUID | None = None


class RoomHousekeepingWrite(ApiModel):
    """The ONE way a room's condition moves. Its own endpoint under its own permission key, because
    OUT_OF_ORDER takes a room off sale and that is a different authority from editing the master."""

    model_config = ConfigDict(extra="forbid")

    status: HousekeepingStatus


class RoomRead(ApiModel):
    id: uuid.UUID
    room_number: str
    room_type_id: uuid.UUID
    housekeeping_status: str


class RatePlanCreate(ApiModel):
    """A manual nightly rate for a room type over a validity window (v1 has no rate calendar).

    ``nightly_amount`` is a ``Decimal`` on the wire and a ``MoneyType`` in the database (D-015):
    money never becomes a float, because this number is what the night audit multiplies into
    revenue. Paired with an explicit ``currency_code`` (STRUCTURE §7's money-pair convention).
    """

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=200)
    room_type_id: uuid.UUID
    nightly_amount: Decimal = Field(ge=0)
    currency_code: str = Field(min_length=3, max_length=3)
    valid_from: date
    valid_to: date | None = None


class RatePlanUpdate(ApiModel):
    """Re-price or re-window a plan. ``code``, ``room_type_id`` and ``currency_code`` are immutable
    and absent: each of them changes what a stored rate MEANS, and a plan that needs a different
    one of them is a different plan. Sending ``valid_to: null`` opens the window (Pydantic's
    ``exclude_unset`` distinguishes that from omitting the field)."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    nightly_amount: Decimal | None = Field(default=None, ge=0)
    valid_from: date | None = None
    valid_to: date | None = None


class RatePlanRead(ApiModel):
    id: uuid.UUID
    code: str
    name: str
    room_type_id: uuid.UUID
    nightly_amount: Decimal
    currency_code: str
    valid_from: date
    valid_to: date | None


class HousekeepingTaskCreate(ApiModel):
    """Raise work on a room. ``predecessor_document_id`` is the doc-flow hook (D-012): Task 4's
    check-out passes the departing reservation's registry id, so the chain reads
    reservation -> housekeeping task without this schema changing."""

    model_config = ConfigDict(extra="forbid")

    room_id: uuid.UUID
    trigger: HousekeepingTrigger
    assigned_user_id: uuid.UUID | None = None
    notes: str | None = Field(default=None, max_length=1000)
    predecessor_document_id: uuid.UUID | None = None


class HousekeepingTaskUpdate(ApiModel):
    """Move the work on, hand it to somebody else, or both — ONE call, the ``amend_reservation``
    shape, because a supervisor reassigning a room mid-shift is doing one thing."""

    model_config = ConfigDict(extra="forbid")

    status: HousekeepingTaskStatus | None = None
    assigned_user_id: uuid.UUID | None = None


class HousekeepingTaskRead(ApiModel):
    """A task as the board sees it. ``document_id`` is the D-012 registry id the chain endpoint
    takes; ``task_number`` is what a human quotes."""

    id: uuid.UUID
    document_id: uuid.UUID
    task_number: str
    room_id: uuid.UUID
    trigger: str
    status: str
    assigned_user_id: uuid.UUID | None
    notes: str | None


# --- The room reservation (PLAN 20.2) -----------------------------------------
# ONE create shape for both surfaces, the ``TableReservationCreate`` precedent: a booking carries no
# money and no internal master data beyond the two ids the property published, so a desk booking and
# a website booking are the same request. What differs is what the CALLER may do next, and that is a
# permission (``room_reservation.book`` cannot confirm), not a second schema.
#
# There is no ``status`` field on any request shape, and ``extra="forbid"`` makes that a REFUSAL
# rather than a silent drop. That is the acknowledgment rule ``place_website_order`` set: an
# external client is told what state its booking is actually in (``RoomReservationRead.status`` is
# TENTATIVE) and cannot assert its way past the human check by sending a state it wants.


class RoomReservationCreate(ApiModel):
    """Ask for a stay. ``departure_date`` is the morning the guest LEAVES and is never a night sold,
    so a 3rd-to-5th booking is two nights — the half-open range the counter keys on."""

    model_config = ConfigDict(extra="forbid")

    room_type_id: uuid.UUID
    rate_plan_id: uuid.UUID
    arrival_date: date
    departure_date: date
    party_size: int = Field(gt=0)
    guest_name: str = Field(min_length=1, max_length=200)
    # ONE free-text field. Structured phone/email parsing is the website's job (Q1): it has already
    # authenticated its guest and owns notification.
    guest_contact: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=1000)


class RoomReservationAmend(ApiModel):
    """Move a stay — dates and party, in ONE call, because a desk re-booking a guest is doing one
    thing and two calls would be two counter passes (see ``amend_room_reservation``).

    ``room_type_id`` and ``rate_plan_id`` are absent: changing the type is two counters rather than
    one AND re-prices the stay, so it is a cancel and a re-book, not an amend.
    ``guest_name``/``guest_contact``/``notes`` are absent for the opposite reason — they touch no
    counter, and folding them in would make a typo correction take the allotment lock.
    """

    model_config = ConfigDict(extra="forbid")

    arrival_date: date | None = None
    departure_date: date | None = None
    party_size: int | None = Field(default=None, gt=0)


class RoomCheckIn(ApiModel):
    """Which physical room the guest is being put in. Required: check-in without a room is the state
    the booking is already in."""

    model_config = ConfigDict(extra="forbid")

    room_id: uuid.UUID


class RoomReservationRead(ApiModel):
    """A stay as the book, the desk and the website all see it.

    ``status`` is AUTHORITATIVE and is why the website never has to guess: a booking it just placed
    comes back TENTATIVE, which is the property's answer that a human still has to confirm it.
    ``document_id`` is the D-012 registry id ``GET /api/v1/documents/{id}/chain`` takes.
    """

    id: uuid.UUID
    document_id: uuid.UUID
    reservation_number: str
    status: RoomReservationStatus
    room_type_id: uuid.UUID
    rate_plan_id: uuid.UUID
    arrival_date: date
    departure_date: date
    party_size: int
    room_id: uuid.UUID | None = None
    guest_name: str
    guest_contact: str | None = None
    notes: str | None = None
