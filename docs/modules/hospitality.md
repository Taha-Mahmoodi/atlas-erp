# Hospitality (`backend/app/modules/hospitality/`)

Hospitality is the **fourteenth module** and the top of the dependency order (STRUCTURE §5) —
nothing imports it. Phase 19 ships the **restaurant** half: a menu whose availability is *stored*
state, an order **ticket** document that fires to the kitchen, ingredient depletion that runs off
the sale, and the read/write API a property's **own website** calls over the Phase 18 machine
credential (**D-069**). **Phase 21** adds the other half of the same loop: **table reservations**,
gated by a per-slot pacing counter (§7).

Spec: [`docs/research/hospitality-industry-plan.md`](../research/hospitality-industry-plan.md) **Q2**
(availability), **Q3** (pacing), **Q4** (depletion), **Q6** (the website read path). Plans:
[`phase-19-restaurant-ordering-plan.md`](../research/phase-19-restaurant-ordering-plan.md),
[`phase-21-table-reservations-plan.md`](../research/phase-21-table-reservations-plan.md).
The decisions this module records are **D-072** (backgrounded depletion, restaurant-scoped),
**D-073** (why the menu read has no ETag), **D-076** (pacing by slot counter; a missing counter row
means default capacity) and **D-077** (no TENTATIVE state; the counter matrix) in
[DECISIONS.md](../../DECISIONS.md).

## Status

**PLAN 19.1–19.5 and 21.1–21.4 shipped.** Rooms, folio, deposits, the business date and the
room-charge bridge are **Phase 20** and nothing here anticipates them beyond publishing
`RestaurantOrderSettled`, which has no subscriber yet.

Deliberately **not** in this phase: modifier-level 86 (Atlas has no modifier model), day-part menus
beyond what `available_until` half-covers, third-party delivery injection, KDS hardware, card
payment, split checks, and tax on a check (see *Known limits*).

| File | Concern | Key decision |
|---|---|---|
| `constants.py` | `AvailabilityState` / `AvailabilitySource` / `OrderTicketStatus` + `TICKET_FLOW`, the five permission keys (registered at import), the doc type / number sequence / event keys, `DEPLETE_MAX_COMPONENTS_PER_JOB` | D-009, D-012, D-072 |
| `models.py` | `MenuAvailability` (`hsp_menu_availability`), `OrderTicket` (`hsp_order_tickets`), `OrderTicketLine` (`hsp_order_ticket_lines`) — flat, under the 600-line split rule | D-007, D-015, D-029 |
| `schemas.py` | staff shapes first, then the website surface; the website request shapes set `extra="forbid"` | D-014, D-015 |
| `events.py` | `RestaurantOrderFired`, `RestaurantOrderSettled`, `TicketIngredientsConsumed` | D-011 |
| `handlers.py` | `submit_ticket_depletion` — subscribes to `RestaurantOrderFired`, explodes the recipe and submits the depletion job(s) in the fire's own transaction | D-011, D-072 |
| `service/availability.py` | `set_availability`, `clear_86`, `decrement_remaining(_many)`, `availability_for_items`, `resolve`, `lapsed_count_expr` | Q2, D-073 |
| `service/tickets.py` | `create_ticket`, `add_lines`, `fire_ticket`, `advance_ticket`, `settle_ticket`, reads | D-012, D-013 |
| `service/depletion.py` | `aggregate_components`, `job_payloads`, `deplete_ticket`, the registered `hospitality.deplete_ticket` job, `remember_job`/`take_depletion_jobs` | D-072 |
| `queries.py` | `at_risk_menu_items`, `list_tickets`, `list_availability_overrides` — the module's read surface (nothing imports it yet; hospitality is the top of the order) | STRUCTURE §5, PERFORMANCE §2 |
| `router.py` | staff REST under `/api/v1/hospitality` | D-009, D-013, D-014 |
| `website_router.py` | the machine-credential surface: menu, 86 board, order | D-069, D-073 |

Migrations: `0047_hospitality_menu_availability`, `0048_hospitality_order_tickets`. Industry
template: [`industry-templates/hospitality.yaml`](../../industry-templates/hospitality.yaml), the
sixth (Guest/Group Account terminology, a Guest Ledger + F&B revenue COA split, FIFO costing,
`TKT-{year}-{000001}` ticket numbering).

## 1. Availability is STORED, never derived (Q2)

