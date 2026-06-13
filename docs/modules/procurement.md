# Procurement module

Procurement is the third business module (PLAN 6), sitting above inventory in the dependency order:
it may read `finance/queries` and `inventory/queries` downward, and everyone above it reads
`procurement/queries`. PLAN 6.1 opened the module with the **vendor master** and the v1
**approved-items** info-record-lite; **PLAN 6.2 adds the requisition → RFQ → PO document chain and
the data-driven approval-threshold rule**. Goods receipt + 3-way match land in PLAN 6.3–6.4 and grow
this package in place.

S/4HANA parity (`docs/research/s4hana-parity.md`, Procurement section): the supplier/vendor master
is **FULL** in v1; purchase requisitions, RFQs and purchase orders are **FULL**; approval/release
strategies are **PARTIAL** — Atlas implements data-driven value-threshold rules only (multi-
characteristic / multi-step release strategies are the documented later). Purchasing info records
are **PARTIAL** — Atlas captures the vendor↔item link ("approved items") but not the time-dependent
pricing/lead-time conditions S/4HANA info records default into POs.

## Code layout (the 6.2 package splits)

The 400-line cap forced three behaviour-preserving package splits at 6.2 (the finance/inventory
precedent), re-exported so existing import sites are unchanged:

- **`models/`** — `vendors.py` (the 6.1 master), `requisitions.py`, `rfqs.py`, `orders.py`,
  `approvals.py`; `models/__init__` re-exports all.
- **`schemas/`** — one file per document family + `approvals.py`; `schemas/__init__` re-exports all.
- **`service/`** — `vendors.py`, `requisitions.py`, `rfqs.py`, `orders.py`, `conversions.py`,
  `approvals.py`, the private `_shared.py` (cross-module validation + numbering helpers);
  `service/__init__` re-exports every public function so `service.create_purchase_order(...)` works.
- **`router.py`** owns the vendor master and **mounts** the sibling `requisition_router` /
  `rfq_router` / `po_router` / `approval_rule_router` under the same prefix (the finance
  `ap_router`/`ar_router` precedent) — one module surface, one mount in `main.py`.

## Vendor master (`proc_vendors`)

A `Vendor` is a supplier record. Key fields:

- **`vendor_code`** — user-supplied, **unique per tenant** (`UNIQUE(tenant_id, vendor_code)`). No
  auto-numbering: a vendor master carries a *code*, not a gapless document number — mirroring
  inventory `item_code` and the finance account `code`. (The P2P *documents* in 6.2+ do claim
  gapless numbers; the master does not.)
- **`status`** — `ACTIVE | BLOCKED | INACTIVE` (`VendorStatus`). Transitions are **unrestricted**
  between the three: a block is reversible and a retired vendor can be reactivated, so there is no
  terminal state (vendor history must stay referenceable). The P2P chain in 6.2 reads the status to
  refuse new POs against `BLOCKED`/`INACTIVE` vendors — a soft policy applied at the chain, not a
  master-level lock.
- **`default_currency_code`** — ISO alpha-3; validated to exist in finance's currency catalog
  (D-029, see below). Defaults onto a vendor's POs/bills in 6.2+.
- **`payment_terms_days`** — see *Payment terms → due dates*.
- **`tax_reference`**, **`email`**, **`phone`**, **`address`**, **`notes`** — modest contact/registration fields.

Indexed `(tenant_id, status)` for the filtered vendor list (PERFORMANCE §1); the list is paginated,
filterable by status, and ETag-conditional reference data (D-035).

### Payment terms → due dates

A vendor carries **`payment_terms_days`** — a plain net-days integer (30 = NET30), CHECK `>= 0`,
defaulting to NET30. This is the simplest model that matches how AP already computes a bill's due
date: `due_date = bill_date + payment_terms_days`. The PO→bill flow (6.4) reads it via
`queries.vendor_payment_terms_days`. Richer term schedules (e.g. 2/10 NET30 early-payment discounts,
multi-instalment plans) are **deferred** per parity and would arrive as a terms entity referenced
from the vendor — the current integer is forward-compatible with that.

## The `partner_id` ↔ vendor relationship with finance AP (D-029)

Finance is the **bottom** of the dependency order and owns **no vendor table**. Every AP document
(`fin_vendor_bills`, `fin_vendor_payments`) stores its vendor as an **opaque `partner_id`** (a plain
`Uuid` column, **no FK**) plus a denormalized `partner_name` for display. **That `partner_id` IS this
module's `Vendor.id`.** Procurement is *above* finance, so finance can never FK-reference the vendor
master; the link is by opaque id only.

