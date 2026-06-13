"""Sales-return (RMA) schemas (Pydantic v2, ApiModel base) for PLAN 7.4 — the reverse-O2C document.

A return is created DRAFT against an order with its returned lines inline (which order line, INTO
which bin, how much, optional lot/serial), then POSTED (which receives stock reversing COGS + posts
the credit note reversing revenue). The ``item_id`` + ``unit_price`` + ``tax_code_id`` are SNAPSHOT
from the order line by the service (the create payload names only the order line / bin / qty) so the
client cannot rewrite the priced item. Quantity/money are plain ``Decimal`` (D-015 via the column
types). Re-exported from ``schemas/__init__``.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from app.core.schemas import ApiModel
from app.modules.sales.constants import ReturnStatus


class ReturnLineCreate(ApiModel):
    """One returned line on a DRAFT return (PLAN 7.4). Names the ``sales_order_line_id`` being
    returned against (the service snapshots its item + price + tax code), the destination ``bin_id``
    (an opaque inventory bin id the stock is received INTO — validated, D-029), and the ``quantity``
    (> 0, capped at the order line's invoiced-not-yet-returned quantity — over-return is rejected
    422). ``lot_code`` / ``serial_code`` (nullable) tag the returned stock for tracked items."""

    sales_order_line_id: uuid.UUID
    bin_id: uuid.UUID
    quantity: Decimal
    lot_code: str | None = None
    serial_code: str | None = None


class ReturnCreate(ApiModel):
    """Create a DRAFT return against a sales order (PLAN 7.4). The order's lines must have been
    delivered AND invoiced. Every returned line must belong to the order and not over-return its
    invoiced-not-yet-returned quantity. ``warehouse_id`` is the inventory warehouse the returned
    goods
    land in; ``return_date`` defaults to today. ``reason`` is an optional RMA reason. The service
    snapshots the customer from the order and claims the RMA number."""

    sales_order_id: uuid.UUID
    warehouse_id: uuid.UUID
    return_date: date | None = None
    reason: str | None = None
    notes: str | None = None
    lines: list[ReturnLineCreate]


class ReturnLineRead(ApiModel):
    id: uuid.UUID
    line_number: int
    sales_order_line_id: uuid.UUID
    item_id: uuid.UUID
    bin_id: uuid.UUID
    quantity: Decimal
    unit_price: Decimal
    line_amount: Decimal
    tax_code_id: uuid.UUID | None
    lot_code: str | None
    serial_code: str | None


class ReturnRead(ApiModel):
    """Return header without lines — the list-row shape."""

    id: uuid.UUID
    return_number: str
    status: ReturnStatus
    sales_order_id: uuid.UUID
    customer_id: uuid.UUID
    warehouse_id: uuid.UUID
    currency_code: str
    return_date: date
    reason: str | None
    total_amount: Decimal
    notes: str | None
    posted_at: datetime | None
    document_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class ReturnDetail(ReturnRead):
    """Return header WITH its lines — the GET /{id} shape."""

    lines: list[ReturnLineRead]


class ReturnFilter(ApiModel):
    """List filters: by order, status and/or return-date range."""

    sales_order_id: uuid.UUID | None = None
    status: ReturnStatus | None = None
    date_from: date | None = None
    date_to: date | None = None
