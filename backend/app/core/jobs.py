"""Background jobs (PLAN 4P.5, PERFORMANCE §3 — closes #26): registry, submit, in-process runner.

Long-running operations (FX revaluation, payment runs, statement imports >1k lines, MRP) must
never execute inside a request that can hit a proxy timeout. The pattern:

1. A module registers a handler at import time::

       @register_job("finance.fx_revaluation")
       async def handler(session, tenant_id, payload: dict) -> dict: ...

   The registry is CODE-DEFINED, exactly like the permission registry (core/rbac.py): a job type
   exists because a handler for it is in the codebase, never as data.
2. The endpoint calls ``submit_job(session, ...)`` INSIDE its ``run_in_uow`` work — the PENDING
   row commits atomically with the request (and with the D-013 idempotency capture, so a replayed
   Idempotency-Key returns the SAME job id) — then, strictly AFTER the uow commit, calls
   ``schedule_job(job.id, session_factory)`` and returns ``202 {job_id, status}``.
3. The client polls ``GET /api/v1/jobs/{job_id}`` (core/jobs_router.py) until COMPLETED/FAILED.

**The runner** (``_execute_job``) opens its OWN session from the factory the submitter passed —
in production that is the request's ``get_session_factory`` dependency (the app factory), in
tests the per-test-engine factory the conftest override injects, so the runner always lands in
the same database as the submit. It restores the submitting context: ``tenant_context(tenant_id)``
(D-007 — handler reads/writes are tenant-filtered and stamped) and the D-010 actor ContextVar from
``submitted_by_user_id`` (handler writes are audited with the submitting user as actor). It marks
RUNNING (own commit), then runs the handler inside ``run_in_uow`` so domain events + audit behave
EXACTLY as in-request; the COMPLETED status + result are set inside the same uow, so business
writes and the terminal status commit atomically. On any exception the uow rolls the work back
and the runner commits only the FAILED status + error string.

**Scheduling happens post-commit by contract** (the router calls ``schedule_job`` after
``run_in_uow`` returns), so the runner never races the submitting transaction's visibility.

**Concurrency cap:** at most ``MAX_CONCURRENT_JOBS`` handlers run at once (an asyncio semaphore,
created lazily PER EVENT LOOP because asyncio primitives bind to their first loop and tests run
one loop per test), so a burst of jobs cannot starve the event loop or the DB pool.

**Swap seam:** submitters call ``schedule_job``, which delegates to the module ``scheduler``
bound to the ``JobScheduler`` Protocol — the same pattern as the D-011 event bus singleton. A
real queue (arq/celery) replaces that one binding (its ``schedule`` enqueues the job id and its
workers own their own engine, ignoring ``session_factory``) with zero submitter changes.

**Not audited (documented exclusion):** ``Job`` rows are request-control infrastructure with
high status churn (PENDING→RUNNING→COMPLETED per job), like ``RefreshSession`` and
``IdempotencyKey`` — auditing them would be noise. The BUSINESS writes a handler makes are
audited as usual through the shared session.
"""

import asyncio
import logging
import uuid
import weakref
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from app.core.audit import actor_user_id_ctx
from app.core.events import run_in_uow
from app.core.exceptions import ValidationFailedError
from app.core.models import (
    JSON_VARIANT,
    Base,
    TenantMixin,
    TimestampMixin,
    UuidPKMixin,
    tenant_fk,
)
from app.core.tenancy import system_context, tenant_context

logger = logging.getLogger("atlas")

MAX_CONCURRENT_JOBS = 4
# The error column is bounded; handler exception text is truncated to fit (D-010 precedent:
# capped values beat an unbounded text column on a high-churn table).
_ERROR_MAX_CHARS = 2000


class JobStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Job(UuidPKMixin, TenantMixin, TimestampMixin, Base):
    """One background-job execution (PLAN 4P.5). NOT ``AuditMixin`` — see module docstring.

    ``submitted_by_user_id`` is attribution metadata like ``core_audit_log.actor_user_id``
    (plain nullable Uuid, no FK/index): the runner copies it into the actor ContextVar so the
    handler's audited writes carry the submitting user."""

    __tablename__ = "core_jobs"
    __table_args__ = (
        tenant_fk("adm_tenants"),
        # Both composites lead with tenant_id (D-022 convention keys on column 0 — name them
        # explicitly). Read paths: the polling list filtered by status, and "runs of one job
        # type over time" (also the list's job_type filter).
        sa.Index("ix_core_jobs_tenant_id_status", "tenant_id", "status"),
        sa.Index(
            "ix_core_jobs_tenant_id_job_type_created_at", "tenant_id", "job_type", "created_at"
        ),
        # The ONE index on this table that does NOT lead with tenant_id, deliberately: the P0
        # stale-job sweep (core/job_sweeper.py) scans for orphans ACROSS tenants, so a
        # tenant-leading index cannot serve it. PARTIAL so it covers only the unfinished rows —
        # COMPLETED/FAILED jobs are the overwhelming majority and never appear in the scan, which
        # keeps the index tiny however long the table grows. Both dialect kwargs are required
        # (core/docflow.py precedent).
        sa.Index(
            "ix_core_jobs_status_updated_at_unfinished",
            "status",
            "updated_at",
            postgresql_where=sa.text("status IN ('PENDING', 'RUNNING')"),
            sqlite_where=sa.text("status IN ('PENDING', 'RUNNING')"),
        ),
    )

    job_type: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(20), nullable=False, default=JobStatus.PENDING.value
    )
    payload: Mapped[Any] = mapped_column(JSON_VARIANT, nullable=False, default=dict)
    result: Mapped[Any] = mapped_column(JSON_VARIANT, nullable=True)
    error: Mapped[str | None] = mapped_column(sa.String(_ERROR_MAX_CHARS), nullable=True)
    submitted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    # How many times the P0 sweeper has re-dispatched this job. DIAGNOSTICS ONLY — nothing
    # branches on it: a high count on a still-PENDING row is how an operator sees that the runner
    # is saturated rather than dead. job_sweeper's docstring explains why a ceiling on it would
    # abandon jobs that never ran.
    attempts: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default="0"
    )
    started_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)


# --- Registry (code-defined, like permissions) ----------------------------------

# A handler runs inside run_in_uow on the runner's session, under the submitting tenant context;
# its dict return value becomes ``job.result`` (must be JSON-serializable).
JobHandler = Callable[[AsyncSession, uuid.UUID, dict[str, Any]], Awaitable[dict[str, Any]]]

_registry: dict[str, JobHandler] = {}


def register_job(job_type: str) -> Callable[[JobHandler], JobHandler]:
    """Decorator registering ``handler`` for ``job_type`` at module import (idempotent for the
    same function; a second DIFFERENT handler for one key is a wiring bug and raises)."""

    def decorator(handler: JobHandler) -> JobHandler:
        existing = _registry.get(job_type)
        if existing is not None and existing is not handler:
            raise ValueError(f"Job type {job_type!r} is already registered")
        _registry[job_type] = handler
        return handler

    return decorator


def registered_job_types() -> tuple[str, ...]:
    return tuple(sorted(_registry))


# --- Submit ----------------------------------------------------------------------


async def submit_job(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    job_type: str,
    payload: dict[str, Any],
    submitted_by: uuid.UUID | None = None,
) -> Job:
    """Insert a PENDING job row (flushed, NOT committed — the caller's ``run_in_uow`` commits it
    atomically with the rest of the request, e.g. the idempotency capture). Rejects an
    unregistered ``job_type`` up front (422). The caller schedules execution AFTER its uow
    commit via ``schedule_job(job.id, session_factory)``."""
    if job_type not in _registry:
        raise ValidationFailedError(
            message=f"Unknown job type {job_type!r}",
            code="jobs.unknown_job_type",
        )
    job = Job(
        tenant_id=tenant_id,
        job_type=job_type,
        payload=payload,
        submitted_by_user_id=submitted_by,
    )
    session.add(job)
    await session.flush()
    return job


# --- Scheduler seam ----------------------------------------------------------------


@runtime_checkable
class JobScheduler(Protocol):
    """The swappable contract (module docstring): schedule ``job_id`` for execution after its
    PENDING row is committed. The in-process implementation needs the submitter's session
    factory to reach the same database; a queue-backed implementation enqueues the id and
    ignores it (workers own their engine)."""

    def schedule(
        self, job_id: uuid.UUID, session_factory: async_sessionmaker[AsyncSession]
    ) -> None: ...


# Live in-process tasks, kept so they are not garbage-collected mid-run; each discards itself
# on completion. ``wait_for_jobs`` (tests) awaits the current loop's members.
_live_tasks: set[asyncio.Task[None]] = set()

# Per-event-loop semaphores: asyncio primitives bind to the first loop that awaits them and
# raise if reused on another, and the test suite runs one loop per test — so the cap is created
# lazily per loop (weak keys: a finished test's loop drops its entry).
_semaphores: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore] = (
    weakref.WeakKeyDictionary()
)


def _semaphore() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    semaphore = _semaphores.get(loop)
    if semaphore is None:
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_JOBS)
        _semaphores[loop] = semaphore
    return semaphore


