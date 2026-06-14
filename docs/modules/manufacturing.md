# Manufacturing (`backend/app/modules/manufacturing/`)

Manufacturing is the **fifth business module** (PLAN 8), sitting **above inventory** in the
dependency order (STRUCTURE §5): it may read `finance/queries.py` and `inventory/queries.py`
**downward** (D-029), and exposes `manufacturing/queries.py` as the only file the modules above it
(production orders 8.2, MRP 8.3) import. The normative design lives in
[docs/architecture.md](../architecture.md) (D-029 opaque cross-module ids, D-015 money/quantity
types) and the **D-047** decision in [DECISIONS.md](../../DECISIONS.md); this guide is the
operator/contributor map and grows with each manufacturing task (PLAN 8.1…8.3).

## Status

**Phase 8 / Manufacturing is COMPLETE.** PLAN 8.1 laid the PP master data — multi-level versioned
**BOMs**, **work centres**, **routings** (s4hana-parity PP: all FULL); 8.2 added **production orders**
(reserve → issue to WIP → finish to stock, the manufacturing↔inventory↔finance seam, D-048); 8.3
added the deterministic **MRP run + rough capacity check** (D-049). Sections below cover each in turn;
`models/`, `service/`, `schemas/` are split into per-concern files (the BOM/routing/production/mrp
split) and re-exported from each package `__init__`.

| File | Concern | Key decision |
|---|---|---|
| `constants.py` | `BomStatus`, `RoutingStatus` enums + permission keys (registered at import) + the identity/numbering/activation documentation | D-047, D-009 |
| `models/workcenters.py` | `WorkCenter` (`mfg_work_centers`) | D-029, D-015 |
| `models/boms.py` | `Bom` (`mfg_boms`) header + `BomComponent` (`mfg_bom_components`) | D-047, D-029, D-015 |
| `models/routings.py` | `Routing` (`mfg_routings`) header + `RoutingOperation` (`mfg_routing_operations`) | D-047, D-029, D-015 |
| `schemas/` | Create/Update/Read/Filter for work centres + BOM header (+ component sub-resource) + routing header (+ operation sub-resource) | D-015 |
| `service/` | `work_centers.py`, `boms.py`, `routings.py` (CRUD + activate/deactivate + the `*_for` read helpers) — re-exported from `__init__` | D-047, D-029 |
| `queries.py` | the cross-module read interface 8.2/8.3 use | STRUCTURE §5 |
| `router.py` + `bom_router.py` + `routing_router.py` | REST under `/api/v1/manufacturing` — work centres here, BOMs + routings as mounted sibling sub-routers (the finance `journal_router` / inventory `stock_router` precedent) | D-009, D-014, D-035 |

Migration: `0032_manufacturing_masters` (five `mfg_` tables + indexes, no triggers). There is **no
`events.py` / `handlers.py`**: masters drive no cross-module effects — production orders in 8.2 will
publish the first manufacturing events (issue to WIP, finish to stock).

## Identity, versioning, activation (D-047)

**A BOM and a routing are identified by `(item_id, version)`** — the item they produce/make plus a
user-supplied version string — `UNIQUE(tenant_id, item_id, version)`. This mirrors S/4HANA keying a
BOM by material + alternative. **Work centres** carry a user-supplied `code` unique per tenant
(`UNIQUE(tenant_id, code)`), the item_code / vendor_code / customer_code master-data precedent.
**Masters carry no gapless document number** — a code/version is a stable handle, not a posted
document number; the *production orders* in 8.2 will claim gapless numbers (D-012), the masters do
not.

**Lifecycle (DRAFT → ACTIVE → INACTIVE):**

- **DRAFT** — editable. A new version is born DRAFT; its header, components/operations may be added,
  changed and removed.
- **ACTIVE** — usable by 8.2/8.3 and **frozen**: components/operations are immutable. Activating
  requires at least one component (BOM) / operation (routing). At most **one ACTIVE + default
  version per item** — activating a version demotes the previously-default ACTIVE version's
  `is_default` flag, so `get_active_bom_for_item` / `get_active_routing_for_item` resolve exactly
  one. Corrections to an active recipe are a **new version**, never an edit (the append-only-master
  philosophy).
- **INACTIVE** — retired (a deactivated former-default), kept for history, never deleted.

