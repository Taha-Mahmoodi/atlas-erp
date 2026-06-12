"""Background-job core (PLAN 4P.5/D-032, closes #26), on real per-test databases.

Proves: submit inserts a PENDING row and rejects unknown job types; the in-process runner
completes a job with its dict result (and the polling endpoints return it); a raising handler
rolls its business writes back and records FAILED + the error; jobs run under the submitting
tenant (writes stamped, reads filtered) with the submitting user as audit actor; the
concurrency cap holds under a burst; and the polling endpoint is tenant-isolated.
"""

import asyncio
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.db import build_session_factory
from app.core.events import run_in_uow
from app.core.exceptions import ValidationFailedError
from app.core.jobs import (
    MAX_CONCURRENT_JOBS,
    Job,
    JobStatus,
    register_job,
    schedule_job,
    submit_job,
    wait_for_jobs,
)
from app.core.models import AuditLog, Role
from app.core.tenancy import tenant_context
from tests.conftest import ProvisionedUser, assert_query_budget

# --- Test handlers (registered once at module import, like production handlers) ---

_concurrency = {"active": 0, "max_active": 0}


@register_job("test.echo")
async def _echo_job(session: AsyncSession, tenant_id: uuid.UUID, payload: dict) -> dict:
    return {"echo": payload.get("value")}


@register_job("test.audited_write")
async def _audited_write_job(
    session: AsyncSession, tenant_id: uuid.UUID, payload: dict
) -> dict:
    # Role is AuditMixin + TenantMixin: the write must be tenant-stamped AND audited with the
    # submitting actor, exactly as an in-request write would be.
    role = Role(name=payload["name"])
    session.add(role)
    await session.flush()
    return {"role_id": str(role.id)}


@register_job("test.failing")
async def _failing_job(session: AsyncSession, tenant_id: uuid.UUID, payload: dict) -> dict:
    role = Role(name=payload["name"])
    session.add(role)
    await session.flush()  # a real write that MUST be rolled back when the raise follows
    raise RuntimeError("boom: handler failed after writing")


@register_job("test.count_roles")
async def _count_roles_job(
    session: AsyncSession, tenant_id: uuid.UUID, payload: dict
) -> dict:
    # No explicit tenant predicate ON PURPOSE: the D-007 session filter must scope this read
    # to the job's tenant — seeing another tenant's roles would be the leak under test.
    names = sorted((await session.execute(select(Role.name))).scalars())
    return {"role_names": list(names)}


@register_job("test.concurrent")
async def _concurrent_job(
    session: AsyncSession, tenant_id: uuid.UUID, payload: dict
) -> dict:
    _concurrency["active"] += 1
    _concurrency["max_active"] = max(_concurrency["max_active"], _concurrency["active"])
    await asyncio.sleep(0.02)
    _concurrency["active"] -= 1
    return {"i": payload["i"]}


# --- Helpers --------------------------------------------------------------------


async def _submit(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    job_type: str,
    payload: dict,
    submitted_by: uuid.UUID | None = None,
) -> uuid.UUID:
    """Submit through the real flow: inside run_in_uow under the tenant context (the PENDING
    row commits exactly as a router's uow would commit it)."""
    holder: dict[str, uuid.UUID] = {}

    async def work() -> None:
        job = await submit_job(session, tenant_id, job_type, payload, submitted_by)
        holder["id"] = job.id

    with tenant_context(tenant_id):
        await run_in_uow(session, work)
    return holder["id"]


async def _get_job(session: AsyncSession, tenant_id: uuid.UUID, job_id: uuid.UUID) -> Job:
    with tenant_context(tenant_id):
        return (
            await session.execute(select(Job).where(Job.id == job_id))
        ).scalar_one()


