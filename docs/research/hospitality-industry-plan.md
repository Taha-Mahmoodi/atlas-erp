# Hospitality (Hotel & Restaurant) — Industry Entry Plan

This document scopes a candidate **6th industry template** — hospitality, specifically a combined
property that runs both room operations and an on-site restaurant (boutique hotel, resort, B&B,
inn) — plus the custom modules it would need beyond the five shipped templates
([docs/industry-templates.md](../industry-templates.md)). Like the
[field-force tracking scan](field-force-tracking-market-scan.md), **this is a proposal, not a
commitment**: no PLAN.md, STRUCTURE.md, or GITHUB-WORKFLOW.md changes accompany this doc, and
nothing described here is scheduled or in flight. Research conducted August 2026 via public
product/feature pages.

## Why not just another `industry-templates/*.yaml`

The five shipped templates are configuration presets over Atlas's existing generic entities
(item, sales order, warehouse, customer). Hospitality doesn't fit that shape. A **room is not a
SKU** — it's a perishable, date-bound inventory slot, simultaneously reserved/occupied/in a
housekeeping state, none of which map to stock-on-hand. A **folio is not a sales order** — it's
an open-ended, multi-source running tab (room, F&B, incidentals) that accumulates over an
indeterminate stay and settles once. A **restaurant table is not a warehouse bin** — it's a
transient service-location with its own real-time occupancy state. Even NetSuite's own
"Hospitality ERP" material concedes generic ERP cores need a purpose-built layer on top for this
industry, not a relabeling. So this proposal is a template *plus* two new modules, not a template
alone.

## Market scan — hotel PMS