AP aging/reporting resolves a bill's `partner_id` back to a vendor (for its name and payment terms)
through `queries.get_vendor_for_partner` — a thin alias over `get_vendor`, named for the reporting
intent. The vendor master is the *owner* of the entity; finance is a *referrer* by opaque id.

## Approved items as info-record-lite (`proc_vendor_approved_items`)

A `VendorApprovedItem` records that a vendor is an approved source for an inventory item, optionally
with the vendor's own SKU (`vendor_item_code`). `UNIQUE(tenant_id, vendor_id, item_id)` so a vendor
approves an item at most once.

- **`vendor_id`** is a composite `tenant_fk` to `proc_vendors` (an intra-module parent).
- **`item_id`** is an **opaque inventory item id** (D-029): a plain `Uuid`, **not** an FK to
  `inv_items`. The service validates it exists via `inventory/queries.item_exists`; procurement
  reads inventory but never cross-module FK-references it.

This is the v1 **info-record-lite**: the vendor↔item link only, with **no** price / lead-time /
valid-from-to. Those time-dependent conditions are deferred per parity and would extend this table
later. 6.2's "only approved sources" policy reads `queries.is_item_approved_for_vendor` (an inactive
approval reads as not-approved).

## The requisition → RFQ → PO document chain (PLAN 6.2)

Three numbered documents, each registered in `core_documents` (D-012, `DocumentMixin`) with a gapless
number **claimed AT CREATION** (D-040 — see below), header + line tables, and docflow
predecessor/successor edges so the DocFlow viewer renders the whole chain.

### Purchase requisitions (`proc_requisitions` / `proc_requisition_lines`)

The internal "we need to buy this" request. Status lifecycle (`RequisitionStatus`):

`DRAFT → SUBMITTED → APPROVED | REJECTED`, plus `DRAFT/SUBMITTED/APPROVED → CANCELLED` and
`APPROVED → CONVERTED` (set by the convert actions).

- **create** (DRAFT): validates each line item exists (inventory/queries), qty > 0, the line currency
  exists in finance; claims the `PR-…` number.
- **submit**: evaluates the **REQUISITION** approval rule on the estimated total
  (Σ qty × estimated_unit_cost). At-or-above the active threshold it stays `SUBMITTED` awaiting an
  approver; below it (or with no rule) it auto-advances to `APPROVED`.
- **decision** (approve/reject, the `procurement.requisition.approve` key): `SUBMITTED → APPROVED |
  REJECTED`.
- **update** (DRAFT only; lines replaced wholesale) / **cancel** (not once CONVERTED/terminal).

### RFQs (`proc_rfqs` / `proc_rfq_lines`)

The sourcing document. **In v1 an RFQ targets ONE vendor** (`vendor_id`, a composite tenant FK); the
multi-bidder comparison is the documented parity later. Lifecycle (`RfqStatus`):
`DRAFT → SENT → QUOTED → CLOSED`, or any non-terminal → `CANCELLED`.

- **create** from scratch, OR **convert from an APPROVED requisition** (copies the lines, sets
  `source_requisition_id`, links docflow `requisition → rfq` `"sourced_by"`, marks the requisition
  `CONVERTED`).
- **send** (`DRAFT → SENT`), **record-quote** (fills `quoted_unit_cost` per line, `SENT → QUOTED`),
  **close**.

### Purchase orders (`proc_purchase_orders` / `proc_purchase_order_lines`)

The committing document. Lifecycle (`PurchaseOrderStatus`) — states **set in 6.2**:
`DRAFT → PENDING_APPROVAL | APPROVED → SENT`, plus `REJECTED` / `CANCELLED`.
`PARTIALLY_RECEIVED / RECEIVED / CLOSED` are declared now as the lifecycle but the transitions INTO
them are **driven by 6.3 goods receipts** (`received_quantity` rises per line).

A PO is created from scratch, OR **converted from an APPROVED requisition** (unit_cost from the
estimate, docflow `requisition → po` `"ordered_by"`), OR **from a QUOTED RFQ** (unit_cost from the
quote, docflow `rfq → po` `"ordered_by"`, RFQ → `CLOSED`). At create the service:

- enforces the **source-control rules** (below): vendor must be `ACTIVE`, every line item must be an
  approved source for that vendor;
- snapshots the vendor's `payment_terms_days` + currency (so a later vendor edit cannot rewrite an
  open PO's due-date math, which the 6.4 bill reads);
- computes `line_amount = qty × unit_cost` and the maintained `total_amount = Σ line_amount`.

**send**: evaluates the **PURCHASE_ORDER** approval rule on `total_amount`. At-or-above the threshold
⇒ `PENDING_APPROVAL` (an approver clears it via the `procurement.po.approve` key → `APPROVED`); below
⇒ auto-approve. **Only an `APPROVED` (or below-threshold) PO becomes `SENT`.** `received_quantity`
(default 0) and the opaque `tax_code_id` land now for 6.3/6.4.

### Numbering claimed at creation (D-040)

Unlike finance (which numbers at *posting*), the three procurement documents claim their gapless
number **at creation** — a DRAFT requisition already prints a `PR-…` number that the sourcing/ordering
chain quotes, so a document is referenceable the moment it exists. Gaplessness still holds: creation
is the committing transaction, so the counter increment and the row insert commit or roll back
together (the orders/receipts claim-timing branch of D-012, the inventory stock-move precedent).

## The approval-threshold rule (`proc_approval_rules`, D-040)

The **data-driven release rule**: a single-characteristic (amount) value threshold per document type.
One active rule per `(tenant, document_type)` (`UNIQUE`, `document_type ∈ {REQUISITION,
PURCHASE_ORDER}`, `threshold_amount` CHECK `>= 0`). The evaluator
`service.requires_approval(document_type, amount, currency)`:

- reads the single **active** rule for the type;
- returns `True` iff `amount >= threshold` **and** the rule's currency matches the document's;
- **no active rule, an inactive rule, or a currency mismatch ⇒ `False`** — no gate. A tenant that
  has not configured thresholds runs without approval; v1 rules are single-currency (cross-currency
  thresholds would need FX, deferred per parity).

This is the parity "data-driven value-threshold rules only" cut; multi-characteristic / multi-step
release strategies are the documented later. CRUD lives behind the single
`procurement.approval_rule.manage` key (a privileged config, no separate read key).

## Source-control rules (the v1 enforcement, D-040)

A PO is the committing document, so at create the service enforces two rules through the
`procurement/queries` contract (never a cross-module FK):

- **Vendor must be ACTIVE** — a `BLOCKED`/`INACTIVE` vendor cannot receive a new PO (422
  `procurement.vendor_not_active`).
- **Every line item must be approved for the vendor** — the item must be in the vendor's approved-
  items list (an inactive approval counts as not approved), else 422 `procurement.item_not_approved`.
  This is the v1 source-control choice: approved-items are **enforced** on POs, not advisory.

## The queries interface

`procurement/queries.py` is the **only** procurement file other modules import — a thin, stable
contract (STRUCTURE §5). Every function is tenant-scoped (D-007 applies on top of the explicit
predicate). 6.3–6.4 and finance AP reporting consume:

| Function | Returns | Used by |
|---|---|---|
| `get_vendor` | the `Vendor` or `None` | generic vendor read |
| `get_vendor_for_partner` | the vendor an AP `partner_id` names (= `get_vendor`) | finance AP aging/reporting (D-029) |
| `vendor_exists` | bool | requisition/PO line validating its `vendor_id` |
| `vendor_payment_terms_days` | net-days `int` or `None` | PO→bill due-date defaulting (6.4) |
| `vendor_default_currency` | ISO code or `None` | PO currency defaulting (6.2) |
| `is_item_approved_for_vendor` | bool (active approvals only) | the PO source-control rule (6.2) |
| `get_purchase_order` | the `PurchaseOrder` or `None` | goods receipt (6.3) / 3-way match (6.4) |
| `po_line_open_quantity` | ordered − received `Decimal` | GR cap (6.3) / match (6.4) |
| `get_po_for_receipt` | `(PO, lines)` or `None` | the data a goods receipt builds from (6.3) |
| `open_po_lines_for_vendor` | open PO lines on SENT/PARTIALLY_RECEIVED orders | awaiting-receipt worklist |

### Sanctioned cross-module additions