@pytest.fixture
def job_factory(db_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """The factory the runner gets — the per-test engine's sessionmaker, mirroring what the
    conftest get_session_factory override hands the routers."""
    return build_session_factory(db_engine)


# --- Submit ----------------------------------------------------------------------


async def test_submit_inserts_pending_row(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    submitter = uuid.uuid4()
    job_id = await _submit(
        db_session, tenant_a, "test.echo", {"value": "hi"}, submitted_by=submitter
    )
    job = await _get_job(db_session, tenant_a, job_id)
    assert job.status == JobStatus.PENDING.value
    assert job.payload == {"value": "hi"}
    assert job.submitted_by_user_id == submitter
    assert job.result is None and job.error is None
    assert job.started_at is None and job.finished_at is None


async def test_submit_unknown_job_type_rejected(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    with tenant_context(tenant_a), pytest.raises(ValidationFailedError) as exc:
        await submit_job(db_session, tenant_a, "test.never_registered", {})
    assert exc.value.code == "jobs.unknown_job_type"


# --- Runner ------------------------------------------------------------------------


async def test_runner_completes_job_with_result(
    db_session: AsyncSession, tenant_a: uuid.UUID, job_factory: async_sessionmaker[AsyncSession]
) -> None:
    job_id = await _submit(db_session, tenant_a, "test.echo", {"value": "pong"})
    schedule_job(job_id, job_factory)
    await wait_for_jobs()
    job = await _get_job(db_session, tenant_a, job_id)
    assert job.status == JobStatus.COMPLETED.value
    assert job.result == {"echo": "pong"}
    assert job.started_at is not None and job.finished_at is not None
    assert job.error is None


async def test_failed_handler_rolls_back_writes_and_records_error(
    db_session: AsyncSession, tenant_a: uuid.UUID, job_factory: async_sessionmaker[AsyncSession]
) -> None:
    job_id = await _submit(db_session, tenant_a, "test.failing", {"name": "doomed-role"})
    schedule_job(job_id, job_factory)
    await wait_for_jobs()
    job = await _get_job(db_session, tenant_a, job_id)
    assert job.status == JobStatus.FAILED.value
    assert "boom" in job.error
    assert job.finished_at is not None
    with tenant_context(tenant_a):
        # The handler's flushed write rolled back with the uow (D-011 all-or-nothing)...
        roles = (await db_session.execute(select(Role))).scalars().all()
        assert roles == []
        # ...and so did its audit capture (audit is exactly as atomic as the change, D-010).
        audit_rows = (
            await db_session.execute(
                select(AuditLog).where(AuditLog.entity_table == "core_roles")
            )
        ).scalars().all()
        assert audit_rows == []


# --- Tenancy + audit context (D-007/D-010) -----------------------------------------


async def test_job_runs_under_submitting_tenant(
    db_session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    job_factory: async_sessionmaker[AsyncSession],
) -> None:
    for tenant_id, name in ((tenant_a, "a-role"), (tenant_b, "b-role")):
        with tenant_context(tenant_id):
            db_session.add(Role(name=name))
            await db_session.commit()
    job_id = await _submit(db_session, tenant_a, "test.count_roles", {})
    schedule_job(job_id, job_factory)
    await wait_for_jobs()
    job = await _get_job(db_session, tenant_a, job_id)
    # The handler's unscoped read saw ONLY tenant A's role — never tenant B's.
    assert job.result == {"role_names": ["a-role"]}


async def test_job_writes_are_tenant_stamped_and_audited_with_submitting_actor(
    db_session: AsyncSession, tenant_a: uuid.UUID, job_factory: async_sessionmaker[AsyncSession]
) -> None:
    submitter = uuid.uuid4()
    job_id = await _submit(
        db_session, tenant_a, "test.audited_write", {"name": "job-role"}, submitted_by=submitter
    )
    schedule_job(job_id, job_factory)
    await wait_for_jobs()
    job = await _get_job(db_session, tenant_a, job_id)
    assert job.status == JobStatus.COMPLETED.value
    with tenant_context(tenant_a):
        role = (
            await db_session.execute(select(Role).where(Role.name == "job-role"))
        ).scalar_one()
        assert role.tenant_id == tenant_a  # stamped by the runner's tenant context
        audit_row = (
            await db_session.execute(
                select(AuditLog).where(
                    AuditLog.entity_table == "core_roles", AuditLog.action == "INSERT"
                )
            )
        ).scalar_one()
    assert audit_row.actor_user_id == submitter  # the submitting user, not None/system
    assert audit_row.entity_id == str(role.id)


# --- Concurrency cap -----------------------------------------------------------------


async def test_burst_respects_concurrency_cap_and_all_complete(
    db_session: AsyncSession, tenant_a: uuid.UUID, job_factory: async_sessionmaker[AsyncSession]
) -> None:
    _concurrency["active"] = 0
    _concurrency["max_active"] = 0
    job_ids = [
        await _submit(db_session, tenant_a, "test.concurrent", {"i": i}) for i in range(6)
    ]
    for job_id in job_ids:
        schedule_job(job_id, job_factory)
    await wait_for_jobs()
    for i, job_id in enumerate(job_ids):
        job = await _get_job(db_session, tenant_a, job_id)
        assert job.status == JobStatus.COMPLETED.value
        assert job.result == {"i": i}
    assert 1 <= _concurrency["max_active"] <= MAX_CONCURRENT_JOBS


# --- Polling endpoints ----------------------------------------------------------------


async def test_polling_endpoint_returns_status_then_result(
    authed_client: AsyncClient,
    provisioned_user: ProvisionedUser,
    db_session: AsyncSession,
    job_factory: async_sessionmaker[AsyncSession],
) -> None:
    tenant_id = provisioned_user.tenant_id
    job_id = await _submit(db_session, tenant_id, "test.echo", {"value": "poll-me"})

    pending = await authed_client.get(f"/api/v1/jobs/{job_id}")
    assert pending.status_code == 200, pending.text
    assert pending.json()["status"] == JobStatus.PENDING.value
    assert pending.json()["result"] is None

    schedule_job(job_id, job_factory)
    await wait_for_jobs()

    done = await authed_client.get(f"/api/v1/jobs/{job_id}")
    assert done.status_code == 200, done.text
    body = done.json()
    assert body["status"] == JobStatus.COMPLETED.value
    assert body["result"] == {"echo": "poll-me"}
    assert body["job_type"] == "test.echo"
    assert body["started_at"] is not None and body["finished_at"] is not None

    listed = await authed_client.get("/api/v1/jobs?status=COMPLETED&job_type=test.echo")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["items"]] == [str(job_id)]


async def test_polling_endpoint_is_tenant_isolated(
    authed_client: AsyncClient,
    db_session: AsyncSession,
    tenant_b: uuid.UUID,
) -> None:
    # A job belonging to ANOTHER tenant: the authed principal (tenant "acme") must not see it.
    foreign_job_id = await _submit(db_session, tenant_b, "test.echo", {"value": "secret"})
    response = await authed_client.get(f"/api/v1/jobs/{foreign_job_id}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "jobs.not_found"
    listed = await authed_client.get("/api/v1/jobs")
    assert listed.status_code == 200
    assert str(foreign_job_id) not in [item["id"] for item in listed.json()["items"]]


async def test_jobs_list_query_count(
    authed_client: AsyncClient,
    provisioned_user: ProvisionedUser,
    db_session: AsyncSession,
    query_counter,
) -> None:
    """PERFORMANCE §2: the warm-path GET /api/v1/jobs runs ≤3 SQL statements."""
    await _submit(db_session, provisioned_user.tenant_id, "test.echo", {"value": "qc"})
    await assert_query_budget(authed_client, query_counter, "/api/v1/jobs")
