"""Inventory constants (STRUCTURE §3): enums (UPPER_SNAKE values stored as strings) and the
permission keys, registered into the core RBAC catalog at import (D-009).

Started as a SINGLE file (STRUCTURE §8.4: split into a constants/ package only at the 400-line
cap, the finance precedent); it sits well under that for PLAN 5.1.

Item codes are USER-SUPPLIED and unique per tenant (the ``UNIQUE(tenant_id, item_code)`` on
inv_items) — mirroring how chart-of-accounts codes work (Account.code is required on create, not
auto-numbered). So item/warehouse/bin MASTERS carry no gapless document number (codes, not
numbers). Stock MOVES (PLAN 5.2) DO register documents and claim a gapless number — the
``inventory.stock_move`` sequence below — because a move is a posted document in the D-012 sense.
"""

from enum import StrEnum

from app.core.rbac import register_permissions

# Quantity scale (D-015): QuantityType stores scale-6 micro-units. Stock moves and quants use the
# same scale; the on-hand>=0 CHECK and the quant sums are exact on both engines.


class ItemType(StrEnum):
    """What an item IS, which decides whether it carries stock (D-020).

    - STOCKED: a physical good tracked in inventory — the only type that participates in stock
      moves, costing and lot/serial tracking.
    - NON_STOCKED: a purchasable/sellable good NOT held in inventory (e.g. drop-ship, expensed
      supplies) — no on-hand quantity, no costing layer.
    - SERVICE: a non-physical line item (labour, fees) — never stocked, never tracked.

    The service rejects tracking/costing participation for NON_STOCKED/SERVICE so the invariant
    "only STOCKED items have stock" holds from the masters up (validated again when moves land)."""

    STOCKED = "STOCKED"
    NON_STOCKED = "NON_STOCKED"
    SERVICE = "SERVICE"


class CostingMethod(StrEnum):
    """How a stocked item is valued (D-020). Defaulted onto the item FROM its category at create
    but STORED on the item, because D-020 changes it only while no stock exists and the item is
    the costing unit. The moving-average valuation table and FIFO cost layers arrive in PLAN 5.3;
    5.1 only records the method so receipts know which engine to use."""

    MOVING_AVERAGE = "MOVING_AVERAGE"
    FIFO = "FIFO"


class TrackingMode(StrEnum):
    """Whether a stocked item's units are individually identified (parity: batch/serial mgmt).

    - NONE: fungible — quantity only (the default).
    - LOT: grouped by lot/batch code; one lot row per received batch (inv_lots), created at
      receipt (5.2+).
    - SERIAL: each unit uniquely identified; one inv_serials row per unit, created at receipt.

    Tracking is PER ITEM and only meaningful for STOCKED items — the service forbids a non-NONE
    mode on NON_STOCKED/SERVICE items."""

    NONE = "NONE"
    LOT = "LOT"
    SERIAL = "SERIAL"


class LotStatus(StrEnum):
    """Lifecycle of a lot/batch instance (parity: batch management). For 5.1 the table merely
    EXISTS — lots are created during receipts (5.2+); AVAILABLE is the default a receipt sets,
    the others are reached by later quality/expiry flows. No dead CRUD now (masters-only)."""

    AVAILABLE = "AVAILABLE"
    BLOCKED = "BLOCKED"
    CONSUMED = "CONSUMED"


class SerialStatus(StrEnum):
    """Lifecycle of a serial-number instance (parity: serial management). Like LotStatus, the
    table exists for 5.1 and is populated at receipt (5.2+): IN_STOCK on receipt, ISSUED when
    the unit leaves, BLOCKED by quality holds."""

    IN_STOCK = "IN_STOCK"
    ISSUED = "ISSUED"
    BLOCKED = "BLOCKED"


class MoveType(StrEnum):
    """The kind of stock movement (PLAN 5.2). The move's QUANTITY is always positive; the TYPE
    decides which of from_bin/to_bin participate (the direction), so a single signed-quantity
    column is never needed (the journal one-side-CHECK philosophy applied to stock):

    - RECEIPT: stock enters a bin from outside inventory (purchase receipt, opening balance,
      positive count adjustment). to_bin REQUIRED, from_bin must be NULL.
    - ISSUE: stock leaves a bin to outside inventory (goods issue, scrap, negative count).
      from_bin REQUIRED, to_bin must be NULL.
    - TRANSFER: stock moves between two bins, conserving total on-hand. BOTH bins REQUIRED and
      they must differ.
    - ADJUSTMENT: a one-sided correction not tied to a business document. EXACTLY ONE of
      from_bin (a decrease) / to_bin (an increase) is set — the side carries the signed intent
      while quantity stays positive (a decrease is from_bin-only, an increase is to_bin-only)."""

    RECEIPT = "RECEIPT"
    ISSUE = "ISSUE"
    TRANSFER = "TRANSFER"
    ADJUSTMENT = "ADJUSTMENT"


