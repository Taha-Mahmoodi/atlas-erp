# Quality (`backend/app/modules/quality/`)

Quality is the **sixth business module** (PLAN 9), sitting **above inventory and procurement** in the
dependency order (STRUCTURE §5 / **D-050**). It is the deliberately small QM core the
[parity doc](../research/s4hana-parity.md) scopes: the goods-receipt inspection **flag** → inspection
**lot** → accept/reject usage **decision** with a stock **disposition**. Everything else QM
(inspection plans, master inspection characteristics, results recording, usage-decision code
catalogs, quality notifications/CAPA, certificates) is **out of v1** — recorded in the parity doc.

The normative design lives in [docs/architecture.md](../architecture.md) (D-011 event bus, D-012
docflow/numbering, D-020 costing offsets, D-029 opaque cross-module ids, D-015 money/quantity types)
and the **D-050** decision in [DECISIONS.md](../../DECISIONS.md); this guide is the operator/contributor
map.

## Status

**PLAN 9.1 is COMPLETE.** A goods receipt with `requires_inspection=True` auto-creates an OPEN
inspection lot (via the event bus); a usage decision accepts/rejects it; a rejection dispositions the
rejected stock (SCRAP write-off / BLOCK transfer) through the event bus. 9.2 (maintenance) is a
separate module.

| File | Concern | Key decision |
|---|---|---|
| `constants.py` | `InspectionLotStatus`, `InspectionSource`, `RejectDisposition` enums + permission keys (registered at import) + the doc-type / number sequence / event key / docflow links | D-050, D-009 |
| `models.py` | `InspectionLot` (`qm_inspection_lots`) — the lot header (one table) | D-029, D-015, D-012 |
| `schemas.py` | `InspectionLotRead`/`Filter` + the `InspectionDecideRequest` usage-decision body | D-015 |
| `events.py` | `InspectionDispositioned` — published on a REJECT so inventory moves the rejected stock | D-011, D-050 |
| `handlers.py` | `create_inspection_lots_for_receipt` — subscribes to procurement's `GoodsReceiptPosted`, creates an OPEN lot per flagged line | D-011, D-050 |
| `service.py` | `create_lot_from_receipt_line` (called by the handler), `list/get`, `decide` (accept/reject + disposition), `cancel_lot` | D-050, D-020 |
| `queries.py` | `get_inspection_lot`, `open_lots_for_item`, `lots_for_goods_receipt` — the only file a later module imports | STRUCTURE §5 |
| `router.py` | REST under `/api/v1/quality` — list + point read + decide + cancel (no create — lots come from the handler) | D-009, D-014 |

Migration: `0035_quality_inspection` (one `qm_inspection_lots` table + indexes, no triggers,
down_revision 0034).

## The flow: GR flag → lot → decide → disposition

```
PO ─received_by→ GR ──(post, requires_inspection=True)──┐
                  │                                     │ event: GoodsReceiptPosted
                  │ (inventory handler, runs FIRST)     │
                  ├─moved_by→ RECEIPT stock move        │ (quality handler, runs SECOND)
                  └─inspected_by→ Inspection Lot (OPEN) ┘
                                     │
                                     │ usage decision (quality.inspection.decide)
                       ┌─────────────┼──────────────┐
                   ACCEPT          REJECT          REJECT
                  (no move)        SCRAP            BLOCK
                                     │                │ event: InspectionDispositioned
                       ADJUSTMENT-out write-off   TRANSFER to blocked bin
                       (Dr adj / Cr Inventory)    (value-neutral)
                       lot ─dispositioned_by→ stock move
```

### Event-driven lot creation (D-011 / D-050)

When a goods receipt posts, procurement publishes **`GoodsReceiptPosted`** (D-041). **Two handlers**
subscribe to that one event key, in registration order:

1. **inventory's `receive_goods_receipt_moves`** — creates the RECEIPT stock moves (Dr Inventory / Cr
   GR-IR), and for a tracked item creates the lot/serial master instance.
