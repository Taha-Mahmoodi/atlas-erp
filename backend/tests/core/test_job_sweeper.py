"""The stale-job sweeper (P0 Task 2): a submitted job always eventually runs or is visibly FAILED.

The gap it closes is concrete. ``submit_job`` commits a PENDING row inside the caller's
transaction and ``schedule_job`` hands it to an asyncio task on the REQUEST's own event loop
(``core/jobs.py``). A deploy, a container restart or an OOM kill between those two points leaves
the row PENDING (never picked up) or RUNNING (picked up, never finished), and nothing in Atlas
ever looks at it again — a restart during service silently loses a COGS posting.

Proven here: both thresholds and why they differ, that a stale RUNNING row is FAILED for a human
rather than re-dispatched under a possibly-live handler, that a job which never got to run is
retried instead of abandoned, the per-tick budget, the constant statement cost, that a reclaimed
job runs under ITS OWN tenant, and the atomic claim that stops a doubly-dispatched job from
running twice.
"""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.db import build_session_factory
from app.core.events import run_in_uow
from app.core.job_sweeper import (
    PENDING_RECLAIM_AFTER,
    RUNNING_ABANDON_AFTER,
    SWEEP_BUDGET,
    _abandon,
    sweep_stale_jobs,
)
from app.core.jobs import Job, JobStatus, register_job, submit_job, wait_for_jobs
from app.core.models import Role
from app.core.tenancy import system_context, tenant_context
from tests.conftest import QueryCounter

_runs: list[tuple[uuid.UUID, str]] = []


@register_job("test.sweeper_marker")
async def _marker_job(session: AsyncSession, tenant_id: uuid.UUID, payload: dict) -> dict:
    """Writes a TENANT-STAMPED row and records the tenant it saw, so a reclaimed job's tenant
    context is observable from two directions (D-007)."""
    role = Role(name=payload["name"])
    session.add(role)
    await session.flush()
    _runs.append((tenant_id, payload["name"]))
    return {"role_id": str(role.id)}


@pytest.fixture(autouse=True)
def _reset_runs() -> None:
    _runs.clear()


