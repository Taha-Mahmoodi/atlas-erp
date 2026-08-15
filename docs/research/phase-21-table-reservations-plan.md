# Phase 21 — Restaurant Table Reservations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`
> (recommended) or `superpowers:executing-plans`. Steps use checkbox (`- [ ]`) syntax.

**Goal:** A guest books a table on the property's website, the booking is gated by a pacing
counter that cannot oversell a service, and staff see the book, seat a party onto an order ticket,
and record no-shows — the reservation loop closed end to end on the Phase 18/19 rails.

**Architecture:** The Q3 pacing model verbatim: a per-15-minute-slot counter row
(`hsp_service_slot`) locked `with_for_update` in the booking transaction, copied in shape from
`backend/app/modules/inventory/service/stock_quants.py:62-118` — the same pattern Phase 20's room
allotment uses. A `table_reservation` document rides the existing document/doc-flow/numbering
core. The website endpoints extend `website_router.py` in the Q6 shape. **No table master, no
floor plan** — physical table assignment stays the revisable free-text `table_code` the ticket
already carries.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async, Alembic, Pydantic v2, pytest, `uv`.

**Spec:** [`hospitality-industry-plan.md`](./hospitality-industry-plan.md) Q3 (the pacing counter
and why per-table locking is wrong) and "The guest-facing surface" (the website-as-client
boundary); owner directive 2026-08-15 (Taha: the restaurant needs its reservation part). This
phase is **new scope relative to PLAN.md** — the phase number 21 is proposed, not reserved, and
PLAN.md stays untouched until Taha ratifies it (the field-force rule).

**Sequencing:** Independent of Phase 20 — it touches no finance code and no shipped module.
Recommended order: **before** Phase 20, because it extends the website loop Phase 19 just proved,
its failure modes are cheap, and the staff value is immediate. Nothing in it blocks on, or is
blocked by, Rooms & Folio.

## Global Constraints

