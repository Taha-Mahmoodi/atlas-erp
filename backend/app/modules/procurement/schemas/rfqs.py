"""RFQ schemas (Pydantic v2, ApiModel base) for PLAN 6.2.

Header + line Create/Read/Detail/Filter plus the action payloads (record-quote, convert-from-
requisition). An RFQ targets ONE vendor in v1. ``quoted_unit_cost`` is filled by the record-quote
action, not at create. Money/quantity are plain ``Decimal`` (D-015 via the column types).
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from app.core.schemas import ApiModel
from app.modules.procurement.constants import RfqStatus


class RfqLineCreate(ApiModel):
    """One line on a new RFQ. ``item_id`` / ``uom_id`` are opaque inventory ids (validated, D-029);
    ``quantity`` must be > 0. No price at create — the vendor quotes later."""

    item_id: uuid.UUID
    description: str | None = None
    quantity: Decimal
    uom_id: uuid.UUID


class RfqCreate(ApiModel):
    """Create a DRAFT RFQ from scratch (PLAN 6.2). ``vendor_id`` is the vendor asked to quote
    (validated to exist). At least one line is required; the service claims the RFQ number."""

    vendor_id: uuid.UUID
    currency_code: str
    valid_until: date | None = None
    notes: str | None = None
    lines: list[RfqLineCreate]


class RfqFromRequisition(ApiModel):
    """Convert an APPROVED requisition into an RFQ (PLAN 6.2): copy its lines, link docflow
    requisition→rfq, set ``source_requisition_id``. ``vendor_id`` is the vendor to ask. The
    requisition id comes from the path."""

    vendor_id: uuid.UUID
    currency_code: str | None = None
    valid_until: date | None = None
    notes: str | None = None


class RfqLineQuote(ApiModel):
    """A vendor's quoted price for one RFQ line (the record-quote action). ``line_id`` identifies
    the line; ``quoted_unit_cost`` is the vendor's price (>= 0)."""

    line_id: uuid.UUID
    quoted_unit_cost: Decimal


class RecordQuotePayload(ApiModel):
    """Record the vendor's quote on a SENT RFQ (PLAN 6.2): one entry per line being priced. Advances
    SENT→QUOTED. Lines not named keep their existing (possibly null) price."""

    quotes: list[RfqLineQuote]


class RfqLineRead(ApiModel):
    id: uuid.UUID
    line_number: int
    item_id: uuid.UUID
    description: str | None
    quantity: Decimal
    uom_id: uuid.UUID
    quoted_unit_cost: Decimal | None


class RfqRead(ApiModel):
    """RFQ header without lines — the list-row shape."""

    id: uuid.UUID
    rfq_number: str
    status: RfqStatus
    vendor_id: uuid.UUID
    currency_code: str
    valid_until: date | None
    source_requisition_id: uuid.UUID | None
    notes: str | None
    document_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class RfqDetail(RfqRead):
    """RFQ header WITH its lines — the GET /{id} shape."""

    lines: list[RfqLineRead]


class RfqFilter(ApiModel):
    """List filters: by status and/or vendor."""

    status: RfqStatus | None = None
    vendor_id: uuid.UUID | None = None
