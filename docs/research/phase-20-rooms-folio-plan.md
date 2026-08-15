# Phase 20 — Rooms & Folio Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`
> (recommended) or `superpowers:executing-plans`. Steps use checkbox (`- [ ]`) syntax.

**Goal:** A property can take a deposit, confirm a reservation without double-selling a room type,
check a guest in, accumulate room-nights and restaurant charges on a folio, run a night audit that
posts room revenue per night, and settle the folio — with every posting landing in the Universal
Journal on the correct business date.

**Architecture:** Counter-gated booking copied from `apply_bin_delta`'s shape; a folio as the
running multi-charge document; the night audit as a set-based idempotent job in the
depreciation-run shape; deposits via a widened `CustomerReceipt` (an unapplied/on-account receipt)
in **finance**, so hospitality writes zero clearing code. The restaurant settlement money path that
Phase 19 deferred lands here, on the folio that owns the money.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async, Alembic, Pydantic v2, pytest, `uv`.

**Spec:** [`hospitality-industry-plan.md`](./hospitality-industry-plan.md) Q3 (overbooking) and Q5
(folio, deposits, business date, night audit); PLAN.md Phase 20 (20.1–20.6); the Phase 19 cut
record in `docs/modules/hospitality.md` §6 items 3, 4 and 6 (tax, split checks/payment, move-date
vs business date).

## Global Constraints

- **D-003** portable constraints: SQLite suite, PostgreSQL runtime. No exclusion constraints, no
  Postgres-only guards for correctness invariants (Q3 rejects `EXCLUDE USING gist` on exactly this
  ground). `with_for_update` is sanctioned as "PG row lock; SQLite no-op" (D-020/D-036) with
  deterministic lock ordering.
- **D-007** tenancy on every table; `tenant_unique` for per-tenant uniqueness.
- **D-011** every money-touching flow runs in `run_in_uow`; **`MAX_DISPATCHES_PER_UOW = 50`**
  (`backend/app/core/events.py:61`) — the night audit and group-folio split must be set-based, one
  or two events per run, never one per reservation.
- **D-012** reservations, folios and housekeeping tasks are documents: registered in
  `core_documents`, numbered, doc-flow linked.
- **Table args**: follow the repo's composite-unique convention — an explicitly NAMED `sa.UniqueConstraint("tenant_id", ...)` **plus** a bare `tenant_unique()` and `tenant_fk("adm_tenants")` in `__table_args__`; `tenant_unique()` takes NO arguments (it is UNIQUE(tenant_id, id) for composite FKs, `core/models.py:104-109`) and any other tenant-leading unique needs its own name or the D-022 naming convention collides. Precedent: `hospitality/models.py:71-84`.
- **D-013** idempotency keys on every endpoint that creates a financial or stock document — but
  D-013 guards the *transport*; the night audit's data-level dedup is a unique index (Q5).
- **PERFORMANCE §2/§6** list endpoints ≤3 queries, paginated; write paths ratcheted in
  `backend/tests/perf/test_write_budgets.py` (the Phase 19 convention).
- **STRUCTURE §8.4** 400-line Python cap. Rooms & Folio is its own service package under
  `backend/app/modules/hospitality/` — plan the split up front, not after the cap trips.
- **Promotion gate (remaining-work-plan §P3):** Task 2 changes shipped finance. This phase lands in
  `dev` and is **reviewed by Taha before any promotion to `main`** — unlike Phases 18/19.

## The four findings that shape this phase

1. **A folio has three posting moments, not one** (Q5): deposit pre-arrival (Dr Bank / Cr Advance
   Deposits — a liability), room+tax **per night** by the night audit (Dr Guest Ledger / Cr Room
   Revenue + Cr Occupancy Tax), and settlement at checkout, which is a *clearing* event, not the
   revenue event. Any task that lets settlement post revenue re-introduces the first draft's bug.
2. **Atlas has no advance-deposit primitive, and both workarounds are dead ends** (Q5, verified
   against `customer_receipts.py:66-90`, `credit_notes.py:160`). The only correct home is a widened
   `CustomerReceipt` in finance. This is the phase's riskiest change and goes second, behind its
   regression net, so everything after it builds on reviewed ground.
3. **Booking is a counter, not an interval lock** (Q3): rooms sell by room type against a per-date
   allotment row, physical room assigned at check-in. The mechanism to copy verbatim in shape is
   `backend/app/modules/inventory/service/stock_quants.py:62-118` — locked read, pre-flight
   negative-delta rejection, upsert-on-lock for a missing row, portable CHECK backstop.
