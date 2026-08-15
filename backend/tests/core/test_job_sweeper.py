"""The stale-job sweeper (P0 Task 2): a submitted job always eventually runs or is visibly FAILED.

The gap it closes is concrete. ``submit_job`` commits a PENDING row inside the caller's
transaction and ``schedule_job`` hands it to an asyncio task on the REQUEST's own event loop
(``core/jobs.py``). A deploy, a container restart or an OOM kill between those two points leaves
the row PENDING (never picked up) or RUNNING (picked up, never finished), and nothing in Atlas
ever looks at it again — a restart during service silently loses a COGS posting.

Proven here: both thresholds and why they differ, the attempt ceiling that abandons instead of
looping, the per-tick budget, the constant statement cost, that a reclaimed job runs under ITS OWN
tenant, and the atomic claim that stops a doubly-dispatched job from running twice.
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
    MAX_JOB_ATTEMPTS,
    PENDING_RECLAIM_AFTER,
    RUNNING_RECLAIM_AFTER,
    SWEEP_BUDGET,
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


async def test_a_running_job_is_given_a_longer_grace_than_a_pending_one(
    db_session: AsyncSession, tenant_a: uuid.UUID, job_factory: async_sessionmaker[AsyncSession]
) -> None:
    """RUNNING means a handler is actually executing. A legitimately slow MRP run must not be
    reclaimed out from under itself, so RUNNING waits far longer than PENDING — and a job aged
    past the PENDING threshold but inside the RUNNING one is deliberately untouched."""
    slow = await _submit(db_session, tenant_a, "slow")
    dead = await _submit(db_session, tenant_a, "dead")
    pending_minutes = PENDING_RECLAIM_AFTER.total_seconds() / 60
    running_minutes = RUNNING_RECLAIM_AFTER.total_seconds() / 60
    assert running_minutes > pending_minutes, "RUNNING needs the longer window, by construction"
    await _age(db_session, slow, minutes=pending_minutes + 1, status=JobStatus.RUNNING)
    await _age(db_session, dead, minutes=running_minutes + 1, status=JobStatus.RUNNING)

    result = await sweep_stale_jobs(job_factory)
    await wait_for_jobs()

    assert result.reclaimed_running == 1
    assert (await _job(db_session, slow)).status == JobStatus.RUNNING.value
    assert (await _job(db_session, dead)).status == JobStatus.COMPLETED.value


# --- The ceiling -----------------------------------------------------------------


async def test_a_job_that_keeps_failing_is_abandoned_not_looped(
    db_session: AsyncSession, tenant_a: uuid.UUID, job_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Reclaim has a ceiling. A job that fails, is reclaimed and fails again must eventually go
    FAILED and STAY there — an unbounded retry loop would burn the runner forever and hide the
    failure from the human who needs to see it."""
    job_id = await _submit(db_session, tenant_a)
    await _age(
        db_session,
        job_id,
        minutes=PENDING_RECLAIM_AFTER.total_seconds() / 60 + 1,
        attempts=MAX_JOB_ATTEMPTS,
    )

    result = await sweep_stale_jobs(job_factory)
    await wait_for_jobs()

    assert (result.abandoned, result.reclaimed_pending) == (1, 0)
    job = await _job(db_session, job_id)
    assert job.status == JobStatus.FAILED.value
    assert str(MAX_JOB_ATTEMPTS) in job.error
    assert _runs == [], "an abandoned job must not be dispatched"

    # ...and stays there: a FAILED row is not stale, so the next sweep leaves it alone.
    assert (await sweep_stale_jobs(job_factory)).abandoned == 0


async def test_each_reclaim_counts_an_attempt(
    db_session: AsyncSession, tenant_a: uuid.UUID, job_factory: async_sessionmaker[AsyncSession]
) -> None:
    """The ceiling only bites if reclaiming records an attempt — otherwise a permanently broken
    job loops forever."""
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
    """PERFORMANCE: the sweep runs on a timer forever. Its cost must be flat in the number of
    stale rows — a per-job UPDATE would make a bad outage quadratically worse. One bounded scan
    plus one bulk UPDATE per outcome, whatever the backlog."""
    for index in range(SWEEP_BUDGET):
        job_id = await _submit(db_session, tenant_a, f"orphan-{index}")
        await _age(db_session, job_id, minutes=PENDING_RECLAIM_AFTER.total_seconds() / 60 + 1)

    with query_counter() as counter:
        await sweep_stale_jobs(job_factory)
    await wait_for_jobs()

    assert counter.count <= 8, (
        f"the sweep took {counter.count} statements for {SWEEP_BUDGET} orphans; it must be "
        "flat in the backlog size"
    )


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