class MoveStatus(StrEnum):
    """Lifecycle of a stock move (PLAN 5.2). Unlike journal entries (DRAFT→POSTED), a stock move
    is created already POSTED and is IMMUTABLE: the move ledger IS the single source of truth for
    quantity, so a move never has a draft phase and is never edited or deleted — corrections are
    REVERSING moves (an opposite move linked via docflow, the append-only ledger philosophy of
    D-017 applied to stock). The column exists for symmetry with the rest of the platform and to
    leave room for a future draft/scheduled-move lifecycle, but every move 5.2 creates is POSTED."""

    POSTED = "POSTED"


# Required bin sides per move type (PLAN 5.2): (from_bin_required, to_bin_required). ADJUSTMENT is
# the special case — exactly one side, validated separately (the service checks the XOR). Used by
# the create-move validator so the rule lives in ONE place, greppable and testable.
MOVE_BIN_SIDES: dict[MoveType, tuple[bool, bool]] = {
    MoveType.RECEIPT: (False, True),
    MoveType.ISSUE: (True, False),
    MoveType.TRANSFER: (True, True),
    # ADJUSTMENT: not in the strict table — the service enforces "exactly one side set".
}


# Stock-move document type + number sequence (D-012): a move registers in core_documents and
# claims its gapless number AT CREATION (a move is permanent at creation — POSTED immediately —
# so it is numbered immediately, the orders/receipts claim-timing branch, not the draft branch).
# The sequence year-resets (STK-2026-00001).
STOCK_MOVE_DOC_TYPE = "inventory.stock_move"
STOCK_MOVE_SEQUENCE_NAME = "inventory.stock_move"
STOCK_MOVE_NUMBER_PREFIX = "STK"
STOCK_MOVE_NUMBER_PADDING = 5

# docflow link type joining a reversing move to the move it reverses (D-012 vocabulary): a
# correction is a NEW move, never an edit, so the ledger stays append-only.
STOCK_MOVE_REVERSES_LINK = "reverses"


# --- Costing (PLAN 5.3, D-020/D-037) ------------------------------------------
# The domain-event key inventory publishes when a move changes valuation (D-011). finance/handlers
# subscribes and posts the COGS/inventory journal in the SAME transaction (D-020). One key carrying
# the move_type; the handler branches on it for the per-move-type postings.
STOCK_VALUED_EVENT_KEY = "inventory.stock.valued"

# docflow link type joining a stock move's document to the journal entry the costing event posts
# (D-012 vocabulary): the move "posts" the valuation journal, mirroring finance's own 'posts' edge.
STOCK_MOVE_POSTS_LINK = "posts"


# --- Physical & cycle counts (PLAN 5.4, D-038) --------------------------------
class CountType(StrEnum):
    """What a stock count covers (parity: physical inventory vs cycle counting).

    - PHYSICAL: a whole-warehouse snapshot — every quant in the warehouse becomes a count line.
    - CYCLE: a chosen subset — the caller picks the items and/or bins to count (the recurring
      ABC-style spot count), so only quants matching that scope become lines.

    The type only changes which quants are enumerated into lines at populate time; the post path
    is identical (variance → ADJUSTMENT move) for both."""

    PHYSICAL = "PHYSICAL"
    CYCLE = "CYCLE"


class CountStatus(StrEnum):
    """Lifecycle of a stock count (PLAN 5.4):

    - DRAFT: created, scope chosen, lines snapshotted (system_qty captured, counted_qty NULL).
    - COUNTING: at least one counted quantity recorded — the warehouse team is entering counts.
    - POSTED: variances posted as ADJUSTMENT moves; TERMINAL — a posted count is never re-posted
      or cancelled (corrections are NEW counts/adjustments, the append-only ledger philosophy).
    - CANCELLED: abandoned before posting (only from DRAFT/COUNTING)."""

    DRAFT = "DRAFT"
    COUNTING = "COUNTING"
    POSTED = "POSTED"
    CANCELLED = "CANCELLED"


# Count document type + number sequence (D-012): a count registers in core_documents and claims its
# gapless CNT number AT CREATION (a count is a real document the moment it exists — its number is
# the stable handle the warehouse team references while counting, so it is claimed at creation, the
# orders/receipts branch, not the draft-numbered-at-post branch). Year-resets (CNT-2026-00001).
STOCK_COUNT_DOC_TYPE = "inventory.stock_count"
STOCK_COUNT_SEQUENCE_NAME = "inventory.count"
STOCK_COUNT_NUMBER_PREFIX = "CNT"
STOCK_COUNT_NUMBER_PADDING = 5

# docflow link type joining a count's document to each ADJUSTMENT move it generates at post (D-012
# vocabulary): the count "counts" the move into existence — the variance-posting edge the DocFlow
# viewer renders from the count to its adjustment moves.
STOCK_COUNT_ADJUSTMENT_LINK = "counts"