This is the **DRAFT-editable-then-activate** model: edit freely while DRAFT, freeze on activation.

## Multi-level BOMs — "via references"

The **schema is single-level-per-BOM**: a `Bom` header lists the **direct** `BomComponent` lines of
one parent item. "Multi-level" emerges because a component item can itself be the parent of its
**own** `Bom`. The full tree is resolved by **explosion at MRP time (8.3)**, which walks a component
item → its active BOM → its components recursively (carrying a visited set + depth cap, the
`docflow.get_chain` precedent). The masters enforce only the local invariant — a **direct
self-component** (a component whose item is the BOM's own parent) is rejected; deeper cycles
(A→B→A) are an 8.3 explosion-time concern, not expressible on a single-level row.

`BomComponent.scrap_percent` is the per-component waste allowance (extra material to plan for, 0 =
none) — 8.2/8.3 inflate the required quantity by it. `Bom.base_quantity` is how many parent units
the BOM yields; component `quantity_per` is per `base_quantity`.

## Work centres + capacity

A `WorkCenter` is the resource an operation runs on. `capacity_hours_per_day` is the available
hours/day 8.3's **rough capacity check** compares operation load against; `efficiency_percent`
(default 100) scales throughput. `cost_center_id` is an **opaque finance** cost-centre id (D-029),
nullable, validated via `finance/queries.cost_center_exists` when set — for the later activity-rate
costing (8.2+). No cross-module FK.

## Routings + operations + times

A `Routing` is the operation sequence to make an item. Each `RoutingOperation` pins a step to a work
centre (`work_center_id`, an **intra-module** composite tenant FK to `mfg_work_centers`) with two
**minute** durations (D-015 `QuantityType`, scale-6 — fractional minutes are exact on both engines):
`setup_time_minutes` (fixed per production order) and `run_time_minutes_per_unit` (per produced
unit). 8.3 loads a work centre as `setup + run × order_qty`. `operation_number` (10/20/30…) is unique
per routing and the run order — auto-appended as the next multiple of 10 when omitted.

## Opaque cross-module ids (D-029)

BOM/routing **item ids** and the BOM **UoM ids** are **opaque inventory ids** — no FK to
`inv_items` / `inv_uoms`. The service validates them via `inventory/queries.item_exists` /
`inventory/queries.uom_exists` (the new `uom_exists` query added in 8.1) before writing. The work
centre's `cost_center_id` is an opaque **finance** id validated via `finance/queries`. This is the
same id-only relationship inventory uses for finance GL accounts: the owning module guarantees the
id; manufacturing never reaches across with an FK.

## The `queries.py` read interface (the 8.2/8.3 contract)

`get_bom` / `get_active_bom_for_item(item_id)` (the ACTIVE default version) / `bom_components(bom_id)`
· `get_routing` / `get_active_routing_for_item(item_id)` / `routing_operations(routing_id)` ·
`get_work_center` / `work_center_capacity(work_center_id)`. 8.3 adds the MRP supply/output reads:
`open_production_order_supply(item_id)` (un-finished open-order quantity, the production analogue of
`procurement.open_incoming_quantity`), `planned_make_supply(item_id)` (firmed/converted planned-order
quantity), `get_mrp_run` / `planned_orders(run_id)`. This is the **only** manufacturing file other
modules import — thin, stable, no service imports.

## Production orders (8.2, D-048) — the manufacturing↔inventory↔finance seam

A **production order** (`mfg_production_orders`, prefix `MO-`) turns components into a finished parent
item. Lifecycle: **DRAFT** (created + the active BOM **exploded** into reserved
`mfg_production_order_components` rows and the routing snapshotted into
`mfg_production_order_operations`) → **RELEASED** (materials reserved — the component rows ARE the
reservation, v1 ATP-style; release does not block on availability) → **IN_PROGRESS** (components
issued to WIP) → **FINISHED** (parent produced to stock) | **CANCELLED** (DRAFT/RELEASED only — once
issued the order must finish, issued stock + WIP cannot strand).

**Explosion (single-level):** `required_quantity = quantity_per × order_qty × (1 + scrap_percent/100)`,
quantized. A sub-assembly component is produced by its OWN order (multi-level via references, D-047);
this order issues it as a finished material, it does not recurse.

**The WIP accounting (event bus, §5):** manufacturing PUBLISHES; inventory/finance handle. Manufacturing
imports only `inventory/queries` + `finance/queries` + its own events — never inventory/finance service.

- **Issue to WIP** — `issue_components` publishes `ComponentsIssued` → inventory's handler creates an
  ISSUE move per component with `valuation_offset_account_id` = the WIP account (the 6.3 GR/IR-override
  pattern applied to an ISSUE) → the costing event posts **Dr WIP / Cr Inventory** at the component's
  moving-average/FIFO cost. The order raises each component's `issued_quantity` and its
  `accumulated_wip_cost` (the running WIP debit, the SSOT for the invariant) and goes IN_PROGRESS.
- **Finish to stock** — `finish_order` publishes `OrderFinished` → inventory's handler creates a RECEIPT
  move with `unit_cost` = accumulated WIP / ordered quantity and the WIP offset → **Dr Inventory / Cr
  WIP**. On the FINAL finish any residual WIP is carried on the event so finance's
  `post_production_variance` handler posts **Dr/Cr WIP / Cr/Dr production-variance** (over/under-
  absorption — the MAV zero-quantity-flush analogue) so **WIP nets to ZERO** at completion.

**WIP-nets-to-zero invariant (proven end-to-end):** once an order is fully issued + finished, the WIP
clearing account balance is exactly 0 (issue debits = finished credit + variance flush), the finished
item's inventory value equals the issued component cost, and any rounding/absorption residual holds in
the production-variance account. Atomic: a closed period or insufficient stock rolls the whole
issue/finish back (the move/journal triggers fire in the same transaction).

**Posting defaults:** a tenant maps the `wip_clearing` (ASSET) and `production_variance` (EXPENSE)
purposes (resolved via `finance/queries.wip_clearing_account` / `.production_variance_account`); an
unmapped WIP account fails an issue/finish loud (422). Permissions: `manufacturing.production_order`
`.read` / `.manage` (create+cancel) / `.release` / `.execute` (issue+finish). Docflow: order →
`issued_to` → ISSUE moves, order → `finished_to` → finished RECEIPT move + variance entry.

## MRP run + rough capacity check (8.3, D-049)

The **MRP run** (`mfg_mrp_runs`, prefix `MRP-`) is a deterministic, set-based, level-ordered planning
pass that nets demand against supply, explodes MAKE items' BOMs into dependent component demand, and
writes **planned orders** (`mfg_planned_orders`) plus a rough per-work-centre **capacity load**
(`mfg_capacity_loads`). It is **always a background job** (`manufacturing.mrp_run`): `POST
/api/v1/manufacturing/mrp/runs` submits the job and returns **202 `{job_id}`** for `/api/v1/jobs`
polling (the depreciation-run precedent — the run scans every planning-relevant item, so it never
runs inline). The submit is idempotent (D-013).

**Demand sources (level-0, independent):**
- **Open sales-order demand** — undelivered quantity on CONFIRMED / PARTIALLY_DELIVERED orders, read
  via `sales/queries.open_demand_item_ids` (the items) + `sales/queries.committed_quantity` (the sum,
  the ATP reservation figure).
- **Reorder-point shortfall** — an item at/below its reorder point demands its `reorder_quantity`, via
  `inventory/queries.items_below_reorder_point` (the 6.4 consumption-based scan).

**Supply (netted off demand):** `inventory/queries.total_on_hand` (on-hand) +
`procurement/queries.open_incoming_quantity` (open POs) +
`manufacturing/queries.open_production_order_supply` (un-finished open production orders) +
`manufacturing/queries.planned_make_supply` (still-open FIRMED/CONVERTED planned orders — a
committed proposal nets as supply so a re-run does not re-propose it).

**Netting formula:** `net_requirement = max(0, demand − supply)`, quantized to the QuantityType scale
(D-015; summed in Python so the exact decimal round-trips identically on both engines).

**Make vs Buy is structural — active-BOM presence:** an item with an ACTIVE default BOM
(`get_active_bom_for_item`) is **MAKE** (produced in-house → a planned **PRODUCTION** order, and its
BOM is exploded into dependent component demand); an item with no active BOM is **BUY** (procured → a
planned **PURCHASE** order, a leaf the explosion stops at). This is how Atlas distinguishes
manufactured from purchased items.

**Multi-level explosion + cycle guard (D-047):** the run is **level-ordered** — level 0 (the
independently-demanded items) nets first; each MAKE item's net requirement explodes its BOM into
dependent demand for its components at the next level (`dependent = quantity_per × parent_net /
base_quantity × (1 + scrap_percent/100)`, the create-production-order math), accumulating across all
parents (a component used by two finished goods sums). Per level the active BOMs and their components
are batched (two queries) and the explosion runs **in memory** — no per-component N+1. The cycle
guard is a **`netted` set** (a component re-appearing at a deeper level is folded into its earlier
net — low-level-code, never re-planned) plus a **`MRP_MAX_EXPLOSION_LEVELS = 20` depth cap** (the
docflow `get_chain` precedent), so a masters-rejected-but-defensive cycle (A↔B across separate BOMs)
terminates cleanly rather than hanging.

**Planned orders are the output + their lifecycle.** `PLANNED` (the fresh proposal — superseded by
the next run, which **regenerates**: deletes the tenant's un-firmed PLANNED rows then writes a fresh
plan) → `FIRMED` (a planner committed to it — survives a re-run and nets as supply) → `CONVERTED`
(turned into a real document) | `CANCELLED` (discarded; the row survives for history, adds no
supply). Each run is its own snapshot (multiple runs allowed).

**Conversion (the §5-clean cross-module write).** `POST /planned-orders/{id}/convert`:
- a **MAKE** order calls manufacturing's OWN `create_production_order` (intra-module) and records
  `converted_document_id` + a docflow run → `planned_to` → production-order edge;
- a **BUY** order **publishes `PlannedBuyConverted`** → procurement's
  `handlers.create_requisition_for_planned_buy` creates the DRAFT requisition in the **same
  transaction** + links run → `planned_to` → requisition (the billing → AR-invoice precedent —
  manufacturing never imports sales/inventory/procurement **service**).

**Rough capacity check (parity capacity = PARTIAL — evaluation only).** For the run's planned MAKE
orders (their items' active routings, batched) **plus** the tenant's open production orders (their
snapshot operations' precomputed `planned_minutes`, one grouped query), the check sums each work
centre's **load** = Σ(`setup_time_minutes + run_time_minutes_per_unit × quantity`) and compares it to
**available** = `capacity_hours_per_day × (efficiency_percent / 100) × horizon_days × 60`;
`utilization_percent = load / available × 100` and **`is_overloaded = load > available`**. There is
**no leveling / finite scheduling** — a rough infinite-capacity load picture only. The loads are
persisted per run (a stable report; the capacity endpoint returns the overloaded ones first).

**Cross-module read directions added (§5, no cycle).** MRP reads three sibling/lower modules'
`queries.py`: manufacturing → `sales/queries` (`open_demand_item_ids` added in 8.3,
`committed_quantity` pre-existing), manufacturing → `procurement/queries`
(`open_incoming_quantity`), manufacturing → `inventory/queries` + `finance/queries` (pre-existing).
Sales and procurement are **siblings** of manufacturing; the reads are **one-directional** (neither
sales nor procurement imports `manufacturing/queries` — manufacturing is the newest module), so there
is **no bidirectional query cycle** (STRUCTURE §5 bans only bidirectional pairs). The planned-BUY →
requisition write is an **event**, never a service import.

**Permissions:** `manufacturing.mrp.read` / `.mrp.run` (segregated — running the engine is a
planning-controller act) / `.planned_order.read` / `.planned_order.manage` (firm/convert/cancel).
**Endpoints** (`mrp_router`, mounted): `POST /mrp/runs` (202 + job), `GET /mrp/runs` (paginated) +
`/{id}` (header + capacity), `GET /{id}/planned-orders` (paginated, filter type/status), `GET
/{id}/capacity`, `POST /planned-orders/{id}/convert` (idempotent) / `/firm` / `/cancel`.

## What parity defers

**Deferred per s4hana-parity (PP):** operation-level confirmations (8.2 plans order-level
completion only), capacity *leveling*/finite scheduling (8.3 does rough infinite-capacity load
only), MRP exception messages / rescheduling / MRP areas / net-change / time-phased planning (8.3 is
a single-bucket regenerative net), MRP-Live performance, demand management/PIRs/planning strategies,
kanban, repetitive manufacturing, PP-PI process orders, and PP/DS — the typical v1-grade boundary,
with each marked as a layer-on-later in the parity map.
