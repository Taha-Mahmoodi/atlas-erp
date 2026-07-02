"""Quality request/response schemas (Pydantic v2, ApiModel base) for PLAN 9.1.

An inspection lot is a header only (no result lines — v1 records a lot-level accept/reject outcome,
not characteristic results). Lots are NOT created via the API: they come from the goods-receipt
handler, so there is no Create schema. The client interacts through the usage DECISION
(accept/reject
with an optional disposition) and the cancel action. Quantities are ``Decimal`` strings (D-015).
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from app.core.schemas import ApiModel
from app.modules.quality.constants import (
    InspectionLotStatus,
    InspectionSource,
    RejectDisposition,
)


class InspectionLotRead(ApiModel):
    """The inspection-lot header (the list row + GET {id} + decide/cancel response)."""

    id: uuid.UUID
    lot_number: str
    status: InspectionLotStatus
    source: InspectionSource
    source_document_id: uuid.UUID
    item_id: uuid.UUID
    warehouse_id: uuid.UUID
    bin_id: uuid.UUID
    inspect_lot_id: uuid.UUID | None
    serial_id: uuid.UUID | None
    quantity: Decimal
    accepted_quantity: Decimal
    rejected_quantity: Decimal
    disposition: RejectDisposition | None
    created_date: date
    decided_date: date | None
    decision_by: uuid.UUID | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class InspectionLotFilter(ApiModel):
    """List filters. None means "no constraint"; folded into the cursor's filter fingerprint so a
    cursor cannot cross filtered views."""

    status: InspectionLotStatus | None = None
    item_id: uuid.UUID | None = None
    source: InspectionSource | None = None


class InspectionDecideRequest(ApiModel):
    """The usage DECISION on an inspection lot (D-050): split the lot's quantity into accepted and
    rejected. ``accepted_quantity`` + ``rejected_quantity`` MUST equal the lot's quantity (v1: a
    single decision covers the whole lot — else 422). When ``rejected_quantity`` > 0 a
    ``disposition`` is REQUIRED (SCRAP or BLOCK; RETURN_TO_VENDOR is not implemented in v1 — 422);
    it
    drives the rejected stock's move via the event bus. A BLOCK disposition additionally REQUIRES
    ``blocked_bin_id`` — the destination quarantine bin the rejected stock transfers to (a SCRAP
    needs none — it is a one-sided write-off). ``notes`` is an optional decision note."""

    accepted_quantity: Decimal
    rejected_quantity: Decimal
    disposition: RejectDisposition | None = None
    blocked_bin_id: uuid.UUID | None = None
    notes: str | None = None
