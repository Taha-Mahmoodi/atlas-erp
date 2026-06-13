"""Inventory request/response schemas (Pydantic v2, ApiModel base) for PLAN 5.1 + 5.2.

Read schemas mirror the models field-for-field in snake_case; enums are typed with the constants
classes (ApiModel's ``use_enum_values`` serializes them as their UPPER_SNAKE string, matching the
columns). Quantities (reorder point/quantity, the UoM conversion factor, move quantity, on-hand)
are ``Decimal`` in Python, serialized as strings (D-015); the frontend types them as string and
formats in lib/format.ts. Create/Update carry only client-settable fields; ids, timestamps and
tenant_id are server-owned.

``costing_method`` is OPTIONAL on ItemCreate — the service defaults it from the item's category
(D-020) when omitted, and STORES it on the item.

PLAN 5.2 adds warehouses, bins, the stock-move ledger (create + read) and the on-hand projection.
A stock move has NO Update schema: a move is POSTED-at-creation and IMMUTABLE; corrections are
reversing moves (a dedicated endpoint), never edits.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from app.core.schemas import ApiModel
from app.modules.inventory.constants import CostingMethod, ItemType, MoveType, TrackingMode

# --- Item categories ----------------------------------------------------------


class ItemCategoryCreate(ApiModel):
    """Create an item category (D-020/D-029). The three GL-account ids are OPTIONAL opaque finance
    uuids — supplied ones are validated to exist in finance; a STOCKED item's category needs them
    before stock moves can post (enforced when moves land, 5.2+)."""

    code: str
    name: str
    default_costing_method: CostingMethod = CostingMethod.MOVING_AVERAGE
    inventory_account_id: uuid.UUID | None = None
    cogs_account_id: uuid.UUID | None = None
    price_difference_account_id: uuid.UUID | None = None


class ItemCategoryUpdate(ApiModel):
    """Partial update — every field optional; ``code`` is immutable after creation (items
    reference the category) and so is deliberately absent."""

    name: str | None = None
    default_costing_method: CostingMethod | None = None
    inventory_account_id: uuid.UUID | None = None
    cogs_account_id: uuid.UUID | None = None
    price_difference_account_id: uuid.UUID | None = None


class ItemCategoryRead(ApiModel):
    id: uuid.UUID
    code: str
    name: str
    default_costing_method: CostingMethod
    inventory_account_id: uuid.UUID | None
    cogs_account_id: uuid.UUID | None
    price_difference_account_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


# --- Units of measure ---------------------------------------------------------


class UomCreate(ApiModel):
    code: str
    name: str


class UomUpdate(ApiModel):
    """Partial update — only the display name; ``code`` is immutable (items/conversions reference
    it) and so is deliberately absent."""

    name: str | None = None


class UomRead(ApiModel):
    id: uuid.UUID
    code: str
    name: str
    created_at: datetime
    updated_at: datetime


# --- Items --------------------------------------------------------------------


class ItemCreate(ApiModel):
    """Create an item. ``costing_method`` is optional — defaulted from the category when omitted
    (D-020). ``tracking_mode`` may be non-NONE only for STOCKED items (the service enforces it).
    ``base_uom_id`` is the unit every quantity is stored in; alternate UoMs are added separately."""

    item_code: str
    name: str
    description: str | None = None
    item_type: ItemType
    category_id: uuid.UUID
    base_uom_id: uuid.UUID
    costing_method: CostingMethod | None = None
    tracking_mode: TrackingMode = TrackingMode.NONE
    is_active: bool = True
    reorder_point: Decimal | None = None
    reorder_quantity: Decimal | None = None


class ItemUpdate(ApiModel):
    """Partial update — every field optional; ``item_code`` and ``item_type`` are immutable after
    creation (later stock/costing history references them) and so are deliberately absent. The
    service still enforces the tracking-only-on-stocked invariant on a changed ``tracking_mode``."""

    name: str | None = None
    description: str | None = None
    category_id: uuid.UUID | None = None
    base_uom_id: uuid.UUID | None = None
    costing_method: CostingMethod | None = None
    tracking_mode: TrackingMode | None = None
    is_active: bool | None = None
    reorder_point: Decimal | None = None
    reorder_quantity: Decimal | None = None


class ItemRead(ApiModel):
    id: uuid.UUID
    item_code: str
    name: str
    description: str | None
    item_type: ItemType
    category_id: uuid.UUID
    base_uom_id: uuid.UUID
    costing_method: CostingMethod
    tracking_mode: TrackingMode
    is_active: bool
    reorder_point: Decimal | None
    reorder_quantity: Decimal | None
    created_at: datetime
    updated_at: datetime


class ItemFilter(ApiModel):
    """List filters for the items endpoint. None means "no constraint"; the router folds the set
    into the cursor's filter fingerprint so a cursor cannot cross filtered views."""

    item_type: ItemType | None = None
    category_id: uuid.UUID | None = None
    is_active: bool | None = None


# --- UoM conversions (nested under an item) -----------------------------------


class UomConversionCreate(ApiModel):
    """Add an alternate UoM for an item. ``factor_to_base`` multiplies an alternate-UoM quantity to
    yield the base-UoM quantity (base EA, alt BOX, factor 12 ⇒ 1 BOX = 12 EA); must be > 0. The
    item_id comes from the path, not the body."""

    alt_uom_id: uuid.UUID
    factor_to_base: Decimal


class UomConversionRead(ApiModel):
    id: uuid.UUID
    item_id: uuid.UUID
    alt_uom_id: uuid.UUID
    factor_to_base: Decimal
    created_at: datetime