class InProcessJobScheduler:
    """v1 execution: an asyncio task on the running loop (the request's loop), capped by the
    per-loop semaphore. Scheduled post-commit by contract, so the PENDING row is visible."""

    def schedule(
        self, job_id: uuid.UUID, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        for task in list(_live_tasks):  # hygiene: drop tasks whose loop is gone (test teardown)
            if task.get_loop().is_closed():
                _live_tasks.discard(task)
        task = asyncio.get_running_loop().create_task(_execute_job(job_id, session_factory))
        _live_tasks.add(task)
        task.add_done_callback(_live_tasks.discard)


# Module singleton, same pattern as the D-011 event bus: a queue-backed scheduler replaces THIS
# binding and nothing else moves.
scheduler: JobScheduler = InProcessJobScheduler()


def schedule_job(
    job_id: uuid.UUID, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Schedule a committed PENDING job via the active scheduler. Call strictly AFTER the
    submitting ``run_in_uow`` has committed."""
    scheduler.schedule(job_id, session_factory)


async def wait_for_jobs() -> None:
    """Test helper: await every live in-process job task on the CURRENT loop (including tasks
    those jobs schedule while we wait), so assertions after submit are deterministic. A task
    raising here is a runner bug — ``_execute_job`` converts handler failures to FAILED rows."""
    loop = asyncio.get_running_loop()
    while True:
        pending = [t for t in _live_tasks if t.get_loop() is loop and not t.done()]
        if not pending:
            return
        await asyncio.gather(*pending)


# --- Runner -------------------------------------------------------------------------


async def _execute_job(
    job_id: uuid.UUID, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Execute one job in its own session/transaction (module docstring: context restore, the
    RUNNING commit, run_in_uow for the handler + COMPLETED, FAILED on exception)."""
    async with _semaphore(), session_factory() as session:
        # The job's tenant is unknown until the row is read — load under system_context
        # (the D-007 fail-closed filter would otherwise reject the read).
        with system_context():
            job = await session.get(Job, job_id)
        if job is None:
            logger.error("Scheduled job %s not found; scheduled before commit?", job_id)
            return
        actor_token = actor_user_id_ctx.set(job.submitted_by_user_id)
        try:
            with tenant_context(job.tenant_id):
                await _run_handler(session, job)
        finally:
            actor_user_id_ctx.reset(actor_token)


async def _run_handler(session: AsyncSession, job: Job) -> None:
    """CLAIM the row (PENDING -> RUNNING, own commit) -> handler inside run_in_uow with COMPLETED
    set in the same uow (business writes + terminal status commit atomically) -> on ANY exception
    the uow has rolled the work back; commit only the FAILED status + truncated error.

    **The claim is CONDITIONAL** (P0): the transition only applies to a row that is still PENDING,
    and a runner that does not win it returns without touching the handler. This is what makes
    re-dispatch safe at all — the P0 sweeper reclaims a stale PENDING row whose original asyncio
    task may merely have been queued behind ``MAX_CONCURRENT_JOBS``, and without the claim BOTH
    tasks would run the same payload, concurrently. Since nothing ever moves a row back OUT of
    RUNNING (the sweeper FAILS a stale RUNNING row rather than re-dispatching it, precisely so it
    cannot race a live handler), this one conditional update is what makes execution
    at-most-once."""
    # Plain locals: a rollback below expires the instance, and expired-attribute access on an
    # async session raises (MissingGreenlet) — never touch job.<col> in the except path.
    tenant_id, job_pk, job_type = job.tenant_id, job.id, job.job_type
    claimed = await session.execute(
        sa.update(Job)
        .where(Job.id == job_pk, Job.status == JobStatus.PENDING.value)
        .values(status=JobStatus.RUNNING.value, started_at=datetime.now(UTC))
    )
    await session.commit()
    if claimed.rowcount != 1:
        logger.info("Job %s (%s) was already claimed by another runner", job_pk, job_type)
        return

    handler = _registry.get(job_type)
    try:
        if handler is None:
            # Validated at submit; only reachable if the code shipped between submit and run.
            raise ValidationFailedError(
                message=f"Unknown job type {job_type!r}",
                code="jobs.unknown_job_type",
            )

        async def work() -> None:
            result = await handler(session, tenant_id, dict(job.payload or {}))
            job.status = JobStatus.COMPLETED.value
            job.result = result
            job.finished_at = datetime.now(UTC)

        await run_in_uow(session, work)
    except Exception as exc:
        logger.exception("Background job %s (%s) failed", job_pk, job_type)
        # run_in_uow rolled back and expired the instance; reload it before writing the
        # terminal status (its row is still RUNNING from the pre-handler commit).
        await session.refresh(job)
        job.status = JobStatus.FAILED.value
        job.error = (str(exc) or type(exc).__name__)[:_ERROR_MAX_CHARS]
        job.finished_at = datetime.now(UTC)
        await session.commit()


__all__ = [
    "MAX_CONCURRENT_JOBS",
    "Job",
    "JobHandler",
    "JobScheduler",
    "JobStatus",
    "register_job",
    "registered_job_types",
    "schedule_job",
    "scheduler",
    "submit_job",
    "wait_for_jobs",
]
