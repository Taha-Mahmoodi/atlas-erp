"""Outbound-delivery schemas (Pydantic v2, ApiModel base) for PLAN 7.3 — the OUTBOUND TWIN of the
procurement goods-receipt schemas, mirrored.

A delivery is created DRAFT against a CONFIRMED sales order with its shipped lines inline (which
order line, FROM which bin, how much, optional lot/serial), then POSTED. ``item_id`` is SNAPSHOT
from the order line by the service (the create payload names only the order line) so the client
cannot rewrite the ordered item. Quantity is a plain ``Decimal`` (D-015 via the column types).
Re-exported from ``schemas/__init__``.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from app.core.schemas import ApiModel
from app.modules.sales.constants import DeliveryStatus


class DeliveryLineCreate(ApiModel):
    """One shipped line on a DRAFT delivery (PLAN 7.3). Names the ``sales_order_line_id`` being
    delivered against (the service snapshots its item), the source ``bin_id`` (an opaque inventory
    bin id the stock issues FROM — validated, D-029), and the ``quantity`` (> 0, capped at the order
    line's open-to-deliver quantity — over-delivery is rejected 422 in v1). ``lot_code`` /
    ``serial_code`` (nullable) are for lot/serial-tracked items (the lot/serial the stock leaves
    on)."""

    sales_order_line_id: uuid.UUID
    bin_id: uuid.UUID
    quantity: Decimal
    lot_code: str | None = None
    serial_code: str | None = None


class DeliveryCreate(ApiModel):
    """Create a DRAFT delivery against a sales order (PLAN 7.3). The order must be CONFIRMED (or
    already PARTIALLY_DELIVERED) — deliverable. Every line must belong to the order and not
    over-deliver its open-to-deliver quantity. ``warehouse_id`` is the inventory warehouse the stock
    issues from; ``delivery_date`` defaults to today. ``shipping_address`` is an optional ship-to
    snapshot. The service claims the DN number and snapshots the customer from the order."""

    sales_order_id: uuid.UUID
    warehouse_id: uuid.UUID
    delivery_date: date | None = None
    shipping_address: str | None = None
    notes: str | None = None
    lines: list[DeliveryLineCreate]


class DeliveryLineRead(ApiModel):
    id: uuid.UUID
    line_number: int
    sales_order_line_id: uuid.UUID
    item_id: uuid.UUID
    bin_id: uuid.UUID
    quantity: Decimal
    lot_code: str | None
    serial_code: str | None


class DeliveryRead(ApiModel):
    """Delivery header without lines — the list-row shape."""

    id: uuid.UUID
    delivery_number: str
    status: DeliveryStatus
    sales_order_id: uuid.UUID
    customer_id: uuid.UUID
    warehouse_id: uuid.UUID
    delivery_date: date
    shipping_address: str | None
    notes: str | None
    posted_at: datetime | None
    document_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class DeliveryDetail(DeliveryRead):
    """Delivery header WITH its lines — the GET /{id} shape."""

    lines: list[DeliveryLineRead]


class DeliveryFilter(ApiModel):
    """List filters: by order, status and/or delivery-date range."""

    sales_order_id: uuid.UUID | None = None
    status: DeliveryStatus | None = None
    date_from: date | None = None
    date_to: date | None = None
