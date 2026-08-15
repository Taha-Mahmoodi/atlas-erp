"""FAILED background jobs are visible to a human (P0 Task 3).

This is the clause that pays for Phase 19's concession. Depletion used to fail LOUDLY at the
guest's table; it now fails quietly as a FAILED job row, and a FAILED row nobody ever sees is not
"recorded", it is lost with extra steps.

Two surfaces, and the KPI is the one that matters — nobody polls an endpoint they have to remember
exists:

* the dashboard's ``failed_jobs`` card, which appears somewhere a person already looks; and
* ``GET /api/v1/jobs?status=FAILED`` (core/jobs_router.py), which ALREADY existed, is
  keyset-paginated (D-014) and carries the handler's error text — so the drill-down needed
  proving, not building.

The KPI gates on ``admin.audit.read`` rather than a new key: the audience is identical (the tenant
admin looking at what the system did), the key is strictly MORE powerful than a count of failed
jobs, and inventing ``admin.job.read`` would leave every existing tenant's admin role without it.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.db import build_session_factory
from app.core.events import run_in_uow
from app.core.jobs import Job, JobStatus, register_job, schedule_job, submit_job, wait_for_jobs
from app.core.rbac import ADMIN_AUDIT_READ
from app.core.tenancy import system_context, tenant_context
from app.modules.reporting import service as reporting
from app.modules.reporting.constants import FAILED_JOB_WINDOW_DAYS

pytestmark = pytest.mark.asyncio

_BOOM = "the storeroom has no stock for item 9f2c; ticket TKT-000123 went undepleted"


@register_job("test.job_health_boom")
async def _boom_job(session: AsyncSession, tenant_id: uuid.UUID, payload: dict) -> dict:
    raise RuntimeError(_BOOM)


@pytest.fixture
def job_factory(db_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return build_session_factory(db_engine)


async def _fail_a_job(
    session: AsyncSession, tenant_id: uuid.UUID, factory: async_sessionmaker[AsyncSession]
) -> uuid.UUID:
    """Drive a job to FAILED through the REAL runner, so the recorded error is the real one."""
    holder: dict[str, uuid.UUID] = {}

    async def work() -> None:
        job = await submit_job(session, tenant_id, "test.job_health_boom", {})
        holder["id"] = job.id

    with tenant_context(tenant_id):
        await run_in_uow(session, work)
    schedule_job(holder["id"], factory)
    await wait_for_jobs()
    return holder["id"]


async def _backdate(session: AsyncSession, job_id: uuid.UUID, *, days: int) -> None:
    with system_context():
        await session.execute(
            sa.update(Job)
            .where(Job.id == job_id)
            .values(finished_at=datetime.now(UTC) - timedelta(days=days))
        )
        await session.commit()


async def _kpi(session: AsyncSession, tenant_id: uuid.UUID, permissions: frozenset[str]):
    with tenant_context(tenant_id):
        return (
            await reporting.dashboard_kpis(session, tenant_id, permissions)
        ).failed_jobs


# --- The KPI ---------------------------------------------------------------------


async def test_failed_jobs_kpi_counts_failures_in_the_window(
    db_session: AsyncSession, tenant_a: uuid.UUID, job_factory: async_sessionmaker[AsyncSession]
) -> None:
    """A failed depletion has to reach a person. The dashboard card is where they already look."""
    await _fail_a_job(db_session, tenant_a, job_factory)
    await _fail_a_job(db_session, tenant_a, job_factory)

    kpi = await _kpi(db_session, tenant_a, frozenset({ADMIN_AUDIT_READ}))

    assert kpi is not None
    assert kpi.count == 2
    assert kpi.window_days == FAILED_JOB_WINDOW_DAYS


async def test_failed_jobs_kpi_ignores_failures_outside_the_window(
    db_session: AsyncSession, tenant_a: uuid.UUID, job_factory: async_sessionmaker[AsyncSession]
) -> None:
    """The card answers 'is something wrong NOW'. A quarter-old failure that was dealt with must
    not keep the card lit forever, or it stops being read."""
    old = await _fail_a_job(db_session, tenant_a, job_factory)
    await _fail_a_job(db_session, tenant_a, job_factory)
    await _backdate(db_session, old, days=FAILED_JOB_WINDOW_DAYS + 1)

    kpi = await _kpi(db_session, tenant_a, frozenset({ADMIN_AUDIT_READ}))

    assert kpi is not None and kpi.count == 1


async def test_failed_jobs_kpi_is_omitted_without_the_read_permission(
    db_session: AsyncSession, tenant_a: uuid.UUID, job_factory: async_sessionmaker[AsyncSession]
) -> None:
    """D-058: the response shape IS the role. A caller without the gating key does not get the
    card at all, rather than getting a zero."""
    await _fail_a_job(db_session, tenant_a, job_factory)

    assert await _kpi(db_session, tenant_a, frozenset()) is None


async def test_failed_jobs_kpi_is_tenant_scoped(
    db_session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    job_factory: async_sessionmaker[AsyncSession],
) -> None:
    """D-007: one property's broken depletions are not another property's problem."""
    await _fail_a_job(db_session, tenant_a, job_factory)
    await _fail_a_job(db_session, tenant_b, job_factory)
    await _fail_a_job(db_session, tenant_b, job_factory)

    a_kpi = await _kpi(db_session, tenant_a, frozenset({ADMIN_AUDIT_READ}))
    b_kpi = await _kpi(db_session, tenant_b, frozenset({ADMIN_AUDIT_READ}))

    assert (a_kpi.count, b_kpi.count) == (1, 2)


async def test_a_healthy_tenant_gets_a_zero_card_not_a_missing_one(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """A permitted caller with nothing wrong sees ``0``, which is the signal that the check ran."""
    kpi = await _kpi(db_session, tenant_a, frozenset({ADMIN_AUDIT_READ}))
    assert kpi is not None and kpi.count == 0


# --- The drill-down (the endpoint that already existed) ---------------------------


async def test_the_failed_job_list_carries_the_error_text(
    db_session: AsyncSession,
    db_engine: AsyncEngine,
    admin_client: AsyncClient,
    job_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The error string is the ONLY record of what went wrong — ``JobRead`` never exposes the
    payload — so the list has to carry it, or the card points at nothing actionable."""
    tenant_id = await _tenant_of(admin_client, db_session)
    await _fail_a_job(db_session, tenant_id, job_factory)

    response = await admin_client.get("/api/v1/jobs", params={"status": JobStatus.FAILED.value})

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert len(items) == 1
    assert _BOOM in items[0]["error"]
    assert items[0]["status"] == JobStatus.FAILED.value


