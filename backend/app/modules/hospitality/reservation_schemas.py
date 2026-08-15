"""Wire shapes for the table-reservation surface (Phase 21).

A SIBLING of ``schemas.py`` rather than more of it, the ``finance/payables_schemas.py`` /
``receivables_schemas.py`` precedent (D-030/D-031): reservations are a second document family in an
already-full module, and folding them in puts ``schemas.py`` over STRUCTURE §8.4's 400-line cap.

**One create shape for both surfaces**, unlike Phase 19's ticket, where the website needed its own
because ``OrderTicketLineCreate`` trusts a caller-supplied price. A reservation carries no money and
no internal master data — a date, a slot, a party size and a name — so a staff booking and a website
booking are the same request, and a second schema would be two things to keep in step for nothing.
``extra="forbid"`` on every request shape: a website that sends a field we ignore believes it set
something (the ``WebsiteOrderLine`` argument).

**``slot_start`` is normalised to UTC at this boundary and a naive value is REJECTED.** The slot
instant is half of ``hsp_service_slots``' unique key, and the two engines disagree about offsets:
SQLAlchemy's SQLite DATETIME writes the wall clock it is handed and drops the tzinfo, while
PostgreSQL converts to UTC. A caller sending ``19:00+02:00`` would therefore key one row on SQLite
and a different one on Postgres — the counter silently split in two on the engine D-003 says is the
real one. Converting here means every reader, writer and lookup below sees the same instant.
"""

import uuid
from datetime import UTC, date, datetime, time
from typing import Annotated

from pydantic import AfterValidator, ConfigDict, Field, model_validator

from app.core.auth import as_utc
from app.core.schemas import ApiModel
from app.modules.hospitality.constants import ReservationStatus


def _utc_instant(value: datetime) -> datetime:
    """Normalise a wire datetime to UTC, refusing a naive one (see the module docstring)."""
    if value.tzinfo is None:
        raise ValueError("must carry a UTC offset, e.g. 2026-08-16T19:00:00Z")
    return value.astimezone(UTC)


SlotStart = Annotated[datetime, AfterValidator(_utc_instant)]

# The READ-side twin. aiosqlite round-trips ``DateTime(timezone=True)`` as a NAIVE datetime
# (``core/auth.as_utc``), so a slot loaded from the database serializes without an offset on SQLite
# and WITH one on PostgreSQL — the same endpoint answering in two different shapes depending on the
# engine, which a website parsing instants has no way to survive. Normalising here makes every
# rendered slot an explicit UTC instant on both.
StoredSlotStart = Annotated[datetime, AfterValidator(as_utc)]


class TableReservationCreate(ApiModel):
    """Book a table. ``service_date`` is the BUSINESS date — for a service running past midnight it
    stays on the day the service opened, which is why it is sent rather than derived from
    ``slot_start``."""

    model_config = ConfigDict(extra="forbid")

    service_date: date
    slot_start: SlotStart
    party_size: int = Field(gt=0)
    guest_name: str = Field(min_length=1, max_length=200)
    # ONE free-text field. Structured phone/email parsing is the website's job (Q1): it has already
    # authenticated its guest and owns notification, and Atlas stores what the floor shouts.
    guest_contact: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=1000)


class TableReservationRead(ApiModel):
    """A booking as the book and the website both see it.

    ``document_id`` is the D-012 registry id: once the party is seated,
    ``GET /api/v1/documents/{document_id}/chain`` renders reservation -> ticket -> (Phase 20 folio).
    ``ticket_id`` is the same edge denormalised onto the row, so the book renders without a join.
    """

    id: uuid.UUID
    document_id: uuid.UUID
    reservation_number: str
    status: ReservationStatus
    service_date: date
    slot_start: StoredSlotStart
    party_size: int
    guest_name: str
    guest_contact: str | None = None
    notes: str | None = None
    ticket_id: uuid.UUID | None = None


