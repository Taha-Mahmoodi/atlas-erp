"""Physical & cycle count request/response schemas (Pydantic v2, PLAN 5.4, D-038).

Split from ``schemas.py`` once the count schemas would have pushed it over the STRUCTURE §8 400-line
cap (the finance ``assets_schemas.py`` sibling precedent). The count router imports these directly.

Quantities and costs are ``Decimal`` in Python, serialized as strings (D-015). Enums are typed with
the constants classes (ApiModel's ``use_enum_values`` serializes them as their UPPER_SNAKE string).
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from app.core.schemas import ApiModel, Page
from app.modules.inventory.constants import CountStatus, CountType


class StockCountCreate(ApiModel):
    """Create a stock count (D-038) and snapshot its lines. ``count_type`` PHYSICAL counts the whole
    warehouse (``item_ids``/``bin_ids`` are ignored); CYCLE counts only the chosen items and/or bins
    (both optional — given an item list, every quant of those items in the warehouse is snapshotted;
    given a bin list, every quant in those bins; given both, the intersection). A line is
    snapshotted for every in-scope quant with ``system_qty`` = current on-hand and ``counted_qty``
    NULL. ``count_date`` defaults to today; it is the posting date the variance ADJUSTMENT moves use
    (a closed-period date makes the post roll back)."""

    count_type: CountType
    warehouse_id: uuid.UUID
    count_date: date | None = None
    description: str | None = None
    item_ids: list[uuid.UUID] | None = None
    bin_ids: list[uuid.UUID] | None = None


class StockCountLineCountUpdate(ApiModel):
    """Record the counted quantity for one line. ``counted_qty`` must be >= 0 (you can count down to
    zero); the service moves the count to COUNTING on the first recorded count."""

    counted_qty: Decimal


class StockCountRead(ApiModel):
    id: uuid.UUID
    count_number: str
    count_type: CountType
    warehouse_id: uuid.UUID
    status: CountStatus
    count_date: date
    description: str | None
    posted_at: datetime | None
    document_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class StockCountLineRead(ApiModel):
    """One count line. ``variance_qty``/``adjustment_move_id``/``unit_cost`` are NULL until the
    count is posted; ``system_qty`` is the snapshot at line creation/recount (the post re-reads live
    on-hand, so the posted variance may differ from ``counted_qty − system_qty`` if stock moved)."""

    id: uuid.UUID
    count_id: uuid.UUID
    line_number: int
    item_id: uuid.UUID
    bin_id: uuid.UUID
    lot_id: uuid.UUID | None
    system_qty: Decimal
    counted_qty: Decimal | None
    variance_qty: Decimal | None
    adjustment_move_id: uuid.UUID | None
    unit_cost: Decimal | None


class StockCountVarianceLine(ApiModel):
    """One variance-preview row (read-only): per line the live system on-hand, the counted qty,
    their difference and the estimated value impact (variance × the item's current unit cost).
    Uncounted lines report ``counted_qty`` NULL and ``variance_qty`` NULL (nothing to post yet)."""

    line_id: uuid.UUID
    item_id: uuid.UUID
    bin_id: uuid.UUID
    lot_id: uuid.UUID | None
    system_qty: Decimal
    counted_qty: Decimal | None
    variance_qty: Decimal | None
    unit_cost: Decimal
    estimated_value_impact: Decimal


class StockCountVariancePreview(ApiModel):
    """The variance preview for a whole count: a keyset PAGE of per-line rows (#78 — a physical
    count routinely has thousands of lines) plus the net estimated value impact over the WHOLE
    count, shown before posting so the operator sees what the post will do."""

    count_id: uuid.UUID
    status: CountStatus
    lines: Page[StockCountVarianceLine]
    total_value_impact: Decimal


class StockCountFilter(ApiModel):
    """List filters for the counts endpoint. None means "no constraint"; folded into the cursor's
    filter fingerprint so a cursor cannot cross filtered views."""

    status: CountStatus | None = None
    warehouse_id: uuid.UUID | None = None
    count_type: CountType | None = None