async def test_the_failed_job_list_is_tenant_scoped_and_paginated(
    db_session: AsyncSession,
    admin_client: AsyncClient,
    tenant_b: uuid.UUID,
    job_factory: async_sessionmaker[AsyncSession],
) -> None:
    """D-014 pagination and D-007 scoping on the drill-down: another tenant's failures are
    invisible, and a long list of them arrives a page at a time."""
    tenant_id = await _tenant_of(admin_client, db_session)
    for _ in range(3):
        await _fail_a_job(db_session, tenant_id, job_factory)
    await _fail_a_job(db_session, tenant_b, job_factory)

    first = await admin_client.get(
        "/api/v1/jobs", params={"status": JobStatus.FAILED.value, "limit": 2}
    )
    body = first.json()

    assert len(body["items"]) == 2
    assert body["next_cursor"] is not None
    second = await admin_client.get(
        "/api/v1/jobs",
        params={
            "status": JobStatus.FAILED.value,
            "limit": 2,
            "cursor": body["next_cursor"],
        },
    )
    assert len(second.json()["items"]) == 1, "tenant B's failure must not appear"


async def _tenant_of(client: AsyncClient, session: AsyncSession) -> uuid.UUID:
    """The tenant id behind the authed client, read back through its own /auth/me."""
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 200, response.text
    return uuid.UUID(response.json()["tenant_id"])