@pytest.fixture
def job_factory(db_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """The factory the sweeper and the runner get — the per-test engine's sessionmaker, exactly
    what the ``get_session_factory`` dependency hands a router (tests/core/test_jobs.py)."""
    return build_session_factory(db_engine)


async def _submit(session: AsyncSession, tenant_id: uuid.UUID, name: str = "swept") -> uuid.UUID:
    """Submit through the real flow: the PENDING row commits inside a uow, as a router's would.
    Deliberately NEVER scheduled — that is what a runner dying before it started looks like."""
    holder: dict[str, uuid.UUID] = {}

    async def work() -> None:
        job = await submit_job(session, tenant_id, "test.sweeper_marker", {"name": name})
        holder["id"] = job.id

    with tenant_context(tenant_id):
        await run_in_uow(session, work)
    return holder["id"]


async def _age(
    session: AsyncSession,
    job_id: uuid.UUID,
    *,
    minutes: float,
    status: JobStatus = JobStatus.PENDING,
    attempts: int = 0,
) -> None:
    """Backdate a job's ``updated_at`` — how a runner dying mid-flight looks from the outside.
    Written through the ORM (not CURRENT_TIMESTAMP) so the stored format is SQLAlchemy's
    canonical one (#34)."""
    with system_context():
        await session.execute(
            sa.update(Job)
            .where(Job.id == job_id)
            .values(
                status=status.value,
                attempts=attempts,
                updated_at=datetime.now(UTC) - timedelta(minutes=minutes),
            )
        )
        await session.commit()


async def _job(session: AsyncSession, job_id: uuid.UUID) -> Job:
    session.expire_all()
    with system_context():
        return (await session.execute(select(Job).where(Job.id == job_id))).scalar_one()


# --- The two thresholds ----------------------------------------------------------


async def test_a_pending_job_older_than_the_threshold_is_reclaimed(
    db_session: AsyncSession, tenant_a: uuid.UUID, job_factory: async_sessionmaker[AsyncSession]
) -> None:
    """A PENDING row that has sat unpicked past the threshold is orphaned: its runner died
    between the commit and the handler. Reclaiming re-dispatches it, and it completes."""
    job_id = await _submit(db_session, tenant_a)
    await _age(db_session, job_id, minutes=PENDING_RECLAIM_AFTER.total_seconds() / 60 + 1)

    result = await sweep_stale_jobs(job_factory)
    await wait_for_jobs()

    assert result.reclaimed_pending == 1
    assert (await _job(db_session, job_id)).status == JobStatus.COMPLETED.value
    assert _runs == [(tenant_a, "swept")]


async def test_a_fresh_pending_job_is_left_alone(
    db_session: AsyncSession, tenant_a: uuid.UUID, job_factory: async_sessionmaker[AsyncSession]
) -> None:
    """A job submitted a second ago is IN FLIGHT, not orphaned — reclaiming it would run it
    concurrently with itself, which is the one thing the sweeper must never cause."""
    job_id = await _submit(db_session, tenant_a)

    result = await sweep_stale_jobs(job_factory)

    assert result.reclaimed_pending == 0
    assert (await _job(db_session, job_id)).status == JobStatus.PENDING.value


async def test_a_stale_running_job_is_failed_for_a_human_never_re_dispatched(
    db_session: AsyncSession, tenant_a: uuid.UUID, job_factory: async_sessionmaker[AsyncSession]
) -> None:
    """RUNNING means a handler was actually executing, and elapsed time cannot tell "the process
    died" from "this MRP run is slow". Re-dispatching such a row would run the same payload
    CONCURRENTLY with a possibly-live handler, and every idempotency guard in Atlas is
    read-then-write with no lock — ``run_payment_batch`` selects bills with ``open_amount > 0``
    before either transaction commits, so the same vendor bill gets paid twice. So the sweep never
    re-dispatches RUNNING: the row goes FAILED with an error a human can act on, and a legitimately
    slow run inside the window is left completely alone."""
    slow = await _submit(db_session, tenant_a, "slow")
    dead = await _submit(db_session, tenant_a, "dead")
    pending_minutes = PENDING_RECLAIM_AFTER.total_seconds() / 60
    running_minutes = RUNNING_ABANDON_AFTER.total_seconds() / 60
    assert running_minutes > pending_minutes, "RUNNING needs the longer window, by construction"
    await _age(db_session, slow, minutes=pending_minutes + 1, status=JobStatus.RUNNING)
    await _age(db_session, dead, minutes=running_minutes + 1, status=JobStatus.RUNNING)

    result = await sweep_stale_jobs(job_factory)
    await wait_for_jobs()

    assert (result.abandoned, result.reclaimed_pending) == (1, 0)
    assert _runs == [], "a stale RUNNING job must never be re-executed"
    assert (await _job(db_session, slow)).status == JobStatus.RUNNING.value
    dead_job = await _job(db_session, dead)
    assert dead_job.status == JobStatus.FAILED.value
    assert "resubmit" in dead_job.error

    # ...and stays there: a FAILED row is not stale, so the next sweep leaves it alone.
    assert (await sweep_stale_jobs(job_factory)).abandoned == 0


async def test_abandoning_cannot_overwrite_a_job_that_finished_in_the_meantime(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """The scan takes no row lock, so a genuinely slow handler can COMPLETE between the SELECT and
    the UPDATE (and a multi-worker deploy runs one sweeper per process). Without the status guard
    the sweeper would rewrite that success as FAILED, discard its result, and light the
    ``failed_jobs`` KPI for work that actually worked."""
    job_id = await _submit(db_session, tenant_a)
    await _age(db_session, job_id, minutes=1, status=JobStatus.COMPLETED)

    with system_context():  # the sweeper's own context (the scan is cross-tenant)
        assert await _abandon(db_session, [job_id], datetime.now(UTC)) == 0
    assert (await _job(db_session, job_id)).status == JobStatus.COMPLETED.value


# --- Retrying vs giving up -------------------------------------------------------


async def test_a_job_that_never_ran_is_retried_indefinitely_not_abandoned(
    db_session: AsyncSession, tenant_a: uuid.UUID, job_factory: async_sessionmaker[AsyncSession]
) -> None:
    """``attempts`` counts SWEEPS, not executions — a handler that actually raises is set FAILED by
    the runner and never swept again — so the only thing an attempt CEILING could ever fire on is a
    job that keeps failing to get STARTED, most often one merely queued behind
    ``MAX_CONCURRENT_JOBS``. Abandoning that marks FAILED something no runner ever touched and
    loses it permanently. However many times it has been swept, a job that has never run must still
    be dispatched."""
    job_id = await _submit(db_session, tenant_a)
    await _age(
        db_session,
        job_id,
        minutes=PENDING_RECLAIM_AFTER.total_seconds() / 60 + 1,
        attempts=99,
    )

    result = await sweep_stale_jobs(job_factory)
    await wait_for_jobs()

    assert (result.reclaimed_pending, result.abandoned) == (1, 0)
    assert (await _job(db_session, job_id)).status == JobStatus.COMPLETED.value
    assert _runs == [(tenant_a, "swept")]


async def test_each_reclaim_counts_an_attempt(
    db_session: AsyncSession, tenant_a: uuid.UUID, job_factory: async_sessionmaker[AsyncSession]
) -> None:
    """``attempts`` is diagnostics, not a ceiling: a high count on a still-PENDING row is how an
    operator sees the runner is saturated rather than dead. It only says that if it is recorded."""
    job_id = await _submit(db_session, tenant_a)
    await _age(db_session, job_id, minutes=PENDING_RECLAIM_AFTER.total_seconds() / 60 + 1)

    await sweep_stale_jobs(job_factory)
    await wait_for_jobs()

    assert (await _job(db_session, job_id)).attempts == 1


# --- Bounded + indexed (PERFORMANCE) ---------------------------------------------


async def test_the_sweep_is_bounded_per_tick(
    db_session: AsyncSession, tenant_a: uuid.UUID, job_factory: async_sessionmaker[AsyncSession]
) -> None:
    """After a long outage there may be thousands of orphans. Reclaiming all at once would
    schedule thousands of asyncio tasks on a system that is already unhealthy, so a tick reclaims
    at most SWEEP_BUDGET and the rest wait for the next one."""
    for index in range(SWEEP_BUDGET + 5):
        job_id = await _submit(db_session, tenant_a, f"orphan-{index}")
        await _age(db_session, job_id, minutes=PENDING_RECLAIM_AFTER.total_seconds() / 60 + 1)

    result = await sweep_stale_jobs(job_factory)
    await wait_for_jobs()

    assert result.reclaimed_pending == SWEEP_BUDGET


async def test_the_sweep_costs_a_constant_number_of_statements(
    db_session: AsyncSession,
    tenant_a: uuid.UUID,
    job_factory: async_sessionmaker[AsyncSession],
    query_counter: Callable[[], QueryCounter],
) -> None:
    """PERFORMANCE: the sweep runs on a timer forever, so its cost must be FLAT in the number of
    stale rows — a per-job UPDATE would make a bad outage quadratically worse, exactly when the
    sweep has to stay cheap.

    Measured at two backlog sizes an order of magnitude apart and asserted EXACTLY, not as a
    ceiling: Phase 19's query-budget breach hid under a ceiling assertion, and a ceiling here would
    let a per-job UPDATE reappear as long as the batch stayed small. The three statements are the
    bounded scan, one bulk reclaim UPDATE, and the retention DELETE."""

    async def sweep_cost(orphans: int) -> int:
        for index in range(orphans):
            job_id = await _submit(db_session, tenant_a, f"orphan-{index}")
            await _age(db_session, job_id, minutes=PENDING_RECLAIM_AFTER.total_seconds() / 60 + 1)
        with query_counter() as counter:
            await sweep_stale_jobs(job_factory)
        await wait_for_jobs()
        return counter.count

    assert await sweep_cost(5) == 3
    assert await sweep_cost(SWEEP_BUDGET) == 3


def test_the_stale_scan_is_index_served() -> None:
    """The scan filters on (status, updated_at) across ALL tenants, so it needs its own partial
    index — the tenant-leading indexes on core_jobs cannot serve it (PERFORMANCE §1)."""
    index = next(
        (i for i in Job.__table__.indexes if i.name == "ix_core_jobs_status_updated_at_unfinished"),
        None,
    )
    assert index is not None, "the sweep's covering index is missing"
    assert [c.name for c in index.columns] == ["status", "updated_at"]
    assert index.dialect_options["postgresql"]["where"] is not None
    assert index.dialect_options["sqlite"]["where"] is not None


# --- Tenancy (D-007) -------------------------------------------------------------


async def test_a_reclaimed_job_runs_under_its_own_tenant(
    db_session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    job_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The sweeper crosses tenants by definition, so each reclaimed job must execute in ITS OWN
    tenant context — never the sweeper's, and never the previous job's."""
    a_job = await _submit(db_session, tenant_a, "for-a")
    b_job = await _submit(db_session, tenant_b, "for-b")
    for job_id in (a_job, b_job):
        await _age(db_session, job_id, minutes=PENDING_RECLAIM_AFTER.total_seconds() / 60 + 1)

    await sweep_stale_jobs(job_factory)
    await wait_for_jobs()

    assert sorted(_runs) == sorted([(tenant_a, "for-a"), (tenant_b, "for-b")])
    for tenant_id, name in ((tenant_a, "for-a"), (tenant_b, "for-b")):
        with tenant_context(tenant_id):
            db_session.expire_all()
            names = (await db_session.execute(select(Role.name))).scalars().all()
        assert list(names) == [name], "the handler's write landed in the wrong tenant"


# --- The atomic claim ------------------------------------------------------------


async def test_a_job_dispatched_twice_runs_once(
    db_session: AsyncSession, tenant_a: uuid.UUID, job_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Reclaim only makes sense if dispatching a job twice runs it once. The runner CLAIMS the row
    with a conditional PENDING -> RUNNING update; the loser sees rowcount 0 and returns. Without
    it, a sweeper reclaiming a job whose original task was merely queued behind the concurrency
    semaphore would run the handler twice, concurrently, against the same payload."""
    from app.core.jobs import schedule_job

    job_id = await _submit(db_session, tenant_a)
    schedule_job(job_id, job_factory)
    schedule_job(job_id, job_factory)
    await wait_for_jobs()

    assert _runs == [(tenant_a, "swept")]
    assert (await _job(db_session, job_id)).status == JobStatus.COMPLETED.value
