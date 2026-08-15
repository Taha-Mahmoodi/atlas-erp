"""Stale-job sweeper + idempotency-key retention (P0, closes the Phase 19 depletion concession).

**The gap.** ``submit_job`` commits a PENDING row inside the caller's transaction and
``schedule_job`` hands it to an asyncio task on the REQUEST's own event loop (``core/jobs.py``).
If the process dies between the commit and the handler finishing — a deploy, a container restart,
an OOM kill — the task dies with it. The row is left PENDING (never picked up) or RUNNING (picked
up, never finished) and nothing in Atlas ever looks at it again. Since Phase 19 moved ingredient
depletion onto the runner, that means a restart during service silently loses a COGS posting.

**The shape.** A periodic sweep re-dispatches orphaned PENDING rows through the ordinary
``schedule_job``/``_execute_job`` path, so a reclaimed job restores ITS OWN tenant and actor
exactly as a fresh one does (D-007/D-010) and still runs inside ``run_in_uow`` (D-011). A stale
RUNNING row is NOT re-dispatched; it is marked FAILED for a human. No new infrastructure: the
sweep runs on the app lifespan, and there is no cron in Atlas.

**Why this is safe, and why RUNNING is treated differently from PENDING.** ``_run_handler``
claims its row with a CONDITIONAL ``PENDING -> RUNNING`` update, and nothing ever moves a row back
out of RUNNING. That single conditional transition gives at-most-once execution outright: however
many times a PENDING row is dispatched, exactly one runner wins the claim and the rest return
without touching the handler.

Re-dispatching a RUNNING row would break that, and the guards cannot cover the gap. A RUNNING row
has a handler that MAY still be alive — nothing distinguishes "the process died" from "this MRP
run is slow" except elapsed time — so re-dispatch would run the same payload CONCURRENTLY with
itself, and every idempotency guard in Atlas is read-then-write with no lock: ``run_payment_batch``
selects bills with ``open_amount > 0`` before either transaction commits, so the same vendor bill
gets paid twice; FX revaluation reverses only a prior COMPLETED run; the depletion guard reads the
already-issued items before the first run's moves commit. Only two handlers have a DB-level
backstop. So the sweep does not re-dispatch RUNNING at all — the row goes FAILED, lands on the
``failed_jobs`` KPI, and a person decides whether to resubmit.

Handler re-run safety (``tests/core/test_job_reruns.py``) remains a hard PRECONDITION: it is what
makes that human's resubmission safe, and what keeps the door open for any future path that
re-publishes an event. It is simply not what makes the sweep safe — the claim is.

**The three numbers**, each a real trade-off rather than a tunable:

* ``PENDING_RECLAIM_AFTER`` is short. A PENDING row is one nobody has started; the only cost of
  reclaiming an in-flight one is the wasted claim the loser drops.
* ``RUNNING_ABANDON_AFTER`` is long, because it is how long we wait before declaring a live
  handler dead. It must exceed the slowest legitimate handler (an MRP run over a full BOM
  explosion) by a wide margin — the price of being wrong is a FAILED row for work that actually
  succeeded, so the row's terminal status is written conditionally on it still being RUNNING.
* ``SWEEP_BUDGET`` bounds a tick. After a long outage there may be thousands of orphans;
  reclaiming them all at once would schedule thousands of asyncio tasks on a system that is
  already unhealthy. The backlog drains over several ticks instead.

**There is deliberately no attempt ceiling on PENDING reclaim.** A ceiling on ``attempts`` would
count SWEEPS, not executions — a handler that actually raises is set FAILED by ``_run_handler``
and is never swept again — so the only thing it could ever fire on is a job that keeps failing to
get STARTED, most often one merely queued behind ``MAX_CONCURRENT_JOBS``. Abandoning that job
marks FAILED something no runner ever touched and loses it permanently, which is the opposite of
this module's purpose. The bound that actually matters comes from the RUNNING rule above: a job
that does start and does not finish is FAILED once, and stays FAILED.

**Retention.** ``core_idempotency_keys`` stored full response bodies forever, and Phase 19 gave a
public website a write channel into that table. The same sweep purges keys past
``IDEMPOTENCY_RETENTION`` — one mechanism on one timer, not two.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.idempotency import IdempotencyKey
from app.core.jobs import Job, JobStatus, schedule_job
from app.core.tenancy import system_context

logger = logging.getLogger("atlas")

# A PENDING row nobody picked up within this window is orphaned. Kept well above the worst-case
# wait behind MAX_CONCURRENT_JOBS so a merely-queued job is never mistaken for a dead one.
PENDING_RECLAIM_AFTER = timedelta(minutes=10)
# A RUNNING row is one with a handler actually executing. Nothing distinguishes "the process died"
# from "this MRP run is slow" except elapsed time, so this window is deliberately far larger than
# any handler's realistic runtime: past it we declare the runner dead and FAIL the row rather than
# re-dispatching it, and being wrong costs a FAILED row for work that succeeded.
RUNNING_ABANDON_AFTER = timedelta(hours=2)
# Orphans handled per tick (see module docstring).
SWEEP_BUDGET = 50
# How often the lifespan loop sweeps. Small enough that PENDING_RECLAIM_AFTER is the real latency
# a lost job waits, large enough that the scan is nowhere near a hot path.
SWEEP_INTERVAL = timedelta(minutes=5)

# D-013 replay protection lasts this long. It must comfortably exceed any realistic client retry
# horizon, because too SHORT silently breaks replay protection: a client retrying with the same
# Idempotency-Key after the key was purged re-executes the side effect instead of replaying it.
# Seven days covers an offline POS terminal reconnecting after a long weekend, which is the
# longest retry Atlas actually has to survive; a key older than that belongs to a request nobody
# is still retrying.
IDEMPOTENCY_RETENTION = timedelta(days=7)
# Rows purged per tick — same reasoning as SWEEP_BUDGET: a backlog drains over ticks rather than
# locking the table in one enormous DELETE.
IDEMPOTENCY_PURGE_BUDGET = 500


@dataclass(frozen=True)
class SweepResult:
    """What one tick did. Returned so the caller (and the tests) can assert on it; also logged."""

    reclaimed_pending: int = 0
    #: Stale RUNNING rows given up on and marked FAILED — never re-dispatched (module docstring).
    abandoned: int = 0
    purged_idempotency_keys: int = 0


def _stale_before(status: JobStatus, moment: datetime) -> datetime:
    grace = PENDING_RECLAIM_AFTER if status is JobStatus.PENDING else RUNNING_ABANDON_AFTER
    return moment - grace


async def sweep_stale_jobs(
    session_factory: async_sessionmaker[AsyncSession], *, now: datetime | None = None
) -> SweepResult:
    """Re-dispatch orphaned PENDING jobs, FAIL the RUNNING ones whose runner never came back,
    purge expired idempotency keys. Opens its own session from ``session_factory`` — the same
    factory the submitter passed the runner, so the sweep always lands in the same database.

    Statement cost is FLAT in the size of the backlog: one bounded scan, then one bulk UPDATE per
    outcome. A per-job UPDATE would make a bad outage quadratically worse, which is exactly when
    the sweep must stay cheap.
    """
    moment = now or datetime.now(UTC)
    async with session_factory() as session:
        # The ONE new system_context() site this work adds (D-007). The sweep is cross-tenant by
        # definition — an orphaned job's tenant is unknown until its row is read — which is the
        # same reason ``_execute_job`` already opens one to load the job it was handed. Reclaim
        # itself does NOT run business logic here: it re-dispatches through ``schedule_job``, and
        # the runner restores the job's own tenant and actor before the handler sees anything.
        with system_context():
            result, reclaimed_ids = await _reclaim(session, moment)
            await session.commit()

    # Post-commit by contract, exactly as a submitting router schedules: the PENDING row must be
    # visible before a runner tries to claim it.
    for job_id in reclaimed_ids:
        schedule_job(job_id, session_factory)
    if result != SweepResult():
        logger.info("Job sweep: %s", result)
    return result


async def _reclaim(
    session: AsyncSession, moment: datetime
) -> tuple[SweepResult, list[uuid.UUID]]:
    """The scan plus the bulk transitions, inside the caller's transaction."""
    stale = (
        await session.execute(
            sa.select(Job.id, Job.status)
            .where(
                sa.or_(
                    sa.and_(
                        Job.status == JobStatus.PENDING.value,
                        Job.updated_at < _stale_before(JobStatus.PENDING, moment),
                    ),
                    sa.and_(
                        Job.status == JobStatus.RUNNING.value,
                        Job.updated_at < _stale_before(JobStatus.RUNNING, moment),
                    ),
                )
            )
            .order_by(Job.updated_at)
            .limit(SWEEP_BUDGET)
        )
    ).all()
    if not stale:
        return SweepResult(purged_idempotency_keys=await _purge_keys(session, moment)), []

    pending = [row.id for row in stale if row.status == JobStatus.PENDING.value]
    running = [row.id for row in stale if row.status == JobStatus.RUNNING.value]
    return (
        SweepResult(
            reclaimed_pending=await _reclaim_batch(session, pending),
            abandoned=await _abandon(session, running, moment),
            purged_idempotency_keys=await _purge_keys(session, moment),
        ),
        # The ids the scan SELECTED, which may be a superset of the ones the conditional UPDATE
        # actually touched if a second sweeper (or a late runner) raced us. Over-scheduling is
        # harmless — the loser's dispatch fails ``_run_handler``'s claim and returns without
        # touching the handler — and it is strictly safer than the alternative, which would be to
        # skip a job we did reclaim.
        pending,
    )


