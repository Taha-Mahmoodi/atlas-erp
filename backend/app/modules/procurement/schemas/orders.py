"""Purchase-order schemas (Pydantic v2, ApiModel base) for PLAN 6.2.

Header + line Create/Read/Detail/Filter plus the convert payloads (from requisition / from RFQ).
``unit_cost`` is required on a from-scratch line; ``line_amount`` / ``total_amount`` /
``received_quantity`` are server-maintained. ``tax_code_id`` (nullable) is carried for the 6.4 bill.
Money/quantity are plain ``Decimal`` (D-015 via the column types).
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from app.core.schemas import ApiModel
from app.modules.procurement.constants import PurchaseOrderStatus


class PurchaseOrderLineCreate(ApiModel):
    """One ordered line on a from-scratch PO. ``item_id`` / ``uom_id`` are opaque inventory ids
    (validated, D-029) and the item must be APPROVED for the vendor (the v1 source-control rule);
    ``unit_cost`` is the negotiated price (>= 0); ``tax_code_id`` (opaque finance tax code) is
    carried for the bill. ``quantity`` must be > 0. The service derives ``line_amount``."""

    item_id: uuid.UUID
    description: str | None = None
    quantity: Decimal
    uom_id: uuid.UUID
    unit_cost: Decimal
    tax_code_id: uuid.UUID | None = None


class PurchaseOrderCreate(ApiModel):
    """Create a DRAFT PO from scratch (PLAN 6.2). ``vendor_id`` must be ACTIVE; every line item must
    be approved for the vendor. Currency / payment terms default from the vendor when omitted. At
    least one line is required; the service claims the number and computes line + total amounts."""

    vendor_id: uuid.UUID
    currency_code: str | None = None
    order_date: date | None = None
    expected_date: date | None = None
    notes: str | None = None
    lines: list[PurchaseOrderLineCreate]


class PurchaseOrderFromRequisition(ApiModel):
    """Convert an APPROVED requisition straight into a PO (PLAN 6.2): copy lines, take ``unit_cost``
    from the requisition's estimate (override per line is a later refinement), snapshot the vendor's
    terms/currency, link docflow requisition→po. The requisition id comes from the path."""

    vendor_id: uuid.UUID
    order_date: date | None = None
    expected_date: date | None = None
    notes: str | None = None


class PurchaseOrderFromRfq(ApiModel):
    """Convert a QUOTED RFQ into a PO (PLAN 6.2): copy lines, take ``unit_cost`` from the RFQ's
    quoted prices, snapshot the RFQ vendor's terms/currency, link docflow rfq→po. The RFQ id comes
    from the path; its vendor is the PO vendor."""

    order_date: date | None = None
    expected_date: date | None = None
    notes: str | None = None


class PurchaseOrderLineRead(ApiModel):
    id: uuid.UUID
    line_number: int
    item_id: uuid.UUID
    description: str | None
    quantity: Decimal
    uom_id: uuid.UUID
    unit_cost: Decimal
    line_amount: Decimal
    received_quantity: Decimal
    tax_code_id: uuid.UUID | None


class PurchaseOrderRead(ApiModel):
    """PO header without lines — the list-row shape."""

    id: uuid.UUID
    po_number: str
    status: PurchaseOrderStatus
    vendor_id: uuid.UUID
    currency_code: str
    order_date: date
    expected_date: date | None
    payment_terms_days: int
    total_amount: Decimal
    notes: str | None
    approved_by: uuid.UUID | None
    approved_at: datetime | None
    source_requisition_id: uuid.UUID | None
    source_rfq_id: uuid.UUID | None
    document_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class PurchaseOrderDetail(PurchaseOrderRead):
    """PO header WITH its lines — the GET /{id} shape."""

    lines: list[PurchaseOrderLineRead]


class PurchaseOrderFilter(ApiModel):
    """List filters: by status and/or vendor."""

    status: PurchaseOrderStatus | None = None
    vendor_id: uuid.UUID | None = None
