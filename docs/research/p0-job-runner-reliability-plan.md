# P0 — Job-runner reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`
> (recommended) or `superpowers:executing-plans`. Steps use checkbox (`- [ ]`) syntax.

**Goal:** A background job that was submitted always eventually runs or is visibly failed — never
silently lost — and a failed job is something a human can find.

**Architecture:** A sweeper that reclaims orphaned `PENDING` and `RUNNING` rows, made safe by
per-handler idempotency guards; plus an admin surface that makes FAILED and stale jobs visible. No
new infrastructure — the sweep runs on the existing app lifespan and reuses the existing scheduler.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async, Alembic, pytest, `uv`.

**Spec:** [`remaining-work-plan.md`](./remaining-work-plan.md) §P0, and the depletion concession in
`DECISIONS.md` recorded by Phase 19.

## Why this is P0

Phase 19 moved ingredient depletion — which posts COGS to the general ledger — onto the job runner.
That was correct: synchronous depletion raised `EventCycleError` at 51 ingredient lines and refused
guests' payments on phantom stock-outs. But the hospitality research attached an explicit condition
to the trade:

> "A loud failure becomes quiet… **This must be bought back with FAILED-job alerting or the change
> is strictly worse than today** — and it lands on a pre-existing core gap: **there is no
> stale-PENDING sweeper**… Tolerable for a stock count; **not tolerable for something with a GL
> effect.**"

The gap is concrete. `submit_job` inserts a `PENDING` row inside the caller's transaction
(`core/jobs.py:157`), and `schedule_job` hands it to `InProcessJobScheduler`, which creates an
asyncio task **on the request's own event loop** (`core/jobs.py:213-226`). If the process dies
between the commit and the handler finishing — a deploy, a container restart, an OOM kill — the task
dies with it. The row is left `PENDING` (never picked up) or `RUNNING` (picked up, never finished),
and **nothing in Atlas will ever look at it again**. A restart during service silently loses COGS.

## Global Constraints

- **D-003** portable constraints (SQLite tests, PostgreSQL runtime).
- **D-007** tenancy; the runner already restores tenant context (`core/jobs.py:297-303`) — the
  sweeper must too, and must add **no** new `system_context()` site beyond the sanctioned ones.
- **D-010** audit actor is restored by the runner; a swept re-run must not attribute work to the
  wrong actor.
- **D-011** handlers run inside `run_in_uow`; that must remain true on the swept path.
- **PERFORMANCE.md** the sweep is a background scan and must be indexed, bounded and paginated —
  never a full-table scan on every tick.
- **STRUCTURE.md** 400-line Python cap; this is core, so it lives in `backend/app/core/`.

---

## Task 1: Make re-running a job safe

**Files:**
- Modify: `backend/app/modules/hospitality/service/depletion.py`
- Modify: `backend/app/modules/inventory/service/count_jobs.py`
- Modify: `backend/app/modules/manufacturing/service/mrp.py`
- Test: `backend/tests/core/test_job_reruns.py`

**Why first.** A sweeper that re-dispatches a job whose handler is not idempotent turns a lost COGS
posting into a **duplicated** one, which is strictly worse. Every existing handler must be safe to
run twice **before** anything re-dispatches it. This ordering is the whole safety argument.

**Interfaces:**
- Produces: each registered handler is idempotent; a shared assertion helper for the tests.

- [ ] **Step 1: Write the failing tests — one per registered handler**

```python
async def test_depletion_run_twice_issues_stock_once(db_session, tenant_a, fired_ticket):
    """The sweeper may re-dispatch a job whose runner died mid-flight. Depletion posts COGS,
    so running twice must not double-issue."""
    await deplete_ticket_job(db_session, tenant_a, {"ticket_id": str(fired_ticket.id)})
    first = await issue_moves_for_ticket(db_session, tenant_a, fired_ticket.id)

    await deplete_ticket_job(db_session, tenant_a, {"ticket_id": str(fired_ticket.id)})
    second = await issue_moves_for_ticket(db_session, tenant_a, fired_ticket.id)

    assert second == first, "re-running depletion must not create a second set of issue moves"
```

Write the equivalent for `count_post_job` and the MRP run job. **Find every handler first** with
`grep -rn "@register_job" backend/app/` — do not assume the list is the three above.

- [ ] **Step 2: Run to verify they fail.** Expected: at least one handler double-posts.
- [ ] **Step 3: Add the guard to each handler.** Prefer a natural-key check over a new flag: for
      depletion, "does this ticket already have issue moves?" is the real question and needs no new
      column. Where a natural key does not exist, say so in the commit rather than inventing state.
- [ ] **Step 4: Run to verify they pass.** **Step 5: Commit.**

---

## Task 2: The sweeper

**Files:**
- Create: `backend/app/core/job_sweeper.py`
- Modify: `backend/app/core/jobs.py` (constants only — thresholds)
- Modify: `backend/app/main.py` (lifespan hook)
- Test: `backend/tests/core/test_job_sweeper.py`

**Interfaces:**
- Produces: `sweep_stale_jobs(session_factory, *, now=None) -> SweepResult` with counts of
  reclaimed-pending, reclaimed-running and abandoned.

**Design notes.**
- Two thresholds, both constants with comments: `PENDING_RECLAIM_AFTER` (a row that has sat unpicked
  is orphaned) and `RUNNING_RECLAIM_AFTER` (a row picked up and never finished). `RUNNING` needs the
  longer window — a legitimately slow MRP run must not be reclaimed underneath itself.