async def _abandon(
    session: AsyncSession, job_ids: list[uuid.UUID], moment: datetime
) -> int:
    """Give up on stale RUNNING jobs: FAILED, with an error a human can act on. NOT re-dispatched
    — see the module docstring on why concurrency is the one thing the handler guards do not
    cover. The error text is the ONLY record of why the job stopped (``JobRead`` exposes no
    payload), so it says what happened and what to do.

    Conditional on the row still being RUNNING, for the same reason ``_reclaim_batch`` is
    conditional: the scan takes no lock, so a genuinely slow handler that finishes between the
    SELECT and this UPDATE would otherwise have its COMPLETED status (and its result) overwritten
    with a failure that never happened."""
    if not job_ids:
        return 0
    outcome = await session.execute(
        sa.update(Job)
        .where(Job.id.in_(job_ids), Job.status == JobStatus.RUNNING.value)
        .values(
            status=JobStatus.FAILED.value,
            error=(
                "Abandoned by the stale-job sweeper: the runner started this job and never "
                "finished it. Part of its work may have been committed. Investigate and resubmit."
            ),
            finished_at=moment,
        )
    )
    return outcome.rowcount


async def _reclaim_batch(session: AsyncSession, job_ids: list[uuid.UUID]) -> int:
    """Count the re-dispatch on a batch of orphaned PENDING rows, in ONE statement. The row is
    already PENDING — the UPDATE exists to bump ``updated_at`` (so the next tick does not re-scan
    a row this tick just handled) and to record ``attempts``, which is diagnostics only: nothing
    branches on it, and the module docstring says why a ceiling on it would be actively harmful.

    Conditional on the row still being PENDING, so a sweeper cannot count an attempt against a job
    a runner claimed between the scan and here — ``rowcount`` is therefore the count of jobs
    actually reclaimed, not merely selected."""
    if not job_ids:
        return 0
    outcome = await session.execute(
        sa.update(Job)
        .where(Job.id.in_(job_ids), Job.status == JobStatus.PENDING.value)
        .values(attempts=Job.attempts + 1)
    )
    return outcome.rowcount


