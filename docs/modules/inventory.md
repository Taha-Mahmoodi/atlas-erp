# Inventory (`backend/app/modules/inventory/`)

Inventory is the **second business module** (PLAN 5), sitting **just above finance** in the
dependency order (STRUCTURE §5): inventory may read `finance/queries.py`; every module above it
(procurement, sales, manufacturing) reads `inventory/queries.py`. The normative design lives in
[docs/architecture.md](../architecture.md) (D-020 inventory costing, D-029 opaque cross-module
ids); this guide is the operator/contributor map and grows with each inventory task (PLAN 5.1…5.4).

## Status

**PLAN 5.1 (this task) lays the master-data foundation:** item categories, units of measure,
per-item UoM conversions, the item master (typed STOCKED/NON_STOCKED/SERVICE with per-item base
UoM, costing method and lot/serial tracking), and the lot/serial instance tables (defined now,
populated by receipts later). Stock moves as the single source of truth, on-hand/availability
projections, moving-average + FIFO costing with same-transaction COGS posting, and physical counts
arrive in PLAN 5.2–5.4 — this package grows in place.

| File | Concern | Key decision |
|---|---|---|
| `constants.py` | `ItemType`, `CostingMethod`, `TrackingMode`, `LotStatus`, `SerialStatus` enums + the six permission keys (registered at import) | D-020, D-009 |
| `models.py` | `ItemCategory`, `Uom`, `Item`, `UomConversion`, `Lot`, `SerialNumber` | D-020, D-029, D-015 |
| `schemas.py` | Create/Update/Read/Filter for categories, UoMs, items, conversions | D-015 |
| `service/` (`categories.py`, `uoms.py`, `items.py`, `conversions.py`) | CRUD + validation for all four masters + the pure `convert_quantity` helper — split into a package at the 400-line cap (STRUCTURE §8.4), fully re-exported from `__init__` | D-020, D-029 |
| `queries.py` | the cross-module read interface (item existence, base UoM, costing method, category accounts) | STRUCTURE §5 |
| `router.py` | REST under `/api/v1/inventory` — categories, UoMs, items, nested uom-conversions | D-009, D-014, D-035 |

Migration `0020_inventory_items` creates the six `inv_` tables. There is **no `events.py` /
`handlers.py` yet**: masters drive no cross-module effects, and the no-stub rule forbids empty
files — those files arrive with stock moves in 5.2, when `inventory.stock.issued` is published and
`finance/handlers.py` posts COGS (D-020).

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

## Cross-module reads (D-029 / STRUCTURE §5)

The category's GL-account ids are **opaque finance uuids**, never a cross-module FK: finance owns
those accounts. The inventory service validates each supplied id through
**`finance/queries.account_exists_by_id`** (a sanctioned cross-module read added for this task) —
the same pattern the journal stores finance dimension ids without an FK on a cross-module table.

`inventory/queries.py` is the **only inventory file other modules import**. For 5.1 it exposes:

- `get_item(session, tenant_id, item_id)` / `item_exists(...)`
- `get_costing_method(...)` — MOVING_AVERAGE | FIFO
- `get_base_uom(...)` — the unit a document line in another UoM converts to
- `get_category_accounts(...)` — `(inventory_acct, cogs_acct, price_diff_acct)` so the COGS handler
  (5.2+) resolves where to post a goods issue.

## Permissions (D-009)

`inventory.item.read` / `inventory.item.manage`, `inventory.category.read` /
`inventory.category.manage`, `inventory.uom.read` / `inventory.uom.manage` — registered into the
core RBAC catalog at import. Every endpoint is permission-guarded; the reference lists
(item-categories, uoms, items) support conditional GETs via a tenant-scoped collection ETag
(PERFORMANCE §3 / D-035) and stay within the ≤3-query list budget (PERFORMANCE §2).