# --- Warehouses (PLAN 5.2) ----------------------------------------------------


class WarehouseCreate(ApiModel):
    code: str
    name: str
    is_active: bool = True


class WarehouseUpdate(ApiModel):
    """Partial update — ``code`` is immutable (bins/moves reference the warehouse) and absent."""

    name: str | None = None
    is_active: bool | None = None


class WarehouseRead(ApiModel):
    id: uuid.UUID
    code: str
    name: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


# --- Bins (PLAN 5.2) ----------------------------------------------------------


class BinCreate(ApiModel):
    """Create a bin in a warehouse. ``warehouse_id`` comes from the body (the bin endpoint is a
    flat collection, filtered by warehouse on list). ``code`` is unique per (warehouse)."""

    warehouse_id: uuid.UUID
    code: str
    name: str
    is_default: bool = False
    is_active: bool = True


class BinUpdate(ApiModel):
    """Partial update — ``code`` and ``warehouse_id`` are immutable (moves/quants reference the
    bin) and absent."""

    name: str | None = None
    is_default: bool | None = None
    is_active: bool | None = None


class BinRead(ApiModel):
    id: uuid.UUID
    warehouse_id: uuid.UUID
    code: str
    name: str
    is_default: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


# --- Stock moves (PLAN 5.2) ---------------------------------------------------


class StockMoveCreate(ApiModel):
    """Create (and immediately POST) a stock move (PLAN 5.2). ``quantity`` is ALWAYS positive and
    is in the item's BASE UoM (the service resolves and freezes ``base_uom_id``). The ``move_type``
    decides which bins are required (constants.MOVE_BIN_SIDES): RECEIPT → ``to_bin_id`` only;
    ISSUE → ``from_bin_id`` only; TRANSFER → both (different bins); ADJUSTMENT → exactly one side.
    ``lot_id``/``serial_id`` are required iff the item's tracking mode demands them; on a RECEIPT a
    NEW ``lot_code``/``serial_code`` may be supplied to create the master instance on the fly.
    ``move_date`` defaults to today when omitted."""

    move_type: MoveType
    item_id: uuid.UUID
    quantity: Decimal
    from_bin_id: uuid.UUID | None = None
    to_bin_id: uuid.UUID | None = None
    lot_id: uuid.UUID | None = None
    serial_id: uuid.UUID | None = None
    # On a RECEIPT of a tracked item, the caller may name a NEW lot/serial code to create the master
    # instance (5.1 deferred instance creation to receipts). For ISSUE/TRANSFER the lot/serial must
    # already exist (by id above).
    lot_code: str | None = None
    serial_code: str | None = None
    move_date: date | None = None
    reference: str | None = None
    # The costing entry cost (PLAN 5.3, D-020): REQUIRED on a RECEIPT / positive ADJUSTMENT (the
    # value stock enters at); IGNORED on an ISSUE / negative ADJUSTMENT (the engine computes COGS)
    # and on a TRANSFER (value carries at the current valuation). Full-precision Decimal (D-015).
    unit_cost: Decimal | None = None


class StockMoveRead(ApiModel):
    id: uuid.UUID
    move_number: str
    move_type: MoveType
    item_id: uuid.UUID
    quantity: Decimal
    base_uom_id: uuid.UUID
    from_bin_id: uuid.UUID | None
    to_bin_id: uuid.UUID | None
    lot_id: uuid.UUID | None
    serial_id: uuid.UUID | None
    move_date: date
    reference: str | None
    posted: bool
    # The entry cost (RECEIPT) or the engine-computed per-unit cost (ISSUE) for this move (D-020).
    unit_cost: Decimal | None
    document_id: uuid.UUID
    created_at: datetime


class StockMoveFilter(ApiModel):
    """List filters for the move ledger. None means "no constraint"; folded into the cursor's
    filter fingerprint so a cursor cannot cross filtered views."""

    item_id: uuid.UUID | None = None
    bin_id: uuid.UUID | None = None
    move_type: MoveType | None = None
    date_from: date | None = None
    date_to: date | None = None


# --- On-hand projection (PLAN 5.2) --------------------------------------------


class StockOnHandRead(ApiModel):
    """One on-hand quant row: current quantity of an item in a bin (optionally a lot). The
    projection endpoint returns these; sales ATP / procurement read the same shape via queries."""

    item_id: uuid.UUID
    bin_id: uuid.UUID
    lot_id: uuid.UUID | None
    on_hand_qty: Decimal


# --- Valuation + cost layers (PLAN 5.3) ---------------------------------------


class StockValuationRead(ApiModel):
    """One moving-average valuation row: an item's value + on-hand + average cost in a warehouse
    (D-020/D-037). The value SSOT for a MOVING_AVERAGE item; the inventory-value dashboard reads
    it."""

    item_id: uuid.UUID
    warehouse_id: uuid.UUID
    on_hand_qty: Decimal
    avg_unit_cost: Decimal
    total_value: Decimal


class CostLayerRead(ApiModel):
    """One FIFO cost layer: the remaining/original quantity and unit cost of a received batch
    (D-020). The FIFO value SSOT; the cost-layer drill-down for an item reads these."""

    id: uuid.UUID
    item_id: uuid.UUID
    warehouse_id: uuid.UUID
    receipt_move_id: uuid.UUID
    received_at: date
    original_qty: Decimal
    remaining_qty: Decimal
    unit_cost: Decimal
    created_at: datetime
