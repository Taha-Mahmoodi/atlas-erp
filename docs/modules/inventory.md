# Inventory (`backend/app/modules/inventory/`)

Inventory is the **second business module** (PLAN 5), sitting **just above finance** in the
dependency order (STRUCTURE §5): inventory may read `finance/queries.py`; every module above it
(procurement, sales, manufacturing) reads `inventory/queries.py`. The normative design lives in
[docs/architecture.md](../architecture.md) (D-020 inventory costing, D-029 opaque cross-module
ids); this guide is the operator/contributor map and grows with each inventory task (PLAN 5.1…5.4).

## Status

**PLAN 5.1 laid the master-data foundation;** PLAN 5.2 adds **warehouses, bins, the stock-move
ledger as the quantity single source of truth, and the on-hand projection.** Moving-average + FIFO
costing with same-transaction COGS posting and physical counts arrive in PLAN 5.3–5.4 — this package
grows in place.

| File | Concern | Key decision |
|---|---|---|
| `constants.py` | `ItemType`, `CostingMethod`, `TrackingMode`, `LotStatus`, `SerialStatus`, **`MoveType`, `MoveStatus`** enums + the **`MOVE_BIN_SIDES`** rule table + the stock-move sequence + permission keys (registered at import) | D-020, D-012, D-009 |
| `models/masters.py` | `ItemCategory`, `Uom`, `Item`, `UomConversion`, `Lot`, `SerialNumber` (5.1) | D-020, D-029, D-015 |
| `models/stock.py` | **`Warehouse`, `Bin`, `StockMove`, `StockQuant`** (5.2) — split into a `models/` package when the stock tables would have passed the 400-line cap (STRUCTURE §3) | D-020, D-036, D-012 |
| `schemas.py` | Create/Update/Read/Filter for masters + warehouses, bins, stock moves, on-hand | D-015 |
| `service/` | masters CRUD (5.1) + **`warehouses.py`, `bins.py`, `stock_moves.py`, `stock_quants.py`** (5.2) — fully re-exported from `__init__` | D-020, D-036, D-029 |
| `queries.py` | the cross-module read interface — item reads (5.1) + **`total_on_hand` / `on_hand` / `on_hand_by_bin` / `on_hand_by_lot`** (5.2) | STRUCTURE §5 |
| `router.py` + `stock_router.py` | REST under `/api/v1/inventory` — masters (5.1) + warehouses, bins, stock-moves, stock-on-hand (5.2, a mounted sibling sub-router, the finance `journal_router` precedent) | D-009, D-013, D-014, D-035 |

Migrations: `0020_inventory_items` (six master tables) + `0021_inventory_stock` (the four stock
tables). There is still **no `events.py` / `handlers.py`**: a 5.2 move publishes nothing
cross-module (on-hand is intra-module; D-020 computes costing *inside* the move transaction). Those
files arrive in 5.3, when `inventory.stock.issued` is published and `finance/handlers.py` posts COGS.

## Entities

- **`inv_item_categories`** — a grouping carrying the **default costing method** copied onto each
  item at create, and the **three GL accounts** COGS/valuation posting will need
  (`inventory_account_id`, `cogs_account_id`, `price_difference_account_id`). Those are **opaque
  finance uuids** (see "Cross-module" below), nullable on the category and validated-present in
  finance only when supplied.
- **`inv_uoms`** — unit definitions (EA, KG, BOX…). Base-ness is **not** here: which UoM is base is
  per item.
- **`inv_items`** — the item master. `item_code` is user-supplied and unique per tenant.
- **`inv_uom_conversions`** — per-item alternate UoMs (see "UoM conversion convention").
- **`inv_lots` / `inv_serials`** — lot/serial instance tables. Defined for 5.1; rows are created by
  receipts (5.2+), so 5.1 ships **no CRUD** for them.

## Item types

`item_type` decides stock participation:

- **STOCKED** — a physical good held in inventory; the **only** type that participates in stock
  moves, costing and lot/serial tracking.
- **NON_STOCKED** — purchasable/sellable but not held (drop-ship, expensed supplies).
- **SERVICE** — non-physical (labour, fees).

The service enforces **tracking only on STOCKED items**: a NON_STOCKED/SERVICE item must keep
`tracking_mode = NONE`.

## Item codes (no auto-numbering)

Item codes are **user-supplied and unique per tenant** (`UNIQUE(tenant_id, item_code)`), mirroring
how chart-of-accounts codes work (`Account.code` is required on create). Masters carry **no gapless
document number** — those are for journal entries / orders / receipts (D-012). So inventory
declares **no number sequence** in 5.1; when stock moves land (5.2) they register documents and
claim numbers, the item master itself does not. `item_code` is required on create.

