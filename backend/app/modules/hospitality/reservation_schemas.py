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
from datetime import UTC, date, datetime
from typing import Annotated

from pydantic import AfterValidator, ConfigDict, Field

from app.core.schemas import ApiModel
from app.modules.hospitality.constants import ReservationStatus


def _utc_instant(value: datetime) -> datetime:
    """Normalise a wire datetime to UTC, refusing a naive one (see the module docstring)."""
    if value.tzinfo is None:
        raise ValueError("must carry a UTC offset, e.g. 2026-08-16T19:00:00Z")
    return value.astimezone(UTC)


SlotStart = Annotated[datetime, AfterValidator(_utc_instant)]


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
    slot_start: datetime
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

    slot_start: datetime
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


__all__ = [
    "ReservationAvailabilityRead",
    "SlotOfferRead",
    "SlotStart",
    "TableReservationCreate",
    "TableReservationRead",
]
