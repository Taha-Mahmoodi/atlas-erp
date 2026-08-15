# Hospitality (`backend/app/modules/hospitality/`)

Hospitality is the **fourteenth module** and the top of the dependency order (STRUCTURE §5) —
nothing imports it. Phase 19 ships the **restaurant** half: a menu whose availability is *stored*
state, an order **ticket** document that fires to the kitchen, ingredient depletion that runs off
the sale, and the read/write API a property's **own website** calls over the Phase 18 machine
credential (**D-069**).

Spec: [`docs/research/hospitality-industry-plan.md`](../research/hospitality-industry-plan.md) **Q2**
(availability), **Q4** (depletion), **Q6** (the website read path). Plan:
[`docs/research/phase-19-restaurant-ordering-plan.md`](../research/phase-19-restaurant-ordering-plan.md).
The two decisions this module records are **D-072** (backgrounded depletion, restaurant-scoped) and
**D-073** (why the menu read has no ETag) in [DECISIONS.md](../../DECISIONS.md).

## Status

**PLAN 19.1–19.5 shipped.** Rooms, folio, deposits, the business date and the room-charge bridge are
**Phase 20** and nothing here anticipates them beyond publishing `RestaurantOrderSettled`, which has
no subscriber yet.

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
- There is **no VOID/CANCELLED**: a comp or a walk-out is a money correction the Phase 20 folio owns.

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
| POST | `/tickets/{id}/settle` | `hospitality.ticket.settle` | its own key: settlement is the money moment |

`settle` is deliberately **not** idempotency-keyed — it creates no document, and the strictly
sequential lifecycle already answers a replay with `409 hospitality.ticket_transition_invalid`.

### Website (machine credential)

`GET /menu`, `GET /menu/availability`, `POST /orders` — the published contract, cache policies and
client rules are in [docs/api.md](../api.md#the-property-website-contract).

### Error codes

| Code | HTTP | When |
|---|---|---|
| `hospitality.ticket_not_found` | 404 | unknown ticket in this tenant |
| `hospitality.ticket_transition_invalid` | 409 | not the next state in `TICKET_FLOW` |
| `hospitality.ticket_not_open` | 409 | adding lines after the ticket fired |
| `hospitality.ticket_empty` | 422 | firing a ticket with no lines |
| `hospitality.no_lines` | 422 | an empty `lines` body |
| `hospitality.status_not_advanceable` | 422 | `/advance` asked for fire or settle |
| `hospitality.item_unavailable` | 422 | an 86'd dish, or a countdown burn larger than the count. `details.item_ids` |
| `hospitality.item_not_found` | 422 | an item id that is not in this tenant. `details.item_ids` |
| `hospitality.item_not_priced` | 422 | no active GENERAL price list prices it today, or its only price is in another currency. `details.item_ids` |
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
