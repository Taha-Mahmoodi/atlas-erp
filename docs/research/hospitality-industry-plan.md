# Hospitality (Hotel & Restaurant) — Industry Entry Plan

This document scopes a candidate **6th industry template** — hospitality, specifically a combined
property that runs both room operations and an on-site restaurant (boutique hotel, resort, B&B,
inn) — plus the custom modules it would need beyond the five shipped templates
([docs/industry-templates.md](../industry-templates.md)). Like the
[field-force tracking scan](field-force-tracking-market-scan.md), **this is a proposal, not a
commitment**: no PLAN.md, STRUCTURE.md, or GITHUB-WORKFLOW.md changes accompany this doc, and
nothing described here is scheduled or in flight. Research conducted August 2026 via public
product/feature pages.

**Revision, August 2026.** The owner clarified the guest-facing architecture (Atlas is the backend
of record; the property's own website is an API client), and six design questions were researched
against the actual codebase. That work invalidated two things in the first draft: the QR-flow
section, which described Atlas hosting a guest ordering page it will not host, and the headline
claim that hospitality requires **no core-platform changes**, which was true only for a flow Atlas
served itself. Both are corrected below, along with the resolutions and costs of all six questions.

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
| COA | Guest Ledger (asset control) / City Ledger (the existing AR control) / Advance Deposits (liability) / Room Revenue / F&B Revenue split out — three control accounts, not one, see Q5 |
| Custom fields | `star_rating`, `check_in_time`, `check_out_time` on the tenant/property record |
| Costing default | FIFO (F&B inventory), matching retail/healthcare |

## New module 1 — Rooms & Folio

- `room_type`, `room` (adds `housekeeping_status: DIRTY|IN_PROGRESS|CLEAN|INSPECTED|OUT_OF_ORDER`)
- `rate_plan` — manual nightly rates in v1, not algorithmic
- `reservation` — new document type (registered in `core_documents`, gets a doc number + doc-flow
  links): `TENTATIVE → CONFIRMED → CHECKED_IN → CHECKED_OUT/NO_SHOW/CANCELLED`
- `hsp_room_type_inventory` — the per-date allotment counter that makes the booking gate safe under
  concurrency (Q3). Rooms are sold **by room type against a date-keyed counter**, with the physical
  room assigned at check-in — the Opera model, not a per-room interval lock.
- `folio` — new document type, the running multi-charge tab. Predecessor = reservation (when one
  exists). `folio_line` rows carry heterogeneous charges (room-night, restaurant, incidentals),
  each traceable to its source document via doc-flow links. **Correction from the first draft:** a
  folio has three posting moments, not one — deposit received pre-arrival, room+tax posted per
  night by the night audit, and settlement at checkout, which is a *clearing* event, not the
  revenue event (Q5).
- **Night audit** — an idempotent, set-based job (D-013 on the transport, a unique index on the
  data), **manually triggered in v1** because Atlas has no scheduler and no machine credential to
  drive one. Posts one room-night line per checked-in reservation, rolls the business date.
- **Business date** — a first-class `hsp_business_dates` row per operating day, not `date.today()`.
  It is the source of `posting_date`; the fiscal period is the authorisation window that must
  contain it (Q5).
- **Group bookings** — room blocks with cutoff dates; a master folio absorbs group F&B/incidentals
  and splits back to individual folios or the group organizer at settlement.
- **Housekeeping** — a `housekeeping_task` document (room, trigger: CHECKOUT/SCHEDULED/GUEST_REQUEST,
  assigned staff, status), not just a status enum — real task assignment and tracking.

## New module 2 — Restaurant Ordering

- `table` (number, section, seats, status)
- **Menu items are not a new entity** — existing `inventory_item` rows with a Manufacturing
  `bill_of_material` defining ingredients. Recipe costing is pure reuse of the manufacturing BOM
  engine. **Qualification from the first draft:** *availability* is a new entity, small but real —
  `hsp_menu_availability`, one row about an item, not a new item (Q2). Reusing `Item.is_active` for
  nightly 86-ing is wrong for three separate reasons documented there.
- `order_ticket` — new document type: `OPEN → SENT_TO_KITCHEN → IN_PREP → READY → SERVED →
  SETTLED`, lines carry seat number + notes. KDS is a status-filtered view over open ticket lines
  grouped by a prep-station field on the menu item — a query, not new hardware/device software.
- **Ingredient depletion fires at `SENT_TO_KITCHEN`, in a background job** — not synchronously at
  settlement. The measured reason is in Q4; the short version is that a synchronous settle-time
  depletion is a shipped HTTP 500 above 49 ingredient lines and refuses the guest's payment when
  theoretical stock is wrong, which in this industry it routinely is.
- `hsp_service_slot` — the 15-minute pacing counter behind table reservation, same shape as the
  room-type allotment counter (Q3).
- Split checks: per-seat/per-item bill splitting at settlement.

**Weekly/monthly item report + margin-driven offer suggestion.** A report ranks items by units
sold and trend (reuses Reporting's existing projection pattern, no new financial engine). The
"offer algorithm" is an explainable rule, not a machine-learning system: rank items by `margin ×
declining velocity`, surface high-margin/slow-moving items as **suggested** discount candidates
with a suggested %, for a manager to approve. It never auto-applies a discount — full
algorithmic/live pricing stays out of scope, same reasoning as the "no dynamic rate pricing" call
on the hotel side.

## The guest-facing surface — Atlas is the backend, the property's website is the client

**This section replaces the first draft's "Guest-facing ordering (QR flow)", which was wrong.**
Atlas does not generate QR codes and does not host a guest-facing ordering page. A QR code on a
table is just a printed link to the restaurant's **own website**. Ordering, table reservation and
room reservation all happen on that website. Atlas is the **backend of record for the menu** — what
is on it, what it costs, what is available, what ran out — and the website is an **API client** of
Atlas.

That inverts one thing and adds one thing.

**Inverted:** there is no `channel: GUEST_QR` variant of a staff-entered ticket living inside
Atlas's own UI. There is a website that POSTs an order ticket over the API. The staff
acknowledgment flag survives and matters more, not less — a ticket arriving from an external
client should never silently skip a human check before kitchen routing.

**Added:** an external website is a **machine principal**, and Atlas has exactly one
request-authentication path today. `backend/app/core/deps.py:71` decodes a user access JWT and
nothing else in `app/` decodes a request credential. A machine credential is therefore a **core
change** — the only one this vertical needs, and the reason the "no core-platform changes" claim
below is corrected rather than repeated.

The boundary that keeps this small: **the website's server is the only Atlas client; the guest's
browser never talks to Atlas.** That keeps the credential off the wire, makes CORS a non-issue
(`backend/app/main.py:188-194` already runs `allow_credentials=True` and prod is same-origin behind
nginx anyway), and makes the website's own cache the rate limiter Atlas does not have. Square draws
the same line explicitly: static tokens are "for custom integrations that only access your own
Square account", never client-side
(https://developer.squareup.com/docs/build-basics/access-tokens).

**Online table reservation** and **online room reservation** are the same shape: the website is the
UI, Atlas holds the counter and arbitrates the race (Q3). A `table_reservation` document still
exists in Atlas — it is just created over the API rather than in an Atlas-hosted page.

**Online payment.** Settlement gains an `ONLINE_CARD` method via a **pluggable payment-provider
interface** (Stripe/Adyen-shaped: create a payment intent, confirm via webhook). Atlas never
touches raw card data — PCI scope stays with the provider. Scoped to restaurant-order settlement
in v1; extending online payment to hotel folio/booking deposits is a separate future decision.
Note that the *deposit* side of this is not a payment-provider problem but a finance-module gap
(Q5).

## The bridge — one genuinely new integration point

`order_ticket.settle(charge_to_room: folio_id)` publishes `RestaurantOrderSettled`; a Rooms &
Folio handler appends a `folio_line` with a doc-flow link back to the ticket. This is the same
shape as the existing `SalesOrderShipped → inventory issues stock → finance posts COGS` pattern —
no new core-platform mechanism, just one new event and two handlers. Direct (non-room) payment
settles like a small POS sale, reusing Sales' existing invoice/payment primitives.

The one thing that must **not** ride this event synchronously is ingredient depletion — see Q4.

---

# Resolved design questions

Six questions were researched against the codebase in August 2026. Each resolution below states
the answer, what it costs, and whether it touches `backend/app/core/`. Code claims carry
`file:line`; research claims carry URLs.

## Q1 — How does the website authenticate to Atlas? **Core change: yes.**

**Answer: a scoped API key that resolves to a dedicated service `User` row, branched inside
`get_current_user`.**

The whole design rests on one structural fact: `backend/app/core/deps.py:64-112` is the *only*
place a request principal is built. It sets the D-007 tenant ContextVar (`deps.py:83`), loads and
validates the user (`deps.py:85-92`), resolves D-009 permissions (`deps.py:97`), sets the masking
ContextVar (`deps.py:102`) and the D-010 audit actor (`deps.py:105`). `require_permission` doesn't
re-implement any of it — it depends on `get_current_user` (`backend/app/core/rbac.py:173,176`). 436
call sites reference `CurrentUserDep` across `app/`. **Any credential that can produce the same
frozen `CurrentUser` dataclass inherits the entire platform with zero router changes**, D-013
idempotency included: `backend/app/core/idempotency.py:310` reads the tenant from the ContextVar,
not from `CurrentUser`.

Shape:

- One `ApiKey` model in `backend/app/core/models.py` beside `RefreshSession` (`models.py:143-171`),
  which it structurally mirrors: tenant_id, user_id, name, prefix, `secret_sha256` (unique index),
  nullable scopes JSON, `expires_at`, `revoked_at`.
- Key format `atk_<tenant-ref>_<32 bytes urlsafe>`, hashed with the existing `sha256_hex`
  (`backend/app/core/auth.py:43-45`) — **not argon2**. The codebase documents argon2id at D-008
  parameters as costing "tens of ms" (`auth.py:68`); running that per request would wreck the
  PERFORMANCE §5 budget, and the argument that forces argon2 for *passwords* does not apply to 256
  bits of CSPRNG output.
- **The tenant rides in the key string**, so D-007 needs no fifth `system_context()` bypass
  (`backend/app/core/tenancy.py:49-64` documents exactly four sanctioned sites). Set
  `current_tenant_id` from the prefix exactly as `deps.py:83` does from the JWT claim, then look
  the key row up under the ordinary tenant filter — a forged prefix finds no row and 401s, the same
  fail-closed argument already written at `deps.py:79-82`.
- **Scopes map onto D-009 by intersection, not by a new mechanism**: effective permissions =
  `resolve_permissions(...) & frozenset(key.scopes)`, validated against `rbac.catalog_keys()`
  (`backend/app/core/rbac.py:47`, 111 keys). A key may only ever *narrow* its user.
- **The key lookup must be folded into the existing user load** — `select(User).join(ApiKey, ...)`.
  `backend/tests/conftest.py:140,160-163` states the ≤3 query budget counts the auth user load plus
  the page select with "one query of slack", and that slack is a regression margin, not headroom. A
  separate SELECT spends it. Corollary: no per-request `last_used_at` write.
- **Bind the key to a real `User` row.** `AuditLog.actor_user_id` is nullable with no FK
  (`backend/app/core/models.py:280`) and modules deliberately never hard-FK to `core_users`
  (`backend/app/modules/hr/models/org.py:139`,
  `backend/app/modules/procurement/models/requisitions.py:67`), so a synthetic principal id would
  insert cleanly and leave an unresolvable actor across 13 `submitted_by`/`approver_id` sites.
  `User.password_hash` is NOT NULL (`models.py:131`), so the service user carries a hash of a
  discarded random secret — a small hack that must carry a comment.
- **Rate limiting is nginx, not Python.** There is none today, for humans either. Prod already
  proxies `/api` through nginx (`frontend/nginx.conf:13`), so `limit_req_zone` keyed on the
  Authorization header is the whole fix. 10 req/s burst 20, sized against Cloudbeds (5 req/s per
  property, 10 for tech partners) and Toast (20 req/s burst, 10,000 per 15 min, 1 req/s on
  `GET /menus`) — https://doc.toasttab.com/doc/devguide/apiRateLimiting.html
- **CORS changes by exactly nothing**, and that is the answer, not a deferral.

**Why not the alternatives.** A **service user on the existing JWT flow** works today with *zero*
new code — create a user, give it a role, POST `/api/v1/auth/login`
(`backend/app/core/security_router.py:80-130`) every 15 minutes — and is the honest day-zero
fallback if hospitality is ever piloted before a credential ships. It has three concrete defects:
the credential is a password on the one unauthenticated public endpoint; every login inserts a
`core_refresh_sessions` row (`security_router.py:116-128`) with **no purge job anywhere in the
repo**, ~35,000 dead rows/year/property at a 15-minute cycle; and revocation granularity is the
whole user, so there is no overlap window for a zero-downtime rotation. **OAuth2
client-credentials** is what Toast does (`userAccessType: TOAST_MACHINE_CLIENT`,
https://doc.toasttab.com/doc/devguide/authentication.html) but Toast needs credential/tenant
separation because one client serves many restaurants — hence the separate
`Toast-Restaurant-External-ID` header. Atlas's website client serves exactly one property. The rest
of the market has moved the other way for first-party use: Mews issues a per-property AccessToken
"identifying the property or properties whose data and services you can access"
(https://docs.mews.com/connector-api/guidelines/authentication); Cloudbeds ships property-scoped
static keys where "the key itself determines the scope of resource access without requiring
additional tenant identifiers" and publishes an explicit *migration from OAuth 2.0 to API keys*
for technology partners
(https://developers.cloudbeds.com/docs/api-keys-authentication-guide-for-technology-partners);
Lightspeed offers personal tokens alongside OAuth for headless scripts
(https://x-series-api.lightspeedhq.com/docs/authorization). Add client-credentials the day Atlas
has external developers to delegate to.

**Cost.** ~25 lines of ORM in `core/models.py`, one Alembic migration, ~30 lines in `core/deps.py`
(one branch, one joined query), ~10 lines in `core/auth.py` for mint/parse. Three admin endpoints
(create/list/revoke) behind a new `admin.apikey.manage` key registered beside the existing `ADMIN_*`
keys at `rbac.py:54-81`. One DECISIONS.md entry recording that bearer credentials now have two
shapes and why the tenant rides in the key. Tenancy tests must gain tenant-A-key-cannot-read-B, plus
revoked and expired cases. **Not taken:** no OAuth server, no token endpoint, no client registry, no
`last_used_at` write, no Python rate limiter, no CORS change, no change to D-007/D-009/D-010/D-011/
D-013, no change to any of the 436 `CurrentUserDep` call sites.

## Q2 — Menu availability and 86-ing: derived or stored? **Core change: no.**

**Answer: store the state, derive only the suggestion.**

The owner's intuition that "we have items that have status" is **wrong, and specifically so**.
`Item.is_active` (`backend/app/modules/inventory/models/masters.py:153-155`) is **filter-only**: read
in exactly two places, the item list filter
(`backend/app/modules/inventory/service/items.py:131-132`) and the reorder scan
(`backend/app/modules/inventory/queries.py:237`). Nothing enforces it — `item_exists`
(`backend/app/modules/inventory/queries.py:48-55`) selects `Item.id` and never looks at
`is_active`, and that is the validator both sales order lines
(`backend/app/modules/sales/service/_shared.py:58-68`) and BOM components
(`backend/app/modules/manufacturing/service/boms.py:37-45`) call. An inactive item can be ordered,
BOM'd and moved today. It also has the wrong *lifetime*: `Item` carries AuditMixin
(`masters.py:110`), so under D-010 every flip writes a before/after audit row — 86-ing is a
shift-scoped toggle a kitchen flips dozens of times a night, and an 86'd dish would also vanish from
purchasing, reporting and recipe costing, not just from the menu.

**Derived-as-truth fails on four counts.** (a) *The ETag trap, which is decisive.*
`collection_etag` (`backend/app/core/conditional.py:65-93`) is `COUNT(id), MAX(updated_at)`, and the
item list serves 304s off it (`backend/app/modules/inventory/router.py:235-246`). If availability
were derived from `inv_stock_quants`, selling the last portion moves no `Item.updated_at` — the
validator doesn't move and **the website keeps receiving a 304 asserting the sold-out dish is
available**. Stored availability on a row the ETag aggregates over invalidates correctly and for
free. (b) *Cost.* `atp_check` is 3 queries per item
(`backend/app/modules/sales/queries/availability.py:120-155` = `total_on_hand` +
`committed_quantity` + `open_incoming_quantity`); a 60-item menu at ~6 components is ~1,080
queries, 360× over PERFORMANCE §2's ≤3. (c) *Wrong formula.* `available = on_hand − committed +
on_order` (`availability.py:142`) — `on_order` adds open PO quantity, so Thursday's tomato delivery
makes tonight's caprese read available, and `committed` subtracts nothing because a restaurant has
no confirmed sales orders. Reusing it verbatim is biased **optimistic** exactly where a restaurant
cannot afford it. (d) *Shared ingredients.* `max_producible = min over components` over-reports:
eight dishes sharing one tub of feta each independently derive "available" while collectively one
portion remains.

Also: an ACTIVE BOM is frozen and immutable
(`backend/app/modules/manufacturing/constants.py:126-137`), correct for manufacturing, real friction
for a kitchen swapping a garnish; a reverse-BOM lookup for auto-86 is unindexed
(`mfg_bom_components` indexes only `(tenant_id, bom_id)`,
`backend/app/modules/manufacturing/models/boms.py:112`); and hanging availability off `StockValued`
(`backend/app/modules/inventory/events.py:27-67`) would let a bug in a menu flag roll back a stock
move and its COGS journal under D-011.

**The industry converges on stored.** Toast: three states (In Stock / Out of Stock / Quantity),
Quantity auto-decremented on send-to-kitchen, manual status persistent, and explicitly "not related
to the Toast Inventory module"
(https://doc.toasttab.com/doc/platformguide/adminMenuItemInventoryOverview.html). Toast's *own*
recipe-based depletion does not auto-86: "When an item's calculated stock hits zero, it appears on
the list with an Out label... you can update your POS by 86ing the item" — the recipe math produces
a **suggestion**, a human makes the **decision**
(https://support.toasttab.com/en/article/Toast-InventoryStock-Depletion). Square makes derived and
manual mutually exclusive, auto-86s at count 0, and auto-resets sold-out at end of business day
(https://squareup.com/help/us/en/article/6425-managing-items-with-square-for-restaurants).
Lightspeed K-Series time-boxes the manual override — snooze 1h/12h/24h/indefinitely, with
out-of-stock rendering red and manually-snoozed rendering orange
(https://k-series-support.lightspeedhq.com/hc/en-us/articles/10724827631259-Setting-up-and-using-Item-availability).
One stored state per sellable thing, two writers, its own expiry, read as one flat field. **Nobody
explodes a recipe on the guest read path.**

**Shape.** `hsp_menu_availability` in the Restaurant module: tenant, `item_id` UNIQUE, `state:
AVAILABLE|LIMITED|EIGHTY_SIXED`, nullable `remaining_qty`, nullable `available_until`, `reason`,
`source: MANUAL|AUTO`. Auto-86 is the **countdown case only** — decrement `remaining_qty` when the
website posts an order, flip at 0 — which is what Toast's and Square's auto-86 actually is: a
per-item counter, not a BOM. Expiry evaluates **lazily on read**
(`WHERE available_until IS NULL OR available_until > now()`), because no scheduler exists. Derivation
earns its place as a **staff-facing "at risk" list**: one endpoint that batch-explodes ACTIVE
default BOMs and reports `max_producible` from **on-hand only** (drop `on_order` and `committed`),
in the set-based shape already proven by `items_below_reorder_point`
(`backend/app/modules/inventory/queries.py:207-251` — one LEFT JOIN + GROUP BY + HAVING). It says
"feta covers 2 more portions"; a human 86s.

**Cost.** One table + migration, one service (~150 lines: set/clear 86, countdown, lazy expiry), one
batched availability read, one derived staff endpoint, plus one new batched
`on_hand_for_items(item_ids) -> dict` in inventory. **Correctness traded:** stored state drifts from
physical reality between 86s — a dish stays AVAILABLE after a prep cook empties the walk-in without
touching the POS. That is the industry-accepted trade (Toast's depletion drifts from the last
physical count for the same reason) and the "at risk" list exists to surface it. `max_producible`
stays advisory and can over-report on shared ingredients, which is precisely why it must never be
the guest-facing number. **Not covered, named rather than hidden:** modifier-level 86 (Toast and
Square both ship it) has no home because modifiers are not modeled in Atlas at all; and day-part
menus ("brunch ends at 11") are a scheduling concern `available_until` only half-covers.

## Q3 — Overbooking prevention for rooms and tables. **Core change: no.**

**Answer: a per-slot counter row locked `with_for_update` inside the booking transaction — copy
`apply_bin_delta` verbatim in shape.**

The premise dissolves under the industry evidence. Hotels do **not** gate on interval exclusivity:
they sell by room type against a per-date inventory count and assign a physical room at check-in
(Oracle: "Availability is calculated and displayed by room type"; the generic room type "does not
have any physical rooms associated with it" —
https://docs.oracle.com/cd/E98457_01/opera_5_6_core_help/room_types.htm). Restaurants gate on
**pacing caps per 15-minute slot**, not per-table locking: OpenTable flow controls set "the maximum
number of guests or parties that can book reservations within each 15-minute time slot of a shift"
(default 30 covers/15 min, https://support.opentable.com/s/article/flow-controls?language=en_US);
Resy defaults to 10 covers/15 min
(https://helpdesk.resy.com/en_us/how-to-setup-flexible-seating-to-maximize-covers-BkL3bvQLO).
Physical table assignment is OpenTable's revisable soft-assignment/reflow step **after** the booking
is accepted. Both reduce to: decrement a counter on a (resource-class, discrete-slot) row, never
below zero.

That is exactly the mechanism Atlas already ships for stock.
`backend/app/modules/inventory/service/stock_quants.py:62-118` is the whole pattern: load the
uniquely-keyed row `with_for_update` (`:80`), pre-flight-reject a negative delta (`:100-103`),
upsert if absent (`:104-113`), all inside the caller's transaction, with a portable
`CHECK(on_hand_qty >= 0)` as the DB backstop (`stock_quants.py:8-10`, proven at
`backend/tests/modules/inventory/test_stock_db_guards.py:118-125`). D-020/D-036 explicitly sanction
`with_for_update` as "PG row lock; SQLite no-op" and require deterministic lock ordering — the
multi-night-stay problem verbatim.

**Shape.** `hsp_room_type_inventory`, UNIQUE(tenant_id, room_type_id, stay_date), columns
`rooms_sellable` / `rooms_sold` / `overbooking_limit`, with `CHECK (rooms_sold >= 0)` and
`CHECK (rooms_sold <= rooms_sellable + overbooking_limit)`; an N-night stay touches N rows locked in
**ascending stay_date order** in one helper. `hsp_service_slot`, UNIQUE(tenant_id, service_date,
slot_start) on a 15-minute grid, `covers_booked`/`covers_max` + `parties_booked`/`parties_max`, same
CHECK shape, locked in ascending `slot_start` order. Take the lock as the **first** write in the
`run_in_uow` body, before pricing/folio/journal, so the hold is the transaction tail rather than its
whole length.

**Why the alternatives are wrong, not merely worse.** `EXCLUDE USING gist (room WITH =, during WITH
&&)` enforces **the wrong invariant**: it structurally forbids deliberate overbooking, which hotels
run at 5-10% of inventory as a no-show buffer, tightening toward arrival
(https://www.mews.com/en/blog/hotel-overbooking-strategy,
https://roompricegenie.com/overbooking-strategy-how-to-maximize-occupancy-and-avoid-relocating-guests/),
and it forbids room-type-level selling. It also needs `btree_gist` to scope the overlap
(https://www.postgresql.org/docs/current/rangetypes.html) and would put the plan's hardest
correctness invariant **entirely outside what the SQLite suite can exercise** — the exact failure
mode `backend/app/core/db_guards.py:6-9` was written to prevent ("getting that branch wrong is
invisible to the SQLite-only test suite (issue #12)"). **Serializable isolation** has zero precedent
in the tree, is engine-wide across all 8 prod workers (`docker-compose.prod.yml:103`), needs a 40001
retry loop Atlas doesn't have, and under D-011 every retry re-runs the folio line and the journal
posting. **A unique row per booked night** works and is portable — the depreciation run already uses
exactly that shape as its "idempotency backbone"
(`backend/app/modules/finance/models/assets.py:17-18`) — but forces committing a physical room at
reservation time and forbids overbooking; keep it for a physical-assignment table, not the
availability decision. **Unlocked read-then-check** is the bug already sitting in
`backend/app/modules/finance/service/periods.py:88-100` (a TOCTOU overlap scan nobody hits because
fiscal years are created once a year by one admin); applying that shape under website traffic is
precisely how you double-book. And **ATP is not a defence** — `atp_check` takes no lock and D-044
makes it explicitly non-blocking (`availability.py:108`,
`backend/app/modules/sales/service/order_confirm.py:5-9`). In-process locking is not an option
either: 8 uvicorn workers means any `asyncio.Lock` is per-process and useless.

**Cost. Zero new core code** — `with_for_update`, portable CHECK, `tenant_unique`
(`backend/app/core/models.py:104`), `run_in_uow` and D-013 all already exist. What it *does* cost:
**(1) A grid to maintain**, which is the real hidden expense — rows must exist for every future date
in the booking window, and every path must go through the counter (cancellation decrements, no-show
does not, out-of-order rooms reduce `rooms_sellable`, group-block release decrements, a date change
is a decrement plus an increment on two different rows). A missing row must upsert-on-lock (the
`quant is None → session.add` branch at `stock_quants.py:104-113`) or it reads as zero availability
and silently refuses bookings. Extending the horizon is night-audit work. **(2) Point-in-time only:**
the counter is authoritative, not reconstructible, so a reconciliation job against actual reservation
rows is needed the way D-036 says the quant is "reconcilable from" the move ledger — budget it or
accept silent drift. **(3) A throughput ceiling on hot slots** — Postgres serializes all bookers of
one room-type-night or one 8pm slot for the transaction's duration, with the folio line and journal
posting inside it under D-011. Fine at one boutique property and PERFORMANCE §5's 50 concurrent
users; **not** fine as a multi-property or OTA/channel-manager gate, both already out of scope. If
that scope returns, revisit this decision rather than stretching it. **(4) A permanent test-coverage
gap, inherited not created:** on SQLite `FOR UPDATE` is omitted, so the default suite proves the
arithmetic and the CHECK but cannot prove the race is prevented. The `@pytest.mark.pg`
two-connection test is **mandatory**, and it lands in an already-wired job —
`.github/workflows/ci.yml:17-31` stands up real `postgres:16-alpine` and line 59 runs `-m pg`.
**(5)** Two near-identical tables rather than one "resource booking" abstraction, deliberately: the
invariants genuinely differ (allotment-with-overbooking vs pacing cap), so a shared interface would
have two implementations differing in every column.

D-013 needs no change and covers the adjacent failure: `reserve`
(`backend/app/core/idempotency.py:200-245`) already returns 409 `idempotency.in_progress` for a
concurrent duplicate of the *same* key and replays a completed one. The row lock handles two
*different* guests. Complementary, not overlapping.

## Q4 — Per-sale ingredient depletion. **Core change: no.**

**Answer: background it, aggregate components, and move the trigger off the payment.**

This one was **measured**, not estimated, using the repo's own `query_counter` fixture
(`backend/tests/conftest.py:85-145`) driving `create_move` through `run_in_uow`. One ingredient ISSUE
move with the inventory→finance COGS handler registered costs **38 SQL statements** (19 SELECT / 10
INSERT / 9 UPDATE). Scaling is exactly linear: 3 lines = 113, 6 = 227, 12 = 455, 24 = **911
statements / 690 ms wall on SQLite**. (Scratch test written, run, deleted — nothing left behind.)

Where the 38 go, per component: 2 validation SELECTs (`stock_moves.py:212,220`), 2 docflow
(`backend/app/core/docflow.py:203-215`), 3 numbering (`backend/app/core/numbering.py:104-110,
161-167, 190-194`), the move INSERT, a doc-status UPDATE, 2 quant
(`stock_quants.py:72-118`), 3 costing lookups (`costing.py:83,93` and `:64-70`), valuation
read+write, a unit_cost UPDATE — **and then the entire journal-posting protocol, ~15 statements**,
because every ingredient line posts its own COGS entry
(`backend/app/modules/finance/handlers/inventory_cogs.py:65-76` →
`backend/app/modules/finance/service/journal.py:97-143, 167-244`), plus 4 `core_audit_log` INSERTs.

**Three hard breaks in shipped code.**

1. **`MAX_DISPATCHES_PER_UOW = 50`** (`backend/app/core/events.py:61`) counts **handler
   invocations**, not events (`:203-209`). Verified by running it: **50 lines commit, 51 raises
   `EventCycleError` → HTTP 500** (`:68-82`). With the plan's own `RestaurantOrderSettled` design the
   settle event consumes one dispatch, so the real ceiling is **49 ingredient lines**. An 8-top
   ordering 8 dishes at 7 ingredients each is 56 lines: **the guest cannot pay their bill, and the
   error is a 500.** This is a wall, not a tuning knob.
2. **A missing ingredient refuses the payment.** `apply_bin_delta` raises `InsufficientStockError`
   when any component would go negative (`stock_quants.py:100-103`) and D-011 rolls the whole uow
   back (`events.py:240-245`). Restaurant theoretical stock is *known to be wrong* — the industry
   benchmark is that actual-vs-theoretical variance under 2% is well-run and above 5% is systematic
   (https://www.crunchtime.com/blog/blog/explaining-actual-vs-theoretical-food-cost-variance,
   https://www.restaurant365.com/blog/closing-the-gap-between-actual-and-theoretical-food-costs/). So
   Atlas will routinely believe an ingredient is at zero while the kitchen still has it, and under
   synchronous all-or-nothing that **blocks the guest from paying**.
3. **Same shape, two more triggers:** a settlement dated into a closed fiscal period fails at
   `journal.py:199-205`; an item category without wired inventory/COGS/price-difference GL accounts
   fails at `costing.py:93-100`. Both roll back the whole settlement. Month-end close running during
   service, and a chef adding an ingredient without GL wiring, are ordinary operational states.

**Plus tenant-wide serialization, and it is not the query count that causes it.** Every stock move
claims the STK number and every journal entry the JE number via `UPDATE core_number_sequences SET
next_value = next_value + 1 ... RETURNING` (`backend/app/core/numbering.py:190-194`). Those row locks
are held until COMMIT *by construction* — D-012's gaplessness depends on it. A 24-line settlement
holds the tenant's stock-move and journal sequence rows for the entire ~0.5-1 s transaction,
serializing every other settlement, delivery, goods receipt and count in the tenant — including the
property's **hotel** postings. FIFO (the plan's own F&B costing default) adds a second contention
point: `consume_layers` runs an **unbounded `SELECT ... FOR UPDATE`** over every open layer for
(item, warehouse) with no LIMIT (`backend/app/modules/inventory/service/costing_fifo.py:76-90`), and
statement count stays flat as layers accumulate (measured 39 at 1, 5 and 20 layers — consumption
inserts batch into one executemany), so this cost is **invisible to a query-count budget**.

**Throughput is not the problem** and it's worth saying plainly rather than implying a scaling
crisis: 300 covers over 4 hours is ~0.02 settlements/s, a 20× burst ~0.4/s. Even fully serialized
1-second transactions absorb that. The problems are the 500, the refused payment, ~0.5-1 s on the
POS settle button, and the hotel-side collateral damage.

**Shape.** (1) The settle transaction does **money only** and calls
`submit_job("restaurant.deplete_ticket", {ticket_id})` inside the same uow, so a D-013 replay returns
the same job id (`backend/app/core/jobs.py:13-16,150-174`). (2) The handler explodes the BOM and
**aggregates components across all ticket lines before issuing** — a 4-dish check sharing onion, oil
and salt collapses from ~24 lines to ~12 distinct items; this roughly halves the statement count,
pushes the dispatch ceiling out of practical reach, and costs nothing architecturally. (3) **Fire at
`SENT_TO_KITCHEN`, not `SETTLED`** — ingredients are consumed at fire, not at tender; a dish comped
or voided after service has already eaten them, and the variance literature counts exactly that as
actual usage
(https://www.marginedge.com/blog/a-restaurant-operators-guide-to-actual-vs-theoretical-food-costs-and-usage).
(4) Reuse the count-post threshold shape verbatim — `post_stock_count` already posts inline at
≤ `COUNT_POST_SYNC_MAX_VARIANCES = 200` and backgrounds above it
(`backend/app/modules/inventory/count_router.py:260-264`,
`backend/app/modules/inventory/constants.py:202`), with the job handler a thin delegation to the same
engine (`backend/app/modules/inventory/service/count_jobs.py:26-44`). Same code, same guarantees,
different transaction boundary. (5) **Before any of this lands, add the write-path query-count test
that does not exist today** — `backend/tests/perf/test_budgets.py` covers only read paths, and
PERFORMANCE §2's ≤3 rule is explicitly a *list-endpoint* rule
(`backend/tests/conftest.py:148-170`). Nothing in CI would catch a settlement regressing from 900 to
9,000 statements.

Industry does not couple depletion to the payment either: a production restaurant-inventory pipeline
is described as POS data feeding item depletion **every 15 minutes**
(https://ustechautomations.com/resources/blog/restaurant-inventory-automation-case-study-2026), and
Toast's own docs say only that stock decrements "every time that menu item is sold", never that the
timing is synchronous with tender. "Perpetual" in this industry means near-real-time, not
in-transaction.

**Cost. No new core code** — `register_job`/`submit_job`/`schedule_job` already do all of it, and the
job runner restores tenant context (D-007) and the D-010 actor and runs the handler **inside
`run_in_uow`** (`backend/app/core/jobs.py:297-303`), so D-011's actual invariant ("goods issue
without COGS can never commit") still holds. What is genuinely traded: **(1) Point-in-time
consistency between the stock ledger and the sales ledger.** For the job's duration a settled ticket
has revenue with no COGS; a trial balance run mid-service is momentarily short the COGS of in-flight
tickets. Real, and must be documented rather than hand-waved. **(2) A loud failure becomes quiet.**
Today a bad depletion is a 422 with a guest standing there; after this it is a FAILED job row
(`jobs.py:304-312`) nobody sees. This must be bought back with FAILED-job alerting or the change is
strictly worse than today — and it lands on a **pre-existing core gap: there is no stale-PENDING
sweeper**, so a job whose PENDING row committed but whose runner died to a restart stays PENDING
forever with no retry. Tolerable for a stock count; not tolerable for something with a GL effect.
**(3) Precision about D-011:** what breaks is the weaker, unstated coupling "the sale and its
depletion commit together", not D-011 itself. **(4) Scope of the concession:** the argument that
stale stock barely matters rests on restaurant theoretical usage being permanently 2-5% wrong by the
industry's own numbers. That reasoning does **not** transfer to the hotel side or any other Atlas
vertical — it must be a restaurant-module DECISIONS.md entry, never a platform-wide relaxation of
D-011. **Rejected:** raising `MAX_DISPATCHES_PER_UOW` treats the symptom and leaves the lock-duration
and phantom-stock-out problems intact; a pure fixed-interval batch needs a scheduler Atlas does not
have.

## Q5 — Folio posting, advance deposits, business date, night audit. **Core change: no — but a shipped *finance* change: yes.**

**Answer: three changes, none in `backend/app/core/`, one of them in the shipped finance module.**

**The first draft's posting model was wrong, not incomplete.** A folio has three distinct posting
moments. *Deposit received pre-arrival:* Dr Bank / Cr Advance Deposits — a contract liability, "a
deposit is a liability, not revenue, until the hotel actually delivers the stay, per ASC 606"
(https://www.docyt.com/article/advance-deposit-revenue-recognition-hotels/). *Each night:* Dr Guest
Ledger / Cr Room Revenue + Cr Occupancy Tax — Oracle's End-of-Day runs "post room and tax" as a
Final Procedure, **per night**
(https://docs.oracle.com/cd/E98457_01/opera_5_6_core_help/about_end_of_day_sequence.htm).
*Settlement at checkout:* a **clearing** event, not the revenue event. The first draft's "successor =
the journal entry posted at settlement" would recognise a 5-night stay's revenue in a single period
even when the stay straddles month-end.

**(1) Deposits — Atlas has no advance-deposit primitive, verified.**
`backend/app/modules/finance/service/customer_receipts.py:66-70` hard-rejects an allocation-less
receipt (`finance.receipt_no_allocations`); `:72-90` requires every allocation to reference an
existing POSTED/PARTIALLY_PAID `CustomerInvoice` of the same partner and currency; `:186-190`
requires amount == sum(allocations). A pre-arrival deposit has no invoice to point at. There is no
unapplied/on-account receipt and no SAP-style customer down-payment. **This gap is not
hospitality-specific** — it is the same gap for any deposit-taking industry.

Both obvious workarounds are dead ends. *Just add an Advance Deposits account and post a journal*
loses open-item tracking: `backend/app/modules/finance/queries/partner_ledger.py:24-90` derives every
open balance from `CustomerInvoice.open_amount` / `VendorBill.open_amount` **rows**, never from
journal lines, so the deposit becomes a GL balance with no per-guest drawdown, invisible to
`service/ar_aging.py` and `service/dunning.py` and unclearable by the receipt engine. *Fake a deposit
invoice* is mechanically possible — `_require_account`
(`backend/app/modules/finance/service/customer_invoices.py:51-62`) validates only that the account
exists, never its `AccountType` — but **fails irrecoverably at release**: freeing the deposit into
the folio at check-in needs a credit note, and
`backend/app/modules/finance/service/credit_notes.py:160` sets `note.open_amount = 0` ("a credit note
is not an open receivable"), with no apply-credit-note-to-invoice path anywhere in finance. The
release leaves a dangling AR debit that can never be cleared.

So: **widen `CustomerReceipt` to allow an unapplied receipt, in finance, not in a hospitality
module.** Make `allocations` optional in `_validated_clearing` (`customer_receipts.py:66`), add an
`unapplied_amount` MoneyType column, credit a configurable advance/on-account control instead of the
AR control for the unapplied portion with `partner_type`/`partner_id` stamped on the line, and add
one `apply_receipt(receipt_id, allocations)` that moves unapplied → allocation and reuses the
existing `clearing_fx` helper verbatim. That is the SAP customer-down-payment shape and every
industry gets it; hospitality then writes **zero** deposit code — check-in and settlement just call
`apply_receipt`. (A folio-owned `folio_deposit` table was rejected: it duplicates AR's entire
clearing engine inside a hospitality module, and two clearing engines rot.)

**Guest ledger vs city ledger is a two-control-account problem, and advance deposits belongs to
neither.** The guest/front-office ledger holds registered guests' folios; the city ledger holds
non-registered accounts — companies, travel agents, card companies — and "upon check-in, advance
deposit amounts transfer from the city ledger's common advance deposit account to the guest's
front-office account (folio)" (https://en.wikipedia.org/wiki/City_ledger). So: **Guest Ledger** = a
new asset control account, **City Ledger** = the existing AR control (`CustomerInvoice.ar_account_id`),
**Advance Deposits** = liability, in neither. `fin_journal_lines` already carries
`partner_type` + `partner_id` (`backend/app/modules/finance/models/journal.py:155-157`), so the
guest-ledger control reconciles to folios line-by-line with **no new column**. The checkout transfer
is what makes dunning work: a direct-bill folio settles by Dr AR control / Cr Guest Ledger,
materialised as a real `CustomerInvoice` so `ar_aging` and `dunning` pick it up; a cash/card folio
settles to bank and never touches AR. The first draft collapsed these two materially different
outcomes into one.

**(2) Business date — it is not a clock.** Oracle is explicit: "As OPERA has its own system date, it
is not automatically changed at midnight but after finishing the End of Day sequence. Therefore, it
is possible to run the End of Day sequence the next morning." It is per-property, several business
dates can be open at once, and "you must close them in chronological order"
(https://docs.oracle.com/en/industries/hospitality/opera-cloud/24.1/ocsuh/t_toolbox_managing_business_date.htm).
This kills any design deriving it from `datetime.now()`.

Atlas's fiscal period is a different kind of object and the two are not in competition:
`fin_fiscal_periods` is a `[start_date, end_date]` range with OPEN/CLOSED
(`backend/app/modules/finance/models/accounts.py:132-167`), resolved from `posting_date` by
`find_period_for_date` (`backend/app/modules/finance/queries/periods.py:23-35`), enforced at
`backend/app/modules/finance/service/journal.py:199-206` and backstopped by trigger
`trg_fin_journal_entries_period_open` → `ATLAS_PERIOD_CLOSED`
(`backend/alembic/versions/0009_finance_journal.py:19`, mapped to 422 at
`backend/app/core/exceptions.py:107`). **Answer: the business date is the *source* of `posting_date`;
the fiscal period is the *authorisation window* that must contain it.** A room-night posted at 3am
carries `posting_date` = the business date being closed. Both govern, at different layers — and
`posting_date` is a required caller-supplied field (`backend/app/modules/finance/schemas.py:180`), so
Atlas never derives it from a clock for journals.

One new table: `hsp_business_dates`, UNIQUE(tenant_id, business_date), `status OPEN|AUDITED`,
`journal_entry_id`, AuditMixin — simultaneously the current-business-date answer, the DB-level
monotonicity backstop (cannot roll backwards or skip a day), and the night-audit run record, exactly
the `fin_depreciation_runs` shape. One table doing three jobs beats an `adm_tenant_settings` KV entry
that has neither constraint nor run record.

**The month-end boundary is the real hazard, and the existing close guard does not catch it.** Night
audit for Jan 31 run on the morning of Feb 1 (entirely normal per Oracle) posts into January.
`assert_period_closable` (`backend/app/modules/finance/service/periods.py:197-209`) refuses a close
only when DRAFT journal entries are dated inside the period — a night audit that simply never ran
leaves **no** draft, so January closes cleanly and the catch-up run then trips `ATLAS_PERIOD_CLOSED`
and rolls the whole night back. Fix: extend `assert_period_closable` to refuse closing a fiscal
period containing an unaudited business date.

**(3) Night audit — manually triggered in v1.** `core/jobs.py` has **no scheduler**:
`InProcessJobScheduler.schedule` (`backend/app/core/jobs.py:213-225`) creates an asyncio task on the
currently-running request's event loop, and `submit_job` is only ever reached from an HTTP handler.
There is no cron, no timer, no periodic tick anywhere. Combined with the absent machine credential,
an unattended 3am run has **no trigger path today** — a cron would have to hold a human's password
and mint a 15-minute D-008 access token. Q1's credential unblocks this and the website API with one
mechanism.

What `core/jobs.py` *does* already give is the most important property: **all-or-nothing**.
`_run_handler` (`:277-312`) marks RUNNING in its own commit, then runs the handler inside
`run_in_uow` with COMPLETED set in the **same** uow, and on any exception commits only FAILED. A
half-posted night audit cannot exist.

**D-013 alone is not enough — it guards the transport, not the data.** `core_idempotency_keys` is PK
`(tenant_id, endpoint, key)` with reserve-then-capture (`backend/app/core/idempotency.py:5-30`) and no
purge, so a business-date-keyed key *is* a permanent dedup — but only for callers that reuse the same
key. A cron generating a fresh uuid4 per attempt re-executes in full. `core_jobs` offers no help
either: no unique index (`jobs.py:97-106`), deliberately not audited (`:42-45`). **The correct
data-level pattern is already in the repo:** `run_depreciation`'s backbone is
`UNIQUE(tenant_id, asset_id, fiscal_period_id)` (`uq_fin_depreciation_entries_asset_period`,
`backend/app/modules/finance/models/assets.py`), plus a set-based NOT EXISTS anti-join
(`backend/app/modules/finance/service/depreciation.py:98-109`), plus a no-op re-run returning the
existing POSTED run (`:179-191`), plus **one grouped journal entry** rather than one per asset
(`:151-176`). Night audit maps one-for-one: a folio line keyed
`UNIQUE(tenant_id, reservation_id, business_date, charge_type=ROOM_NIGHT)` makes a re-run pick up
exactly what was missed and makes two concurrent runs collide at the index. A `UniqueConstraint` is
portable across both engines, so **D-003 is satisfied with no Postgres-only guard** — unlike the
exclusion constraint Q3 rejected.

It must be **set-based with a bounded event count**: `MAX_DISPATCHES_PER_UOW = 50`
(`backend/app/core/events.py:61`) means a night audit publishing one event per checked-in reservation
dies above 50 occupied rooms and loses the entire night. One or two events for the whole run.

**Cost.** One finance service change + an Alembic migration on `fin_customer_receipts`, one
`hsp_business_dates` table, one night-audit job handler, one added assertion in
`assert_period_closable`. **The deposit change is the expensive one politically** — it touches a
shipped, tested financial path that sales order-to-cash
(`backend/app/modules/finance/handlers/order_to_cash.py`) and the seed data both drive, so it needs
regression coverage on the existing invoice→receipt flow, not just new tests. **Not solved, named as
scope:** an unattended 3am night audit is impossible in v1; and a **pre-existing wrong-day defect
independent of hospitality** stays in place — `date.today()` is the document-date default at ~20 call
sites (`backend/app/modules/sales/service/orders.py:208`, `deliveries.py:184`, `billing.py:217`,
`quotes.py:151`, `returns.py:171`, `backend/app/modules/quality/service.py:265`,
`backend/app/modules/manufacturing/mrp_router.py:81`,
`backend/app/modules/procurement/service/conversions.py:158,224`, `backend/app/core/numbering.py:112`)
and `Tenant` carries no timezone (`backend/app/modules/admin/models.py:19-32`), so at a UTC+4 property
a charge entered at 03:00 local is stamped the **previous** calendar day. Hospitality merely makes it
visible. Fixing it properly is a cross-module change (~20 sites plus a tenant timezone column) and
should be its own issue, not smuggled into this vertical. **Perf:** per-folio Dr lines mean ~60
journal lines/night for a 60-room property, ~22k/year — trivial for Postgres and worth it for
control-account-to-sub-ledger reconciliation.

## Q6 — The website read path, caching, and failure modes. **Core change: no.**

**Answer: two read resources with different cache policies on the existing `Page` envelope, plus one
idempotent write. No new core code.**

Conditional GET is already core infrastructure and is the highest-leverage mechanism here.
`backend/app/core/conditional.py:65-93` computes a weak collection ETag from **one** aggregate,
tenant-scoped automatically by the D-007 listener (`:20-27`), with cursor+limit+filters folded in
(`:146-155`) so a 304 can only ever serve the identical page request; `:123-143` returns 304
**without awaiting the page builder**, so a revalidation costs one query and no body. The
menu-structure endpoint effectively exists already: `backend/app/modules/inventory/router.py:221-246`
is `GET /items?item_type=&category_id=&is_active=` returning ETag'd `Page[ItemRead]`.

**Toast made the same structural split**, which is the strongest external validation: `GET /menus`
returns fully resolved JSON for all menus in one call, no pagination
(https://doc.toasttab.com/doc/devguide/apiComparingTheMenusApiWithTheConfigurationApiAndMenuJsonExport_V2.html),
rate-limited to 1 req/s per location, while a **separate** stock API carries the fast-changing
three-state availability (https://doc.toasttab.com/doc/devguide/apiUsingTheStockApi.html). Square
splits Catalog from Inventory counts with distinct webhooks
(https://developer.squareup.com/docs/inventory-api/webhooks); Lightspeed K-Series exposes item
availability per location separately from menu items
(https://api-docs.lsk.lightspeedhq.com/group/endpoint-items). Toast also **forbids** the naive
fetch-per-page-view: "You should not make a call to the /menus endpoint for a restaurant unless you
have used one of these methods to determine that the menu data you have for that restaurant is
stale"
(https://doc.toasttab.com/doc/devguide/apiDeterminingIfYourMenuJsonIsOutdated_V2.html).

**Atlas cannot push invalidation.** D-011's bus is in-process and synchronous and there is no
outbound HTTP anywhere in app code. So the Toast/Square webhook pattern is unavailable and the
website **pulls with a validator**. Fine at this scale, but it means the staleness windows below are
the contract, not a fallback.

| Endpoint | Shape | Cache policy |
|---|---|---|
| `GET /api/v1/hospitality/menu` | `Page[MenuItemRead]` — item_id, code, name, description, category, price (decimal **string**, D-015), prep_station | ETag over `Item`; `Cache-Control: private, max-age=60, stale-while-revalidate=600, stale-if-error=86400` |
| `GET /api/v1/hospitality/menu/availability` | `Page[ItemAvailabilityRead]` — item_id, state, quantity — plus a top-level `as_of` | ETag over `hsp_menu_availability`; `Cache-Control: no-cache, must-revalidate, stale-if-error=300` |

Cursor pagination (D-014, `MAX_LIMIT = 200` at `backend/app/core/pagination.py:49`) fits a menu only
incidentally — a boutique menu is one page, so the cursor is inert. What does **not** fit is
paginating availability: two pages are two snapshots at different instants. Keep the `Page` envelope
(no new wire shape, no PERFORMANCE §3 deviation) but **contract that availability must fit one page**
and carry `as_of`. Documented ceiling: 200 orderable items in v1.

**Staleness by field class.** Menu structure and price: 60 s fresh, 10 min stale-while-revalidate —
safe *only because* the order response is authoritative and the website must display the total Atlas
returns before payment, never the total it computed from cached prices. Availability/86: 10 s.
Anything Atlas has not confirmed: zero.

**When Atlas is unreachable — fail to last-known state, never to empty.** Menu: serve the last
successfully fetched menu (`stale-if-error` covers browser/CDN; the website's server also persists
it) — a restaurant with no ERP still has a menu. Availability: **fail open** for items last seen
AVAILABLE or LIMITED, and **keep** items last seen UNAVAILABLE unavailable — showing an available
dish that is out is a normal restaurant apology, showing an empty menu is lost revenue. Orders: the
website queues to its own durable store and replays. This is exactly Toast's shipped offline mode,
which keeps taking orders and printing tickets off the last synced menu and submits card
authorizations once back online
(https://support.toasttab.com/en/article/Using-Toast-in-Offline-Mode).

**Write path — one endpoint, existing mechanism.** `POST /api/v1/hospitality/order-tickets` guarded
by `Idempotent("hospitality.order_ticket.create")` (`backend/app/core/idempotency.py:270`). The
website generates **one** UUID key when the guest presses submit, stores it with the queued order,
and reuses it for every retry forever. `backend/app/core/idempotency.py:270-357` already gives the
full contract: same key + same body replays the stored response with `Idempotency-Replayed: true`
(`:234-236`); same key + different body → 422 `idempotency.key_reuse` (`:237-240`); concurrent
duplicate → 409 `idempotency.in_progress` (`:242-245`). This matches Square's retry contract
(https://developer.squareup.com/docs/build-basics/common-api-patterns/idempotency).

**The 409 is the trap** a retrying website will fall into and it must be in the published client
contract: treat 409 as *retry later with the same key*, never as a failure and never as a reason to
mint a new key — minting a new key on 409 is exactly how you get the duplicate order the mechanism
exists to prevent.

Price needs one small addition: `backend/app/modules/sales/service/price_resolution.py:73-118`
requires `customer_id` and returns `_NO_MATCH` for an unknown customer (`:96-99`); a GENERAL price
list (`:105-107`) is matched only inside that customer-bound path. A customer-less
`resolve_list_price(item_id, on_date, currency)` variant is needed — 2 queries for one item, still 2
batched over N. Module code in sales, no core change.

**Query budget.** Menu read: auth user SELECT (`backend/app/core/deps.py:85-87`) + RBAC (memoized
60 s, `backend/app/core/rbac.py:105`) + 1 ETag aggregate + 1 page query. Availability read: auth + 1
ETag + 1 page. Both inside PERFORMANCE §3; a 304 drops the page query. Ship a query-count assertion on
both per PERFORMANCE §6.

**Cost.** No new core code — conditional GET (D-035), keyset pagination (D-014), gzip
(`backend/app/main.py:198`), the error envelope and D-013 already do this job. **Correctness traded,
deliberately:** availability is eventually consistent with a 10 s window and fails open, so a guest
can order an 86'd dish — mitigated by the staff-acknowledgment gate, not eliminated; and a displayed
price can be up to 10 minutes stale, so the guest can see one price and be charged the authoritative
one, mitigated by a **contract obligation on a system Atlas does not control**, which is the weakest
link in the design. **Scope this pulls in:** a `Cache-Control` convention that exists nowhere in the
codebase today (grep returns nothing; only ETag is set); a published client contract document (retry
semantics, 409 handling, staleness windows, fail-open rules) maintained alongside the endpoints; and
an **idempotency-key retention job**, because a public order channel makes `core_idempotency_keys`
grow forever with full response bodies stored (`idempotency.py:99`) and nothing purges them — a
`register_job("core.idempotency_purge")` on the existing framework is the fix. **Ruled out:** reusing
ATP for menu availability, and any design where the guest browser calls Atlas directly.

---

## What this actually costs the core — the corrected claim

The first draft said plainly that this vertical requires **no core-platform changes**. That was true
for a guest-facing flow Atlas hosted itself. It is **not** true once the property's own website is an
external API client. The corrected claim:

> Hospitality requires **exactly one core-platform addition — a machine credential** — plus one
> change to the shipped **finance** module, plus four pre-existing core gaps it makes urgent. Every
> other question resolved to module code on mechanisms Atlas already ships.

| Question | Core change? | Where the work lands |
|---|---|---|
| Q1 machine credential | **Yes** | `core/models.py`, `core/deps.py`, `core/auth.py`, one migration, `admin` endpoints, `nginx.conf` |
| Q2 menu availability | No | new hospitality table + service; one batched inventory query |
| Q3 overbooking | No | two hospitality counter tables; `with_for_update` + portable CHECK |
| Q4 ingredient depletion | No | hospitality job handler on existing `core/jobs.py`; a write-path perf test |
| Q5 folio / deposits / business date | No — but **yes to shipped finance** | `finance/service/customer_receipts.py` + migration; `assert_period_closable`; one hospitality table |
| Q6 website read path | No | two hospitality endpoints; a customer-less price resolver in sales |

**Four pre-existing core gaps this vertical makes urgent** (none of them created by hospitality, all
of them load-bearing once it ships):

1. **No stale-PENDING job sweeper.** A job whose PENDING row committed but whose runner died stays
   PENDING forever, silently. Tolerable for a stock count; not for a depletion with a GL effect.
2. **No idempotency-key retention.** `core_idempotency_keys` stores full response bodies forever
   (`backend/app/core/idempotency.py:99`); a public order channel makes that unbounded.
3. **No `core_refresh_sessions` purge.** Only matters if the service-user fallback is used, and it is
   one of the three reasons not to.
4. **No rate limiting anywhere**, for humans either. Q1 puts it in nginx rather than Python.

Also worth recording: `docs/research/s4hana-parity.md:247` already logs "Released APIs and
event-based integration" as an explicit v1 scope cut, so the machine credential has a **recorded
home** rather than being unplanned scope.

## Reuse map

| Need | Atlas mechanism reused | New code |
|---|---|---|
| Recipe costing | Manufacturing BOM engine | None — data only |
| Ingredient depletion | Inventory stock moves + `core/jobs.py` | Job handler, module-level (Q4) |
| Menu availability / 86 | — | One small hospitality table + service (Q2) |
| Booking concurrency | `with_for_update` + portable CHECK (D-020/D-036) | Two counter tables, module-level (Q3) |
| Advance deposits | `CustomerReceipt` clearing engine | Widened in **finance**, not duplicated (Q5) |
| Business date / night audit | `run_depreciation` shape + `core/jobs.py` | One table + one handler (Q5) |
| Website read path | Conditional GET (D-035), keyset pagination (D-014), gzip | Two endpoints (Q6) |
| Website write path | D-013 idempotency | None — mechanism unchanged (Q6) |
| Website authentication | — | **`ApiKey` in core (Q1)** |
| F&B / housekeeping supply purchasing | Inventory + Procurement | None |
| Staff scheduling, payroll | HR | None |
| Journal posting, tax, COA | Finance | None |
| Corporate/group accounts | CRM (optional) | None |
| Tenancy, audit, event bus, doc-flow, numbering | core | None |

## Explicitly out of scope for v1

| Capability | Reason |
|---|---|
| OTA/channel-manager two-way sync (Booking.com, Expedia, Airbnb) | Its own category even among incumbents; also outside what the Q3 counter design tolerates as a gate |
| Algorithmic/dynamic room pricing | Rate plans are manual in v1 |
| Guest loyalty/rewards programs | Differentiator, not baseline |
| Third-party delivery-platform order injection (DoorDash/Uber Eats/Grubhub) | Separate integration surface |
| Real KDS hardware/terminal client | v1 ships a status view, not a kitchen-floor device app |
| Online payment on hotel folio/booking deposits | Scoped to restaurant settlement only this pass |
| Multi-property/portfolio-level reporting | Single-tenant-per-property model, matching Atlas's existing tenant model |
| Unattended (scheduled) night audit | No scheduler exists in `core/jobs.py`; v1 is a human action, which is also what Opera's own prerequisites imply |
| Modifier-level 86 | Modifiers are not modeled in Atlas at all |
| Day-part / shift menus ("brunch ends at 11") | `available_until` only half-covers it; a scheduling concern |
| Expiring booking holds ("hold this slot 10 minutes while the guest enters card details") | Not scoped or costed; the most likely thing to change the Q3 table shapes later |
| OAuth2 client-credentials | Buys a delegation model Atlas has no third party to delegate to; add it the day Atlas has external developers |
| Tenant timezone / the `date.today()` document-date defect | Real, pre-existing, ~20 call sites plus a schema column — its own issue, not smuggled in here |
| Any AI feature (concierge, forecasting, etc.) | Not evaluated in this pass |

## Open questions — still genuinely unresolved

1. **Where does the depletion transaction reach the availability row?** Q2's countdown-decrement
   assumes the order-ticket transaction can touch `hsp_menu_availability`. Q4 moves depletion to a
   background job fired at `SENT_TO_KITCHEN`. Those are compatible — the countdown is a different
   write from the goods issue — but nobody has traced the exact call path, and if ordering posts
   through a path that cannot reach the row, the design needs revisiting.
2. **Expiring holds.** Every real booking engine holds a slot while the guest enters payment details.
   That is a separate design layered on Q3's counter and it is the single most likely thing to change
   those table shapes.
3. **Is a manually-triggered night audit acceptable to operators?** Argued from Opera's documented
   prerequisites and its explicit support for running End of Day the next morning, but it is a
   product judgement, and Mews/Cloudbeds/RoomRaccoon behaviour was not re-derived.
4. **Does the finance deposit change break anything downstream?** It touches a shipped path driven by
   order-to-cash and the seed data. The D-021 statement projections' behaviour with an unapplied
   receipt line is untested.
5. **Is the ≤3-query fold in Q1 actually achievable?** Folding the `ApiKey` join into the existing
   user load is a design assertion about SQLAlchemy lazy-load behaviour, not a measured result — and
   the budget has no slack left if it fails.
6. **What does `Item.is_active` becoming enforced break?** Q2 documents that it is filter-only and
   nothing enforces it. Making it enforced is out of scope here, but the finding is a latent
   correctness issue for every vertical, not just this one.
7. **Does any existing endpoint already approach `MAX_DISPATCHES_PER_UOW = 50`?** A large multi-line
   delivery or goods receipt might. Not checked; if one does, that is a latent pre-existing bug worth
   its own issue.

## Unverified — carried forward from the research, not quietly dropped

Every claim below was flagged by the researcher who made it. They are recorded here rather than
laundered into the body text.

**Q1 (machine credential).** The test suite was not run and mounted routes were not exhaustively
enumerated to confirm all are guarded — the "only request-auth decode site" claim rests on
`deps.py:71` plus grep. That folding the `ApiKey` join keeps the query count at one is a design
assertion, not a measurement. The nginx `limit_req` sizing is an industry anchor from Toast and
Cloudbeds docs, not a measurement against PERFORMANCE.md's 4 vCPU target. Whether adding a fifth
`system_context()` site would actually break the D-007 grep gate (`tenancy.py:78-79`) was designed
around rather than tested. The Mews auth page does **not** document token rotation, revocation or
scopes — the Mews claims cover only the ClientToken/AccessToken/property-identification model that
page states. Toast's scope list came from the read-only standard tier; write-scope naming for partner
tier is unverified.

**Q2 (availability).** No test suite run and no SQLAlchemy statement counter instrumented — every
query count (3 per `atp_check`, ~1,080 for a 60-item menu) is read off the code. The ETag-staleness
failure is reasoned from `conditional.py:83` aggregating only over the passed model; no test
reproduces a stale 304 on a sold-out item. The 60-items × 6-components menu shape is an assumption,
not a figure from any source. Vendor *behaviour* was verified from public docs only — "they store it"
is inferred from documented behaviour (persistent status, auto-reset, snooze durations), not from any
schema. Lightspeed evidence is K-Series only; whether L-Series ingredient depletion auto-blocks a
product is not stated anywhere found. "No scheduler exists" is a grep result over `backend/app`,
`pyproject.toml`, `docker-compose.prod.yml` and the Makefile — a systemd timer or external cron would
not appear. **The frontend was not read at all**; if any menu or availability UI already exists there,
it is unaccounted for.

**Q3 (overbooking).** No code run, no benchmark. All latency, lock-hold and contention claims are
reasoning from PERFORMANCE.md §5 and worker counts; "milliseconds of contention at 50 concurrent
users" is an inference, not a number. That SQLAlchemy's SQLite dialect silently *omits* `FOR UPDATE`
rather than erroring is asserted repeatedly by the codebase itself and the shared pg/SQLite test
passes on both engines — strong evidence, but the dialect source was not read. Whether a portable
two-column CHECK behaves identically under D-015's SQLite micro-unit encoding was not verified;
these would be plain integer counts, not MoneyType/QuantityType, so it should not apply, but the
column type was not settled. The ascending-order deadlock argument is carried across from D-036's
ascending-bin-id rule by analogy, not demonstrated. The OpenTable flow-controls page was not read
directly (the fetch returned a JS shell); the Resy and Oracle quotations came through search
summaries. DECISIONS.md was not read in full — D-001 to D-015 in full, D-020/D-036/D-037/D-044/D-045
by grep — so a later decision bearing on concurrency may be unsurfaced.

**Q4 (depletion).** All statement counts were measured on **SQLite** via the repo's own
`query_counter`; identical counts on Postgres are expected (same ORM path) but unconfirmed. The
690 ms wall for 24 lines is SQLite on a Mac, not the 4 vCPU Postgres target — the 0.5-1.5 s estimate
for a real settlement is inference. That `core_number_sequences` row locks are held until COMMIT is
standard Postgres behaviour inferred from code structure; no concurrent-settlement test was run, so
the tenant-wide serialization claim is reasoned, not observed. The verified ceiling is 50 commit / 51
raise measured by creating moves directly; "49 ingredient lines" is arithmetic on the dispatch loop.
Toast's actual depletion timing (at tender vs on a schedule) is **not publicly documented**; the
"near-real-time, not in-transaction" claim rests on a single source, the US Tech Automations case
study. The "roughly halves" saving from component aggregation is an estimate, not a benchmark.

**Q5 (folio / deposits / business date).** **Code was read; nothing was run** — no test, no migration,
no query executed. The `_require_account` and `credit_notes.py:160` conclusions in particular deserve
one runnable check before anyone builds on them. **USALI itself is paywalled and was not read**
(hftp.org returned 403). Everything asserted about USALI comes from secondary sources: the AHLA press
release confirming the 12th Revised Edition (adoption 1 Jan 2026,
https://www.ahla.com/news/hftp-ahla-and-gfc-unveil-groundbreaking-12th-revised-edition-uniform-system-accounts-lodging),
the Wikipedia city-ledger article, and trade write-ups. **The proposed COA account names are
unconfirmed against the standard's own text** — someone should buy the book before the COA is called
USALI-compliant. End-to-end behaviour of `create_customer_invoice` with a LIABILITY-typed line account
was not tested (only that `_require_account` ignores `AccountType`); whether D-021 statement
projections would mis-classify such a line is untested — the option was ruled out on release-path
grounds instead, which is the stronger argument anyway. The `uq_fin_depreciation_entries_asset_period`
constraint was read via a range dump, so no line number is cited. "`core_idempotency_keys` is never
purged" is a negative grep result; Alembic migrations and ops tooling were not audited for an external
cleanup. PERFORMANCE.md was not read directly — the ≤3-query and 50-user figures come from the brief
and from docstring references inside finance and jobs.

**Q6 (read path).** Query counts and latencies are read from source; the app, the perf suite and
EXPLAIN were not run. That toggling `Item.is_active` writes an audit row is inferred from AuditMixin
on `Item` plus D-010's before-flush diffing, not traced through the listener. The 200-orderable-item
ceiling is an assumption made so one page equals one snapshot; no source verified it, and a tenant
with a large menu plus modifiers could exceed it. Lightspeed's separate availability retrieval is from
search-result text plus a page title — the online-ordering features page returned 403. Toast's stock
API doc gives **no** polling-frequency or rate-limit guidance (verified absent), so the 10 s
availability window is a recommendation, not a published number. Square's idempotency-key retention
period is likewise not stated in its own docs, so there is no external benchmark for how long
`core_idempotency_keys` rows should be kept. `httpx` appears in `backend/pyproject.toml:20` but no
`import httpx` exists in `backend/app` — test-only is an inference. It was not verified that
GZipMiddleware leaves a 304 body-less response untouched, nor that `conditional_response`'s 304
survives the middleware ordering at `main.py:189-201`. Whether `collection_etag`'s COUNT/MAX aggregate
over `inv_items` is index-served on a large tenant is unverified — no EXPLAIN was run, and PERFORMANCE
§1 asks for one on hot paths. The D-008 multi-process refresh-token collision (two website containers
revoking each other via family revocation outside the 10 s grace) is reasoned from the D-008 text, not
reproduced.

## Status

**Proposal only.** Not scheduled, not part of the v1 build order, no PLAN.md/STRUCTURE.md/
GITHUB-WORKFLOW.md changes accompany this doc. A prior session scoped a different candidate
capability (field-force tracking) and let it drift into a ticked PLAN.md phase and actual scaffold
code before it was fully reverted as unplanned scope (PR #143, 2026-07-20) — this doc deliberately
stays on the safe side of that line, the same way
[field-force-tracking-market-scan.md](field-force-tracking-market-scan.md) did. The August 2026
revision deepened the design and added measurements; it did not change that status. If hospitality is
pursued, it needs its own explicit go-ahead and a proper implementation plan before any PLAN.md
entry or code lands — and the Q1 machine credential in particular is a core change that would need
its own DECISIONS.md entry and its own review, independent of whether hospitality ships.