4. **The business date is not a clock** (Q5): it is the *source* of `posting_date`, rolled by the
   night audit, monotonic, per-tenant; the fiscal period is the *authorisation window*. The
   month-end hazard is real and pre-existing: `assert_period_closable`
   (`backend/app/modules/finance/service/periods.py:197-209`) lets January close with Jan-31's
   audit never run, and the catch-up then trips `ATLAS_PERIOD_CLOSED`. This phase extends that
   guard.

## File Structure

```
backend/app/modules/hospitality/
  models.py                      # + Room-side models IF the cap allows; otherwise models/ package:
  models/                        #   split into ordering.py (Phase 19 models) + rooms.py + folio.py
  constants.py                   # + reservation/folio/housekeeping statuses, permissions, job names
  service/
    rooms.py                     # room_type / room / rate_plan / housekeeping_task CRUD
    reservations.py              # booking gate + reservation transitions + the allotment helper
    folio.py                     # folio lifecycle, folio lines, settlement clearing
    night_audit.py               # business date + the audit job handler
    tickets.py                   # MODIFIED: settle gains the money path (Task 8)
  router.py                      # + staff endpoints for all of the above
  website_router.py              # + room availability read + room booking write (same Q6 shape)
  handlers.py                    # + RestaurantOrderSettled → folio_line (the bridge)
backend/app/modules/finance/
  service/customer_receipts.py   # MODIFIED: unapplied receipts + apply_receipt (Task 2)
  models/receipts.py             # MODIFIED: unapplied_amount column
backend/alembic/versions/        # 3 migrations: receipts widening; rooms+reservation+counter;
                                 # folio+business-date+housekeeping
backend/tests/modules/hospitality/   # per-service test files, race tests pg-marked where Q3 says
backend/tests/modules/finance/       # receipt-widening regression + new-behaviour tests
backend/tests/perf/test_write_budgets.py  # + booking / night-audit / settlement ceilings
```

Migration count is three, grouped by task boundary, so a revert of the risky finance change never
drags module tables with it.

---

## Task 1: The regression net around `CustomerReceipt` (do this FIRST)

**Files:**
- Create: `backend/tests/modules/finance/test_receipt_regression_pins.py`
- Modify: `backend/tests/perf/test_write_budgets.py`

**Why first.** Task 2 rewrites the validation spine of a shipped, seeded, order-to-cash-driven
financial path (`backend/app/modules/finance/handlers/order_to_cash.py` drives it; the seed data
exercises it). Q5 is blunt: it "needs regression coverage on the existing invoice→receipt flow, not
just new tests." The pins land before the change so the change's diff cannot quietly move them.