PLAN 6.1 added **`finance/queries.currency_exists(session, tenant_id, code)`** — the by-code
existence check the vendor master validates `default_currency_code` against (D-029), mirroring
`account_exists`. No addition was needed to `inventory/queries` (the existing `item_exists` covers
approved-item validation).

## Permissions (D-009)

- `procurement.vendor.read` / `.manage` — read / create-edit vendors + their approved items
  (approved-item management rides `.manage`, the inventory item/uom-conversion precedent).
- `procurement.requisition.read` / `.manage` / `.approve` — read / create-edit-submit-convert-cancel
  / the distinct **approve** authority on submitted requisitions.
- `procurement.rfq.read` / `.manage` — read / create-send-quote-close-convert (no approve gate —
  sourcing is not committing).
- `procurement.po.read` / `.manage` / `.approve` — read / create-convert-send-cancel / the distinct
  **approve** authority on POs pending approval.
- `procurement.approval_rule.manage` — manage the value-threshold rules.

**manage vs approve are distinct keys**: a buyer can raise + submit a requisition (or create + send a
PO) without holding the approver authority that clears the threshold gate.

## Cross-module effects (none yet — D-040)

PLAN 6.2 publishes **no events** and adds **no `events.py`/`handlers.py`**. Nothing in the chain posts
to finance or inventory: a PO is a commitment, not a posting. The first procurement event arrives in
**6.3** (goods receipt → inventory stock move + GR/IR journal); the AP bill arrives in **6.4**. The
no-stub rule keeps `events.py` absent until then.

## REST surface (`/api/v1/procurement`)

Vendor master (6.1) plus the P2P documents (6.2). Document-creating + convert + submit/approve
endpoints are **idempotent** (D-013); lists are paginated + filterable; routers are thin and commit
through the D-011 uow.

| Method | Path | Permission |
|---|---|---|
| GET/POST | `/vendors` (+ `{id}`, approved-items) | `vendor.read` / `vendor.manage` |
| POST GET | `/requisitions` (+ `{id}`, `?status=`, `?requested_by=`) | `requisition.manage` / `.read` |
| PATCH | `/requisitions/{id}` | `requisition.manage` |
| POST | `/requisitions/{id}/submit` · `/cancel` | `requisition.manage` |
| POST | `/requisitions/{id}/decision` | `requisition.approve` |
| POST | `/requisitions/{id}/convert-to-rfq` · `/convert-to-po` | `requisition.manage` |
| POST GET | `/rfqs` (+ `{id}`, `?status=`, `?vendor_id=`) | `rfq.manage` / `.read` |
| POST | `/rfqs/{id}/send` · `/record-quote` · `/close` | `rfq.manage` |
| POST | `/rfqs/{id}/convert-to-po` | `po.manage` |
| POST GET | `/purchase-orders` (+ `{id}`, `?status=`, `?vendor_id=`) | `po.manage` / `.read` |
| POST | `/purchase-orders/{id}/send` · `/cancel` | `po.manage` |
| POST | `/purchase-orders/{id}/decision` | `po.approve` |
| GET/POST/PATCH | `/approval-rules` (+ `{id}`) | `approval_rule.manage` |

The document headers are `AuditMixin`; lines ride the header's audit story (the journal/bill-line
exclusion). The DocFlow chain for any document is the core endpoint
`GET /api/v1/documents/{document_id}/chain`, which renders requisition → rfq → po.

## What's deferred (per parity)

- **Multi-characteristic / multi-step release strategies** — Atlas implements amount-only,
  single-currency, single-step value thresholds (the data-driven cut).
- **Multi-bidder RFQs** — v1 RFQs target one vendor; bid comparison across vendors is later.
- **Time-dependent info-record conditions** (price, lead-time, valid-from/to) on approved items.
- **Partner functions** (separate ordering vs invoicing addresses) and **granular block levels**.
- **Source determination** (source lists, quota arrangements, automatic source proposal).
- **Goods receipt + 3-way match** — land in PLAN 6.3–6.4 (the `received_quantity` / `tax_code_id`
  columns + the `get_po_for_receipt` / `po_line_open_quantity` queries are staged for them now).

Migrations: **0024_procurement_vendors** (`proc_vendors` + `proc_vendor_approved_items`);
**0025_procurement_documents** (`proc_requisitions`/`_lines`, `proc_rfqs`/`_lines`,
`proc_purchase_orders`/`_lines`, `proc_approval_rules` + indexes). Both no trigger-bearing alters,
portable on SQLite + Postgres.