- A reclaim **budget per sweep**. An unbounded reclaim after a long outage would schedule thousands
  of asyncio tasks at once and fall over exactly when the system is already unhealthy.
- An **attempt count** with a ceiling: a job that fails, is reclaimed, and fails again must
  eventually be marked `FAILED` and left alone rather than looping forever. This needs a column and
  a migration.
- The sweep runs **on startup** (catching everything the last shutdown orphaned) and then
  **periodically** on the app lifespan. There is no cron in Atlas and this plan does not add one.

- [ ] **Step 1: Write the failing tests**

```python
async def test_a_pending_job_older_than_the_threshold_is_reclaimed(db_session, tenant_a):
    job = await submit_job(db_session, tenant_a, COUNT_POST_JOB, {...})
    await db_session.commit()
    await _age_job(db_session, job.id, minutes=30)      # simulate the runner dying

    result = await sweep_stale_jobs(session_factory, now=datetime.now(UTC))
    assert result.reclaimed_pending == 1


async def test_a_fresh_pending_job_is_left_alone(db_session, tenant_a):
    """A job submitted a second ago is in flight, not orphaned — reclaiming it would run it twice
    concurrently with itself."""
    job = await submit_job(db_session, tenant_a, COUNT_POST_JOB, {...})
    await db_session.commit()
    result = await sweep_stale_jobs(session_factory, now=datetime.now(UTC))
    assert result.reclaimed_pending == 0


async def test_a_running_job_is_given_a_longer_grace_than_a_pending_one(db_session, tenant_a):
    """A legitimately slow MRP run must not be reclaimed out from under itself."""


async def test_a_job_that_keeps_failing_is_abandoned_not_looped(db_session, tenant_a):
    """Reclaim has a ceiling; past it the row goes FAILED and stays there."""


async def test_the_sweep_is_bounded_per_tick(db_session, tenant_a):
    """After a long outage there may be thousands of orphans. Reclaiming all at once would
    schedule thousands of tasks on a system that is already unhealthy."""


async def test_the_sweep_does_not_scan_the_whole_table(db_session, tenant_a, query_counter):
    """PERFORMANCE: the sweep runs on a timer forever; it must be indexed and bounded."""


async def test_a_reclaimed_job_runs_under_its_own_tenant(db_session, tenant_a, tenant_b):
    """D-007: the sweeper crosses tenants by definition, so each reclaimed job must execute in
    ITS OWN tenant context, never the sweeper's or the previous job's."""
```

- [ ] **Step 2: Run to verify they fail.** **Step 3: Implement** the sweeper, the attempt column and
      its migration, and the lifespan hook. **Step 4: Verify.** **Step 5: Commit.**

---

## Task 3: Make failure visible

**Files:**
- Modify: `backend/app/modules/admin/` (router, schemas, service)
- Modify: `backend/app/core/rbac.py` (a permission key if none fits)
- Modify: `backend/app/modules/reporting/` (a KPI tile)
- Test: `backend/tests/modules/admin/test_job_health.py`

**Design note.** This is the clause that pays for Phase 19's concession. A FAILED row that no human
ever sees is not "recorded", it is lost with extra steps. Minimum: an endpoint listing FAILED and
stale jobs for the tenant with their error text, and a dashboard KPI so it appears somewhere a
person already looks. The KPI matters more than the endpoint — nobody polls an endpoint they have
to remember exists.

- [ ] **Step 1: Write the failing tests** — the list endpoint is permission-gated, tenant-scoped,
      paginated (D-014), returns the error text, and the KPI counts FAILED-in-window.
- [ ] **Step 2-5:** fail → implement → pass → commit.

---

## Task 4: Idempotency-key retention

**Files:**
- Modify: `backend/app/core/idempotency.py`, `backend/app/core/job_sweeper.py`
- Test: `backend/tests/core/test_idempotency_retention.py`

**Design note.** `core_idempotency_keys` stores full response bodies forever
(`core/idempotency.py:99`). Phase 19 gave a website a write channel, so it now grows with guest
traffic. Add a retention window and purge it on the same sweep as Task 2 — one mechanism, not two.
The window must exceed any realistic client retry horizon; state the number and its reasoning in a
comment, because too short silently breaks replay protection.

- [ ] **Step 1: Write the failing tests** — a key inside the window still replays; one outside is
      purged; the purge is bounded per tick; purging never touches another tenant's rows.
- [ ] **Step 2-5:** fail → implement → pass → commit.

---

## Task 5: Document it

**Files:** `DECISIONS.md`, `docs/architecture.md`, `PROGRESS.md`, `docs/research/remaining-work-plan.md`

- [ ] Record the sweeper as a DECISIONS entry: the two thresholds and why they differ, the attempt
      ceiling, the per-tick budget, and **that handler idempotency is a precondition of reclaim,
      not a nice-to-have**.
- [ ] Note in the Phase 19 depletion decision that its "bought back with alerting" clause is now
      satisfied, with a pointer.
- [ ] Tick P0 in the remaining-work plan; log `PROGRESS.md`.

---

## Done when

- [ ] Full suite green; `ruff` clean
- [ ] Every `@register_job` handler has a re-run test proving it does not double-post
- [ ] A killed runner's job is reclaimed and completes
- [ ] A permanently failing job is abandoned, not looped
- [ ] FAILED jobs are visible without knowing an endpoint exists
- [ ] The sweep is indexed, bounded per tick, and does not scan the table
- [ ] A reclaimed job runs under its own tenant, with no new `system_context()` site