async def _purge_keys(session: AsyncSession, moment: datetime) -> int:
    """Delete idempotency keys past the retention window, bounded per tick (D-013).

    Tenant-agnostic on purpose: expiry is an age question, not a tenancy one, and the ``created_at
    < cutoff`` predicate can only ever match rows that are expired in EVERY tenant. Deleting by
    the natural composite PK of a bounded sub-select keeps the DELETE bounded without a second
    round trip."""
    cutoff = moment - IDEMPOTENCY_RETENTION
    victims = (
        sa.select(IdempotencyKey.tenant_id, IdempotencyKey.endpoint, IdempotencyKey.key)
        .where(IdempotencyKey.created_at < cutoff)
        .limit(IDEMPOTENCY_PURGE_BUDGET)
    )
    outcome = await session.execute(
        sa.delete(IdempotencyKey).where(
            sa.tuple_(
                IdempotencyKey.tenant_id, IdempotencyKey.endpoint, IdempotencyKey.key
            ).in_(victims)
        )
    )
    return outcome.rowcount


async def run_sweeper(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    interval: timedelta = SWEEP_INTERVAL,
) -> None:
    """Sweep on startup — catching everything the last shutdown orphaned, which is the common case
    since a deploy IS a shutdown — then every ``interval`` forever. Mounted on the app lifespan
    (``app/main.py``).

    A failing sweep NEVER kills the loop: the whole point is to survive the conditions that
    orphaned the jobs in the first place, and a database blip that takes the sweeper down
    permanently would be a silent regression to no sweeper at all."""
    while True:
        try:
            await sweep_stale_jobs(session_factory)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Stale-job sweep failed; retrying on the next tick")
        await asyncio.sleep(interval.total_seconds())


__all__ = [
    "IDEMPOTENCY_RETENTION",
    "IDEMPOTENCY_PURGE_BUDGET",
    "PENDING_RECLAIM_AFTER",
    "RUNNING_ABANDON_AFTER",
    "SWEEP_BUDGET",
    "SWEEP_INTERVAL",
    "SweepResult",
    "run_sweeper",
    "sweep_stale_jobs",
]
