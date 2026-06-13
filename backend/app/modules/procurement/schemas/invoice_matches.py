"""Invoice-match schemas (Pydantic v2, ApiModel base) for PLAN 6.4 (the 3-way match → AP bill).

Header + line Create/Read/Detail/Filter plus the tolerance-config schemas. Money/quantity are plain
``Decimal`` (the finance/procurement schema precedent — exact on both engines via the MoneyType /
QuantityType columns, D-015). ``status`` is typed with ``MatchStatus``. Server-owned + computed
fields (id, number, status, variances, within_tolerance, line_amount, timestamps) are absent from
Create — the service computes them from the PO/GR snapshots and the tolerance rule.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from app.core.schemas import ApiModel
from app.modules.procurement.constants import MatchStatus


class InvoiceMatchLineCreate(ApiModel):
    """One invoiced line to match (PLAN 6.4). ``purchase_order_line_id`` is the PO line being billed
    against; ``goods_receipt_line_id`` (optional) records which receipt line it draws from.
    ``matched_quantity`` is the quantity being invoiced (the service caps it at received − billed);
    ``unit_price`` is the vendor's invoiced unit price (the service compares it to the PO price for
    the variance + tolerance). ``tax_code_id`` is unused at line level in v1 (the header tax code
    drives the bill); kept off the line to match the header-tax model."""

    purchase_order_line_id: uuid.UUID
    goods_receipt_line_id: uuid.UUID | None = None
    matched_quantity: Decimal
    unit_price: Decimal


class InvoiceMatchCreate(ApiModel):
    """Create a DRAFT 3-way match against a PO (PLAN 6.4). ``vendor_invoice_ref`` is the vendor's
    own invoice number (free text). ``invoice_date`` dates the triggered bill (its due date =
    invoice date + the vendor's payment terms). ``tax_code_id`` (optional, opaque) drives the input
    tax. At least one line is required; the service validates over-billing, computes variances +
    tolerance, and claims the MATCH number. ``total_amount`` (the vendor-invoiced total) is computed
    from the lines (Σ matched_quantity × unit_price + tax) — not accepted from the caller."""

    purchase_order_id: uuid.UUID
    vendor_invoice_ref: str | None = None
    invoice_date: date | None = None
    tax_code_id: uuid.UUID | None = None
    notes: str | None = None
    lines: list[InvoiceMatchLineCreate]


class InvoiceMatchLineRead(ApiModel):
    id: uuid.UUID
    line_number: int
    purchase_order_line_id: uuid.UUID
    goods_receipt_line_id: uuid.UUID | None
    item_id: uuid.UUID
    matched_quantity: Decimal
    unit_price: Decimal
    po_unit_cost: Decimal
    price_variance: Decimal
    quantity_variance: Decimal
    line_amount: Decimal
    within_tolerance: bool


class InvoiceMatchRead(ApiModel):
    """Match header without lines — the list-row shape."""

    id: uuid.UUID
    match_number: str
    status: MatchStatus
    purchase_order_id: uuid.UUID
    vendor_id: uuid.UUID
    vendor_invoice_ref: str | None
    invoice_date: date
    currency_code: str
    total_amount: Decimal
    tax_code_id: uuid.UUID | None
    notes: str | None
    document_id: uuid.UUID
    posted_at: datetime | None
    created_at: datetime
    updated_at: datetime


class InvoiceMatchDetail(InvoiceMatchRead):
    """Match header WITH its lines + variances — the GET /{id} shape."""

    lines: list[InvoiceMatchLineRead]


class InvoiceMatchFilter(ApiModel):
    """List filters: by PO and/or status. None means no constraint (folds into the cursor
    fingerprint so a cursor cannot cross filtered views)."""

    purchase_order_id: uuid.UUID | None = None
    status: MatchStatus | None = None


# --- Match tolerance config ---------------------------------------------------


class MatchToleranceUpsert(ApiModel):
    """Set (or replace) the tenant's 3-way-match tolerances (PLAN 6.4). Percentages a line's price /
    quantity may deviate before it becomes an EXCEPTION; both default 0 (strict). The single-per-
    tenant row is upserted by the service."""

    price_tolerance_percent: Decimal = Decimal(0)
    quantity_tolerance_percent: Decimal = Decimal(0)


class MatchToleranceRead(ApiModel):
    id: uuid.UUID
    price_tolerance_percent: Decimal
    quantity_tolerance_percent: Decimal
    created_at: datetime
    updated_at: datetime
