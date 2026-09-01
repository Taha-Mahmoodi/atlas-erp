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

**PLAN 19.1–19.5, 21.1–21.4, 20.1 and 20.2 shipped.** 20.1 is the HOTEL half's masters — room
types, rooms, manual rate plans and the housekeeping task document (§9); 20.2 is the BOOKING GATE —
the per-date allotment counter and the room reservation (§10). The folio, deposits, the business
date and the room-charge bridge are 20.3–20.6, and nothing here anticipates them beyond publishing
`RestaurantOrderSettled`, which has no subscriber yet. The guest-facing room-AVAILABILITY read is
Task 9; 20.2 ships the booking WRITE only.

Deliberately **not** in this phase: modifier-level 86 (Atlas has no modifier model), day-part menus
beyond what `available_until` half-covers, third-party delivery injection, KDS hardware, card
payment, split checks, and tax on a check (see *Known limits*).

| File | Concern | Key decision |
|---|---|---|
| `constants/` | a PACKAGE since 20.1 (the single file hit the §8.4 cap, the `sales/constants/` precedent): `enums.py` (the RESTAURANT's lifecycles — `AvailabilityState` / `AvailabilitySource` / `OrderTicketStatus` + `TICKET_FLOW`, the table booking), `rooms.py` (the HOTEL's — `HousekeepingStatus`, the two housekeeping flows, `RoomReservationStatus` + `ROOM_RESERVATION_FLOW`, `DEFAULT_OVERBOOKING_LIMIT`; split out at the §8.4 cap in 20.2, the same seam `models/rooms.py` cut), `permissions.py` (the keys, registered at import), `documents.py` (doc types, number sequences, docflow link types, event and job keys). `__init__` re-exports everything, so `from ...constants import X` is unchanged | D-009, D-012, D-072, STRUCTURE §8.4 |
| `models/ordering.py` | `MenuAvailability` (`hsp_menu_availability`), `OrderTicket` (`hsp_order_tickets`), `OrderTicketLine` (`hsp_order_ticket_lines`) | D-007, D-015, D-029 |
| `models/menu.py` | `MenuSection` (`hsp_menu_sections`), `MenuPlacement` (`hsp_menu_placements`), `MenuItemTag` (`hsp_menu_item_tags`) | D-081 |
| `models/table_reservations.py` | `ReservationSettings` (`hsp_reservation_settings`), `ServiceSlot` (`hsp_service_slots`), `TableReservation` (`hsp_table_reservations`) | D-007, D-012 |
| `models/room_inventory.py` | `RoomTypeInventory` (`hsp_room_type_inventory`) — the allotment counter — and `RoomReservation` (`hsp_room_reservations`), the HOTEL booking. A sibling of `rooms.py` rather than more of it: that file could not take them under the §8.4 cap | D-007, D-012, D-087 |
| `service/allotment.py` | `adjust_allotment`, `adjust_sellable`, `stay_nights`, `RoomTypeSoldOutError` — the booking gate, and the only code that moves `rooms_sold` | D-003, D-020/D-036, D-087 |
| `service/room_reservations.py` | the `TENTATIVE → CONFIRMED → CHECKED_IN → CHECKED_OUT \| NO_SHOW \| CANCELLED` lifecycle, and where each transition touches the counter | D-012, D-087 |
| `service/room_stays.py` | ARRIVAL and DEPARTURE — the only code that reads `Room` or writes `RoomReservation.room_id`, and where the occupancy refusal lives. Split out of `service/room_reservations.py` when that file reached the §8.4 cap; the seam is the BOOK against the OCCUPANCY, and Task 5's folio hangs here | D-012, D-087, STRUCTURE §8.4 |
| `service/rate_plans.py` | rate-plan CRUD, moved out of `service/rooms.py` when 20.2's allotment hook took that file to the §8.4 cap; it imports `require_code_free` / `sent_fields` / `get_room_type` from there | STRUCTURE §3, §8.4 |
| `room_reservation_router.py` | the desk's book (`/room-reservations`) and the ONE website route (`/website/room-reservations`), two `APIRouter`s in one file because the website's surface here is a single route sharing the desk's create | D-009, D-013, D-069 |
| `models/__init__.py` | the one import surface — `from app.modules.hospitality.models import X` for every model above; a `models/` package rather than one file because Phase 21 took `models.py` to 451 lines, past the STRUCTURE §8.4 cap (#176) | STRUCTURE §3, §8.4 |
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
| POST | `/tickets` | `hospitality.ticket.manage` | 201, **idempotent** (`hospitality.order_ticket.create`). No service date in the body: the server stamps today (#207) |
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
| POST | `/reservations/{id}/seat` | `hospitality.reservation.manage` | body `{table_code}`; opens the linked check. It carries the BOOKING's service date only while that service is running (a party seated at 23:50 orders onto the day it booked); otherwise today, like a walk-in's (#207) |
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

5. **The check prints from its own markup, not from a second rendering of it** (#211). `Print`
   calls `window.print()`; `styles.css`'s `@media print` block hides the shell, keys off
   `data-print-region="receipt"` for an 80 mm column, and drops anything marked `data-print-hide`
   (the breadcrumb, the action row, the add-a-line form). A separate "printable view" component
   would be a second place for the numbers to drift from §6 limit 3's pre-tax label. The paper
   carries the property's name, which is why `GET /auth/me` returns `tenant_name`: it is the only
   read of it the SPA has, and a tenant read is an admin endpoint a server does not hold.

Known UI gaps, recorded not hidden: a kitchen card shows the check, the table, the covers and the
time since it fired but **no line summary** (that would cost one `GET /tickets/{id}/lines` per card
per poll); there is **no prep-station filter**, because nothing in Phase 19 stores a station; and
`available_until` is entered as a date and sent as the end of that day, because the shared
FormBuilder has no datetime control.

## 9. Rooms, rates and housekeeping (Phase 20.1)

The first slice of the **hotel** half. Three masters and one document — enough for a property to
describe what it sells and keep its rooms serviceable. It deliberately sells **nothing** yet:
availability, the allotment counter and the room reservation are Phase 20 Task 4, and the folio,
deposits and the night audit are Tasks 5–7.

| File | Concern |
|---|---|
| `constants/` | the package `constants.py` became at the §8.4 cap — `enums.py` (the restaurant's status enums + transition tables + defaults), `rooms.py` (the hotel's, split out at the same cap in 20.2), `permissions.py` (the keys, registered at import), `documents.py` (doc types, sequences, link and event keys). `__init__` re-exports everything, so every `from ...constants import X` still resolves from one surface |
| `models/rooms.py` | `RoomType` (`hsp_room_types`), `Room` (`hsp_rooms`), `RatePlan` (`hsp_rate_plans`), `HousekeepingTask` (`hsp_housekeeping_tasks`) |
| `rooms_schemas.py` | the wire shapes; a fourth schemas sibling (D-030/D-031) |
| `service/rooms.py` | the three masters' CRUD + paginated reads, and `set_housekeeping_status` |
| `service/housekeeping.py` | the task document: raise, move, reassign, board read |
| `rooms_router.py` | staff REST under `/api/v1/hospitality` — a fourth router, no website half |

Migration: `0054_hsp_rooms`.

### Rooms sell by TYPE, not by room

The guest buys "a double" and the physical room is assigned at check-in (spec Q3). So `RatePlan`
prices a room **type** and `Room` carries no price at all — a per-room price would turn the front
desk's room assignment into a pricing decision. `base_capacity` is what Task 4 will validate a
booking's party size against; extra beds are a rate question v1 does not model.

Rates are **manual**: one nightly amount per plan over a validity window, no rate calendar, no yield
rules, no length-of-stay pricing. A seasonal rate is a second plan with a second window. The only
rule the database enforces about the window is that it is not backwards
(`hospitality.rate_plan_window_invalid`, with the CHECK as the backstop).

### `Room.housekeeping_status` has exactly one writer, and that is the point

`DIRTY → IN_PROGRESS → CLEAN → INSPECTED`, with `OUT_OF_ORDER` reachable from every state (a pipe
bursts whatever condition the room was in) and leaving only to `DIRTY` (a room that has been out of
service is cleaned before it is sold, not declared sellable by a supervisor). A new room starts
`DIRTY`: nobody has made it up, and starting sellable is the assumption that walks a guest into an
unserviced room.

`CLEAN` and `INSPECTED` also go back to `IN_PROGRESS`, and **that edge is what makes the two
non-`CHECKOUT` triggers work**: a `GUEST_REQUEST` arrives mid-stay on a room that is `CLEAN` and a
`SCHEDULED` stayover service lands on one a supervisor has `INSPECTED`, so without it either task
could be raised and never started, and the departure clean would be the only trigger that
functioned. An attendant standing in a made-up room *is* the `IN_PROGRESS` fact. The way back out is
always `CLEAN` — never straight to `INSPECTED`, because somebody has been in the room since it was
signed off, so it needs inspecting again. `DIRTY → CLEAN` stays absent: no path in the module
declares a room clean without an attendant having been in it.

`OUT_OF_ORDER` is the one state with a revenue consequence — Phase 20 Task 4 decrements
`rooms_sellable` on the future dates a room out of service covers, and raises it again when the room
comes back. That works only if the column has ONE writer, which is why:

* `RoomUpdate` has no `housekeeping_status` field and forbids extras, so a PATCH that tries to move
  it is a **422**, not a silent no-op;
* the housekeeping board never writes the column either — starting a task calls
  `rooms.set_housekeeping_status`, and so does finishing one;
* every move is checked against `HOUSEKEEPING_FLOW` inside that function, so starting work on a room
  the property has taken out of service is refused with the ROOM's error code
  (`hospitality.room_not_transitionable`) rather than quietly returning it to sale.

**Task 4's hook is that function's transition branch**, comparing the old and new status against
`HOUSEKEEPING_UNSELLABLE`. No caller has to change.

### The task and the room are two different facts

`HousekeepingTask.status` (`OPEN → IN_PROGRESS → DONE | CANCELLED`) is the work order's progress;
`Room.housekeeping_status` is the room's condition. Starting the work moves both; finishing it makes
the room CLEAN. **Cancelling never makes a room clean** — but it does put a room the cancelled task
had *started* back to DIRTY, because the alternative strands it in IN_PROGRESS with no open task and
no transition left that reaches it. Cancelling a task nobody picked up changes nothing.

`DONE` and `CANCELLED` are terminal: a room needing more work gets a NEW task, so the board shows
what is outstanding rather than reopened history.

The task is a **D-012 document** — registered in `core_documents`, numbered `HKT-2026-000001` at
creation (the order-ticket branch: the board quotes the number the moment the work is raised), and
doc-flow linked to whatever caused it through `predecessor_document_id`. Task 4's check-out passes
the departing reservation's registry id through that same field, and the chain then reads
reservation → housekeeping task with no change here.

### Endpoints (`/api/v1/hospitality`, staff only)

| Method | Path | Permission |
|---|---|---|
| GET/POST | `/room-types`, PATCH `/room-types/{id}` | `rooms.read` / `rooms.manage` |
| GET/POST | `/rooms`, GET/PATCH `/rooms/{id}` | `rooms.read` / `rooms.manage` |
| POST | `/rooms/{id}/housekeeping-status` | `housekeeping.manage` |
| GET/POST | `/rate-plans`, PATCH `/rate-plans/{id}` | `rooms.read` / `rooms.manage` |
| GET/POST | `/housekeeping-tasks`, GET/PATCH `/housekeeping-tasks/{id}` | `rooms.read` / `housekeeping.manage` |

**No website half.** A guest site asks about availability and books, which is Task 4's surface; the
room master, the rate sheet and the housekeeping board are internal, and a leaked website credential
must never be able to read that a property has six rooms out of order (D-069's narrowing rule).

`housekeeping.manage` is a third key rather than a slice of `rooms.manage`, on the `ticket.settle`
precedent: taking a room out of service has a revenue consequence, and that is a different authority
from editing the room master. Reading is one key — an attendant's device needs the room list and the
board together.

Only `POST /housekeeping-tasks` takes an idempotency key (D-013): it is the only write here that
registers a document and burns a gapless number. The masters claim no number, and re-sending a
housekeeping status is refused by the transition table as an illegal move, so a retry cannot double
anything.

### Error codes

| Code | Status | Meaning |
|---|---|---|
| `hospitality.room_type_not_found` / `room_not_found` / `rate_plan_not_found` / `housekeeping_task_not_found` | 404 | unknown in this tenant (a foreign id reads the same) |
| `hospitality.room_type_code_conflict` / `rate_plan_code_conflict` | 409 | the code is taken in this tenant |
| `hospitality.room_number_conflict` | 409 | the property already has that room number — on `POST /rooms` and on a `PATCH` that renumbers, which share the pre-check (`room_number` is the one mutable code-like column here; a room type's and a rate plan's codes are immutable) |
| `hospitality.rate_plan_window_invalid` | 422 | `valid_to` is before `valid_from` |
| `hospitality.room_not_transitionable` | 409 | the housekeeping move is not in `HOUSEKEEPING_FLOW` |
| `hospitality.housekeeping_task_not_transitionable` | 409 | the task move is not in `HOUSEKEEPING_TASK_FLOW` |

### Known limits (Phase 20.1, recorded not hidden)

1. **No delete or deactivate on any of the three masters.** A typo is fixed by PATCH; a room type
   the property stopped selling stays on the list. A rate plan expires through its window and a room
   goes `OUT_OF_ORDER`, so only the room TYPE has no way off the list at all.
2. **`assigned_user_id` is not validated.** It is a plain `adm_users` id with no FK, the
   `QualityInspection.decision_by` / journal `posted_by` precedent, so a wrong id is stored and
   reads back as an unresolvable assignee rather than a refusal.
3. **No rate resolution.** Nothing yet answers "what does a double cost on 3 March"; overlapping
   plans for one room type are allowed, and Task 4/5 decide which one a booking takes.
4. **No room attributes** — floor, view, connecting rooms, accessibility. Every one of them is a
   filter somebody will want at assignment time, and none of them has a consumer until check-in
   exists.
5. **The housekeeping board is not scheduled.** `SCHEDULED` is a trigger a human selects; nothing
   raises a stayover clean on its own, because Atlas has no scheduler (the same argument that makes
   the 86 time box lazily evaluated).
---

## 10. The booking gate and the room reservation (PLAN 20.2, spec Q3, **D-087**)

A property can now take a room booking, sell it against a per-night allotment, put the guest in a
room and close the stay — without ever selling the same room-night twice.

### Two reservations in one module, named apart

This module holds two unrelated bookings, so **neither is a bare `Reservation`**:

| | restaurant (Phase 21) | hotel (Phase 20.2) |
|---|---|---|
| model | `TableReservation` | `RoomReservation` |
| table | `hsp_table_reservations` | `hsp_room_reservations` |
| status | `ReservationStatus` | `RoomReservationStatus` |
| number | `RSV-2026-000001` | `RMR-2026-000001` |
| permissions | `hospitality.reservation.*` | `hospitality.room_reservation.*` |
| the unit it holds | one 15-minute pacing slot | one room-night per night slept |

The two number series are deliberately distinct: a number a guest quotes down the phone must be
exactly one document.

### The gate is a per-date counter, not an interval lock

One `hsp_room_type_inventory` row per `(room_type_id, stay_date)`, carrying three integers that mean
three different things:

- `rooms_sellable` — the physical supply, a SNAPSHOT seeded at materialisation from a COUNT of the
  type's rooms outside `HOUSEKEEPING_UNSELLABLE`, and moved thereafter only by
  `rooms.set_housekeeping_status` (D-085's single writer).
- `rooms_sold` — what confirmed bookings hold. The only column a booking moves.
- `overbooking_limit` — how far past the supply the property will sell, per night. **Zero by
  default**, and it is what pays for a no-show releasing nothing.

`adjust_allotment(session, tenant_id, room_type_id, stay_dates, delta, *, released_dates=())` is the
ONE helper every counter touch routes through. Three phases, and the order is the contract: **lock**
every night in ONE ascending `stay_date` pass (materialising a missing row on the lock, under a
SAVEPOINT, so two guests booking the same untouched night do not race the unique constraint into a
500), **check** every night, then **apply**. Refusing before any counter has moved is what lets a
caller promise a refused booking left the book exactly as it was.

Q3's rejected alternative was `EXCLUDE USING gist` over a daterange: PostgreSQL-only, so the SQLite
suite (D-003) could not exercise the invariant the money path depends on. The shape actually copied
is `inventory/service/stock_quants.apply_bin_delta` (D-020/D-036) — locked read, pre-flight refusal,
upsert-on-lock, portable CHECK backstop. One pattern, now four counters.

### FOUR locks, and the order is reservation → room → room type → nights

The night counter is not the only exclusive thing in the module, and treating it as though it were
is how three separate double-write paths got in — one per review round, each a call site further
over than the last. The rule that replaces "remember to lock" is: **every path that writes
`rooms_sold` or `rooms_sellable` locks the row whose state decides its delta, before it reads the
counter.** Every writer takes a subsequence of the order below and none takes it out of order.

| lock | taken by | the race it covers |
|---|---|---|
| the RESERVATION row (`get_room_reservation(for_update=True)`) | confirm, cancel, no-show, amend, check-in, check-out | **one booking moved twice at once.** A double-clicked Confirm is two CONCURRENT requests; `ROOM_RESERVATION_FLOW` is an in-Python read, so both racers see TENTATIVE, both pass it, then both serialize correctly on the night rows and BOTH take the nights. The counter is then overstated forever — the later cancel gives back one, not two. `/cancel` has the same shape on the way out, and worse: a double release is floored at zero and looks perfectly plausible |
| the ROOM row (`get_room(for_update=True)`) | check-in, `update_room`, `set_housekeeping_status` | **two guests handed the same key** at check-in; and **one room taken off its type twice** on the two paths that change what the property can sell. `room.room_type_id` and `room.housekeeping_status` are both read in Python, so two concurrent `PATCH {room_type_id: SGL}` both see DBL and both apply −1: a silent, permanent UNDER-sell on every materialised night |
| the ROOM TYPE row (`allotment._lock_room_type_supply`) — SHARE on the counter path, EXCLUSIVE on the supply path | taken by `allotment` itself, not by its callers | **a night materialising from a supply that has already changed.** `adjust_sellable` reaches only MATERIALISED nights, while a night with no row is seeded from a live `COUNT(hsp_rooms)`; unordered, a booking counts three rooms while a closure commits the second, and the night is one room over forever |
| the per-night ALLOTMENT rows, ascending | confirm, cancel, the date change | **two DIFFERENT bookings overselling one night**, and (via the sort) the deadlock two overlapping multi-night stays would otherwise reach |

Every path in the module that writes either counter, and what it locks:

| path | writes | the row that decides the delta | locks |
|---|---|---|---|
| `room_reservations.confirm_room_reservation` | `rooms_sold` +1/night | the RoomReservation (its status) | reservation FOR UPDATE → type SHARE → nights asc |
| `room_reservations.cancel_room_reservation` | `rooms_sold` −1/night | the RoomReservation (its status) | reservation FOR UPDATE → type SHARE → nights asc |
| `room_reservations.amend_room_reservation` | `rooms_sold` ±1/night | the RoomReservation (its status and dates) | reservation FOR UPDATE → type SHARE → nights asc |
| `rooms.update_room` (`room_type_id` changed) | `rooms_sellable` −1 and +1 | the Room (its current type) | room FOR UPDATE → each type FOR UPDATE in ascending id order → that type's nights asc |
| `rooms.set_housekeeping_status` (crossing `HOUSEKEEPING_UNSELLABLE`) | `rooms_sellable` ±1 | the Room (its current status) | room FOR UPDATE → type FOR UPDATE → nights asc |
| `allotment._row_for_update` (materialising a night) | `rooms_sellable` at birth | every `hsp_rooms` row of the type, so no single row lock can order it | type SHARE, taken before the first night — the reason that lock exists |
| `room_stays.check_in/check_out` | **nothing** | — | reservation FOR UPDATE → room FOR UPDATE |

The type lock is taken by `allotment` itself rather than by its callers, because a lock a caller
must remember is the defect this module shipped three times. What remains the caller's job — the
reservation or the room — is held by a STATIC census,
`test_allotment_lock_discipline.py`: it fails on any function under `service/` that reaches the
counter without appearing in its table, and on any declared writer whose lock is missing or taken
after the counter call. Each lock is ALSO pinned by its own `-m pg` race in
`test_room_booking_races.py`, and each of those races fails when its lock is deleted — including
the cancellation one, which first had to be rewritten because it passed the mutation for the wrong
reason (see *Racing on purpose* below).

### Racing on purpose

The `-m pg` races in `test_room_booking_races.py` needed two harness fixes before any of them proved
anything, and both are the same class of mistake as a test that cannot fail:

- **The gate has to release both parties and wait for both to RESUME.** `Event.set()` only makes a
  waiter runnable; the last arriver keeps the loop and can run its whole transaction to COMMIT
  before the waiter is scheduled back on.
- **The connection pool has to be WARM.** A session that finds the pool empty pays a fresh TCP
  connect plus asyncpg's auth — about fifteen milliseconds — and a racer paying that inside the
  window reads state its opponent already committed. Real web workers hold warm connections.

Until both were fixed the cancellation race answered 409 for the wrong reason and passed with the
row lock deleted.

### A missing allotment row means DEFAULT supply, not zero

Nothing pre-creates the grid — that would be one row per room type per night forever, for nights
nobody books — so **every first booking of a night reads no row at all**. If absence read as
"nothing on sale" (the `StockQuant` meaning, where a missing quant really is zero on hand) a
property could never take a booking, and one that materialised 90 days could never take a booking on
day 91. This is D-076's rule for `ServiceSlot`, restated: absence of a counter is absence of a
BOOKING, never absence of a room.

### A stay is `[arrival, departure)`

The departure date is never a night sold. A guest arriving on the 3rd and leaving on the 5th sleeps
two nights, and a guest arriving on the 5th buys a different night of the same room — back-to-back
availability with no interval arithmetic at all. `CHECK (departure_date > arrival_date)` and a
readable `hospitality.stay_range_invalid` both refuse a stay that sleeps nobody.

### The transition / counter matrix

| transition | counter |
|---|---|
| create (TENTATIVE) | **nothing** — an enquiry is not a sale |
| CONFIRMED | `rooms_sold += 1` on every night, or `hospitality.room_type_sold_out` |
| CANCELLED from CONFIRMED / CHECKED_IN | release every night, at any time before it is slept |
| CANCELLED from TENTATIVE | nothing — it never took them |
| **NO_SHOW** | **NOTHING RELEASED** |
| CHECKED_IN, CHECKED_OUT | nothing — the nights are consumed, not re-sold |
| date change | release the old nights, take the new, in ONE locked ascending pass |
| room → `OUT_OF_ORDER` | `rooms_sellable -= 1` on materialised FUTURE nights; back on return |
| room moved to another TYPE | `rooms_sellable -= 1` on the losing type and `+= 1` on the gaining one, both on materialised FUTURE nights |

**NO_SHOW is the row that differs from the restaurant, and it is not an oversight in either
direction.** A table no-showed before its slot is still resellable, so D-077 gives the covers back;
a room stood empty and unsellable all night, so there is nothing to give back, and what pays for
that loss is `overbooking_limit` — the buffer the property sold into in advance. Releasing here
would spend it twice. `test_a_hotel_no_show_keeps_the_night_while_the_restaurant_gives_covers_back`
drives BOTH modules in one test, so unifying the two rules fails loudly whichever way it is done.

**A date change passes both night sets to one call.** Two calls would be two lock passes starting at
different points — the deadlock D-020/D-036 forbids, reaching a receptionist as a 500 rather than a
409. Nights the stay KEEPS net to a delta of zero and are neither re-checked nor re-written, so a
full property can still shift a booking by a day. Changing the ROOM TYPE is deliberately not
offered: two counters rather than one, and it re-prices the stay, so it is a cancel and a re-book.

**Taking the last sellable room off a fully sold night is REFUSED**, not recorded. Pushing the row
past its CHECK would be a 500 on the housekeeping board; recording the oversell would leave a guest
booked into a room the property cannot give them, and Atlas has no walk-the-guest flow to resolve
one. So the manager is told which night to move a booking off first.

**`rooms_sellable` has THREE writers, not one, and none of them is the counter's own file.** D-085
gave `housekeeping_status` a single writer so the counter could hang off it; `RoomUpdate.room_type_id`
— "renumber a room or move it to another type" — changes exactly the same fact and had no hook at
all, so moving 101 out of DBL left every materialised DBL night still counting a room the type no
longer has. That is a SILENT oversell: the gate then confirms a stay for a room that does not exist
and the walk happens at check-in. `rooms.update_room` now routes both types through
`adjust_sellable`, in ascending room-type id order so two rooms swapping types at once cannot
deadlock, and the losing type refuses with `hospitality.room_type_sold_out` on the same argument as
the housekeeping case. A room already in `HOUSEKEEPING_UNSELLABLE` is supply for neither type, so
moving it moves nothing. The third writer is `_row_for_update` **seeding a new night** from a live
`COUNT(hsp_rooms)`, which is why the room-type row is locked SHARE by the counter path and EXCLUSIVE
by the two supply paths: it is the only one of the three whose deciding state is a SET of rows, so
no `for_update` on a single row can order it. All three, and the rows they lock, are in the table
under *FOUR locks* above — and that table is enforced by `test_allotment_lock_discipline.py`, not
just written down.

**A physical room holds ONE guest at a time, and that starts at check-in.** The counter sells a room
TYPE, so two confirmed doubles on one night are a correct book and nothing above check-in makes 101
exclusive. Check-in reads the room's current occupant and answers 409 `hospitality.room_occupied`,
under a partial unique index `(tenant_id, room_id) WHERE status = 'CHECKED_IN'` — partial, because a
room houses a different guest every week and every past stay keeps its `room_id`, and declared
outside the class body so its dialect predicates are column expressions rather than `sa.text`, which
the D-007 grep gate bans under `app/modules/` (the `hr/models/payroll.py` precedent). The read gives
the friendly answer, the index is the backstop, and the room row lock is what makes the read
trustworthy when two receptionists check in at the same instant.

### Endpoints

Desk (`/api/v1/hospitality`, `hospitality.room_reservation.read` / `.manage`):

| method | path | notes |
|---|---|---|
| GET | `/room-reservations` | the arrivals book; `status`, `arriving_from`, `arriving_to`; keyset-paginated, ≤3 queries |
| GET | `/room-reservations/{id}` | one booking |
| POST | `/room-reservations` | takes a TENTATIVE booking; **idempotent** (D-013) |
| PATCH | `/room-reservations/{id}` | dates and party size, in one locked pass |
| POST | `/room-reservations/{id}/confirm` | the sale — the counter touch |
| POST | `/room-reservations/{id}/check-in` | body `{room_id}`; the room must be of the booked type, sellable, and unoccupied |
| POST | `/room-reservations/{id}/check-out` | terminal |
| POST | `/room-reservations/{id}/cancel` | releases whatever it held |
| POST | `/room-reservations/{id}/no-show` | releases nothing |

Website (machine credential, `hospitality.room_reservation.book` and nothing else):

| method | path | notes |
|---|---|---|
| POST | `/website/room-reservations` | takes a **TENTATIVE** booking; idempotent; cannot confirm |

The website key cannot confirm, cannot read the book, and cannot assert a `status` (the request
shapes have no such field and `extra="forbid"` makes the attempt a 422). That is
`place_website_order`'s acknowledgment rule: an external client never silently skips a human check,
and it is told the state its booking is actually in. What confirms a stay is a member of staff or —
from PLAN 20.4 — a recorded deposit; taking payment on the booking is out until a payment provider
exists.

### Error codes

| code | status | when |
|---|---|---|
| `hospitality.room_type_sold_out` | 422 | no room-night left on that night (naming the night), or a room going `OUT_OF_ORDER` on one |
| `hospitality.room_reservation_not_found` | 404 | unknown id, or another tenant's |
| `hospitality.room_reservation_not_transitionable` | 409 | the move is not in `ROOM_RESERVATION_FLOW`, or the booking is past amending |
| `hospitality.stay_range_invalid` | 422 | departure on or before arrival |
| `hospitality.rate_plan_room_type_mismatch` | 422 | the rate plan prices a different room type |
| `hospitality.party_size_exceeds_capacity` | 422 | the party is larger than the type's `base_capacity` |
| `hospitality.room_type_mismatch` | 422 | check-in into a room of the wrong type |
| `hospitality.room_not_sellable` | 422 | check-in into an `OUT_OF_ORDER` room |
| `hospitality.room_occupied` | 409 | check-in into a room another booking is still CHECKED_IN to |

### Write budget

`tests/perf/test_write_budgets.py` pins the shape, not just a ceiling: a 3-night confirmation costs
12 statements and each further night costs exactly 2, so a 14-night one costs 34. The assertion is
on the DIFFERENCE, because the two regressions that matter — a room COUNT per night instead of one
per call, and a per-night document read — are invisible to every behavioural test and satisfy a
plain ceiling.

### Known limits (PLAN 20.2, recorded not hidden)

1. **No guest-facing availability read.** The website can book but cannot ask what is bookable;
   that is Task 9 (`GET /website/room-availability`), and until it ships a site must know the room
   type and rate plan ids out of band.
2. **No rate resolution and no window check.** A booking names a rate plan and the service only
   checks it prices the booked room TYPE — not that its validity window covers the stay. Overlapping
   plans are still allowed (20.1 limit 3), so which one applies is the caller's choice.
3. **"Future nights" is `date.today()`, not a business date.** `adjust_sellable` rewrites nights
   from today forward; PLAN 20.5a introduces the business date and this is where it will land.
4. **No room-type change on an amend.** Two counters and a re-price, so it is a cancel and a
   re-book.
5. **No group bookings, no allotment blocks, no rooming lists.** One reservation is one room; a
   party needing three rooms is three bookings. PLAN 20.5c.
6. **`overbooking_limit` has no endpoint.** The column exists and the gate honours it, but nothing
   yet lets a manager set it per night — it is written only by the migration's default of zero.
7. **Check-out raises no housekeeping task and opens no folio.** Both are Task 5; check-out today is
   a status move, and the `HOUSEKEEPING_TRIGGERED_BY_LINK` edge 20.1 declared still has no writer.
8. **The Phase 21 TABLE reservation has the room booking's old shape**, and this PR did not change
   it: `reservations.get_reservation` is a plain read, so two concurrent `/seat` or `/cancel` calls
   on ONE table booking can both pass `RESERVATION_FLOW` and both move the pacing counter. Same
   class, different counter — filed rather than fixed here, because it is shipped behaviour with its
   own tests.
9. **The `ck_` double-prefix trap is fixed on these two tables only.** `Base.metadata`'s convention
   is `ck_%(table_name)s_%(constraint_name)s`, and because that pattern contains
   `%(constraint_name)s` it composes with an explicitly named CHECK rather than only filling in an
   anonymous one. **Alembic applies the same convention** — `schemaobj.metadata()` copies
   `naming_convention` off `env.py`'s `target_metadata`, which is `Base.metadata` — so a
   `ck_`-prefixed literal double-prefixes on BOTH sides, to 71 chars, which PostgreSQL then takes at
   60 (SQLAlchemy hash-truncates past its 63-byte cap) while SQLite keeps all 71. Making only ONE
   side bare is the single way to make the two disagree, and it shipped for a review round. The five
   new CHECKs are declared bare on both, verified against a real PostgreSQL 17 and against
   `sqlite_master` after a real migration by
   `test_the_new_tables_emit_the_constraint_names_the_database_gets` and
   `test_the_phase_20_check_constraints_are_named_on_postgres_as_the_models_declare`; **57 other
   CHECK names across the platform are still double-prefixed**, several past 63 bytes, and renaming
   shipped constraints is its own migration. Filed as #260.
