"""Hospitality wire shapes (Pydantic v2 on the ``ApiModel`` base) for PLAN 19.

A SINGLE file, matching the flat ``models.py`` next to it (STRUCTURE §8.4: split into a package at
the 400-line cap, not before). Two audiences share it, separated by the section rule below: STAFF
shapes first, then the WEBSITE surface Task 7 exposes to a machine credential.

Every schema here has an endpoint that renders it — a response model with no route is the dead
config STRUCTURE §8.3 forbids.

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

from pydantic import ConfigDict, Field, model_validator

from app.core.schemas import ApiModel, Page
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


class OrderTicketCancel(ApiModel):
    """Close an OPEN check that should never have been opened (D-080). The reason is REQUIRED and
    non-empty: cancelling is the one terminal state a human picks for a reason nothing else on the
    check records, and "why is this table's check gone" is the question it exists to answer."""

    reason: str = Field(min_length=1, max_length=200)


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
    cancelled_at: datetime | None = None
    cancel_reason: str | None = None
    total_amount: Decimal
    notes: str | None = None


# --- The website surface (Task 7) ---------------------------------------------


class MenuItemRead(ApiModel):
    """One sellable dish as the property's WEBSITE sees it (spec Q6).

    Structure and price only — availability is a SEPARATE resource on a completely different cache
    policy, because a menu changes when a chef rewrites it and availability changes when a table
    orders the last portion. Folding them together would force the slow half to the fast half's
    freshness and pull the whole payload over the wire every ten seconds.

    ``price`` is None when no ACTIVE general price list prices the item today. Such an item is
    still LISTED rather than hidden: a dish missing from the website with no error anywhere is a
    misconfiguration nobody finds, and the order endpoint refuses it loudly (422
    ``hospitality.item_not_priced``) rather than selling it for nothing. ``currency_code`` labels
    the price with the currency it actually resolved in.

    NO ``prep_station``. Nothing in Phase 19 reads one — KDS hardware is explicitly out of scope —
    so it would be a column, a template field and a wire field with no consumer (STRUCTURE §8.3).
    It belongs with the kitchen display that needs it.
    """

    item_id: uuid.UUID
    item_code: str
    name: str
    description: str | None = None
    category_id: uuid.UUID
    price: Decimal | None = None
    currency_code: str | None = None


class MenuAvailabilityPage(Page[MenuAvailabilityRead]):
    """The 86 board, plus the instant it describes.

    The ``Page`` envelope unchanged (D-014 items/next_cursor/limit) with ONE field added: two pages
    of availability are two snapshots taken at different instants, so a client that stitched them
    would render a state the kitchen was never in. ``as_of`` is what makes the incoherence visible
    instead of silent, and spec Q6's contract is that availability FITS ONE PAGE — a property with
    more than ``MAX_LIMIT`` (200) simultaneous overrides is outside v1's envelope.

    Only OVERRIDDEN items appear. Everything absent is available; that is the contract, and it is
    what keeps the payload a handful of rows through a service.
    """

    as_of: datetime


class WebsiteOrderLine(ApiModel):
    """One dish a guest ordered on the website. **NO ``unit_price``** — the whole reason this shape
    exists instead of reusing ``OrderTicketLineCreate``, which trusts a caller-supplied price. The
    server resolves the price from the menu price list; a body carrying one is rejected, not
    ignored, so a website cannot order a lobster for a penny."""

    # UNKNOWN FIELDS ARE REJECTED, not ignored (the OnboardTenantRequest precedent, and for the same
    # reason: this is a payload from outside the organization). A website that sends unit_price
    # believes it set the price; a silent 201 at a different number is the worst of both worlds.
    model_config = ConfigDict(extra="forbid")

    item_id: uuid.UUID
    quantity: Decimal = Field(gt=0)
    seat_number: int | None = Field(default=None, ge=1)
    notes: str | None = Field(default=None, max_length=500)


class WebsiteOrderCreate(ApiModel):
    """A website order. At least one line, unlike a staff ticket: a server opens an empty check when
    a table is seated and takes the order later, but a website order IS the order — an empty one is
    a bug in the caller, and it would fire an empty ticket at the kitchen."""

    model_config = ConfigDict(extra="forbid")

    table_code: str | None = Field(default=None, max_length=20)
    guest_count: int | None = Field(default=None, ge=1)
    notes: str | None = Field(default=None, max_length=1000)
    lines: list[WebsiteOrderLine] = Field(min_length=1)


class WebsiteOrderRead(ApiModel):
    """The accepted order. ``total_amount`` is AUTHORITATIVE (Q6): the menu is cached for 60 s, so
    the website must show this number before payment and never one it computed from a cached price.

    ``status`` is already SENT_TO_KITCHEN — a website order has no server standing by to fire it —
    which also means the ingredients have NOT left the storeroom yet: depletion is a background job
    submitted by the same transaction (Q4). ``/api/v1/jobs`` and the ticket document's D-012 chain
    are where that is watched; this response deliberately claims nothing about it.
    """

    ticket_id: uuid.UUID
    ticket_number: str
    status: OrderTicketStatus
    opened_date: date
    total_amount: Decimal
    currency_code: str | None = None


__all__ = [
    "MenuAvailabilityPage",
    "MenuAvailabilityRead",
    "MenuAvailabilitySet",
    "MenuItemAtRiskRead",
    "MenuItemRead",
    "OrderTicketAdvance",
    "OrderTicketCancel",
    "OrderTicketCreate",
    "OrderTicketLineCreate",
    "OrderTicketLineRead",
    "OrderTicketLinesAdd",
    "OrderTicketRead",
    "WebsiteOrderCreate",
    "WebsiteOrderLine",
    "WebsiteOrderRead",
]