# Background-job threshold (PERFORMANCE §3): a count whose post would generate more than this many
# variance (non-zero) lines runs as an 'inventory.count_post' job (202 {job_id}); at or below it the
# post runs inline (201) — mirroring the depreciation-run (100) / bank-import (1000) precedent. Each
# variance is a real ADJUSTMENT document, so the post is O(N) moves; above this count the request is
# backgrounded so it cannot hit a proxy timeout.
COUNT_POST_SYNC_MAX_VARIANCES = 200

# The background-job type for a large count post (code-defined registry key, like the permission
# catalog — a job type exists because a handler for it ships in the codebase).
COUNT_POST_JOB = "inventory.count_post"

# The currency the COGS/inventory valuation journal posts in when the tenant has not configured a
# functional currency (the v1 single-currency default, mirroring the journal tests' USD/2-dp). When
# a functional currency IS configured the handler uses it; either way costs quantize to its decimals
# (D-015). Stored layer/valuation costs keep full scale-6 precision — only the posted COGS rounds.
DEFAULT_COSTING_CURRENCY = "USD"


# --- Permissions (D-009): one key per guarded endpoint action -----------------
INVENTORY_ITEM_READ = "inventory.item.read"
INVENTORY_ITEM_MANAGE = "inventory.item.manage"
INVENTORY_CATEGORY_READ = "inventory.category.read"
INVENTORY_CATEGORY_MANAGE = "inventory.category.manage"
INVENTORY_UOM_READ = "inventory.uom.read"
INVENTORY_UOM_MANAGE = "inventory.uom.manage"
# Warehouses + bins (PLAN 5.2): reference data — read vs create/edit.
INVENTORY_WAREHOUSE_READ = "inventory.warehouse.read"
INVENTORY_WAREHOUSE_MANAGE = "inventory.warehouse.manage"
INVENTORY_BIN_READ = "inventory.bin.read"
INVENTORY_BIN_MANAGE = "inventory.bin.manage"
# Stock moves (PLAN 5.2): read the move ledger + on-hand vs create a move (which is POSTED and
# changes on-hand, so it is its own action — the journal.post precedent).
INVENTORY_MOVE_READ = "inventory.move.read"
INVENTORY_MOVE_CREATE = "inventory.move.create"
# Stock valuation visibility (PLAN 5.3): reading the moving-average/FIFO valuation + cost layers is
# its own read action (a finance-adjacent concern — value, not just quantity), distinct from the
# move-ledger read so the value views can be granted to costing/controlling roles independently.
INVENTORY_VALUATION_READ = "inventory.valuation.read"
# Physical/cycle counts (PLAN 5.4): read counts/variances vs create+edit a count (scope, snapshot,
# record counted qty) vs POST it (the privileged action — posting variances changes on-hand AND
# posts GL journals via the 5.3 path, so it is its own key, the journal.post / depreciation.run
# precedent).
INVENTORY_COUNT_READ = "inventory.count.read"
INVENTORY_COUNT_MANAGE = "inventory.count.manage"
INVENTORY_COUNT_POST = "inventory.count.post"

register_permissions(
    INVENTORY_ITEM_READ,
    INVENTORY_ITEM_MANAGE,
    INVENTORY_CATEGORY_READ,
    INVENTORY_CATEGORY_MANAGE,
    INVENTORY_UOM_READ,
    INVENTORY_UOM_MANAGE,
    INVENTORY_WAREHOUSE_READ,
    INVENTORY_WAREHOUSE_MANAGE,
    INVENTORY_BIN_READ,
    INVENTORY_BIN_MANAGE,
    INVENTORY_MOVE_READ,
    INVENTORY_MOVE_CREATE,
    INVENTORY_VALUATION_READ,
    INVENTORY_COUNT_READ,
    INVENTORY_COUNT_MANAGE,
    INVENTORY_COUNT_POST,
    descriptions={
        INVENTORY_ITEM_READ: "Read items and their UoM conversions",
        INVENTORY_ITEM_MANAGE: "Create and edit items and their UoM conversions",
        INVENTORY_CATEGORY_READ: "Read item categories",
        INVENTORY_CATEGORY_MANAGE: "Create and edit item categories",
        INVENTORY_UOM_READ: "Read units of measure",
        INVENTORY_UOM_MANAGE: "Create and edit units of measure",
        INVENTORY_WAREHOUSE_READ: "Read warehouses",
        INVENTORY_WAREHOUSE_MANAGE: "Create and edit warehouses",
        INVENTORY_BIN_READ: "Read storage bins",
        INVENTORY_BIN_MANAGE: "Create and edit storage bins",
        INVENTORY_MOVE_READ: "Read the stock-move ledger and on-hand projections",
        INVENTORY_MOVE_CREATE: "Create stock moves (receipts, issues, transfers, adjustments)",
        INVENTORY_VALUATION_READ: "Read stock valuations and FIFO cost layers",
        INVENTORY_COUNT_READ: "Read stock counts and their variances",
        INVENTORY_COUNT_MANAGE: "Create stock counts and record counted quantities",
        INVENTORY_COUNT_POST: "Post stock-count variances as adjustment moves",
    },
)
