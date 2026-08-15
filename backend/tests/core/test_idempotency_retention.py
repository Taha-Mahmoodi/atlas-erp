"""Idempotency-key retention (P0 Task 4): the D-013 table stops growing forever.

``core_idempotency_keys`` stores full response BODIES and nothing ever deleted them. Phase 19
handed a public restaurant website a write channel into that table, so it now grows with guest
traffic rather than with staff traffic. The purge rides the stale-job sweep — one mechanism on one
timer, not two.

The window is the delicate part and is what these tests pin: too short silently breaks replay
protection, because a client retrying with the same Idempotency-Key after its row was purged
re-executes the side effect instead of replaying the stored response. So the properties proven
here are, in order: a key INSIDE the window still replays (no side effect runs twice), a key
outside it is gone, the purge is bounded per tick, and it never touches a live row belonging to
anybody — including another tenant.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.db import build_session_factory
from app.core.idempotency import STATUS_COMPLETED, IdempotencyKey
from app.core.job_sweeper import (
    IDEMPOTENCY_PURGE_BUDGET,
    IDEMPOTENCY_RETENTION,
    sweep_stale_jobs,
)
from app.core.tenancy import system_context, tenant_context

_ENDPOINT = "test.retention"


@pytest.fixture
def job_factory(db_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return build_session_factory(db_engine)


async def _seed_key(
    session: AsyncSession, tenant_id: uuid.UUID, key: str, *, age: timedelta
) -> None:
    """One COMPLETED reservation of a given age, written through the ORM so ``created_at`` uses
    SQLAlchemy's canonical stamp format rather than SQLite's second-precision CURRENT_TIMESTAMP
    (#34)."""
    with tenant_context(tenant_id):
        session.add(
            IdempotencyKey(
                tenant_id=tenant_id,
                endpoint=_ENDPOINT,
                key=key,
                status=STATUS_COMPLETED,
                request_hash="0" * 64,
                response_status=201,
                response_body={"id": key},
                created_at=datetime.now(UTC) - age,
                completed_at=datetime.now(UTC) - age,
            )
        )
        await session.commit()


async def _keys(session: AsyncSession, tenant_id: uuid.UUID) -> list[str]:
    session.expire_all()
    with tenant_context(tenant_id):
        return sorted(
            (
                await session.execute(
                    select(IdempotencyKey.key).where(IdempotencyKey.tenant_id == tenant_id)
                )
            )
            .scalars()
            .all()
        )


async def test_a_key_inside_the_retention_window_still_replays(
    db_session: AsyncSession, tenant_a: uuid.UUID, job_factory: async_sessionmaker[AsyncSession]
) -> None:
    """The whole risk of retention: purging a key a client is still retrying against turns a
    REPLAY into a second execution of the side effect. A key one hour short of the window keeps
    its stored response verbatim."""
    await _seed_key(db_session, tenant_a, "fresh", age=IDEMPOTENCY_RETENTION - timedelta(hours=1))

    result = await sweep_stale_jobs(job_factory)

    assert result.purged_idempotency_keys == 0
    assert await _keys(db_session, tenant_a) == ["fresh"]
    with tenant_context(tenant_a):
        db_session.expire_all()
        stored = (
            await db_session.execute(
                select(IdempotencyKey).where(IdempotencyKey.key == "fresh")
            )
        ).scalar_one()
    assert stored.status == STATUS_COMPLETED
    assert stored.response_body == {"id": "fresh"}


async def test_a_key_past_the_retention_window_is_purged(
    db_session: AsyncSession, tenant_a: uuid.UUID, job_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Nobody is still retrying a week-old request; the stored response body is dead weight."""
    await _seed_key(db_session, tenant_a, "stale", age=IDEMPOTENCY_RETENTION + timedelta(hours=1))
    await _seed_key(db_session, tenant_a, "fresh", age=timedelta(minutes=5))

    result = await sweep_stale_jobs(job_factory)

    assert result.purged_idempotency_keys == 1
    assert await _keys(db_session, tenant_a) == ["fresh"]


async def test_the_purge_is_bounded_per_tick(
    db_session: AsyncSession, tenant_a: uuid.UUID, job_factory: async_sessionmaker[AsyncSession]
) -> None:
    """A tenant that never purged could have millions of expired rows. One enormous DELETE would
    hold locks for the length of the backlog, exactly when the sweep is supposed to be cheap — so
    a tick takes a bounded bite and the rest drains over later ticks."""
    over_budget = IDEMPOTENCY_PURGE_BUDGET + 3
    with tenant_context(tenant_a):
        old = datetime.now(UTC) - IDEMPOTENCY_RETENTION - timedelta(days=1)
        db_session.add_all(
            IdempotencyKey(
                tenant_id=tenant_a,
                endpoint=_ENDPOINT,
                key=f"old-{index}",
                status=STATUS_COMPLETED,
                request_hash="0" * 64,
                created_at=old,
            )
            for index in range(over_budget)
        )
        await db_session.commit()

    result = await sweep_stale_jobs(job_factory)

    assert result.purged_idempotency_keys == IDEMPOTENCY_PURGE_BUDGET
    assert len(await _keys(db_session, tenant_a)) == over_budget - IDEMPOTENCY_PURGE_BUDGET


async def test_the_purge_never_touches_another_tenants_live_keys(
    db_session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    job_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The purge runs cross-tenant under system_context — the one place a badly-written predicate
    would quietly delete somebody else's replay protection. Expiry is an AGE question, so tenant B's
    live key must survive tenant A's expired one being removed."""
    await _seed_key(db_session, tenant_a, "a-old", age=IDEMPOTENCY_RETENTION + timedelta(days=1))
    await _seed_key(db_session, tenant_b, "b-live", age=timedelta(minutes=1))

    result = await sweep_stale_jobs(job_factory)

    assert result.purged_idempotency_keys == 1
    assert await _keys(db_session, tenant_a) == []
    assert await _keys(db_session, tenant_b) == ["b-live"]


def test_the_retention_window_exceeds_any_realistic_retry_horizon() -> None:
    """A regression guard on the number itself: shortening this silently converts replays into
    re-executions, which is a data-integrity bug that no other test would catch."""
    longest_realistic_client_retry = timedelta(days=7)
    assert longest_realistic_client_retry <= IDEMPOTENCY_RETENTION


async def test_the_purge_scan_is_index_served(db_session: AsyncSession) -> None:
    """The purge filters on created_at across ALL tenants every tick, so that column carries its
    own index (PERFORMANCE §1)."""
    with system_context():
        plan = (
            await db_session.execute(
                sa.text(
                    "EXPLAIN QUERY PLAN SELECT tenant_id, endpoint, key "
                    "FROM core_idempotency_keys WHERE created_at < '2020-01-01'"
                )
            )
        ).all()
    assert any("ix_core_idempotency_keys_created_at" in " ".join(map(str, row)) for row in plan), (
        f"the purge scan is not index-served: {plan}"
    )


async def test_the_sweep_result_reports_both_kinds_of_work(
    db_session: AsyncSession, tenant_a: uuid.UUID, job_factory: async_sessionmaker[AsyncSession]
) -> None:
    """One sweep, one result: the purge is folded into the job sweep rather than being a second
    timer, and its count is reported alongside the reclaim counts."""
    await _seed_key(db_session, tenant_a, "gone", age=IDEMPOTENCY_RETENTION + timedelta(days=2))

    result = await sweep_stale_jobs(job_factory)

    assert (result.reclaimed_pending, result.abandoned) == (0, 0)
    assert result.purged_idempotency_keys == 1


async def test_key_counts_stay_zero_when_nothing_is_expired(
    db_session: AsyncSession, tenant_a: uuid.UUID, job_factory: async_sessionmaker[AsyncSession]
) -> None:
    with tenant_context(tenant_a):
        before = (
            await db_session.execute(select(func.count()).select_from(IdempotencyKey))
        ).scalar_one()
    assert (await sweep_stale_jobs(job_factory)).purged_idempotency_keys == 0
    with tenant_context(tenant_a):
        db_session.expire_all()
        after = (
            await db_session.execute(select(func.count()).select_from(IdempotencyKey))
        ).scalar_one()
    assert after == before