## UoM conversion convention

Each item has **one `base_uom_id`**; all quantities are stored/costed in the base UoM. An
`UomConversion` row expresses an **alternate** UoM for that item as **`factor_to_base`**:

> multiplying a quantity in the alternate UoM by `factor_to_base` yields the **base-UoM** quantity.

Example: an item whose base is **EA** with a **BOX** conversion of factor **12** means **1 BOX =
12 EA**. `UNIQUE(tenant_id, item_id, alt_uom_id)` keeps one factor per (item, alternate); a DB
`CHECK(factor_to_base > 0)` backs the positive-factor rule.

This is the standard ERP shape (S/4HANA's alternative-UoM table): simpler than a full from/to
graph, and **base↔alt and alt↔alt both derive from the single per-alternate factor**. The pure
`service.convert_quantity(qty, from_uom, to_uom, base_uom, factors)` helper does
`qty * factors[from] / factors[to]` (base maps to factor 1), quantizing to scale 6 (D-015); an
unknown UoM for the item raises (conversions are per item). It is used by stock moves later but
shipped and unit-tested now.

## Costing method from category (D-020)

`Item.costing_method` (MOVING_AVERAGE | FIFO) is **defaulted from the item's category** when
omitted on create but **stored on the item**, because the item is the costing unit and D-020 lets
the method change only while no stock exists. The moving-average valuation table and FIFO cost
layers arrive in PLAN 5.3; 5.1 only records the method so receipts know which engine to run.

## Lot / serial tracking

`tracking_mode` (NONE | LOT | SERIAL) is **per item** and meaningful only for STOCKED items. The
`inv_lots` and `inv_serials` master tables exist now and are **populated at receipt** (5.2+): a
LOT-tracked item gets one `inv_lots` row per received batch, a SERIAL-tracked item one
`inv_serials` row per unit. `UNIQUE(tenant_id, item_id, lot_code)` /
`UNIQUE(tenant_id, item_id, serial_code)` keep codes unique within an item.

## Warehouses, bins, stock moves & on-hand (PLAN 5.2)

**Topology.** `inv_warehouses` group `inv_bins`; on-hand is tracked **per bin**. Both are reference
data (codes, not gapless numbers) and are **deactivated, never deleted** (`is_active=False`) because
moves and quants reference them. A bin's `code` is unique per `(tenant, warehouse)`.

**The move ledger is the quantity single source of truth (D-020).** `inv_stock_moves` is an
**append-only** ledger: each row is **POSTED at creation and IMMUTABLE** — there is no draft phase,
no edit, no delete. A move carries `DocumentMixin` (registered in `core_documents`) and a **gapless
`STK-` number claimed at creation** (D-012 claim-at-permanence — a move is permanent the moment it
exists). `quantity` is **always positive**; the **`move_type` decides direction** (which bins
participate), the universal-journal one-sided-amount philosophy applied to stock.

**Move types & required bin sides** (`constants.MOVE_BIN_SIDES`, validated in one place):

| move_type | from_bin | to_bin | effect |
|---|---|---|---|
| `RECEIPT` | — | required | stock enters a bin (purchase receipt, opening balance) |
| `ISSUE` | required | — | stock leaves a bin (goods issue, scrap) |
| `TRANSFER` | required | required (≠ from) | stock moves between bins, total conserved |
| `ADJUSTMENT` | exactly one side | exactly one side | a one-sided correction (decrease = from-only, increase = to-only) |

**The quant is a maintained projection (D-036), not a second source of truth.** `inv_stock_quants`
holds current on-hand per `(item, bin, lot)` and is updated **in the same transaction as every
move** (decrement from_bin, increment to_bin) — so on-hand is an **indexed point lookup**, not an
unbounded SUM over move history (PERFORMANCE §1), the moving-average `inv_item_valuations` precedent.
The move ledger stays the SSOT/audit trail; the quant is **reconcilable from it**. A quant reaching
exactly 0 is **deleted**, so the projection holds only live stock. Concurrency: the move engine
locks quant rows `with_for_update` (PG takes the row lock; SQLite omits the clause as a no-op,
D-020) in deterministic bin-id order (deadlock avoidance).

**Negative stock is forbidden outright (D-020), on both engines.** The service raises
`InsufficientStockError` → **422 `inventory.insufficient_stock`** *pre-flight*; the DB
**`CHECK (on_hand_qty >= 0)`** on `inv_stock_quants` is the bypass-proof backstop (a portable
single-column CHECK, proven on SQLite and Postgres by the `-m pg` guard tests).

**Lot / serial.** On a `RECEIPT` of a tracked item, a new `lot_code`/`serial_code` **creates** the
`inv_lots`/`inv_serials` master instance (5.1 deferred instance creation to receipts); an
`ISSUE`/`TRANSFER` must reference an existing one (its stock is then checked by the quant delta). A
**serial moves wholesale** — the service requires `quantity == 1` for a serial-tracked move.

**Corrections are reversals, not edits.** `POST /stock-moves/{id}/reverse` posts the **opposite
move** (from/to swapped, a `RECEIPT` reverses as an `ISSUE` and vice versa), linked to the original
via docflow `reverses`. The ledger stays append-only; a move may be reversed once.

**On-hand reads** (`inventory/queries.py`, what sales ATP / procurement call): `total_on_hand(item)`,
`on_hand(item, bin?, lot?)`, `on_hand_by_bin(item)`, `on_hand_by_lot(item)`. The HTTP projection is
`GET /stock-on-hand` (paginated, by item/bin). The move ledger is `GET /stock-moves` (paginated,
filtered by item/bin/type/date). `POST /stock-moves` and the reverse endpoint are **idempotent**
(D-013) — a move changes on-hand, so a retried request must not double-move.

## Cross-module reads (D-029 / STRUCTURE §5)

The category's GL-account ids are **opaque finance uuids**, never a cross-module FK: finance owns
those accounts. The inventory service validates each supplied id through
**`finance/queries.account_exists_by_id`** (a sanctioned cross-module read added for this task) —
the same pattern the journal stores finance dimension ids without an FK on a cross-module table.

`inventory/queries.py` is the **only inventory file other modules import**. For 5.1 it exposes:

- `get_item(session, tenant_id, item_id)` / `item_exists(...)`
- `uom_exists(...)` — the UoM analogue of `item_exists` (added in PLAN 8.1 for the manufacturing BOM
  header/component, which reference the parent/component UoM by opaque id, D-029); a UoM is a
  distinct inventory entity, so it has its own existence check
- `get_costing_method(...)` — MOVING_AVERAGE | FIFO
- `get_base_uom(...)` — the unit a document line in another UoM converts to
- `get_category_accounts(...)` — `(inventory_acct, cogs_acct, price_diff_acct)` so the COGS handler
  (5.2+) resolves where to post a goods issue.

## Permissions (D-009)

`inventory.item.read` / `inventory.item.manage`, `inventory.category.read` /
`inventory.category.manage`, `inventory.uom.read` / `inventory.uom.manage`, **`inventory.warehouse.read`
/ `inventory.warehouse.manage`, `inventory.bin.read` / `inventory.bin.manage`, `inventory.move.read`,
`inventory.move.create`, `inventory.valuation.read`** — registered into the core RBAC catalog at import. Every endpoint is
permission-guarded; the reference lists (item-categories, uoms, items, warehouses, bins) support
conditional GETs via a tenant-scoped collection ETag (PERFORMANCE §3 / D-035), while the
transactional lists (stock-moves, stock-on-hand) carry none. All list endpoints stay within the
≤3-query budget (PERFORMANCE §2), and `create_move` runs a bounded number of statements (no N+1).

## Costing (PLAN 5.3, D-020/D-037)

Inventory valuation is the inventory↔finance seam: every value-changing stock move updates the
**value SSOT** AND posts its COGS/inventory journal **in the same transaction** as the move and the
quant update. The move ledger + quants stay the **quantity SSOT**; `inv_item_valuations` (moving
average) and `inv_cost_layers` + `inv_layer_consumptions` (FIFO) are the **value SSOT**. Which engine
a `(item, warehouse)` uses is the item's `costing_method` (defaulted from its category, D-020). The
three GL account ids (inventory / COGS / price-difference) come from the item's category as **opaque
finance uuids** (D-029) — no cross-module FK.

### Stock-move cost input

`inv_stock_moves` carries a nullable `unit_cost` (MoneyType, full scale-6 precision):
- **RECEIPT / positive ADJUSTMENT** REQUIRE `unit_cost` — the value stock enters at (validated at the
  service edge before any write).
- **ISSUE / negative ADJUSTMENT** IGNORE any passed cost — the engine **computes** the outbound cost
  and writes it back onto the move.
- **TRANSFER** carries the current valuation (value-neutral within one inventory account).

### Moving average

Per `(item, warehouse)` in `inv_item_valuations` under `with_for_update` (PG row lock serializes
concurrent movers; SQLite omits FOR UPDATE as a no-op + single-writer lock, D-020):
- **Receipt:** `total_value += qty × unit_cost`; `on_hand += qty`; `avg = total_value / on_hand`
  **unrounded** (full precision, so successive issues never drift).
- **Issue:** `cogs = quantize(qty × avg, currency dp, HALF_UP)`; `total_value -= cogs`; `on_hand -=
  qty`. When `on_hand` hits **exactly 0**, the residual `total_value` is **flushed** to the
  price-difference account so value and quantity never disagree — even when the average is
  non-terminating, value lands at exactly 0.

### FIFO

One `inv_cost_layers` row per receipt (`original_qty = remaining_qty = qty`, `unit_cost`), consumed
oldest-first by `(received_at, created_at, id)` under `with_for_update` (each receipt is its own
transaction, so `created_at` is the insertion-order tiebreaker when dates tie — uuid4 ids are not
monotonic). One `inv_layer_consumptions` row per touched layer records `qty` + `cost`; COGS is the
sum of per-layer `quantize(qty_from_layer × unit_cost)`. A `CHECK(0 <= remaining_qty <= original_qty)`
backs it on both engines.

### Same-transaction COGS via the event bus (D-011)

`create_move` computes cost, updates the valuation/layers, then `publish(StockValued(...))` carrying
the value Δ + the three GL account ids + the chosen **offset account**. The endpoint runs in
`run_in_uow`, which drains the event **before commit**: `finance/handlers.py` builds + posts the
journal **through the finance posting service** (never raw inserts) in the shared session. One commit
= move + quant + valuation + journal + docflow link; **any handler failure rolls the whole
transaction back**, so a stock move can never exist without its journal entry (the most-tested
invariant). The handler is registered at the app factory (`register_event_handlers`), the
deterministic D-011 registration seam.

### GL postings per move type

| Move | Posting |
|------|---------|
| RECEIPT / ADJUSTMENT-up | Dr inventory / Cr price-difference (standalone offset; procurement GR overrides later) |
| ISSUE | Dr COGS / Cr inventory at the computed cost |
| ADJUSTMENT-down | Dr price-difference / Cr inventory (write-off, no document) |
| TRANSFER (within one inventory account) | **no journal** — value-neutral (the engine publishes no event) |
| MAV zero-qty flush | residual to price-difference **within the issue's entry** |
| Reversal | the **exact reverse** of the original move's entry (reversing an issue credits COGS; reversing a receipt debits price-difference) |

The COGS journal posts with the move's `move_date`. **A move dated into a CLOSED period fails** — the
finance period trigger fires inside the same transaction and rolls the whole move back. You cannot
move stock into a closed accounting period; this is correct by construction.

### Reversal

A reversing move runs the **costing reversal** path (replay, not recompute): reversing an ISSUE
replays its `inv_layer_consumptions` rows backward onto the exact layers (restoring `remaining_qty`)
or re-adds the moving-average value at the **original** cost; reversing a RECEIPT zeros its layer
(only valid while unconsumed) or removes the moving-average value. It emits the opposite `StockValued`
event so the COGS journal is reversed too.

### Read endpoints + queries

`GET /api/v1/inventory/stock-valuations` (per item/warehouse value + qty + avg cost) and
`GET /api/v1/inventory/items/{id}/cost-layers` (FIFO layers, oldest-first) — guarded by
`inventory.valuation.read`. `inventory/queries.py` adds `item_value(item, warehouse?)` and
`valuation_summary()` (the inventory-value dashboard KPI). The qty × cost product is summed in
**Python** (each factor a typed Decimal), never `func.sum(qty × cost)` — multiplying two
scaled-integer columns on SQLite would yield a ×10^12 value the MoneyType result processor cannot
un-scale (D-015 trigger discipline).

## Physical & cycle counts (PLAN 5.4, D-038)

A **stock count** captures the warehouse team's *counted* quantity per `(item, bin, lot)`, compares
it to system on-hand, and posts the differences. Two tables: `inv_stock_counts` (the count document —
`DocumentMixin` + a gapless `CNT-` number claimed at creation, `count_type`, `warehouse_id`,
`status`, `count_date`) and `inv_stock_count_lines` (one line per in-scope quant — `system_qty`
snapshot, `counted_qty`, and, filled at post, `variance_qty` / `adjustment_move_id` / `unit_cost`).

**Physical vs cycle.** A `PHYSICAL` count snapshots **every** quant in the warehouse; a `CYCLE` count
snapshots only the chosen `item_ids` / `bin_ids` (the recurring spot count). The type only changes
which quants are enumerated into lines — the post path is identical for both.

**The flow: snapshot → count → post.** `POST /api/v1/inventory/stock-counts` creates the count
(`DRAFT`) and snapshots one line per in-scope quant with `system_qty` = current on-hand and
`counted_qty` NULL. `POST /stock-counts/{id}/lines/{line}/count` records a counted quantity and moves
the count to `COUNTING`. `GET /stock-counts/{id}/variance-preview` shows per-line live-system vs
counted vs variance vs estimated value impact before posting. `POST /stock-counts/{id}/post` posts
the variances; `POST /stock-counts/{id}/cancel` abandons a `DRAFT`/`COUNTING` count.

**Variance posts via an ADJUSTMENT move, never a bespoke journal (D-038).** For each line the post
computes `variance = counted − live-system`; a non-zero variance posts ONE stock **ADJUSTMENT** move
through `stock_moves.create_move` (positive → ADJUSTMENT *into* the bin, negative → *out of* it). That
move runs the 5.3 costing engine and publishes `StockValued`, so the price-difference journal posts
via the event bus **in the same transaction** — the count inherits every costing/GL/audit invariant
for free. The count's document is linked to each adjustment move via docflow (`counts`), so the
DocFlow viewer renders count → adjustment-move → journal. A **zero-variance** line posts no move
(`adjustment_move_id` stays NULL). The positive-adjustment **unit cost** is sourced from
`queries.current_unit_cost` (the moving-average `avg_unit_cost`, or the FIFO live-layer weighted
average — the same book cost a value-neutral transfer carries), so the value added matches the book
cost; an item the system thinks is empty enters at cost 0 (a quantity-only correction).

**`system_qty` is re-validated at post (D-038 concurrency safety).** The `system_qty` snapshot is only
the *preview* baseline; `post_count` **re-reads live on-hand** for each line as the authoritative
system quantity, so a move that lands between snapshot and post can never post a wrong variance — the
resulting on-hand always equals the *counted* quantity, not `counted − stale`.

**Closed-period interaction.** The whole post runs in `run_in_uow`, so every variance move's costing
journal + the count commit as one transaction. A **closed-period `count_date`** makes the
adjustment's journal trip the period trigger inside that transaction, rolling the **whole** post back
— the count stays unposted (D-018).

**`POSTED` is terminal.** A posted count is never re-posted (the status guard rejects re-post — no
double adjustment, D-013) and never cancelled; corrections are new counts/adjustments (the
append-only ledger philosophy). Posting requires **every** line to be counted (else 422).

**Large counts run as a background job (PERFORMANCE §3).** A post whose snapshot shows more than
`COUNT_POST_SYNC_MAX_VARIANCES` (200) variance lines is submitted as an `inventory.count_post` job
and returns `202 {job_id}` for `/api/v1/jobs` polling; at or below it the post runs inline (200) —
mirroring the depreciation-run (100) / bank-import (1000) thresholds. The job handler delegates to the
same `post_count` engine, so the re-validation and one-transaction guarantee hold off-request too.

Permissions: `inventory.count.read` (the GETs), `inventory.count.manage` (create / record-count /
cancel), `inventory.count.post` (the privileged post — it changes on-hand AND posts GL journals).

## Valuation-offset override on a RECEIPT (PLAN 6.3 / D-041)

A standalone RECEIPT (opening balance, manual stock-in) posts **Dr Inventory / Cr price-difference**
— the costing engine's default offset. `create_move` accepts an optional
`valuation_offset_account_id` that, when provided for a RECEIPT, **OVERRIDES** that offset: the
`StockValued` event carries it as `offset_account_id` and finance's handler credits it instead. This
is the sanctioned override path for procurement's goods receipt (6.3): the inventory handler that
reacts to `procurement.goods_receipt.posted` creates each RECEIPT move with the GR/IR clearing
account as the offset, yielding **Dr Inventory / Cr GR-IR** (the three-way-match clearing leg) rather
than price-difference. The override is ignored on non-receipt move types (an ISSUE charges COGS, an
ADJUSTMENT/TRANSFER its own offset) and on reversals; default `None` ⇒ behaviour unchanged. It
threads end-to-end `create_move → costing.apply_costing → StockValued.offset_account_id →
finance/handlers` and changes only the Cr leg, never the costing math.

The cross-module bridge lives in `inventory/handlers.py` (new): it subscribes to procurement's
`GoodsReceiptPosted` event and creates the moves in the same transaction — the mirror of the
inventory→finance COGS handler (inventory publishes, finance handles), here procurement publishes and
inventory handles. The GR↔move linkage is recorded via docflow (`moved_by`), not a cross-module FK.
