# Procurement module

Procurement is the third business module (PLAN 6), sitting above inventory in the dependency order:
it may read `finance/queries` and `inventory/queries` downward, and everyone above it reads
`procurement/queries`. PLAN 6.1 opens the module with the **vendor master** and the v1
**approved-items** info-record-lite. The procure-to-pay chain (requisition → RFQ → PO → goods
receipt → 3-way match) lands in PLAN 6.2–6.4 and grows this package in place.

S/4HANA parity (`docs/research/s4hana-parity.md`, Procurement section): the supplier/vendor master
is **FULL** in v1; purchasing info records are **PARTIAL** — Atlas captures the vendor↔item link
("approved items") but not the time-dependent pricing/lead-time conditions S/4HANA info records
default into POs.

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

## The queries interface

`procurement/queries.py` is the **only** procurement file other modules import — a thin, stable
contract (STRUCTURE §5). Every function is tenant-scoped (D-007 applies on top of the explicit
predicate). 6.2–6.4 and finance AP reporting consume:

| Function | Returns | Used by |
|---|---|---|
| `get_vendor` | the `Vendor` or `None` | generic vendor read |
| `get_vendor_for_partner` | the vendor an AP `partner_id` names (= `get_vendor`) | finance AP aging/reporting (D-029) |
| `vendor_exists` | bool | requisition/PO line validating its `vendor_id` |
| `vendor_payment_terms_days` | net-days `int` or `None` | PO→bill due-date defaulting (6.4) |
| `vendor_default_currency` | ISO code or `None` | PO currency defaulting (6.2) |
| `is_item_approved_for_vendor` | bool (active approvals only) | "only approved sources" policy (6.2) |

### Sanctioned cross-module additions

PLAN 6.1 added **`finance/queries.currency_exists(session, tenant_id, code)`** — the by-code
existence check the vendor master validates `default_currency_code` against (D-029), mirroring
`account_exists`. No addition was needed to `inventory/queries` (the existing `item_exists` covers
approved-item validation).

## Permissions (D-009)

- `procurement.vendor.read` — read vendors and their approved items.
- `procurement.vendor.manage` — create/edit vendors and their approved items. Approved-item
  management rides this key (it is vendor configuration, not a distinct privileged action — the
  inventory item/uom-conversion precedent).

## REST surface (`/api/v1/procurement`)

| Method | Path | Permission |
|---|---|---|
| GET | `/vendors` (paginated, `?status=`, ETag) | `vendor.read` |
| POST | `/vendors` | `vendor.manage` |
| GET | `/vendors/{id}` | `vendor.read` |
| PATCH | `/vendors/{id}` | `vendor.manage` |
| GET | `/vendors/{id}/approved-items` | `vendor.read` |
| POST | `/vendors/{id}/approved-items` | `vendor.manage` |
| DELETE | `/vendors/{id}/approved-items/{itemId}` | `vendor.manage` |

Routers are thin (parse → service → schema); writes commit through the D-011 uow so audit rows ride
the same transaction. Vendors and approved items are audited at the vendor level (`Vendor` is
`AuditMixin`; the approved-item link rides the vendor's audit story like inventory's `UomConversion`).

## What's deferred (per parity)

- **Time-dependent info-record conditions** (price, lead-time, valid-from/to) on approved items.
- **Partner functions** (separate ordering vs invoicing addresses) and **granular block levels**.
- **Source determination** (source lists, quota arrangements, automatic source proposal).
- The **P2P documents** themselves — requisitions, RFQs, POs, goods receipt, 3-way match — land in
  PLAN 6.2–6.4.

Migration: **0024_procurement_vendors** (`proc_vendors` + `proc_vendor_approved_items` + indexes; no
trigger-bearing alters).