- **D-003** portable: the counter CHECKs are plain `CHECK`, the lock is `with_for_update` ("PG row
  lock; SQLite no-op", D-020/D-036), races proven with pg-marked tests in the
  `test_availability_races.py` harness shape.
- **D-007** tenancy; **D-011** `run_in_uow`; **D-012** the reservation is a document (numbered,
  doc-flow); **D-013** idempotency key on the booking write.
- **Q1 boundary:** the website's *server* is the only client; the guest's browser never talks to
  Atlas. Guest identity, guest notification (email/SMS), and guest-facing cancel links are the
  website's problem — Atlas exposes tenant-scoped operations under the Phase 18 credential and
  trusts the website to have authenticated its guest.
- **PERFORMANCE §2/§6**: reads ≤3 queries and paginated; write budgets ratcheted in
  `backend/tests/perf/test_write_budgets.py`.

## The four findings that shape this phase

1. **Booking gates on pacing, not tables** (Q3). OpenTable and Resy cap *covers per 15-minute
   slot*; the physical table is a revisable soft assignment made after acceptance. So the unit of
   availability is a `(service_date, slot_start)` counter row, and "which table" is decided by a
   human at seating — exactly like Phase 20's rooms assigning physical rooms at check-in.
2. **No table master in v1.** Phase 19 already litigated this: `table_code` is free text because
   "a table master nothing else references would be config for its own sake"
   (`backend/app/modules/hospitality/models.py:168-170`). Pacing does not reference tables either.
   The master earns its existence the day a floor-plan UI or capacity-aware auto-assignment is
   built — record it as the named upgrade path, do not build it now.
3. **A missing slot row means DEFAULT capacity, not zero.** This is the one place the shape
   differs from the room allotment (where a missing date row legitimately reads "nothing on
   sale"). A restaurant's capacity is standing config; making every future slot a materialised row
   before anyone can book would be the grid-maintenance trap Q3 warns about, doubled. So:
   defaults live in one per-tenant settings row, and the slot row is **materialised lazily by the
   first booking's upsert-on-lock** (the `quant is None → session.add` branch,
   `stock_quants.py:104-113`). An explicit slot row exists only when booked against or when a
   manager overrides it — including `covers_max = 0` to close a slot.
4. **The counter only means something before the slot.** CANCELLED before `slot_start` gives the
   capacity back (decrement); NO_SHOW and any post-slot transition are bookkeeping and touch no
   counter — there is nothing left to resell. This is simpler than the rooms rule (where NO_SHOW
   deliberately keeps the count for the overbooking buffer) and each rule gets a named test so
   nobody "unifies" them later.

## File Structure

```
backend/app/modules/hospitality/
  models.py (or models/ if Phase 20's split landed first)   # + ReservationSettings, ServiceSlot,
                                                            #   TableReservation
  constants.py        # + statuses, permissions (hospitality.reservation.read|manage), error codes
  schemas.py          # + settings/slot/reservation schemas
  service/reservations.py    # settings, the pacing gate, transitions, seating
  queries.py          # + the slot-grid availability read (set-based, one query)
  router.py           # + staff endpoints
  website_router.py   # + availability read + booking write + cancel
backend/alembic/versions/00XX_hsp_table_reservations.py
backend/tests/modules/hospitality/test_table_reservations.py
backend/tests/modules/hospitality/test_reservation_pacing_races.py
backend/tests/perf/test_write_budgets.py                    # + booking ceiling
```

---

## Task 1: The write-budget ratchet (do this FIRST)

**Files:**
- Modify: `backend/tests/perf/test_write_budgets.py`

**Why first.** The Phase 19/20 convention, and this phase's own history argues for it: the
availability burn shipped per-row once and only the pre-existing flatness test caught it. The
booking write touches exactly one slot row regardless of party size or how full the night is —
pin that before the feature exists to pin it against.

- [ ] **Step 1:** Add `test_booking_a_table_is_flat_in_party_size_and_book_depth` in the house
      style (measure a party-of-2 booking on an empty night and a party-of-8 on a night with 50
      existing reservations; assert equality, then a ceiling on the measured number). It will not
      compile until Task 3 — write it `pytest.mark.skip` with the reason string
      `"Phase 21 Task 3"` and un-skip it there, so the ratchet's shape is reviewed first.
- [ ] **Step 2: Commit.**

---

## Task 2: Settings and the slot counter

**Files:**
- Modify: models home, `constants.py`, `schemas.py`
- Create: `backend/app/modules/hospitality/service/reservations.py`
- Create: `backend/alembic/versions/00XX_hsp_table_reservations.py`
- Test: `backend/tests/modules/hospitality/test_table_reservations.py` (settings + counter half)

**Interfaces:**
- `ReservationSettings` — one row per tenant (`tenant_unique()` on tenant alone): `service_open` /
  `service_close` (times), `default_covers_max`, `default_parties_max`, `min_party`, `max_party`,
  `booking_horizon_days`. The 15-minute slot width is a **constant**, not a setting — both vendors
  Q3 cites fix it, and a configurable grid would change the unique key's meaning under existing
  rows.
- `ServiceSlot` — `tenant_unique(service_date, slot_start)`, `covers_booked`/`covers_max`,
  `parties_booked`/`parties_max`, `CHECK (covers_booked >= 0)`,
  `CHECK (covers_booked <= covers_max)`, same pair for parties.
- `book_into_slot(session, tenant_id, service_date, slot_start, covers)` — THE gate, and its
  inverse `release_from_slot(...)`. Contract copied from `stock_quants.py:62-118` in shape: load
  the slot row `with_for_update`; if absent, materialise it from settings defaults
  (upsert-on-lock); pre-flight refuse `hospitality.slot_full` (422) when covers or parties would
  exceed max; the CHECK is the backstop, never the primary. Single-slot — no multi-row lock
  ordering to get wrong (a named difference from the rooms helper; a long meal spanning slots is
  out of scope, recorded below).
- Manager override: `PATCH` a slot's `covers_max`/`parties_max` (permission
  `hospitality.reservation.manage`); `covers_max = 0` closes the slot; an override below
  `covers_booked` is **refused**, not clamped — the manager sees the conflict instead of a
  constraint violation surfacing as a 500.