`hsp_menu_availability` holds **one row per item the kitchen has said something about, and nothing
else**. An item with no row reads AVAILABLE — absence of an override is not unavailability — and
`clear_86` **deletes** the row rather than storing `AVAILABLE`, so there is exactly one spelling of
each answer.

| State | Meaning |
|---|---|
| `AVAILABLE` | Sellable. The default, and normally *not* stored. |
| `LIMITED` | Sellable with a countdown. `remaining_qty` is the portions left; firing burns it and the row flips to `EIGHTY_SIXED` (`source = AUTO`) at zero. Requires a positive count (`hospitality.countdown_required`). |
| `EIGHTY_SIXED` | Off the menu. `fire_ticket` refuses it and the website must not offer it. |

`available_until` time-boxes any of them (Lightspeed's "snooze"). **Expiry is lazy and evaluated in
Python**, in one helper (`availability.resolve`) that both the read path and the writes use —
aiosqlite round-trips `DateTime(timezone=True)` naive, so a SQL predicate would be a second, drifting
copy of the rule (D-003, the `core/deps.py` credential-expiry precedent).

### Why not derive it from stock

`atp_check` is 3 queries per item — **~1,080 for a 60-item menu** — and its
`on_hand − committed + on_order` formula lets an open PO make tonight's dish read available.
Decisively, `collection_etag` is `COUNT(id), MAX(updated_at)`: selling the last portion moves no
`Item.updated_at`, so a derived answer **never invalidates** and the website receives a 304
asserting a sold-out dish is available. Reading a whole 60-item menu's stored availability is
**exactly 1 statement**. `Item.is_active` is not the home either — it is filter-only (`item_exists`
never reads it), it hides the item from purchasing and costing too, and `Item` carries `AuditMixin`,
so a shift's worth of 86-ing would be a shift's worth of audit rows.

The table therefore carries **no `AuditMixin`** on purpose; `source` (MANUAL / AUTO) is the audit
substitute, recording whether a human or the countdown wrote the row.

### The derived list that *does* exist, and is advisory

`GET /menu/at-risk` explodes every active default BOM against on-hand and reports the dishes the
storeroom covers `threshold` portions or fewer of, worst first. It is **staff-only and takes no
action** — a human reads it and 86s, which writes the stored row the guest path actually serves. It
reads **on-hand only** (a kitchen cannot cook an open PO) and over-reports on shared ingredients.
Cost: **3 statements flat**, measured identical at 2 and 22 dishes, and unchanged by recipe size or
BOM depth. Ceiling, stated: the scan covers the tenant's whole active-default-BOM set, because Atlas
ships no menu-membership entity; `limit` bounds the response, not the scan.

## 2. The order ticket

```
OPEN ──fire──> SENT_TO_KITCHEN ──> IN_PREP ──> READY ──> SERVED ──> SETTLED
 │                    │                                              │
 └──cancel──> CANCELLED (terminal; OPEN only, reason required — D-080)
 │                    │
 │ lines may be       │ event RestaurantOrderFired                   │ event RestaurantOrderSettled
 │ added ONLY here    │   └─> depletion job(s) submitted             │   (no subscriber until 20.6)
 │                    │        └─> TicketIngredientsConsumed
 │                    │             └─> inventory ISSUE moves + COGS
 │                    │                  ticket doc ─depleted_by→ each move doc (D-012)
```

Transitions are **strictly sequential** — next state only, never a skip. Forward-only would allow
`OPEN → SERVED`, and `SENT_TO_KITCHEN` is the single point at which ingredients are committed, so a
skip is revenue with no depletion. The cost is that a counter-service property ticks through
`IN_PREP`.

- `OrderTicket` is a **D-012 document**: it registers in `core_documents` and claims its gapless
  `TKT-` number **at creation** (the sales-order branch, not finance's number-at-post branch),
  because a ticket is referenceable by the kitchen and the guest the moment it opens.
- Lines carry **no `uom_id`** — quantity is always in the item's base UoM, which is also the basis a
  recipe BOM explodes against, so depletion needs no conversion.
- Tickets carry **no `currency_code`**: every check is in the tenant's functional currency (D-019),
  the ticket trades no FX and posts no journal of its own. The website order response labels the
  currency it resolved.
- **`CANCELLED` is reachable only from OPEN** (D-080, #206), with a required reason. A check opened
  on the wrong table has cooked nothing and moved no money, so closing it costs nothing — while
  leaving it OPEN forever is what makes the floor's live list unreadable. It is deliberately NOT a
  step in `TICKET_FLOW`: it is a branch, so the "index + 1" arithmetic the kanban and the status
  button share is untouched and nothing may follow it. Past the fire there is still **no void**: a
  comp or a walk-out on a cooked check is a money correction the Phase 20 folio owns.

Firing an 8-line ticket costs **10 statements**, and the count does not grow with the line count or
with countdown lines (`tests/perf/test_write_budgets.py`, `FIRED_TICKET_CEILING = 14`). It rises by
one statement per 40 distinct ingredients, because each depletion chunk is its own job row.

## 3. Depletion runs OFF the sale (Q4 / **D-072**)

`fire_ticket` publishes `RestaurantOrderFired`; `handlers.submit_ticket_depletion` explodes the
recipe **at fire time** (snapshotting it, so a chef editing a BOM mid-service cannot retroactively
change what an already-cooked ticket consumed) and submits one `hospitality.deplete_ticket` job per
40 distinct components, in the fire's own transaction. The route then schedules them **after** the
uow commits:

```python
await run_in_uow(session, work)
for job_id in depletion.take_depletion_jobs(session):
    schedule_job(job_id, factory)
```

Any future caller of `fire_ticket` must repeat that drain. Forgetting it loses only the
*scheduling*, never the job row — but core has no stale-PENDING sweeper, so the row would sit
forever.

**There is no synchronous branch.** Unlike the count-post threshold it otherwise mirrors, depletion
always backgrounds: Q4's phantom-stock-out argument applies to a one-line ticket exactly as it does
to a fifty-line one.

The job publishes `TicketIngredientsConsumed`; **inventory's** `issue_ticket_ingredients` handler
creates the ISSUE moves and the `depleted_by` docflow edge. Hospitality never calls inventory's
service — that is the same bus bridge sales' delivery and manufacturing's component issue use
(STRUCTURE §5). It is the only two-hop chain in Atlas whose hops are in *different* transactions.

**Aggregation, chunking and the dispatch wall.** A check's dishes sharing onion, oil and salt
collapses ~24 raw lines to ~12 distinct components. Backgrounding alone does not lift
`MAX_DISPATCHES_PER_UOW = 50` — the job runner executes its handler inside `run_in_uow` too — so the
aggregate is chunked at `DEPLETE_MAX_COMPONENTS_PER_JOB = 40`. Measured: the job's uow COMPLETES at
49 components and FAILS at 50 (one dispatch per ISSUE move for the finance COGS handler, plus one
for the consumed event). That margin rests on "one ISSUE move costs one dispatch", which nothing
enforces —
`tests/modules/hospitality/test_depletion_dispatch_ceiling.py::test_a_full_width_chunk_costs_one_dispatch_per_component_plus_one`
is the tripwire that fails the day another module subscribes to `StockValued` or
`JournalEntryPosted`.

**When depletion fails.** The guest is still served: the ticket fires, advances and settles, and the
failure is a FAILED `core_jobs` row. Verified against a partial stock-out, an unwired GL category, a
closed fiscal period, a DRAFT BOM, and a dish with no BOM and no stock. Because `core/jobs.py` keeps
only `str(exc)`, the message is deliberately self-describing:

```
Ticket TKT-2026-000001 (<uuid>) could not deplete item <uuid> from bin <uuid>: Insufficient stock to issue from this bin
```

A property finds it at `GET /api/v1/jobs?status=FAILED` — **polling, not push**. Read D-072 before
relying on that: the concession is only sound once FAILED-job alerting exists.

Two behaviours worth knowing: a dish with **no active BOM depletes itself** (a bottled beer is a
sellable item with no recipe, and reading "no BOM" as "nothing to deplete" would make its stock
silently never move) — so a dish whose BOM is still DRAFT fails loudly rather than silently. And the
source bin is derived as *the bin holding the most* of each item (`issue_bins_for_items`, one query
for the whole ticket), because a ticket has no warehouse concept; bin-level splits are not resolved.

## 3b. The menu's own structure (#212, **D-081**)

A dish's only grouping used to be its `ItemCategory`, and that entity decides how the dish is
VALUED — costing method, inventory/COGS/price-difference accounts. A menu is a different axis, and
it is **two** axes rather than one:

| | Shape | A dish has | Answers |
|---|---|---|---|
| **Sections** (`hsp_menu_sections`) | tree, max 3 deep | exactly one | "print the menu in the property's order" |
| **Tags** (`hsp_menu_item_tags`) | flat strings | any number | "show me everything vegan" |

Sections carry `sort_order`, so Desserts come last because the restaurant says so rather than
because D sorts after M. A dish with no placement is simply unplaced — it still sells.

Both live in **hospitality**, keyed on `item_id` as an opaque id (D-029). Inventory is untouched:
the item keeps its category and its GL wiring, and the reverse import stays forbidden
(STRUCTURE §5).

**Three rules the database cannot enforce**, so the service does:

- a section may not be moved inside its own branch (`hospitality.menu_section_cycle`) — both ends
  are valid rows in the right tenant, and the move would detach the branch;
- the tree stops at three levels (`hospitality.menu_section_too_deep`);
- a section still holding dishes or sub-sections is REFUSED, never cascaded
  (`hospitality.menu_section_not_empty`) — a cascade under a mis-click unplaces every dish under it
  and the rows it removes carry no way back.

**The structure is its own read.** `GET /menu` is budgeted at exactly three statements
(PERFORMANCE §2) and already spends them; `GET /menu/placements` carries the map in two more. That
split is the same cache argument §1 makes: structure, price and availability change on three
different clocks.

## 4. Endpoints

### Staff (`/api/v1/hospitality`, JWT or a staff-scoped key)

| Method | Path | Permission | Notes |
|---|---|---|---|
| GET | `/menu/at-risk` | `hospitality.menu.read` | advisory list, `threshold` + `limit`, worst first |
| PUT | `/menu/{item_id}/availability` | `hospitality.menu.manage` | 86, countdown, or time-box. Replaces the one stored answer, so no idempotency key |
| DELETE | `/menu/{item_id}/availability` | `hospitality.menu.manage` | 204; a no-op if never 86'd |
| POST | `/tickets` | `hospitality.ticket.manage` | 201, **idempotent** (`hospitality.order_ticket.create`) |
| GET | `/tickets` | `hospitality.ticket.read` | `Page[OrderTicketRead]`, filter by `status` / `opened_on` |
| GET | `/tickets/{id}` · `/tickets/{id}/lines` | `hospitality.ticket.read` | the KDS is a status-filtered query over these, not new infrastructure |
| POST | `/tickets/{id}/lines` | `hospitality.ticket.manage` | OPEN only (`hospitality.ticket_not_open`) |
| POST | `/tickets/{id}/fire` | `hospitality.ticket.manage` | **idempotent**; refuses an 86'd dish; burns countdowns; submits depletion |
| POST | `/tickets/{id}/advance` | `hospitality.ticket.manage` | IN_PREP / READY / SERVED only |
| GET | `/menu/sections` | `hospitality.menu.read` | the whole tree, each heading with its DIRECT dish count. Two statements |
| POST · PATCH · DELETE | `/menu/sections[/{id}]` | `hospitality.menu.manage` | add, rename/reorder/move, remove. Delete refuses a non-empty section |
| GET | `/menu/placements` | `hospitality.menu.read` | {item -> section, tags} for every placed or tagged dish |
| GET | `/menu/tags` | `hospitality.menu.read` | the tags actually in use — the picker's options, no master table (D-081) |
| PUT | `/menu/{item_id}/placement` | `hospitality.menu.manage` | section AND tags replaced together |
| POST | `/tickets/{id}/cancel` | `hospitality.ticket.manage` | OPEN only, `reason` required. Not `.settle`: nothing was cooked and no money moved |
| POST | `/tickets/{id}/settle` | `hospitality.ticket.settle` | its own key: settlement is the money moment |

`settle` is deliberately **not** idempotency-keyed — it creates no document, and the strictly
sequential lifecycle already answers a replay with `409 hospitality.ticket_transition_invalid`.

### Website (machine credential)

`GET /menu`, `GET /menu/availability`, `POST /orders` — the published contract, cache policies and
client rules are in [docs/api.md](../api.md#the-property-website-contract). The section tree and the
placement map (§3b) are read with the same `menu.read` scope, which is how a site renders the menu in
the property's own order.

The reference client is in this repo (**D-082**): `frontend/src/modules/hospitality/website/`, its own
Vite entry (`website.html`) served by its own nginx on its own port — `docker compose up` puts it on
<http://localhost:8080> for the seeded `hospitality` tenant. It exists on a separate origin for one
reason: a guest has no session, so the site authenticates as the PROPERTY, and a key in the browser
bundle is a key the public holds. `frontend/website-nginx.conf.template` attaches it at the edge —
the menu key on the four menu reads and the order write, the booking key on the grid read and the
booking write, one exact `location` each.

Two things the site does that any client of this API has to do, and neither is in the payloads:

- **A dish is an item with a PLACEMENT.** `GET /menu` unfiltered is every active item in the tenant,
  ingredients included; the site joins the placement map and shows only placed items, which is why it
  needs no `category_id` and never lists `ING-BEEF` next to the ribeye.
- **Absence from the 86 board means available.** The board carries only items the kitchen has spoken
  about. A client that treats a missing row as unknown empties a healthy menu the first time the
  board comes back empty.

### Error codes

| Code | HTTP | When |
|---|---|---|
| `hospitality.ticket_not_found` | 404 | unknown ticket in this tenant |
| `hospitality.ticket_transition_invalid` | 409 | not the next state in `TICKET_FLOW` |
| `hospitality.ticket_not_open` | 409 | adding lines, or cancelling, after the ticket fired |
| `hospitality.ticket_empty` | 422 | firing a ticket with no lines |
| `hospitality.no_lines` | 422 | an empty `lines` body |
| `hospitality.status_not_advanceable` | 422 | `/advance` asked for fire or settle |
| `hospitality.item_unavailable` | 422 | an 86'd dish, or a countdown burn larger than the count. `details.item_ids` plus `details.items`, the dish names the message also carries (#205) |
| `hospitality.item_not_found` | 422 | an item id that is not in this tenant. `details.item_ids` |
| `hospitality.item_not_priced` | 422 | no active GENERAL price list prices it today, or its only price is in another currency. `details.item_ids` |
| `hospitality.menu_section_not_found` | 404 | unknown section in this tenant |
| `hospitality.menu_section_cycle` | 422 | moving a section inside its own branch |
| `hospitality.menu_section_too_deep` | 422 | nesting past three levels |
| `hospitality.menu_section_not_empty` | 409 | deleting a section that still holds dishes or sub-sections. `details` carries both counts |
| `hospitality.menu_too_many_tags` | 422 | more than 12 tags on one dish |
| `hospitality.countdown_required` | 422 | `LIMITED` without a positive `remaining_qty` |
| `hospitality.component_out_of_stock` | 422 | recorded on a FAILED depletion job, never returned to a guest |

## 5. What Phase 19 added outside this module

Every one of these is a read seam or a core primitive, never a service import (STRUCTURE §5):

- `inventory/queries.py` — `existing_item_ids`, `issue_bins_for_items`, `on_hand_for_items`,
  `list_active_items` (all one statement, all batched).
- `inventory/handlers.py` — `issue_ticket_ingredients`, the `TicketIngredientsConsumed` subscriber.
- `manufacturing/queries.py` — `active_boms_for_items`, `components_for_boms`,
  `active_bom_requirements` (the whole-tenant one-level explosion the at-risk scan uses); `mrp.py`'s
  private copies were promoted rather than duplicated.
- `sales/queries.resolve_list_prices` — the customer-less D-043 rule (GENERAL lists only), one
  statement for a whole page of items.
- `core/money.py` — `quantize_quantity`, and `MONEY_SCALE` made public.
- `core/conditional.collection_etag` — the `extra_components` kwarg (D-073); empty by default, so
  every existing caller emits a byte-identical tag.
- `core/idempotency.py` — the D-071 fix: the request hash now covers `path?query` as well as the
  body, so a key spent on one document can no longer answer for another on an empty-body action
  route. Platform-wide, found here.

## 6. Known limits (v1, recorded not hidden)

1. **FAILED-job alerting does not exist.** A failed depletion is findable only by polling
   `GET /api/v1/jobs?status=FAILED`. D-072 says plainly that without alerting the backgrounding is
   strictly worse than a loud refusal.
2. **No stale-PENDING sweeper** anywhere in core. A job whose row committed but whose runner died
   stays PENDING forever.
3. **A check carries no tax.** `total_amount` is pre-tax, while the hospitality template seeds F&B
   and occupancy tax codes. Phase 19 takes no payment and posts no journal of its own, so nothing is
   mis-posted — but a property displaying the total as the amount due would understate it.
4. **No split checks and no payment.** Settlement flips a status; the folio and the payment provider
   are Phase 20.
5. **Price resolution assumes quantity 1.** A menu price with `min_quantity > 1` is invisible to
   both the menu read (`price: null`) and the order write (422) — consistent and fail-safe, but the
   dish is silently unsellable.
6. **A tracked ingredient gets no lot/serial selection** (that needs a FEFO policy), and the
   depletion move date is the UTC date of `fired_at`, so a service crossing midnight books late
   tickets on the next day. Phase 20's business date (Q5) is where that belongs.
7. **One 86 board fits one page by contract** (`MAX_LIMIT` = 200 overrides). Past that `next_cursor`
   is non-null and a client that ignores it reads a truncated board as "everything else is
   available".
8. **Line lists are unbounded**, as they are on every document-create endpoint in Atlas; the only
   bound is nginx's default 1 MB body. Measured harmless (2,000 lines aggregate to one component and
   one job) but it belongs in a platform-wide bound, not a hospitality-only one.
9. **Concurrency on SQLite.** `with_for_update` is a no-op there, so two simultaneous fires can both
   take the last portion of a countdown in tests; on PostgreSQL (the runtime, D-003) the row lock
   serialises and the loser is refused.
10. **File-size debt:** `inventory/queries.py` (527) and `inventory/handlers.py` (441) are over
    STRUCTURE §4's 400-line cap, as is `hospitality/service/tickets.py` (407). Split-only refactors
    belong in commits of their own (STRUCTURE §8.10) — tracked as tech debt, fixed before the next
    promotion per STRUCTURE §9.


## 7. Table reservations (Phase 21, spec Q3)

A guest books on the property's website, the booking is gated by a **pacing counter** that cannot
oversell a service, and staff see the book, seat the party onto an order ticket, and record
no-shows. **D-076** and **D-077** record the design; the two findings worth reading before changing
anything are below.

### The gate is a counter, not a table

`hsp_service_slots` holds ONE row per `(service_date, slot_start)` — 15 minutes, a constant — with
`covers_booked/covers_max` and `parties_booked/parties_max`. A booking locks that row
(`with_for_update`), is refused **pre-flight** with `422 hospitality.slot_full`, and the portable
`CHECK` pairs are the DB backstop. That is `inv_stock_quants` in shape (D-020/D-036). OpenTable and
Resy both cap covers per slot and leave the physical table a revisable soft assignment made at
seating, so **there is no table master and no floor plan**: `table_code` stays the free text the
check already carries, and the master earns its existence the day a floor-plan UI needs something
to reference.

Measured: **12 statements to take a booking**, flat between a party of 2 on an empty night and a
party of 8 on a night already holding 50 reservations
(`tests/perf/test_write_budgets.py::test_booking_a_table_is_flat_in_party_size_and_book_depth`).

### A missing slot row means DEFAULT capacity, not zero

This is the one place the shape **inverts** the stock-quant reading it otherwise copies. A quant
that does not exist means nothing on hand; a slot that does not exist means the whole room is free,
because a restaurant's capacity is standing config. So the defaults live in one per-tenant
`hsp_reservation_settings` row whose **absence is itself a complete answer** (the `MenuAvailability`
idiom), and a counter row is materialised **lazily by the first booking's upsert-on-lock**. Its
`covers_max`/`parties_max` are a snapshot taken at that moment: changing the settings does not reach
back into nights already being sold, and the per-slot override is how a manager reaches one that is.

`covers_max = 0` **closes** a slot — there is no separate flag, because a closed slot and a full one
answer a guest identically. An override **below** what is already booked is refused
(`hospitality.slot_override_below_booked`), never clamped.

**Times are UTC.** Atlas stores no per-tenant timezone anywhere, so `service_open`/`service_close`
are UTC times and a slot is an INSTANT; the property's website converts. A close at or before the
open means the service runs past midnight and the window rolls into the next calendar day, which is
why `service_date` is a BUSINESS date separate from the slot's own instant.

### The transition / counter matrix

`CONFIRMED → SEATED → COMPLETED | NO_SHOW | CANCELLED`, through an explicit `RESERVATION_FLOW` table
(the lifecycle branches, so there is no "next state" arithmetic to lean on). **There is no
TENTATIVE**: passing the gate IS the confirmation, which is why the gate runs inside the create
transaction.

| Transition | Counter effect |
|---|---|
| create (gate passes) | `covers_booked += party_size`, `parties_booked += 1` |
| CANCELLED / NO_SHOW **before** `slot_start` | both decrement |
| CANCELLED / NO_SHOW **at or after** `slot_start` | none — there is nobody left to resell to |
| SEATED / COMPLETED | none — the covers were spent at confirmation |
| party-size change before `slot_start` | delta on covers, same locked row, **no extra party** |
| slot change before `slot_start` | release the old slot + book the new one, ONE transaction |

Deliberately **simpler than the hotel's rule** (Phase 20, where a no-show keeps its count to feed
the overbooking buffer). Each row has its own named test so the two do not get unified later. A
no-show marked EARLY releases like a cancel because NO_SHOW is terminal: a host mis-clicking it on
tomorrow's eight-top would otherwise strand those covers with no transition left to give them back.

Seating opens the `OrderTicket` (`guest_count = party_size`, the host's free-text `table_code`) and
writes the `seated_as` doc-flow edge in the same transaction, so
`GET /api/v1/documents/{id}/chain` renders reservation → ticket → (Phase 20 folio line). A walk-in
needs nothing from this module: it is exactly the ticket Phase 19 already creates.

### Endpoints

Staff (`/api/v1/hospitality`, JWT or a staff-scoped key):

| Method | Path | Permission | Notes |
|---|---|---|---|
| GET | `/reservations` | `hospitality.reservation.read` | the book, `Page[TableReservationRead]`, **ascending by slot**, filter by `service_date` / `status` |
| GET | `/reservations/{id}` | `hospitality.reservation.read` | |
| POST | `/reservations` | `hospitality.reservation.manage` | 201, **idempotent** (`hospitality.table_reservation.create`); the same gate the website uses |
| PATCH | `/reservations/{id}` | `hospitality.reservation.manage` | party size and/or slot; omitted fields unchanged |
| POST | `/reservations/{id}/seat` | `hospitality.reservation.manage` | body `{table_code}`; opens the linked check |
| POST | `/reservations/{id}/no-show` · `/cancel` · `/complete` | `hospitality.reservation.manage` | the transitions above |
| GET | `/reservation-settings` | `hospitality.reservation.read` | defaults applied; carries `slot_minutes` |
| PUT | `/reservation-settings` | `hospitality.reservation.manage` | full replacement; no key needed (one row, same state) |
| PUT | `/service-slots` | `hospitality.reservation.manage` | one slot's capacity, identified in the BODY; `covers_max: 0` closes it |

Website (machine credential, `hospitality.reservation.book`): `GET /reservation-availability`,
`POST /table-reservations`, `POST /table-reservations/{id}/cancel` — the published contract is in
[docs/api.md](../api.md#the-reservation-contract). `.book` is a **third** key on purpose: the BOOK
is every guest's name and contact detail for the night, so a leaked website key must not read it
(D-069's narrowing rule).

### Error codes

| Code | HTTP | When |
|---|---|---|
| `hospitality.reservation_not_found` | 404 | unknown reservation in this tenant |
| `hospitality.reservation_not_transitionable` | 409 | not a legal move in `RESERVATION_FLOW` (includes cancelling a SEATED party) |
| `hospitality.reservation_slot_started` | 409 | amending a booking whose slot has begun |
| `hospitality.slot_full` | 422 | `details.limit` is `covers` or `parties`, plus `requested`/`available`; on the website booking route it also carries `alternatives` |
| `hospitality.slot_override_below_booked` | 422 | a manager cutting capacity under confirmed bookings; carries both numbers |
| `hospitality.party_size_not_accepted` | 422 | outside `min_party`..`max_party` |
| `hospitality.outside_booking_window` | 422 | a service whose hours have already closed, or a date past `booking_horizon_days`. The floor is the SERVICE, not the UTC calendar day, so a service running past midnight stays bookable while it is running |
| `hospitality.outside_service_hours` | 422 | a slot outside `service_open`..`service_close` for that date (booking **and** `PUT /service-slots`) |
| `hospitality.slot_not_aligned` | 422 | a slot not on a 15-minute boundary (booking **and** `PUT /service-slots`) |

### Known limits (Phase 21, recorded not hidden)

11. **A booking consumes its ARRIVAL slot only** — the OpenTable semantics. A three-hour tasting menu
    is counted against 19:00 and nothing else, so a property whose sittings genuinely overlap must
    set `default_covers_max` to what one slot's arrivals may be, not to the room's seat count.
    Multi-slot pacing is the named upgrade.
12. **No deposits and no no-show fees.** They need Phase 20's `apply_receipt` and an online payment
    provider; wiring guest money before those exist would rebuild both badly.
13. **No waitlist.** A refused booking is answered with the nearest bookable alternatives and
    nothing is remembered.
14. **Guest notification is the website's job** (Q1 boundary). Atlas sends no email or SMS, has no
    guest-facing cancel link, and does not know which guest owns which booking — the website
    authenticates its guest and calls a tenant-scoped operation under its own credential.
15. **A slot earlier TODAY is bookable.** That is deliberate (a host taking a party walking in in ten
    minutes) but it means the same route accepts a booking for a slot that has already gone, which
    then holds capacity nothing can release.
16. **Service hours are UTC**, because Atlas has no per-tenant timezone. A property whose local
    service crosses a UTC day boundary must send the right `service_date` itself; the API cannot
    infer it. It will not REFUSE the right one, though: the booking window's floor is the service's
    own close instant, so the second half of a midnight-crossing service stays bookable and
    readable while it is being run.
17. **The staff surface has no slot-grid read.** A manager sets capacity blind and learns the current
    counters only from the refusal (`covers_booked`/`parties_booked` in `details`). One endpoint over
    `queries.slot_counters` closes it the day somebody builds the screen.

## 8. The staff UI (PLAN 22.2)

`frontend/src/modules/hospitality/` — the first module guide to document its UI, because this
module's screens carry two limits the API alone does not make visible (the pre-tax total, and the
one screen in Atlas that refreshes itself).

| Route | Page | Needs |
|---|---|---|
| `/hospitality` | module home; tiles are filtered by permission, because a chef holds `menu.*` and a server holds `ticket.*` | any `hospitality.*` |
| `/hospitality/menu` | the 86 board + the set-availability editor | `menu.read`; the editor and Clear need `menu.manage` |
| `/hospitality/at-risk` | the advisory coverage list, read-only | `menu.read` |
| `/hospitality/tickets` · `/tickets/new` · `/tickets/{id}` | checks: list, open, lines, the status flow | `ticket.read`; New/lines/fire/advance need `ticket.manage`; Settle needs `ticket.settle`. Dish NAMES and the price prefill also need `menu.read` — without it the check still opens, with item ids and an empty dish picker |
| `/hospitality/kitchen` | the kitchen display | `ticket.read`; dragging a card needs `ticket.manage` |

Five things about it are decisions rather than styling:

1. **The kitchen display polls, and it is the only thing in the frontend that does.** Three
   `useKdsColumn` queries on a 10 s `refetchInterval` with `staleTime: 0` — the global 30 s
   staleTime (`lib/queryClient.ts`) would otherwise freeze the board between navigations. One query
   per column because `GET /tickets` takes a single `status`; the three can land a beat apart, and
   widening the endpoint to a repeated parameter is the fix if that ever shows.
2. **Every total is labelled pre-tax**, on the list and on the check — §6 limit 3 is a limit a user
   can see, not only a documented one.
3. **The availability editor offers EIGHTY_SIXED and LIMITED only.** AVAILABLE is spelled by the
   absence of a row (`clear_86` deletes), so a third dropdown entry would give "back on the menu"
   two spellings, one of which leaves a row behind. Clear is the other half.
4. **Ticket line prices are typed, prefilled from the menu read.** The staff service trusts a
   caller-supplied `unit_price` by contract, and there is no staff-side price-resolution endpoint —
   `/sales/price-quote` needs a customer id and a walk-in table has none. The website surface
   resolves price server-side instead, because that caller is untrusted.
5. **The dish picker offers only what can be sold, and shows the 86 board on the options** (#208):
   priced items only — `GET /menu` unfiltered returns every ACTIVE item, ingredients included,
   which is honest for the website read and useless on a POS — with an 86'd dish rendered disabled
   with its reason and a LIMITED one showing its count, rather than a pick that is refused at fire
   time with the whole check. Both of the picker's reads are `menu.read`, so both carry
   `throwOnError: false` on the check screen: they are lookups, not the record the page is for, and
   a server holding only `ticket.*` must not be handed a full-page 403 for either. On
   `/hospitality/menu` the same board read keeps the default and takes the page, because there it
   IS the record. The check screen reads one more thing that persona cannot read — the currency
   CODE beside every total, from `GET /finance/currencies` under `finance.fx.manage` — and it
   degrades the same way, in the shared `useFunctionalCurrency` hook rather than here, because 15
   screens across 8 modules print that label (#237, docs/modules/finance.md §Permissions). Those
   three reads are the whole reason the row above can promise a `ticket.read` server a check at
   all.

Known UI gaps, recorded not hidden: a kitchen card shows the check, the table, the covers and the
time since it fired but **no line summary** (that would cost one `GET /tickets/{id}/lines` per card
per poll); there is **no prep-station filter**, because nothing in Phase 19 stores a station; and
`available_until` is entered as a date and sent as the end of that day, because the shared
FormBuilder has no datetime control.
