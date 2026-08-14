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
from datetime import date
from decimal import Decimal

from pydantic import Field

from app.core.schemas import ApiModel


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


__all__ = ["OrderTicketCreate", "OrderTicketLineCreate"]