**Interfaces:**
- Consumes: existing finance fixtures (read `backend/tests/modules/finance/` conftest and an
  existing receipts test first; use the repo's real fixture names).
- Produces: behaviour pins Task 2 must keep green, and a write-budget ceiling for one
  invoice+receipt+clearing round trip.

- [ ] **Step 1: Write the pins against TODAY's behaviour.** One test per currently-enforced rule,
      asserting the exact error codes:

```python
async def test_a_receipt_with_no_allocations_is_refused_today(...):
    """Pins finance.receipt_no_allocations (customer_receipts.py:66-70). Task 2 RELAXES this rule
    deliberately — when it does, this test is UPDATED IN THE SAME COMMIT to assert the new
    contract (unapplied receipt accepted, unapplied_amount == amount), never deleted."""

async def test_allocations_must_reference_posted_invoices_of_the_same_partner(...):
    """Pins customer_receipts.py:72-90. Task 2 must NOT relax this — an applied allocation keeps
    every existing rule."""

async def test_receipt_amount_must_equal_allocation_sum_today(...):
    """Pins customer_receipts.py:186-190. Task 2 changes '==' to '>=' (the excess becomes
    unapplied); the updated pin asserts over-allocation is still refused."""
```

- [ ] **Step 2: Add the write-budget ceiling** for invoice → receipt → cleared, measured today, in
      the `test_write_budgets.py` house style (measure, then set ceiling to measured + small
      headroom, comment the measured number).
- [ ] **Step 3: Run the full finance suite; record the count in the commit body** so the Task 2 PR
      can show it unchanged. **Step 4: Commit.**

```bash
git commit -m "test(finance): pin CustomerReceipt behaviour before the deposit widening

Phase 20 Task 2 relaxes the no-allocations rule; these pins make every
OTHER receipt rule a named test so the diff cannot move one silently."
```

---

## Task 2: Unapplied receipts — the finance widening (PLAN 20.4)

**Files:**
- Modify: `backend/app/modules/finance/service/customer_receipts.py`
- Modify: `backend/app/modules/finance/models/receipts.py` (find the real file with
  `grep -rn "class CustomerReceipt" backend/app/modules/finance/models/`)
- Modify: `backend/app/modules/finance/schemas.py` (receipt create/apply schemas)
- Create: `backend/alembic/versions/00XX_receipt_unapplied.py`
- Test: `backend/tests/modules/finance/test_unapplied_receipts.py`

**Interfaces:**
- Produces: `CustomerReceipt.unapplied_amount: Decimal` (MoneyType, default 0);
  `create_receipt(...)` accepting `allocations: list[...] = []` where the shortfall between
  `amount` and the allocation sum becomes `unapplied_amount`, credited to a configurable
  advance/on-account control account with `partner_type`/`partner_id` stamped on the journal line
  (`fin_journal_lines` already carries both — `models/journal.py:155-157`, no new column);
  `apply_receipt(session, tenant_id, receipt_id, allocations) -> CustomerReceipt` that moves
  unapplied → allocated, reusing the existing `clearing_fx` helper verbatim.
- Consumes: the advance/on-account control account comes from posting defaults — follow the
  existing pattern for `ar_account_id` resolution (read how the AR control is configured before
  inventing a mechanism; the industry template's COA already seeds an Advance Deposits liability
  account for hospitality).

**Design rails (from Q5 — the plan argues from these, do not re-litigate):**
- An *applied* allocation keeps every existing rule: POSTED/PARTIALLY_PAID invoice, same partner,
  same currency.
- `amount >= sum(allocations)`; the excess is `unapplied_amount`. `amount < sum` stays refused.
- `apply_receipt` refuses to apply more than `unapplied_amount`, refuses cross-partner and
  cross-currency exactly as `create` does, posts the reclass journal (Dr Advance control / Cr AR
  control clearing) through the same `clearing_fx` path, and is idempotency-keyed (D-013 — it
  creates a financial document effect).
- A folio-owned deposit table was **rejected** (two clearing engines rot); do not add one.

- [ ] **Step 1: Write the failing tests**

```python
async def test_an_allocationless_receipt_posts_to_the_advance_control_with_partner_stamped(...):
    """Dr Bank / Cr Advance control; the credit line carries partner_type/partner_id so the
    control reconciles per guest. unapplied_amount == amount; the receipt is queryable as the
    partner's on-account balance."""

async def test_a_partially_allocated_receipt_splits_ar_and_advance(...):
    """amount 500, allocations 300 → 300 clears the invoice exactly as today, 200 lands unapplied."""

async def test_apply_receipt_moves_unapplied_to_a_posted_invoice(...):
    """apply_receipt(...) drops unapplied_amount, clears the invoice, reuses clearing_fx (assert
    the FX treatment matches a direct allocation of the same amounts to the digit)."""

async def test_apply_receipt_refuses_more_than_the_unapplied_balance(...):
async def test_apply_receipt_refuses_a_cross_partner_invoice(...):
async def test_over_allocation_is_still_refused(...):
async def test_partner_ledger_shows_the_unapplied_balance(...):
    """partner_ledger derives from rows, not journal lines (partner_ledger.py:24-90) — the
    unapplied receipt must surface there or the deposit is invisible to AR."""
```

- [ ] **Step 2: Run — all fail.** **Step 3: Implement** (service + column + migration + schema),
      updating the Task 1 pins that deliberately change *in the same commit*.
- [ ] **Step 4: Run the ENTIRE finance suite + seed + order-to-cash tests, and the Task 1 write
      budget — the count must be unchanged for the allocated path.** **Step 5: Commit**, PR body
      explicitly flagging this as the shipped-finance change requiring Taha's review.

---

## Task 3: Rooms masters (PLAN 20.1)

**Files:**
- Create: `backend/app/modules/hospitality/service/rooms.py`
- Modify: `backend/app/modules/hospitality/models.py` — **first check the cap**: `wc -l` it; Phase
  19 left it near the 400 line ceiling, and this phase adds ~8 models. If it cannot take them,
  split into a `models/` package (`ordering.py` + `rooms.py` + `folio.py`) in a separate
  no-behaviour-change commit *before* adding anything (#176 already tracks cap debt; do not add to
  it).
- Modify: `backend/app/modules/hospitality/constants.py`, `schemas.py`, `router.py`
- Create: `backend/alembic/versions/00XX_hsp_rooms.py` (shared with Task 4's tables)
- Test: `backend/tests/modules/hospitality/test_rooms.py`

**Interfaces:**
- Produces: `RoomType` (code, name, base capacity), `Room` (number, room_type FK,
  `housekeeping_status: DIRTY|IN_PROGRESS|CLEAN|INSPECTED|OUT_OF_ORDER`), `RatePlan` (room_type FK,
  nightly amount MoneyType, currency — manual in v1, no date ranges beyond a validity window),
  `HousekeepingTask` — a **document** (D-012): room FK, trigger `CHECKOUT|SCHEDULED|GUEST_REQUEST`,
  assigned user, status flow. Permissions `hospitality.rooms.read` / `hospitality.rooms.manage` /
  `hospitality.housekeeping.manage` in the Phase 19 naming shape (`constants.py:115-119`).
- Standard tenant-scoped CRUD in the house style — copy the anatomy of an existing master's
  service/router/tests rather than inventing one.

- [ ] **Step 1: failing tests** (creation, uniqueness per tenant, status transitions on
      housekeeping, permission gating, list pagination ≤3 queries). **Steps 2–5:** fail →
      implement → pass → commit.

---

## Task 4: The booking gate and the reservation document (PLAN 20.2)

**Files:**
- Create: `backend/app/modules/hospitality/service/reservations.py`
- Modify: `models` (Task 3's home), `constants.py`, `schemas.py`, `router.py`,
  `website_router.py`
- Test: `backend/tests/modules/hospitality/test_reservations.py`,
  `backend/tests/modules/hospitality/test_reservation_races.py` (pg-marked where the row lock is
  the guarantee), `backend/tests/perf/test_write_budgets.py` (booking ceiling)

**Interfaces:**
- Produces: `hsp_room_type_inventory` — unique on `(tenant_id, room_type_id, stay_date)`, columns
  `rooms_sellable`/`rooms_sold`/`overbooking_limit`, `CHECK (rooms_sold >= 0)` and
  `CHECK (rooms_sold <= rooms_sellable + overbooking_limit)`; `Reservation` document —
  `TENTATIVE → CONFIRMED → CHECKED_IN → CHECKED_OUT | NO_SHOW | CANCELLED`, room_type FK, stay
  range, party, rate_plan FK, optional physical `room_id` assigned at check-in;
  `adjust_allotment(session, tenant_id, room_type_id, stay_dates, delta)` — the one helper every
  counter touch routes through.
- The counter contract (Q3, copied from `stock_quants.py:62-118` in shape): rows locked
  `with_for_update` in **ascending `stay_date` order**, missing row upserts on lock from
  `rooms_sellable` = count of non-OUT_OF_ORDER rooms of that type, pre-flight rejection with its
  own error code (`hospitality.room_type_sold_out`, 422) before the CHECK backstop, the lock taken
  as the **first** write in the `run_in_uow` body.
- Counter discipline per transition — each is a named test: CONFIRM increments N nights; CANCEL
  decrements; **NO_SHOW does not decrement** (the no-show buffer is why `overbooking_limit`
  exists); date change = decrement old rows + increment new rows in one transaction, both row sets
  locked in one ascending pass; `Room.housekeeping_status → OUT_OF_ORDER` decrements
  `rooms_sellable` on the affected future dates, and back.

- [ ] **Step 1: failing tests** — the transition/counter matrix above, plus:

```python
@pytest.mark.pg
async def test_two_concurrent_bookings_of_the_last_room_serialize(...):
    """Two sessions book the last sellable room-night concurrently; exactly one confirms, the
    loser gets hospitality.room_type_sold_out. The row lock is the mechanism (SQLite no-op,
    D-003) — same harness shape as test_availability_races.py."""

@pytest.mark.pg
async def test_two_multi_night_bookings_lock_dates_in_the_same_order(...):
    """Overlapping stays lock ascending stay_date — the deadlock test, per D-020/D-036."""

async def test_a_missing_allotment_row_upserts_rather_than_reading_zero(...):
    """Q3's named hidden cost: a date outside the materialised grid must not silently refuse."""
```

- [ ] **Step 2–4: fail → implement → pass** (service, document registration, staff endpoints,
      website booking endpoint in the Q6 shape: D-013 idempotency, acknowledgment flag semantics
      copied from `place_website_order`, `website_router.py:224`). Add the booking write-budget
      ceiling: a 3-night booking and a 14-night booking differ by exactly the counter rows — pin
      flatness of everything else, the Phase 19 lesson.
- [ ] **Step 5: Commit.**

---

## Task 5: The folio (PLAN 20.3)

**Files:**
- Create: `backend/app/modules/hospitality/service/folio.py`
- Modify: models home, `constants.py`, `schemas.py`, `router.py`
- Create: `backend/alembic/versions/00XX_hsp_folio.py` (shared with Tasks 6–7's tables)
- Test: `backend/tests/modules/hospitality/test_folio.py`

**Interfaces:**
- Produces: `Folio` document (predecessor = reservation when one exists; walk-in restaurant folios
  have none), status `OPEN → SETTLED | TRANSFERRED`; `FolioLine` — heterogeneous charges,
  `charge_type: ROOM_NIGHT | RESTAURANT | INCIDENTAL | TAX | DEPOSIT_APPLIED`, amount, tax code,
  `source_document_id` doc-flow link, `business_date` (nullable until Task 6 exists, then
  required); partial unique index `(tenant_id, reservation_id, business_date) WHERE charge_type =
  'ROOM_NIGHT'` — the night audit's idempotency backbone (Q5). Partial indexes are portable and
  already used here: declare BOTH `postgresql_where=` and `sqlite_where=`, the
  `core/docflow.py:71-72` precedent.
- Folio settlement is a **clearing** event (finding 1): cash/card → Dr Bank / Cr Guest Ledger,
  never touching AR; direct-bill → materialise a real `CustomerInvoice` (Dr AR control / Cr Guest
  Ledger) so `ar_aging` and `dunning` see it (Q5's city-ledger transfer). Deposit application at
  check-in/settlement calls Task 2's `apply_receipt` — **zero clearing code here**.
- The Guest Ledger control is a new asset account seeded by the hospitality template's COA;
  reconciliation to folios rides `partner_type`/`partner_id` on journal lines, no new column.

- [ ] **Step 1: failing tests** — folio opens on check-in with the reservation as predecessor;
      lines link their source documents; settlement of a cash folio posts the clearing entry and
      no revenue; direct-bill settlement creates the invoice AND ages; a deposit taken pre-arrival
      applies at settlement through `apply_receipt` and the guest pays only the remainder;
      a folio with unposted room nights refuses settlement (`hospitality.folio_unaudited_nights`).
- [ ] **Steps 2–5: fail → implement → pass → commit.**

---

## Task 6: The business date (PLAN 20.5a)

**Files:**
- Create: `backend/app/modules/hospitality/service/night_audit.py` (date half)
- Modify: models home; `backend/app/modules/finance/service/periods.py` (one added assertion)
- Test: `backend/tests/modules/hospitality/test_business_date.py`,
  `backend/tests/modules/finance/test_period_close_guard.py`

**Interfaces:**
- Produces: `hsp_business_dates` — unique on `(tenant_id, business_date)`, `status OPEN|AUDITED`,
  `journal_entry_id` FK (the audit's grouped entry), AuditMixin. One table, three jobs: current
  business date (the single OPEN row), monotonicity backstop (roll refuses backwards/skip), audit
  run record (Q5's `fin_depreciation_runs` shape).
- `current_business_date(session, tenant_id) -> date` — the source of `posting_date` for every
  hospitality posting; **never `date.today()`** (the ~20-site `date.today()` defect is
  pre-existing, cross-module, and explicitly NOT this phase's to fix — file/point to its own
  issue).
- Extends `assert_period_closable` (`periods.py:197-209`): refuse closing a fiscal period that
  contains an OPEN (unaudited) hospitality business date — Q5's month-end hazard. Guarded to
  tenants that have any `hsp_business_dates` row at all, so non-hospitality tenants close exactly
  as today (a named regression test).

- [ ] **Step 1: failing tests** — roll advances exactly one day; backwards/skip refused; the
      period-close guard refuses with an unaudited Jan-31 inside January and passes once AUDITED;
      a tenant with no business dates closes periods exactly as before.
- [ ] **Steps 2–5.** The `periods.py` change ships in the same commit as its regression test.

---

## Task 7: The night audit job (PLAN 20.5b) and group bookings (20.5c)

**Files:**
- Modify: `backend/app/modules/hospitality/service/night_audit.py`, `constants.py` (job name),
  `handlers.py` (job registration), `router.py` (the manual trigger endpoint)
- Test: `backend/tests/modules/hospitality/test_night_audit.py`,
  `backend/tests/perf/test_write_budgets.py` (audit ceiling)

**Interfaces:**
- Produces: `NIGHT_AUDIT_JOB` on the existing runner (`core/jobs.py`), **manually triggered in v1**
  (Q5: no scheduler exists; Phase 18's credential makes an external cron possible later — out of
  scope here); `run_night_audit(session, tenant_id, business_date)`.
- The audit, in the depreciation-run shape (Q5 maps it one-for-one to
  `service/depreciation.py:98-191`): set-based NOT-EXISTS anti-join finds checked-in reservations
  missing their ROOM_NIGHT folio line for the date; inserts lines (rate from the rate plan, tax
  from the template's occupancy tax code); posts **one grouped journal entry** (Dr Guest Ledger /
  Cr Room Revenue + Cr Occupancy Tax, `posting_date` = the business date being closed); marks the
  date AUDITED with the entry id; rolls the next date OPEN. **One or two events for the whole
  run** — `MAX_DISPATCHES_PER_UOW = 50` makes per-reservation events a lost night above 50
  occupied rooms.
- Group bookings: `RoomBlock` (room_type, date range, blocked count, cutoff date) holds allotment
  via the same Task 4 counter (block = increment `rooms_sold`, release at cutoff = decrement); a
  master folio flagged on the block absorbs group charges; settlement splits back to individual
  folios or bills the organizer as one direct-bill settlement (Task 5's path). Splitting is a
  folio-line transfer inside one uow — set-based, bounded events.

- [ ] **Step 1: failing tests**

```python
async def test_the_audit_posts_one_room_night_per_checked_in_reservation(...):
async def test_a_rerun_picks_up_only_what_was_missed(...):
    """Kill the first run after N of M lines (the depreciation no-op-rerun shape): the rerun
    inserts M-N, never duplicates — the partial unique index is the backbone, D-013 only the
    transport."""
async def test_two_concurrent_runs_collide_at_the_index_not_the_ledger(...):
async def test_the_audit_posts_one_grouped_journal_entry(...):
    """60 occupied rooms → one entry, ~60+2 lines, ≤2 events — asserted, because >50 dispatches
    kills the uow (events.py:61)."""
async def test_an_audit_never_run_blocks_the_period_close(...):   # ties Task 6 to Task 7
async def test_a_room_block_holds_and_releases_allotment_at_cutoff(...):
async def test_a_master_folio_splits_back_at_settlement(...):
```

- [ ] **Steps 2–5**, including the audit write-budget ceiling (flat in reservations count for the
      query side; line inserts are the only growing term — assert the shape, the Phase 19 lesson).

---

## Task 8: Restaurant settlement money path + the room-charge bridge (PLAN 20.6, Phase 19 cuts)

**Files:**
- Modify: `backend/app/modules/hospitality/service/tickets.py` (settle), `handlers.py` (the
  bridge), `schemas.py`, `router.py`
- Test: `backend/tests/modules/hospitality/test_settlement_money.py`

**Interfaces:**
- `settle_ticket` gains a settlement instruction:
  `{method: CASH | CARD | CHARGE_TO_ROOM, folio_id?: uuid, splits?: [...]}`.
- **CHARGE_TO_ROOM** (the bridge): validates the folio is OPEN and belongs to a CHECKED_IN
  reservation, then publishes `RestaurantOrderSettled`; the folio handler appends a `FolioLine`
  (charge_type RESTAURANT, doc-flow link back to the ticket). Same event shape as
  `SalesOrderShipped` — one event, two handlers, no new mechanism.
- **CASH/CARD** (direct): settles like a small POS sale reusing Sales' invoice/payment primitives
  (read `backend/app/modules/sales/service/billing.py` first and reuse, not re-implement), which
  closes §6 limit 3: **tax is computed at settlement** from the template's F&B tax code, so the
  amount due is no longer pre-tax.
- **Split checks** (§6 limit 4): per-seat or per-item split at settlement — N splits produce N
  settlements against one ticket, each with its own method; the split must cover every line
  exactly once (a refusal code for gaps/overlaps: `hospitality.split_incomplete`).
- The ticket's depletion move date and folio line stamp `current_business_date` (§6 limit 6
  closes).
- **Not here:** the ONLINE_CARD payment-provider interface. It is guest-money plumbing with its
  own webhook/PCI surface — split it to its own follow-up phase; record the cut in
  `s4hana-parity.md` per the scope-cut rule. v1 settlement methods are CASH, CARD (captured
  outside Atlas), CHARGE_TO_ROOM.

- [ ] **Step 1: failing tests** — charge-to-room appends the folio line with the doc-flow link;
      a SETTLED folio refuses new charges; direct settle posts invoice+payment with tax; split by
      seat covers all lines or refuses; business date stamped throughout.
- [ ] **Steps 2–5.**

---

## Task 9: Website surface for rooms (Q6 shape)

**Files:**
- Modify: `backend/app/modules/hospitality/website_router.py`, `queries.py`
- Test: `backend/tests/modules/hospitality/test_website_rooms.py`

**Interfaces:**
- `GET /website/room-availability?from=&to=&party=` — room types with per-date availability from
  the Task 4 counter, conditional GET with the same etag pattern as the menu read
  (`website_router.py:146-191`), ≤3 queries, paginated.
- `POST /website/room-bookings` — creates a TENTATIVE reservation under D-013 idempotency, the
  acknowledgment-flag semantics of `place_website_order` (an external client never silently skips
  a human check). Deposit-taking on booking is **out** until the payment provider exists; a
  booking confirms manually (staff) or by recorded deposit (Task 2's receipt referencing the
  reservation).

- [ ] **Steps 1–5** in the established shape.

---

## Task 10: Documentation and recorded decisions

**Files:** `DECISIONS.md`, `docs/modules/hospitality.md`, `docs/research/s4hana-parity.md`,
`PROGRESS.md`, `docs/research/remaining-work-plan.md`

- [ ] DECISIONS entries: the unapplied-receipt widening (and that a hospitality-local deposit
      table was rejected); the counter-not-exclusion booking gate (pointing at Q3); the business
      date/fiscal period two-layer rule; the night-audit idempotency backbone; ONLINE_CARD
      deferred.
- [ ] `docs/modules/hospitality.md`: §6 limits 3, 4, 6 marked resolved with pointers; new limits
      added honestly (manual night audit, no online payment, no dynamic pricing).
- [ ] Parity doc: ONLINE_CARD cut recorded. `PROGRESS.md` one line per task as they land.

---

## Phase 20 done when

- [ ] Full suite green on SQLite and the pg-marked subset; `ruff` clean; write budgets hold
- [ ] The Task 1 pins pass in their updated form; the allocated-receipt path's budget unchanged
- [ ] Two concurrent last-room bookings: one wins, one 422s (pg)
- [ ] A killed night audit reruns to exactly-once room nights; January cannot close with Jan-31
      unaudited
- [ ] A deposit taken pre-arrival settles a folio through `apply_receipt` with no hospitality
      clearing code
- [ ] A restaurant ticket charges to a room with a doc-flow chain ticket → folio line
- [ ] Split checks cover-all-lines-or-refuse; settled totals include tax
- [ ] **Taha has reviewed the finance diff before any dev → main promotion**

## Explicitly not in Phase 20

- ONLINE_CARD payment provider (own phase; cut recorded in parity doc)
- Unattended 3am night audit (needs a scheduler; Phase 18's credential + external cron later)
- Dynamic/algorithmic pricing, OTA/channel sync, loyalty (spec out-of-scope list)
- The `date.today()`/tenant-timezone defect (pre-existing, cross-module, its own issue)
- Table reservations (its own plan: `phase-21-table-reservations-plan.md`)

## Self-review

Checked against PLAN.md 20.1–20.6: 20.1→Task 3, 20.2→Task 4, 20.3→Task 5, 20.4→Task 2,
20.5→Tasks 6–7, 20.6→Task 8. Checked against Q5's three posting moments: deposit→Task 2,
per-night→Task 7, settlement-as-clearing→Task 5. Phase 19 §6 cuts: tax→Task 8, split
checks/payment→Task 8 (provider deferred, recorded), move-date→Tasks 6/8. Names used across tasks:
`apply_receipt` (2→5), `adjust_allotment` (4→7 blocks), `current_business_date` (6→7/8),
`hospitality.room_type_sold_out` (4→9).