2. **quality's `create_inspection_lots_for_receipt`** — creates **one OPEN `InspectionLot` per GR line
   flagged `requires_inspection=True`** (an unflagged line creates none), snapshotting the line's
   item / bin / quantity, resolving the lot/serial code to the instance inventory just created, and
   writing the GR document → `inspected_by` → lot docflow edge.

Both run in the **same transaction** as the GR post (D-011 `run_in_uow` drains before commit), so a
flagged GR atomically creates its inspection lots. Quality is registered **after** inventory so the
lot/serial instance exists when quality resolves the code.

### The usage decision (accept/reject)

`POST /api/v1/quality/inspection-lots/{id}/decide` (permission `quality.inspection.decide`, distinct
from `.manage`) splits the lot's quantity into `accepted_quantity` + `rejected_quantity`. **v1 is a
single decision covering the whole lot**: the two must sum to exactly the lot quantity (else 422
`quality.decision_quantity_mismatch`). The lot lands:

- **ACCEPTED** when `rejected_quantity == 0`;
- **REJECTED** when `rejected_quantity > 0` (any rejection — including a partial accept/reject —
  lands REJECTED, with both quantities recorded; there is no `PARTIALLY_ACCEPTED` status in v1).

A rejection **requires a disposition**. The whole decision is atomic (D-011): a closed-period SCRAP
write-off rolls the entire decision back (the lot stays OPEN). The decide endpoint is idempotent
(D-013); a decided lot is terminal (re-decide → 409 `quality.lot_not_open`).

### Dispositions and their stock effects (D-020 / D-050)

| Disposition | Stock move | Journal | On-hand effect |
|---|---|---|---|
| **SCRAP** | ADJUSTMENT-out from the receiving bin | Dr inventory-adjustment / price-difference, Cr Inventory (the write-off, at book value) | total on-hand **drops** by the rejected qty |
| **BLOCK** | TRANSFER from the receiving bin to the destination blocked/QI bin | none (a within-warehouse transfer is value-neutral) | total on-hand **unchanged**; stock leaves the usable bin |
| **RETURN_TO_VENDOR** | — | — | **declared, not implemented in v1** (needs the vendor-return chain — parity-doc "later"; choosing it → 422 `quality.disposition_not_implemented`) |

A **BLOCK** requires `blocked_bin_id` on the decide request (the destination quarantine bin,
validated via `inventory/queries.bin_exists`); a SCRAP needs none (it is one-sided).

The stock effect always goes **through the event bus** (STRUCTURE §5): a reject publishes
`InspectionDispositioned`, and inventory's `disposition_rejected_stock` handler creates the move via
its own service and writes the lot → `dispositioned_by` → move docflow edge. Quality never imports
inventory's service.

### Why ACCEPTED needs no stock move

A v1 inspection lot **does not hold stock in a separate quality-inspection bucket** — the received
stock is already on hand and usable the moment the GR posts. So an ACCEPT just records the outcome and
moves nothing; only a REJECT moves stock (SCRAP out / BLOCK aside). (This is the documented v1
simplification vs S/4HANA's quality-inspection stock type — recorded in the parity doc.)

## Cross-module directions (§5, no cycle)

- **quality → procurement/events** (subscribes to `GoodsReceiptPosted` — the sanctioned declarative
  event import, D-011).
- **quality → inventory/queries** (downward: `bin_exists`, `lot_id_for_code`, `serial_id_for_code`).
- **quality publishes `InspectionDispositioned`** → **inventory/handlers** moves the rejected stock.

Procurement and inventory are **older** modules and import nothing from quality, so all quality
cross-module imports are **one-directional** (STRUCTURE §5 bans only *bidirectional* query imports) —
**no cycle**. `quality/queries.py` is the only file a later module would import. Quality imports **no**
procurement / inventory / finance **service** (grep-verified).

## What's out of scope (parity)

Inspection plans, master inspection characteristics, results recording (measured values),
usage-decision **code catalogs** + quality scores, multi-bucket split postings beyond
accept/reject+SCRAP/BLOCK, quality notifications / complaints / CAPA, quality certificates, and
non-goods-receipt lot origins (production, delivery, manual) are all **later** — see the
[parity doc](../research/s4hana-parity.md) QM section.
