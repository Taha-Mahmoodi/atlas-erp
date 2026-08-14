# Phase 19 — Restaurant Ordering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`
> (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** A restaurant runs its menu, orders and ingredient depletion in Atlas, with the property's
own website reading the menu and posting orders over the Phase 18 API credential.

**Architecture:** A new `hospitality` module. Menu items are existing inventory `Item` rows with a
manufacturing BOM for the recipe — no new item entity. Availability is **stored state**, not derived
(the recipe math is demoted to a staff-facing suggestion). Ingredient depletion moves **off the
settle transaction** onto the existing job runner and fires at **send-to-kitchen**, not at tender.
The website talks to two read endpoints with different cache policies plus one idempotent write.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async, Alembic, Pydantic v2, PostgreSQL
(SQLite for tests), pytest. Managed with `uv`.

**Spec:** [`hospitality-industry-plan.md`](./hospitality-industry-plan.md) — Q2 (availability), Q4
(depletion), Q6 (website read path). This plan argues from those three sections; executors read both
documents. Every measured number below comes from Q4, which was measured with the repo's own
`query_counter` fixture rather than estimated.

**Status:** Committed scope. `PLAN.md` Phase 19. Phase 18 (the machine credential) is merged to
`dev` and is a hard prerequisite — the website cannot authenticate without it.

## Global Constraints

Every task's requirements implicitly include this section.

- **D-003** portable constraints (tests SQLite, runtime PostgreSQL).
- **D-007** tenancy via the non-bypassable session filter; no new `system_context()` site.
- **D-009** RBAC keys are code-declared; new keys register in the catalog.
- **D-011** the event bus is in-process, synchronous, in-transaction, all-or-nothing.
- **D-013** idempotency keys on every endpoint creating a financial or stock document.
- **D-014** cursor pagination, `MAX_LIMIT = 200` (`core/pagination.py:49`).
- **D-015** money crosses the wire as a decimal **string**, never a float.
- **PERFORMANCE.md** ≤3 queries per list request.
- **STRUCTURE.md** 400-line Python cap; module anatomy `models/ schemas/ service/ router.py
  events.py queries.py constants.py`; terminology lock (`item`, `vendor`, `customer`, `warehouse`,
  `journal entry`).
- **Definition of done** (CLAUDE.md §5): code, tests passing, committed, logged in `PROGRESS.md`,
  plus the PERFORMANCE §6 checklist for endpoints.

## The three findings that shape this phase

Read these before writing code; they are why the obvious implementation is wrong.

1. **Availability cannot be derived (Q2).** `atp_check` costs 3 queries per item, so a 60-item menu
   at ~6 components is ~1,080 queries — 360× over budget. Its formula is
   `on_hand − committed + on_order`, so an open PO for tomatoes makes tonight's dish read available.
   And decisively, the **ETag trap**: `collection_etag` (`core/conditional.py:65-93`) is
   `COUNT(id), MAX(updated_at)`, so selling the last portion moves no `Item.updated_at` and the
   website keeps receiving a **304 asserting a sold-out dish is available**. Stored state on a row
   the ETag aggregates over invalidates correctly and for free.
2. **Synchronous depletion breaks in three measured ways (Q4).** One ingredient ISSUE move costs
   **38 SQL statements**; 24 lines costs **911 statements / 690 ms**. `MAX_DISPATCHES_PER_UOW = 50`
   (`core/events.py:61`) counts handler *invocations*, so **51 lines raise `EventCycleError` → HTTP
   500** and an 8-top ordering 8 dishes at 7 ingredients is 56 lines — *the guest cannot pay their
   bill*. A missing ingredient raises `InsufficientStockError` and D-011 rolls back the whole uow,
   so **phantom stock-outs refuse the payment** — and restaurant theoretical stock is *known* to be
   2–5% wrong by the industry's own benchmark. Numbering row locks are held to COMMIT by
   construction (D-012 gaplessness), so a long settlement serializes every other posting in the
   tenant **including the hotel's**.
3. **`Item.is_active` is not the answer (Q2).** It is filter-only — read in exactly two places, and
   `item_exists` (`inventory/queries.py:48-55`) never checks it, which is the validator both sales
   order lines and BOM components call. An inactive item can be ordered and BOM'd today. It also
   carries `AuditMixin`, so every 86 would write an audit row for a toggle a kitchen flips dozens of
   times a night.

## File Structure

New module `backend/app/modules/hospitality/`, following STRUCTURE's anatomy.

| File | Responsibility |
|---|---|
| `models/menu.py` | `MenuAvailability` (`hsp_menu_availability`) |
| `models/tickets.py` | `OrderTicket`, `OrderTicketLine` |
| `constants.py` | statuses, RBAC keys, `DEPLETE_TICKET_JOB`, the sync/async threshold |
| `schemas/` | menu read, availability read, ticket create/read — wire shapes |
| `service/availability.py` | set/clear 86, countdown, lazy expiry |
| `service/tickets.py` | ticket lifecycle, fire, settle |
| `service/depletion.py` | BOM explosion + **component aggregation**, the job handler |
| `queries.py` | batched menu read, batched on-hand, the "at risk" derived list |
| `router.py` | staff endpoints |
| `website_router.py` | the two cached reads + the idempotent order write |
| `events.py` | `RestaurantOrderFired`, `RestaurantOrderSettled` |
| `industry-templates/hospitality.yaml` | the 6th template |
| `backend/tests/modules/hospitality/` | one test module per service file |
| `backend/tests/perf/test_write_budgets.py` | **new** — the write-path budget test that does not exist today |

---

## Task 1: The write-path query-count test (do this FIRST)

**Files:**
- Create: `backend/tests/perf/test_write_budgets.py`

**Why first.** Q4's measurements are the whole basis of this phase's design, and *nothing in CI
would catch a settlement regressing from 900 to 9,000 statements* — `backend/tests/perf/
test_budgets.py` covers only read paths, and PERFORMANCE §2's ≤3 rule is explicitly a list-endpoint
rule (`backend/tests/conftest.py:148-170`). Landing the ratchet before the feature means every later
task is measured against it.

**Interfaces:**
- Consumes: the `query_counter` fixture (`backend/tests/conftest.py:85-145`).
- Produces: a reusable write-path budget assertion for later tasks.

- [ ] **Step 1: Write the test against TODAY's behaviour**

```python
# backend/tests/perf/test_write_budgets.py
"""Write-path statement budgets.

PERFORMANCE §2's <=3 rule is a LIST-ENDPOINT rule; nothing has ever bounded a write. Q4 of the
hospitality plan measured one ingredient ISSUE move at 38 statements and 24 lines at 911, and the
Phase 19 design turns on those numbers, so they get a ratchet here before the feature lands.

These are CEILINGS, not targets. A number moving down is good and the ceiling should follow it
down; a number moving up is a regression that must be explained in the PR that causes it.
"""
import pytest

STOCK_MOVE_ISSUE_CEILING = 45  # measured 38 (Q4), headroom for incidental growth


@pytest.mark.asyncio
async def test_single_ingredient_issue_move_stays_within_its_ceiling(
    session, tenant, query_counter, stocked_item, warehouse
):
    with query_counter() as counted:
        await create_issue_move(session, tenant.id, stocked_item.id, warehouse.id, "1")
    assert counted.total <= STOCK_MOVE_ISSUE_CEILING, (
        f"one ingredient issue now costs {counted.total} statements; Q4 measured 38. "
        "A rise here multiplies by every component on every ticket."
    )
```

Use the repo's real fixture names — read `backend/tests/conftest.py` and an existing perf test
first, and follow them rather than the placeholder names above.

- [ ] **Step 2: Run it and record the REAL number**

Run: `cd backend && ~/.local/bin/uv run pytest tests/perf/test_write_budgets.py -v`
Expected: PASS. If the real count differs from 38, **update the constant and the comment to the
number you actually measured** — the ratchet must reflect reality, not the spec's memory.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/perf/test_write_budgets.py
git commit -m "test(perf): ratchet the stock-move write path before Phase 19

PERFORMANCE §2 bounds list endpoints only; nothing bounded a write. Q4
measured one ingredient issue at 38 statements and the Phase 19 design turns
on that number, so it gets a ceiling before the feature lands."
```

---

## Task 2: The `hospitality` module skeleton and its template

**Files:**
- Create: `backend/app/modules/hospitality/{__init__.py,constants.py,models/__init__.py,router.py}`
- Create: `industry-templates/hospitality.yaml`
- Modify: wherever modules register their routers and permission keys — **find the existing
  registration site by reading how `quality` or `maintenance` (the smallest modules) wire themselves
  in, and follow it exactly.**
- Test: `backend/tests/modules/hospitality/test_module_registration.py`,
  `backend/tests/test_industry_templates.py` (extend the existing template test)

**Interfaces:**
- Produces: the module package; RBAC keys `hospitality.menu.read`, `hospitality.menu.manage`,
  `hospitality.ticket.read`, `hospitality.ticket.manage`, `hospitality.ticket.settle`;
  `DEPLETE_TICKET_JOB = "hospitality.deplete_ticket"`.

- [ ] **Step 1: Write the failing tests**

```python
def test_hospitality_permission_keys_are_in_the_catalog():
    """D-009: a tenant can only be granted keys code declares."""
    from app.core.rbac import catalog_keys
    keys = catalog_keys()
    for key in (
        "hospitality.menu.read",
        "hospitality.menu.manage",
        "hospitality.ticket.read",
        "hospitality.ticket.manage",
        "hospitality.ticket.settle",
    ):
        assert key in keys


def test_hospitality_template_loads_and_is_idempotent(session, tenant):
    """Applying the 6th template twice must leave the same state as applying it once."""
    first = await apply_template(session, tenant.id, "hospitality")
    second = await apply_template(session, tenant.id, "hospitality")
    assert first == second
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && ~/.local/bin/uv run pytest tests/modules/hospitality/ -v`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Create the module and the template**

Follow `industry-templates/_schema.yaml` and the five shipped templates exactly. Per the spec's
template table: terminology `customer → Guest / Group Account`; COA split for Guest Ledger, Advance
Deposits, Room Revenue, F&B Revenue; FIFO costing default; **manufacturing off in the
production-order/MRP sense, with only the BOM sub-engine pulled in for recipe costing**.

- [ ] **Step 4: Run to verify they pass**, then **Step 5: Commit.**

---

## Task 3: `MenuAvailability` — stored state, lazy expiry

**Files:**
- Create: `backend/app/modules/hospitality/models/menu.py`, `service/availability.py`
- Create: migration
- Test: `backend/tests/modules/hospitality/test_availability.py`

**Interfaces:**
- Produces: `MenuAvailability` model; `set_availability(...)`, `clear_86(...)`,
  `decrement_remaining(...)`, `availability_for_items(item_ids) -> dict[UUID, AvailabilityState]`.

**Design note.** `item_id` is UNIQUE per tenant — one row per sellable thing. `state` is
`AVAILABLE | LIMITED | EIGHTY_SIXED`. `remaining_qty` and `available_until` are nullable.
`source` is `MANUAL | AUTO`. **Expiry evaluates lazily on read** (`WHERE available_until IS NULL OR
available_until > now()`), because Atlas has no scheduler — do not add one.

- [ ] **Step 1: Write the failing tests**

```python
async def test_86_persists_and_reads_back(session, tenant, item):
    await set_availability(session, tenant.id, item.id, state="EIGHTY_SIXED", reason="out of feta")
    got = await availability_for_items(session, tenant.id, [item.id])
    assert got[item.id].state == "EIGHTY_SIXED"


async def test_expiry_is_evaluated_lazily_on_read(session, tenant, item):
    """No scheduler exists, so an expired 86 must lapse when read, not when a job runs."""
    await set_availability(
        session, tenant.id, item.id, state="EIGHTY_SIXED",
        available_until=datetime.now(UTC) - timedelta(minutes=1),
    )
    got = await availability_for_items(session, tenant.id, [item.id])
    assert got[item.id].state == "AVAILABLE"


async def test_countdown_flips_to_86_at_zero(session, tenant, item):
    await set_availability(session, tenant.id, item.id, state="LIMITED", remaining_qty=2)
    await decrement_remaining(session, tenant.id, item.id, 1)
    assert (await availability_for_items(session, tenant.id, [item.id]))[item.id].state == "LIMITED"
    await decrement_remaining(session, tenant.id, item.id, 1)
    assert (await availability_for_items(session, tenant.id, [item.id]))[item.id].state == "EIGHTY_SIXED"


async def test_reading_availability_for_a_whole_menu_is_one_query(
    session, tenant, query_counter, sixty_items
):
    """The guest read path must not scale with menu size (Q2: derived would be ~1,080 queries)."""
    with query_counter() as counted:
        await availability_for_items(session, tenant.id, [i.id for i in sixty_items])
    assert counted.total == 1


async def test_items_without_a_row_default_to_available(session, tenant, item):
    """A dish nobody has ever 86'd is sellable; absence is not unavailability."""
    got = await availability_for_items(session, tenant.id, [item.id])
    assert got[item.id].state == "AVAILABLE"
```

- [ ] **Step 2: Run to verify they fail.** **Step 3: Implement** the model, migration and service.
      **Step 4: Run to verify they pass.** **Step 5: Commit.**

---

## Task 4: `OrderTicket` — the document, and firing to the kitchen

**Files:**
- Create: `backend/app/modules/hospitality/models/tickets.py`, `service/tickets.py`,
  `schemas/tickets.py`, `events.py`
- Create: migration
- Test: `backend/tests/modules/hospitality/test_tickets.py`

**Interfaces:**
- Produces: `OrderTicket`, `OrderTicketLine`; `create_ticket`, `add_lines`, `fire_ticket`,
  `settle_ticket`; events `RestaurantOrderFired`, `RestaurantOrderSettled`.

**Design note.** Register `order_ticket` in `core_documents` and claim a number
(`core/numbering.py`) exactly as other document types do — `doc_type` is a plain string, so this
costs no core change. Lifecycle: `OPEN → SENT_TO_KITCHEN → IN_PREP → READY → SERVED → SETTLED`.
Lines carry seat number and notes. **KDS is a status-filtered query over open ticket lines grouped
by the menu item's prep station — a query, not new infrastructure.**

- [ ] **Step 1: Write the failing tests**

```python
async def test_ticket_lifecycle_transitions_are_enforced(session, tenant, ticket):
    await fire_ticket(session, tenant.id, ticket.id)
    assert (await get_ticket(session, tenant.id, ticket.id)).status == "SENT_TO_KITCHEN"
    with pytest.raises(InvalidTransitionError):
        await fire_ticket(session, tenant.id, ticket.id)  # already fired


async def test_firing_an_86d_item_is_refused(session, tenant, item, ticket_with_item):
    """The 86 has to bite at fire time, not just hide the dish on the website."""
    await set_availability(session, tenant.id, item.id, state="EIGHTY_SIXED")
    with pytest.raises(ItemUnavailableError):
        await fire_ticket(session, tenant.id, ticket_with_item.id)


async def test_fire_publishes_the_fired_event_not_settle(session, tenant, ticket, captured_events):
    """Q4: ingredients are consumed at fire, not at tender — a dish comped after service has
    already eaten them."""
    await fire_ticket(session, tenant.id, ticket.id)
    assert any(isinstance(e, RestaurantOrderFired) for e in captured_events)


async def test_ticket_registers_a_document_and_claims_a_number(session, tenant, ticket):
    assert ticket.ticket_number.startswith("TKT-")
    assert await document_exists(session, tenant.id, "hospitality.order_ticket", ticket.id)
```

- [ ] **Step 2: Run to verify they fail.** **Step 3: Implement.** **Step 4: Verify.** **Step 5: Commit.**

---

## Task 5: Depletion — aggregated, backgrounded, fired at send-to-kitchen

**Files:**
- Create: `backend/app/modules/hospitality/service/depletion.py`
- Modify: `constants.py` (add `DEPLETE_TICKET_JOB`, the sync/async threshold)
- Test: `backend/tests/modules/hospitality/test_depletion.py`, extend
  `backend/tests/perf/test_write_budgets.py`

**Interfaces:**
- Consumes: `register_job` / `submit_job` (`core/jobs.py:129,150`), the BOM explosion
  (`manufacturing/service/boms.py`), `create_move` (`inventory/service/stock_moves.py`).
- Produces: `deplete_ticket_job` registered under `DEPLETE_TICKET_JOB`; `aggregate_components(...)`.

**Design note — this is the task the whole phase turns on.** Copy the count-post pattern
**verbatim in shape**: `post_stock_count` posts inline at ≤ `COUNT_POST_SYNC_MAX_VARIANCES = 200`
and backgrounds above it (`inventory/count_router.py:260-264`, `inventory/constants.py:202`), with
the job handler a thin delegation to the same engine (`inventory/service/count_jobs.py:26-44`). Same
code, same guarantees, different transaction boundary.

Two non-negotiables from Q4:
- **Aggregate components across all ticket lines before issuing.** A 4-dish check sharing onion, oil
  and salt collapses ~24 lines to ~12 distinct items. This halves the statement count and pushes the
  50-dispatch ceiling out of practical reach.
- **The job is submitted inside the same uow as the fire**, so a D-013 replay returns the same job
  id (`core/jobs.py:13-16,150-174`).

- [ ] **Step 1: Write the failing tests**

```python
async def test_components_are_aggregated_across_lines(session, tenant, ticket_4_dishes_shared_onion):
    """Q4: without this, a 4-dish check is ~24 issue lines; with it, ~12 distinct items."""
    components = await aggregate_components(session, tenant.id, ticket_4_dishes_shared_onion.id)
    onion = [c for c in components if c.item_code == "ITM-ONION"]
    assert len(onion) == 1, "shared ingredients must collapse to one line"
    assert onion[0].quantity == Decimal("4")


async def test_a_large_ticket_does_not_hit_the_dispatch_ceiling(session, tenant, ticket_8_dishes_7_ingredients):
    """56 raw lines exceeds MAX_DISPATCHES_PER_UOW=50 and would 500 at the guest's table.
    Aggregation plus backgrounding is what makes this pass."""
    await fire_ticket(session, tenant.id, ticket_8_dishes_7_ingredients.id)  # must not raise


async def test_a_missing_ingredient_does_not_block_the_guest(session, tenant, ticket, out_of_stock_component):
    """Restaurant theoretical stock is 2-5% wrong by the industry's own benchmark, so a phantom
    stock-out must never refuse service. The ticket fires; the job records the failure."""
    await fire_ticket(session, tenant.id, ticket.id)
    job = await latest_job(session, tenant.id, DEPLETE_TICKET_JOB)
    assert job.status in {"PENDING", "FAILED"}


async def test_depletion_job_is_submitted_in_the_same_uow_as_the_fire(session, tenant, ticket):
    """D-013: a replayed fire must return the same job id, not submit a second depletion."""
    first = await fire_ticket(session, tenant.id, ticket.id)
    second = await fire_ticket_replay(session, tenant.id, ticket.id, same_idempotency_key=True)
    assert first.job_id == second.job_id
```

- [ ] **Step 2: Run to verify they fail.** **Step 3: Implement.**

Register the handler exactly like `count_post_job`:

```python
@register_job(DEPLETE_TICKET_JOB)
async def deplete_ticket_job(
    session: AsyncSession, tenant_id: uuid.UUID, payload: dict[str, Any]
) -> dict[str, Any]:
    """Issue a fired ticket's aggregated ingredients off-request (Q4).

    The runner restores tenant context (D-007) and the D-010 actor and runs this inside
    run_in_uow (core/jobs.py:297-303), so D-011's actual invariant — goods issue without
    COGS can never commit — still holds. What moves is the transaction boundary, not the
    guarantee.
    """
```

- [ ] **Step 4: Add the budget assertion** to `tests/perf/test_write_budgets.py` for a fired
      ticket, with a ceiling based on what you actually measure.
- [ ] **Step 5: Run everything.** **Step 6: Commit.**

---

## Task 6: The staff endpoints and the derived "at risk" list

**Files:**
- Create: `backend/app/modules/hospitality/router.py`, `queries.py`
- Test: `backend/tests/modules/hospitality/test_staff_endpoints.py`

**Design note.** The derived recipe math earns its place here and **only** here: one endpoint that
batch-explodes ACTIVE default BOMs and reports `max_producible` from **on-hand only** — drop
`on_order` and `committed`, whose inclusion is what makes `atp_check`'s formula wrong for a kitchen.
Build it in the set-based shape already proven by `items_below_reorder_point`
(`inventory/queries.py:207-251`: one LEFT JOIN + GROUP BY + HAVING). It says *"feta covers 2 more
portions"*; **a human 86s.** It is advisory, it can over-report on shared ingredients, and that is
exactly why it must never be the guest-facing number.

This task also needs one new batched helper in inventory: `on_hand_for_items(item_ids) -> dict`.

- [ ] **Step 1: Write the failing tests** — including
      `test_at_risk_list_is_one_query_regardless_of_menu_size` and
      `test_at_risk_uses_on_hand_only_not_on_order` (seed an open PO and assert it does **not**
      raise `max_producible`).
- [ ] **Step 2-5:** fail → implement → pass → commit.

---

## Task 7: The website-facing API

**Files:**
- Create: `backend/app/modules/hospitality/website_router.py`, `schemas/website.py`
- Test: `backend/tests/modules/hospitality/test_website_api.py`

**Interfaces:**
- Consumes: `collection_etag` (`core/conditional.py:65-93`), `Page` (D-014), the Phase 18 API-key
  credential, D-013 idempotency.

**Design note.** Two reads with **different cache policies**, which is the structural split Toast,
Square and Lightspeed all make independently:

| Endpoint | Shape | Cache policy |
|---|---|---|
| `GET /api/v1/hospitality/menu` | `Page[MenuItemRead]` — item_id, code, name, description, category, price (decimal **string**, D-015), prep_station | ETag over `Item`; `Cache-Control: private, max-age=60, stale-while-revalidate=600, stale-if-error=86400` |
| `GET /api/v1/hospitality/menu/availability` | `Page[ItemAvailabilityRead]` + top-level `as_of` | ETag over `hsp_menu_availability`; `Cache-Control: no-cache, must-revalidate, stale-if-error=300` |

**Availability must fit one page** — two pages are two snapshots at different instants. Keep the
`Page` envelope (no new wire shape) but contract a documented ceiling of 200 orderable items in v1
and carry `as_of`.

Atlas **cannot push invalidation** — the bus is in-process and there is no outbound HTTP anywhere in
app code — so the website pulls with a validator and these staleness windows are the contract, not a
fallback.

- [ ] **Step 1: Write the failing tests**

```python
async def test_menu_read_is_within_the_query_budget(api_key_client, query_counter, sixty_item_menu):
    with query_counter() as counted:
        await api_key_client.get("/api/v1/hospitality/menu")
    assert counted.total <= 3  # PERFORMANCE §2


async def test_availability_304s_on_an_unchanged_etag(api_key_client):
    first = await api_key_client.get("/api/v1/hospitality/menu/availability")
    again = await api_key_client.get(
        "/api/v1/hospitality/menu/availability",
        headers={"If-None-Match": first.headers["etag"]},
    )
    assert again.status_code == 304


async def test_86ing_an_item_changes_the_availability_etag(api_key_client, session, tenant, item):
    """The ETag trap in reverse: the validator MUST move when availability changes, or the
    website keeps serving a sold-out dish from cache."""
    before = (await api_key_client.get("/api/v1/hospitality/menu/availability")).headers["etag"]
    await set_availability(session, tenant.id, item.id, state="EIGHTY_SIXED")
    after = (await api_key_client.get("/api/v1/hospitality/menu/availability")).headers["etag"]
    assert before != after


async def test_a_scoped_key_cannot_post_an_order_without_the_permission(read_only_key_client):
    response = await read_only_key_client.post("/api/v1/hospitality/orders", json={...})
    assert response.status_code == 403


async def test_a_replayed_order_does_not_create_two_tickets(api_key_client):
    """D-013: the website will retry on a timeout and must not double-fire the kitchen."""
    body, key = {...}, str(uuid.uuid4())
    first = await api_key_client.post("/api/v1/hospitality/orders", json=body,
                                      headers={"Idempotency-Key": key})
    second = await api_key_client.post("/api/v1/hospitality/orders", json=body,
                                       headers={"Idempotency-Key": key})
    assert first.json()["ticket_id"] == second.json()["ticket_id"]


async def test_order_response_carries_the_authoritative_total(api_key_client):
    """Menu price is cached 60s; the website must display the total Atlas returns, never one it
    computed from a cached price."""
    response = await api_key_client.post("/api/v1/hospitality/orders", json={...})
    assert isinstance(response.json()["total_amount"], str)  # D-015
```

- [ ] **Step 2-5:** fail → implement → pass → commit.

---

## Task 8: Documentation and the recorded concessions

**Files:** `DECISIONS.md`, `docs/modules/hospitality.md`, `docs/api.md`, `PROGRESS.md`, `PLAN.md`

- [ ] **Step 1: Record the depletion concession as a DECISIONS entry.** It must state precisely
      what is traded, because Q4 is emphatic that this must not be read as a platform-wide
      relaxation:
      - Between fire and job completion a ticket has revenue with no COGS; a trial balance run
        mid-service is momentarily short the COGS of in-flight tickets.
      - A loud failure becomes quiet: today a bad depletion is a 422 with a guest standing there,
        after this it is a FAILED job row nobody sees. **This must be bought back with FAILED-job
        alerting or the change is strictly worse than today.**
      - It lands on a pre-existing core gap: **there is no stale-PENDING sweeper**, so a job whose
        PENDING row committed but whose runner died stays PENDING forever. Tolerable for a stock
        count; not for something with a GL effect.
      - What actually breaks is the unstated coupling "the sale and its depletion commit together",
        **not D-011 itself**.
      - **This is a restaurant-module decision, never a platform-wide relaxation.** The argument
        rests on restaurant theoretical usage being permanently 2–5% wrong; that reasoning does not
        transfer to the hotel side or any other vertical.
- [ ] **Step 2: Write `docs/modules/hospitality.md`** (module docs have one home, STRUCTURE §9).
- [ ] **Step 3: Document the website contract in `docs/api.md`** — the two endpoints, their cache
      policies, the one-page availability ceiling, and that the order response total is
      authoritative over any cached price.
- [ ] **Step 4: Tick PLAN 19.1-19.5 and log PROGRESS.** **Step 5: Commit.**

---

## Phase 19 done when

- [ ] Full backend suite green; the write-path budget test passes with real measured ceilings
- [ ] `ruff check .` clean
- [ ] An 8-top ordering 8 dishes at 7 ingredients fires without a 500 (the `MAX_DISPATCHES_PER_UOW`
      wall)
- [ ] A phantom stock-out does not refuse service
- [ ] 86-ing an item changes the availability ETag and the website stops selling it
- [ ] The menu read stays within PERFORMANCE §2 at 60 items
- [ ] A replayed order creates one ticket and one depletion job
- [ ] The depletion concession is recorded as a **restaurant-module** DECISIONS entry
- [ ] No new `system_context()` site; no change to D-007/D-009/D-011/D-013

## Explicitly not in Phase 19

Modifier-level 86 (no modifier model exists in Atlas at all) · day-part menus beyond what
`available_until` half-covers · third-party delivery injection · KDS hardware · online card payment
(Q1's provider interface is Phase 20+ scope) · the room-charge bridge, which needs the folio and is
**Phase 20.6**.

## Self-review

**Spec coverage.** Q2 → Tasks 3 and 6 (stored state; derived demoted to advisory). Q4 → Tasks 1 and
5 (the ratchet first, then aggregation + backgrounding + fire-at-send). Q6 → Task 7 (two cache
policies, one-page availability, idempotent write). The template and module skeleton are Task 2;
the concessions are Task 8.

**Placeholders.** Three steps deliberately send the implementer to read existing code rather than
hardcode: the fixture names in Task 1, the module-registration site in Task 2, and the real measured
ceilings in Tasks 1 and 5. Each says what to look for and why. Task 1 Step 2 explicitly instructs
updating the constant to the *measured* number rather than trusting the spec's 38.

**Type consistency.** `availability_for_items` returns `dict[UUID, AvailabilityState]` in Task 3 and
is consumed in that shape in Tasks 4, 6 and 7. `aggregate_components` returns component rows with
`item_code` and `quantity` in Task 5 and is asserted in that shape. `DEPLETE_TICKET_JOB` is declared
in Task 2's constants and used in Tasks 5 and 8. Money crosses the wire as a string (D-015) in
Task 7's tests.

**Known risk, stated rather than hidden.** Task 5's ceiling test
(`test_a_large_ticket_does_not_hit_the_dispatch_ceiling`) depends on aggregation actually collapsing
enough components. If a real menu's dishes share fewer ingredients than Q4's example assumes, an
extreme ticket could still approach 50 dispatches. The mitigation is already in the design — the
count-post threshold shape means large tickets background rather than run inline — but the
threshold value must be set from measurement in Task 5, not guessed.