class SlotOfferRead(ApiModel):
    """One quarter-hour of a service as the WEBSITE sees it: an instant and a yes/no.

    Deliberately NOT the counter. ``covers_booked``/``covers_max`` are how full the dining room is,
    which is commercial information a property publishes to nobody; the guest's question is only
    "can we have 19:15 for four", and the answer is already computed against THEIR party size.
    """

    slot_start: StoredSlotStart
    bookable: bool


class ReservationAvailabilityRead(ApiModel):
    """A whole service date's grid for one party size.

    The party size rides in the response because ``bookable`` is meaningless without it — the same
    grid says yes to a deuce and no to a twelve-top — and a website rendering a cached payload
    against the wrong size would offer tables that do not exist.
    """

    service_date: date
    party_size: int
    slots: list[SlotOfferRead]


class TableReservationAmend(ApiModel):
    """Move a booking: a bigger party, a different time, or both. Every field is optional and an
    omitted one is UNCHANGED — a host correcting the party size must not have to restate the slot
    and risk retyping it wrong."""

    model_config = ConfigDict(extra="forbid")

    party_size: int | None = Field(default=None, gt=0)
    service_date: date | None = None
    slot_start: SlotStart | None = None


class TableReservationSeat(ApiModel):
    """Sit the party down. ``table_code`` is the floor's own free text ("T12", "BAR-3") and lands on
    the check opened for them — Phase 19 already litigated why a table master nothing else
    references would be config for its own sake, and pacing does not reference tables either."""

    model_config = ConfigDict(extra="forbid")

    table_code: str | None = Field(default=None, max_length=20)


class ReservationSettingsWrite(ApiModel):
    """The property's pacing configuration. A full REPLACEMENT (PUT), not a patch: the seven values
    are one policy and a manager reasons about them together — a partial update that widened
    ``max_party`` while leaving ``default_covers_max`` behind is a booking the room cannot seat.

    The 15-minute slot width is deliberately absent: it is a constant, because it is half the
    meaning of every stored counter row (``constants.SLOT_MINUTES``).
    """

    model_config = ConfigDict(extra="forbid")

    service_open: time
    service_close: time
    default_covers_max: int = Field(ge=0)
    default_parties_max: int = Field(ge=0)
    min_party: int = Field(gt=0)
    max_party: int = Field(gt=0)
    booking_horizon_days: int = Field(gt=0)

    @model_validator(mode="after")
    def _party_range_is_sane(self) -> "ReservationSettingsWrite":
        # Checked here as well as by the CHECK constraint so a typo comes back as a 422 body error
        # rather than as an IntegrityError (the MenuAvailabilitySet precedent).
        if self.max_party < self.min_party:
            raise ValueError("max_party must not be below min_party")
        return self


class ReservationSettingsRead(ReservationSettingsWrite):
    """What the property is configured to sell — the same seven values, plus the slot width so a
    client never has to hard-code the grid step it renders against."""

    slot_minutes: int


class ServiceSlotCapacityWrite(ApiModel):
    """A manager's capacity override for ONE slot, identified in the BODY because a slot's identity
    is the pair ``(service_date, slot_start)`` and a two-segment path would read as a hierarchy that
    does not exist. ``covers_max = 0`` is how a slot is CLOSED — there is no separate flag, because
    a closed slot and a full one answer a guest identically."""

    model_config = ConfigDict(extra="forbid")

    service_date: date
    slot_start: SlotStart
    covers_max: int = Field(ge=0)
    parties_max: int = Field(ge=0)


class ServiceSlotRead(ApiModel):
    """One slot's counter as STAFF see it — the numbers the website is deliberately never given,
    because how full the dining room is, is commercial information."""

    service_date: date
    slot_start: StoredSlotStart
    covers_booked: int
    covers_max: int
    parties_booked: int
    parties_max: int


__all__ = [
    "ReservationAvailabilityRead",
    "ReservationSettingsRead",
    "ReservationSettingsWrite",
    "ServiceSlotCapacityWrite",
    "ServiceSlotRead",
    "SlotOfferRead",
    "SlotStart",
    "StoredSlotStart",
    "TableReservationAmend",
    "TableReservationCreate",
    "TableReservationRead",
    "TableReservationSeat",
]