Surveyed: **Oracle Opera Cloud PMS** (enterprise benchmark; tiered editions; first-party coupling
to its own restaurant POS, Simphony), **Mews** (cloud-native, single data model across PMS +
booking engine + payments + its own POS, #1 in Europe per Hotel Tech Report), **Cloudbeds**
("one platform, one data model" for independents; algorithmic Pricing Intelligence Engine;
native + marketplace POS), **RoomRaccoon** (boutique/independent all-in-one, automation-heavy),
**Little Hotelier** (lightest tier, ~$29/mo, small B&Bs), **Hotelogix** (small-to-mid multi-property,
built-in housekeeping).

Consolidated feature list: reservations + real-time availability calendar; rate plans (manual
baseline, algorithmic as an advanced tier); guest folio (itemized multi-charge running tab,
checkout settlement); housekeeping room-status workflow (Dirty → In Progress → Clean → Inspected,
tied to checkout/check-in events); channel-manager/OTA sync (Booking.com, Expedia, Airbnb — sold
as its own category even by incumbents); guest CRM/loyalty; night audit (automated day-close
batch: transaction verification, status rollover); group bookings (room blocks, cutoff dates,
rooming lists, master folio with per-room split).

## Market scan — restaurant POS

Surveyed: **Toast** (restaurant-only, strongest KDS + menu tooling, native DoorDash/Uber
Eats/Grubhub integration), **Square for Restaurants** (retail-rooted, weak ingredient-level
tracking, best for food trucks), **Lightspeed Restaurant** (hybrid retail+restaurant, open API,
enterprise multi-unit), **TouchBistro** (purpose-built full-service: floor plan, seat-level check
splitting).

Consolidated feature list: table/floor management (visual plan, tab-to-table transfer); order
taking + kitchen display system (station routing, elapsed-time coding); **menu & recipe/ingredient
costing — functionally a bill-of-materials** (a recipe defines component ingredients and
quantities of a finished menu item, sub-recipes nest into multiple parents, one edit recosts and
re-depletes everywhere — directly analogous to Atlas's existing manufacturing BOM); split
checks/tipping; online ordering/delivery integration; perpetual per-sale ingredient depletion
(now the default expectation over periodic manual counts).

## The folio-unification finding — the actual differentiator

Hotel PMS and restaurant POS are sold as **separate-but-integrated** systems in every product
surveyed — nobody ships one monolithic codebase. Oracle connects Opera and Simphony via
"Transaction Services" (a server enters room number + guest name, the check posts to the folio at
tender — Oracle markets this explicitly as "Better Together"). Cloudbeds ships a native POS
*inside* its own platform for exactly this reason, plus marketplace POS integrations, all
supporting the same **"charge to room"** pattern. Mews shares one folio/webhook layer across its
own PMS and POS modules.

The differentiator isn't building one unified app — it's building the room-charge posting bridge
correctly: validate guest/room against an open reservation, post as a traceable folio line item,
support the group variant (a master folio absorbing a whole group's F&B, split back per room at
settlement).

## Proposed template: `hospitality.yaml` (6th industry template)

Same mechanism as the existing five (`industry-templates/_schema.yaml`), same apply/idempotency
flow via `apply_template`.

| Section | Hospitality distinctive |
|---|---|
| Terminology | `customer → Guest / Group Account` (billing accounts — corporate travel, group/event organizers; individual walk-in guests live on the reservation/folio, not as a persistent customer record) |
| Modules | Manufacturing off in the classic production-order/MRP sense; only the **BOM sub-engine** is pulled in for recipe costing |
| COA | Guest Ledger / Advance Deposits / Room Revenue / F&B Revenue split out |
| Custom fields | `star_rating`, `check_in_time`, `check_out_time` on the tenant/property record |
| Costing default | FIFO (F&B inventory), matching retail/healthcare |

## New module 1 — Rooms & Folio

- `room_type`, `room` (adds `housekeeping_status: DIRTY|IN_PROGRESS|CLEAN|INSPECTED|OUT_OF_ORDER`)
- `rate_plan` — manual nightly rates in v1, not algorithmic
- `reservation` — new document type (registered in `core_documents`, gets a doc number + doc-flow
  links): `TENTATIVE → CONFIRMED → CHECKED_IN → CHECKED_OUT/NO_SHOW/CANCELLED`
- `folio` — new document type, the running multi-charge tab. Predecessor = reservation (when one
  exists), successor = the journal entry posted at settlement. `folio_line` rows carry
  heterogeneous charges (room-night, restaurant, incidentals), each traceable to its source
  document via doc-flow links.
- **Night audit** — an idempotent batch job (same idempotency pattern as D-013), not a literal
  human workflow tool: posts one room-night line per checked-in reservation, reconciles folios,
  rolls the business date.
- **Group bookings** — room blocks with cutoff dates; a master folio absorbs group F&B/incidentals
  and splits back to individual folios or the group organizer at settlement.
- **Housekeeping** — a `housekeeping_task` document (room, trigger: CHECKOUT/SCHEDULED/GUEST_REQUEST,
  assigned staff, status), not just a status enum — real task assignment and tracking.

## New module 2 — Restaurant Ordering

- `table` (number, section, seats, status)
- **Menu items are not a new entity** — existing `inventory_item` rows with a Manufacturing
  `bill_of_material` defining ingredients. Recipe costing and depletion are pure reuse of the
  manufacturing BOM engine; zero new tables.
- `order_ticket` — new document type: `OPEN → SENT_TO_KITCHEN → IN_PREP → READY → SERVED →
  SETTLED`, lines carry seat number + notes. KDS is a status-filtered view over open ticket lines
  grouped by a prep-station field on the menu item — a query, not new hardware/device software.
- Split checks: per-seat/per-item bill splitting at settlement.

**Guest-facing ordering (QR flow).** Each `table` gets a QR code encoding a stable, no-login
ordering URL scoped to that table. The public menu page lists `menu_item`s with price/photo; a
guest builds a cart and submits. Submission creates/appends to that table's `order_ticket` — the
**same entity as staff-entered orders**, tagged `channel: GUEST_QR` vs `channel: STAFF`. A staff
acknowledgment flag gates kitchen routing so a guest order never silently skips a human check.

**Online table reservation.** A new `table_reservation` document (party size, time slot, contact,
status) — same doc-numbering/flow pattern as everything else, distinct from the hotel room
`reservation`.

**Online payment.** Settlement gains an `ONLINE_CARD` method via a **pluggable payment-provider
interface** (Stripe/Adyen-shaped: create a payment intent, confirm via webhook). Atlas never
touches raw card data — PCI scope stays with the provider. Scoped to restaurant-order settlement
in v1; extending online payment to hotel folio/booking deposits is a separate future decision.

**Weekly/monthly item report + margin-driven offer suggestion.** A report ranks items by units
sold and trend (reuses Reporting's existing projection pattern, no new financial engine). The
"offer algorithm" is an explainable rule, not a machine-learning system: rank items by `margin ×
declining velocity`, surface high-margin/slow-moving items as **suggested** discount candidates
with a suggested %, for a manager to approve. It never auto-applies a discount — full
algorithmic/live pricing stays out of scope, same reasoning as the "no dynamic rate pricing" call
on the hotel side.

## The bridge — one genuinely new integration point

`order_ticket.settle(charge_to_room: folio_id)` publishes `RestaurantOrderSettled`; a Rooms &
Folio handler appends a `folio_line` with a doc-flow link back to the ticket. This is the same
shape as the existing `SalesOrderShipped → inventory issues stock → finance posts COGS` pattern —
no new core-platform mechanism, just one new event and two handlers. Direct (non-room) payment
settles like a small POS sale, reusing Sales' existing invoice/payment primitives.

## Reuse map

| Need | Atlas mechanism reused | New code |
|---|---|---|
| Recipe costing, ingredient depletion | Manufacturing BOM engine | None — data only |
| F&B / housekeeping supply purchasing | Inventory + Procurement | None |
| Staff scheduling, payroll | HR | None |
| Journal posting, tax, COA | Finance | None |
| Corporate/group accounts | CRM (optional) | None |
| Tenancy, audit, event bus, doc-flow, numbering, idempotency | core | None |

Worth stating plainly: this vertical requires **no core-platform changes** — a real test of
whether Atlas's architecture generalizes beyond the five shipped templates.

## Explicitly out of scope for v1

| Capability | Reason |
|---|---|
| OTA/channel-manager two-way sync (Booking.com, Expedia, Airbnb) | Its own category even among incumbents; external integration surface |
| Algorithmic/dynamic room pricing | Rate plans are manual in v1 |
| Guest loyalty/rewards programs | Differentiator, not baseline |
| Third-party delivery-platform order injection (DoorDash/Uber Eats/Grubhub) | Separate integration surface |
| Real KDS hardware/terminal client | v1 ships a status view, not a kitchen-floor device app |
| Online payment on hotel folio/booking deposits | Scoped to restaurant settlement only this pass |
| Multi-property/portfolio-level reporting | Single-tenant-per-property model, matching Atlas's existing tenant model |
| Any AI feature (concierge, forecasting, etc.) | Not evaluated in this pass |

## Status

**Proposal only.** Not scheduled, not part of the v1 build order, no PLAN.md/STRUCTURE.md/
GITHUB-WORKFLOW.md changes accompany this doc. A prior session scoped a different candidate
capability (field-force tracking) and let it drift into a ticked PLAN.md phase and actual scaffold
code before it was fully reverted as unplanned scope (PR #143, 2026-07-20) — this doc deliberately
stays on the safe side of that line, the same way
[field-force-tracking-market-scan.md](field-force-tracking-market-scan.md) did. If hospitality is
pursued, it needs its own explicit go-ahead and a proper implementation plan before any PLAN.md
entry or code lands.