- [ ] **Step 1: failing tests** — defaults materialise on first touch; a booking outside
      `service_open/close` or past `booking_horizon_days` refused with its own code; slot-full
      refusal names covers vs parties in `details`; override-below-booked refused; closed slot
      refuses.
- [ ] **Steps 2–5: fail → implement → pass → commit.**

---

## Task 3: The `table_reservation` document

**Files:**
- Modify: models home, `constants.py`, `schemas.py`, `service/reservations.py`, `router.py`
- Test: `backend/tests/modules/hospitality/test_table_reservations.py`,
  `backend/tests/modules/hospitality/test_reservation_pacing_races.py`

**Interfaces:**
- `TableReservation` — a D-012 document (registered, numbered `RSV-…` via `core/numbering.py`,
  AuditMixin): `service_date`, `slot_start`, `party_size`, `guest_name`, `guest_contact` (one
  free-text field; structured phone/email parsing is the website's job), `notes`,
  `status: CONFIRMED → SEATED → COMPLETED | NO_SHOW | CANCELLED`, `ticket_id` FK set at seating.
  There is no TENTATIVE: passing the pacing gate **is** the confirmation — the OpenTable model,
  and the reason the gate lives inside the create transaction.
- Transitions and the counter (finding 4, each row a named test):

  | Transition | Counter effect |
  |---|---|
  | create (gate passes) | `covers_booked += party`, `parties_booked += 1` |
  | CANCELLED before slot_start | both decrement |
  | CANCELLED/NO_SHOW at-or-after slot_start | none |
  | SEATED / COMPLETED | none |
  | party-size change before slot_start | delta on covers, same locked row |
  | slot change before slot_start | release old slot + book new slot, one transaction |

- `seat_reservation(session, tenant_id, reservation_id, *, table_code, create_ticket=True)` —
  marks SEATED and opens an `OrderTicket` (`table_code` free text, `guest_count = party_size`)
  with a doc-flow link reservation → ticket, so the chain reservation → ticket → (Phase 20 folio
  line) renders in the document-flow viewer. Walk-ins need nothing: they are exactly the ticket
  Phase 19 already creates.

- [ ] **Step 1: failing tests** — the transition/counter matrix; seating creates the linked
      ticket; illegal jumps refused (`hospitality.reservation_not_transitionable`, the
      `TICKET_FLOW` idiom); plus the races:

```python
@pytest.mark.pg
async def test_two_bookings_racing_the_last_covers_serialize(...):
    """Slot has 4 covers left; two concurrent parties of 3 book. Exactly one confirms, the loser
    gets hospitality.slot_full — the row lock is the mechanism (SQLite no-op, D-003)."""

async def test_a_cancel_racing_a_booking_never_tears_the_counter(...):
    """Cancel decrements while a booking increments the same locked row; the counter ends
    exactly right on both engines — the CHECK pair is the backstop."""
```

- [ ] **Steps 2–4**, un-skipping and satisfying the Task 1 ratchet. **Step 5: Commit.**

---

## Task 4: The website surface

**Files:**
- Modify: `backend/app/modules/hospitality/website_router.py`, `queries.py`, `schemas.py`
- Test: `backend/tests/modules/hospitality/test_website_reservations.py`

**Interfaces:**
- `GET /reservation-availability?service_date=&party_size=` — the day's slot grid with a boolean
  `bookable` per slot (computed from materialised rows overlaid on settings defaults — **one
  set-based query plus the settings read**, never a per-slot loop), conditional GET with the same
  etag pattern as the menu read (`website_router.py:146-191`). Guarded by the Phase 18 credential
  scope the menu read uses (`hospitality.menu.read`'s website sibling — read the guard wiring at
  `website_router.py:94` and follow it; a new `hospitality.reservation.book` scope keeps the
  website key mintable at exactly the width it needs, D-069's narrowing rule).
- `POST /table-reservations` — D-013 idempotency key required; the pacing gate inside the
  transaction; 422 `hospitality.slot_full` is a **normal answer**, not an error state, and the
  response body carries the nearest bookable alternatives (same query as the grid read, so the
  website can offer "19:15 or 19:45 instead" without a second round trip).
- `POST /table-reservations/{id}/cancel` — the website cancels on the guest's behalf (Q1
  boundary: guest auth is the website's problem). Refuses after SEATED.

- [ ] **Step 1: failing tests** — grid read ≤3 queries with the budget asserted; etag stable
      until a booking lands, then moves; booking under a replayed idempotency key returns the
      original reservation; cancel releases within the window and refuses after seating; the
      website scope cannot call staff endpoints (the D-069 narrowing proof, same shape Phase 18
      tested).
- [ ] **Steps 2–5.**

---

## Task 5: The staff book

**Files:**
- Modify: `backend/app/modules/hospitality/router.py`, `queries.py`
- Test: extend `backend/tests/modules/hospitality/test_table_reservations.py`

**Interfaces:**
- `GET /reservations?service_date=&status=` — the book: paginated (D-014), ≤3 queries, ordered by
  `slot_start`; `hospitality.reservation.read`.
- `POST /reservations` — staff take a phone booking through the same `book_into_slot` gate (one
  gate, every writer — the availability-module lesson).
- `POST /reservations/{id}/seat` (body: `table_code`), `POST /reservations/{id}/no-show`,
  `POST /reservations/{id}/cancel` — the Task 3 transitions over HTTP;
  `hospitality.reservation.manage`.

- [ ] **Steps 1–5** in the established shape (permission-gated, error codes asserted, list budget
      pinned).

---

## Task 6: Documentation and recorded decisions

**Files:** `DECISIONS.md`, `docs/modules/hospitality.md`, `docs/api.md`, `PROGRESS.md`,
`docs/research/remaining-work-plan.md`

- [ ] DECISIONS entries: pacing-not-tables (pointing at Q3), the missing-row-means-default rule
      and why it inverts the room-allotment reading, the no-TENTATIVE call, no-table-master with
      its named upgrade path.
- [ ] `docs/modules/hospitality.md`: the reservation surface, the transition/counter matrix, new
      known limits (below) recorded not hidden. `docs/api.md`: the website scope for the operator
      flow.
- [ ] `PROGRESS.md` per task; propose the PLAN.md Phase 21 block for Taha to ratify (proposed
      text in the PR body, **not** committed to PLAN.md).

---

## Phase 21 done when

- [ ] Full suite green on SQLite and pg-marked subset; `ruff` clean; the booking budget holds
- [ ] Two parties racing the last covers: one confirms, one 422s (pg)
- [ ] The website books, is refused with alternatives when full, and cancels — all under the
      Phase 18 credential at reservation-only scope
- [ ] Staff see the book, seat a party onto a doc-flow-linked ticket, and record a no-show
- [ ] A manager can close a slot and cannot set capacity below what is already booked

## Explicitly not in Phase 21

- **A table master / floor plan / capacity-aware auto-assignment** — the named upgrade path;
  `table_code` stays free text until a floor-plan UI exists to reference it.
- **Deposits and no-show fees** — they need Phase 20's `apply_receipt` and an online payment
  provider; wiring guest money before those exist would rebuild both badly.
- **Waitlists**, **multi-slot pacing for long meals** (a booking consumes its arrival slot only —
  the OpenTable semantics), **guest notifications** (the website's job, Q1 boundary).
- **PLAN.md edits** — proposed in the PR body for Taha's ratification.

## Self-review

Every writer routes through `book_into_slot`/`release_from_slot` (Tasks 3, 4, 5 all name them);
the counter matrix appears once (Task 3) and the other tasks reference it; names used across
tasks match: `hospitality.slot_full` (2→4), `seat_reservation` (3→5), `ReservationSettings`
defaults (2→4's grid overlay). The Q3 mechanism citation (`stock_quants.py:62-118`) matches the
one Phase 20's Task 4 copies — one pattern, three counters.
