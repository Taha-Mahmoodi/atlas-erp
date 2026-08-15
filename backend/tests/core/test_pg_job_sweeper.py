"""The stale-job sweep on the REAL engine (run with `-m pg` against a real PostgreSQL).

What SQLite cannot prove, and issue #12 is this repo's standing reminder of: the sweep's SQL is
dialect-sensitive in two places — the bulk conditional `UPDATE ... WHERE id IN (...) AND status =`
transitions, and the row-value `(tenant_id, endpoint, key) IN (SELECT ... LIMIT n)` DELETE the
retention purge uses to stay bounded against a composite natural PK. Both run on a timer FOREVER
in production against Postgres, so a Postgres-only failure here would be a sweeper that quietly
does nothing while every SQLite test stays green.

Skipped automatically unless ATLAS_DATABASE_URL points at PostgreSQL, exactly like
test_pg_migrations.py; CI's Postgres step sets that URL and selects `-m pg`.
"""

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.db import build_session_factory
from app.core.job_sweeper import (
    IDEMPOTENCY_RETENTION,
    PENDING_RECLAIM_AFTER,
    sweep_stale_jobs,
)
from app.core.jobs import JobStatus, register_job, wait_for_jobs

pytestmark = pytest.mark.pg

_URL = os.environ.get("ATLAS_DATABASE_URL", "")

if not _URL.startswith("postgresql"):
    pytest.skip("pg-marked tests require a PostgreSQL ATLAS_DATABASE_URL", allow_module_level=True)

_JOB_TYPE = "test.pg_sweeper_marker"
_ran: list[uuid.UUID] = []


@register_job(_JOB_TYPE)
async def _pg_marker_job(session: AsyncSession, tenant_id: uuid.UUID, payload: dict) -> dict:
    _ran.append(tenant_id)
    return {"ok": True}


async def test_the_sweep_reclaims_and_purges_on_postgres() -> None:
    """One orphaned PENDING job is reclaimed, re-dispatched and COMPLETES, and one expired
    idempotency key is purged — end to end on the production engine."""
    _ran.clear()
    engine = create_async_engine(_URL)
    tenant_id, job_id = uuid.uuid4(), uuid.uuid4()
    stale = datetime.now(UTC) - PENDING_RECLAIM_AFTER - timedelta(minutes=5)
    expired = datetime.now(UTC) - IDEMPOTENCY_RETENTION - timedelta(days=1)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO adm_tenants (id, slug, name) "
                    "VALUES (:id, :slug, 'PG sweeper tenant')"
                ),
                {"id": tenant_id, "slug": f"pg-sweep-{tenant_id.hex[:12]}"},
            )
            await conn.execute(
                text(
                    "INSERT INTO core_jobs "
                    "(id, tenant_id, job_type, status, payload, attempts, created_at, updated_at) "
                    "VALUES (:id, :tid, :jt, 'PENDING', '{}', 0, :ts, :ts)"
                ),
                {"id": job_id, "tid": tenant_id, "jt": _JOB_TYPE, "ts": stale},
            )
            await conn.execute(
                text(
                    "INSERT INTO core_idempotency_keys "
                    "(tenant_id, endpoint, key, status, request_hash, created_at) "
                    "VALUES (:tid, 'test.pg', :key, 'completed', :hash, :ts)"
                ),
                {"tid": tenant_id, "key": job_id.hex, "hash": "0" * 64, "ts": expired},
            )

        result = await sweep_stale_jobs(build_session_factory(engine))
        await wait_for_jobs()

        assert result.reclaimed_pending >= 1
        assert result.purged_idempotency_keys >= 1
        assert tenant_id in _ran, "the reclaimed job must run under its own tenant"

        async with engine.connect() as conn:
            status = (
                await conn.execute(
                    text("SELECT status FROM core_jobs WHERE id = :id"), {"id": job_id}
                )
            ).scalar_one()
            keys = (
                await conn.execute(
                    text("SELECT count(*) FROM core_idempotency_keys WHERE tenant_id = :tid"),
                    {"tid": tenant_id},
                )
            ).scalar_one()
        assert status == JobStatus.COMPLETED.value
        assert keys == 0
    finally:
        async with engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM core_idempotency_keys WHERE tenant_id = :tid"),
                {"tid": tenant_id},
            )
            await conn.execute(
                text("DELETE FROM core_jobs WHERE tenant_id = :tid"), {"tid": tenant_id}
            )
            await conn.execute(
                text("DELETE FROM adm_tenants WHERE id = :tid"), {"tid": tenant_id}
            )
        await engine.dispose()
