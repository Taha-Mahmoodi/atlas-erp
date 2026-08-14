"""Hospitality wire shapes (Pydantic v2 on the ``ApiModel`` base) for PLAN 19.

A SINGLE file, matching the flat ``models.py`` next to it (STRUCTURE §8.4: split into a package at
the 400-line cap, not before). Task 7's website shapes land here too.

Only the CREATE payloads exist so far, because only they have a consumer: the ticket service takes
them. Read schemas arrive with the routes that render them (Tasks 6 and 7) — a response model with
no endpoint is the dead config STRUCTURE §8.3 forbids.

MONEY (D-015): ``Decimal`` in Python, serialized as a JSON string by the column/wire types. Never
float, anywhere on this path.

**``unit_price`` is caller-supplied and the service trusts it — so the ROUTER must not.** Task 7's
website endpoint takes item ids and quantities from an untrusted origin and MUST resolve the price
server-side before calling ``create_ticket``; if it ever forwards a request body's price straight
through, a website can order a lobster for zero. That check belongs at the trust boundary (the
router), which is why this schema is the service's input shape and not the website's request shape.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import Field, model_validator

from app.core.schemas import ApiModel
from app.modules.hospitality.constants import (
    AvailabilitySource,
    AvailabilityState,
    OrderTicketStatus,
)


class OrderTicketLineCreate(ApiModel):
    """One ordered dish. ``item_id`` is an opaque inventory id, validated to exist (D-029).

    ``quantity`` is in the item's BASE UoM — there is no ``uom_id`` because a kitchen sells the
    dish in the unit it is costed in, and that is also the basis its recipe BOM explodes against.
    """

    item_id: uuid.UUID
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal = Field(ge=0)
    seat_number: int | None = Field(default=None, ge=1)
    notes: str | None = Field(default=None, max_length=500)


class OrderTicketCreate(ApiModel):
    """Open a check. Every field is optional except the lines, and those may be empty: a server
    opens a ticket when the table is seated and takes the order afterwards, so an empty OPEN ticket
    is the normal first state rather than an error (unlike a sales order, which needs a line to
    mean anything). Firing an empty ticket is what is refused.

    ``opened_on`` defaults to today; it is the service date the TKT- number year-resets on.
    """

    table_code: str | None = Field(default=None, max_length=20)
    guest_count: int | None = Field(default=None, ge=1)
    opened_on: date | None = None
    notes: str | None = Field(default=None, max_length=1000)
    lines: list[OrderTicketLineCreate] = Field(default_factory=list)


class OrderTicketLinesAdd(ApiModel):
    """Add dishes to an OPEN check. A wrapper rather than a bare list so the body stays an object
    and a later field (a course number, a fire-together flag) is an additive change."""

    lines: list[OrderTicketLineCreate] = Field(min_length=1)


class OrderTicketAdvance(ApiModel):
    """Move a fired check through the kitchen's own progress. Only IN_PREP / READY / SERVED are
    accepted (``TICKET_PROGRESS_STATES``); firing and settling keep their own endpoints because
    each carries effects — the 86 check and the fired event, the settled event — that a generic
    status PATCH must never be able to skip past."""

    status: OrderTicketStatus


class MenuAvailabilitySet(ApiModel):
    """86 a dish, start a countdown, or time-box either (spec Q2).

    LIMITED requires a positive ``remaining_qty`` — LIMITED *is* the countdown state, and without a
    count the dish could never flip. The service rejects it too (code
    ``hospitality.countdown_required``); it is checked here as well so a typo comes back as a 422
    body-validation error rather than reaching the service.
    """

    state: AvailabilityState
    remaining_qty: Decimal | None = Field(default=None, gt=0)
    available_until: datetime | None = None
    reason: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _countdown_needs_a_count(self) -> "MenuAvailabilitySet":
        # ``==``, not ``is``: ApiModel sets use_enum_values, so ``state`` is the StrEnum's value.
        if self.state == AvailabilityState.LIMITED and self.remaining_qty is None:
            raise ValueError("remaining_qty is required when state is LIMITED")
        return self


class MenuAvailabilityRead(ApiModel):
    """One item's RESOLVED availability — expiry already applied, so a lapsed 86 reads AVAILABLE
    and an item with no stored row does too. Built from the service's frozen
    ``MenuItemAvailability`` plus the item id the caller asked about (the dataclass carries no id:
    it is the value in a per-item map)."""

    item_id: uuid.UUID
    state: AvailabilityState
    remaining_qty: Decimal | None = None
    available_until: datetime | None = None
    reason: str | None = None
    source: AvailabilitySource | None = None


class MenuItemAtRiskRead(ApiModel):
    """How many more portions the storeroom covers, and the ingredient that runs out first.

    ADVISORY and STAFF-ONLY. It over-reports on shared ingredients (every dish is costed against
    the whole storeroom), which is precisely why the guest-facing answer is the stored 86 row this
    number prompts a human to write — see ``queries.at_risk_menu_items``.
    """

    item_id: uuid.UUID
    max_producible: int
    limiting_item_id: uuid.UUID


class OrderTicketLineRead(ApiModel):
    """One ordered dish. ``quantity`` is in the item's base UoM (there is no ``uom_id`` to send)."""

    id: uuid.UUID
    line_number: int
    item_id: uuid.UUID
    quantity: Decimal
    unit_price: Decimal
    line_amount: Decimal
    seat_number: int | None = None
    notes: str | None = None


class OrderTicketRead(ApiModel):
    """The check. ``total_amount`` is the MAINTAINED Σ line_amount, never recomputed on read — Q6
    requires it to be authoritative over whatever price a caller cached.

    ``document_id`` is the D-012 registry id: ``GET /api/v1/documents/{document_id}/chain`` renders
    the ticket and, once its background depletion job has drained, the ingredient ISSUE moves that
    hang off it. That chain is how a fired ticket's depletion is inspected — the fire response
    deliberately claims nothing about it, because at that moment nothing has been issued yet.
    """

    id: uuid.UUID
    document_id: uuid.UUID
    ticket_number: str
    status: OrderTicketStatus
    opened_date: date
    table_code: str | None = None
    guest_count: int | None = None
    fired_at: datetime | None = None
    settled_at: datetime | None = None
    total_amount: Decimal
    notes: str | None = None


__all__ = [
    "MenuAvailabilityRead",
    "MenuAvailabilitySet",
    "MenuItemAtRiskRead",
    "OrderTicketAdvance",
    "OrderTicketCreate",
    "OrderTicketLineCreate",
    "OrderTicketLineRead",
    "OrderTicketLinesAdd",
    "OrderTicketRead",
]
