"""Goods-receipt schemas (Pydantic v2, ApiModel base) for PLAN 6.3.

A goods receipt is created DRAFT against a PO with its received lines inline (which PO line, into
which bin, how much, optional lot/serial, inspection flag), then POSTED. ``item_id`` / ``unit_cost``
are SNAPSHOT from the PO line by the service (the create payload names only the PO line) so the
client cannot rewrite the ordered item or its cost. Money/quantity are plain ``Decimal`` (D-015 via
the column types).
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from app.core.schemas import ApiModel
from app.modules.procurement.constants import GoodsReceiptStatus


class GoodsReceiptLineCreate(ApiModel):
    """One received line on a DRAFT goods receipt (PLAN 6.3). Names the ``purchase_order_line_id``
    being received against (the service snapshots its item + unit_cost), the target ``bin_id`` (an
    opaque inventory bin id the stock lands in — validated, D-029), and the ``received_quantity``
    (> 0, capped at the PO line's still-open quantity — over-receipt is rejected 422 in v1).
    ``lot_code`` / ``serial_code`` (nullable) are for lot/serial-tracked items.
    ``requires_inspection`` is the v1 inspection FLAG (defaults to False when the client omits it;
    Phase 9 adds the disposition)."""

    purchase_order_line_id: uuid.UUID
    bin_id: uuid.UUID
    received_quantity: Decimal
    lot_code: str | None = None
    serial_code: str | None = None
    requires_inspection: bool | None = None


class GoodsReceiptCreate(ApiModel):
    """Create a DRAFT goods receipt against a PO (PLAN 6.3). The PO must be APPROVED/SENT (or
    already PARTIALLY_RECEIVED) — receivable. Every line must belong to the PO and not over-receive
    its open quantity. ``warehouse_id`` is the inventory warehouse the stock lands in;
    ``receipt_date`` defaults to today. The service claims the GR number and snapshots vendor."""

    purchase_order_id: uuid.UUID
    warehouse_id: uuid.UUID
    receipt_date: date | None = None
    notes: str | None = None
    lines: list[GoodsReceiptLineCreate]


class GoodsReceiptLineRead(ApiModel):
    id: uuid.UUID
    line_number: int
    purchase_order_line_id: uuid.UUID
    item_id: uuid.UUID
    bin_id: uuid.UUID
    received_quantity: Decimal
    unit_cost: Decimal
    lot_code: str | None
    serial_code: str | None
    requires_inspection: bool


class GoodsReceiptRead(ApiModel):
    """GR header without lines — the list-row shape."""

    id: uuid.UUID
    gr_number: str
    status: GoodsReceiptStatus
    purchase_order_id: uuid.UUID
    vendor_id: uuid.UUID
    warehouse_id: uuid.UUID
    receipt_date: date
    notes: str | None
    posted_at: datetime | None
    document_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class GoodsReceiptDetail(GoodsReceiptRead):
    """GR header WITH its lines — the GET /{id} shape."""

    lines: list[GoodsReceiptLineRead]


class GoodsReceiptFilter(ApiModel):
    """List filters: by PO, status and/or receipt-date range."""

    purchase_order_id: uuid.UUID | None = None
    status: GoodsReceiptStatus | None = None
    date_from: date | None = None
    date_to: date | None = None
