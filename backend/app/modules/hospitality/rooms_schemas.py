"""Wire shapes for the rooms masters and the housekeeping board (PLAN 20.1).

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
