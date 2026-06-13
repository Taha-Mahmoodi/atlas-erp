# Manufacturing (`backend/app/modules/manufacturing/`)

Manufacturing is the **fifth business module** (PLAN 8), sitting **above inventory** in the
dependency order (STRUCTURE §5): it may read `finance/queries.py` and `inventory/queries.py`
**downward** (D-029), and exposes `manufacturing/queries.py` as the only file the modules above it
(production orders 8.2, MRP 8.3) import. The normative design lives in
[docs/architecture.md](../architecture.md) (D-029 opaque cross-module ids, D-015 money/quantity
types) and the **D-047** decision in [DECISIONS.md](../../DECISIONS.md); this guide is the
operator/contributor map and grows with each manufacturing task (PLAN 8.1…8.3).

## Status

**PLAN 8.1 laid the PP master data:** multi-level versioned **BOMs**, **work centres**, and
**routings** (s4hana-parity PP: BOMs multi-level+versioned, work centers, routings — all FULL).
Production orders (8.2) and the deterministic MRP run + rough capacity check (8.3) build on these
masters in place.

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
`get_work_center` / `work_center_capacity(work_center_id)`. This is the **only** manufacturing file
8.2/8.3 import — thin, stable, no service imports.

## What 8.2 / 8.3 add (and what parity defers)

- **8.2 — production orders:** material reservation, issue to WIP, finish to stock, WIP journals
  (the first manufacturing cross-module events + `handlers.py`).
- **8.3 — MRP run + rough capacity check:** explode sales-order demand + reorder points against
  supply → planned orders; load work centres vs available hours.

**Deferred per s4hana-parity (PP):** operation-level confirmations (8.2 plans order-level
completion only), capacity *leveling*/finite scheduling (8.3 does rough infinite-capacity load
only), demand management/PIRs/planning strategies, kanban, repetitive manufacturing, PP-PI process
orders, and PP/DS — the typical v1-grade boundary, with each marked as a layer-on-later in the
parity map.
