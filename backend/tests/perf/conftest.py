"""Perf-suite fixtures (PLAN 4P.7, PERFORMANCE §5): ONE mid-volume tenant per session.

The dataset is seeded once per pytest session onto its own database — a copy of the D-025
migrated SQLite template by default, or the database named by ``ATLAS_PERF_DATABASE_URL``
(a real Postgres for the pre-promotion run, PERFORMANCE §5; each run seeds a FRESH tenant
so reruns never collide). The builders — bulk-insert mechanics, trigger-safety rationale,
volume constants — live in tests/perf/factories.py (the tests/modules/finance split,
STRUCTURE §8.4); this conftest keeps only the thin fixtures. Nothing here registers
globally (no autouse fixtures); every fixture is pulled explicitly by test_budgets.py.

The ``timed`` helper reports the MEDIAN of 5 timed runs after 1 warmup — with 5 samples
the median is far stabler than a p95 estimate, so the CI smoke asserts median <= 2x the
PERFORMANCE §5 (Postgres-defined) budget on SQLite, and median <= 1x against Postgres.
"""

import asyncio
import os
import shutil
import statistics
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.db import build_engine, build_session_factory, get_session, get_session_factory
from app.main import create_app
from tests.perf.factories import PerfDataset, seed_dataset

# The ``timed`` fixture's shape: awaitable (name, call, *, warmup, runs) -> median seconds.
TimedFn = Callable[..., Awaitable[float]]


@pytest.fixture(scope="session")
def perf_dataset(
    template_db_path: Path,
    tmp_path_factory: pytest.TempPathFactory,
    make_alembic_config: Callable[[str], Config],
) -> PerfDataset:
    """The session-wide mid-volume tenant. Default: a copy of the migrated SQLite template
    (D-025). With ATLAS_PERF_DATABASE_URL set (the local-Postgres pre-promotion run,
    PERFORMANCE §5) the named database is migrated to head and a fresh tenant is seeded
    into it. Sync fixture + asyncio.run: the seed loop closes before any test loop opens,
    so no loop-bound connection leaks into the per-test engines."""
    override = os.environ.get("ATLAS_PERF_DATABASE_URL")
    if override:
        database_url = override
        command.upgrade(make_alembic_config(database_url), "head")
    else:
        db_path = tmp_path_factory.mktemp("perf") / "perf.sqlite"
        shutil.copy(template_db_path, db_path)
        database_url = f"sqlite+aiosqlite:///{db_path}"
    dataset = asyncio.run(seed_dataset(database_url, database_url.startswith("postgresql")))
    print(
        f"\n[perf] dataset: {dataset.entry_count} entries / {dataset.line_count} lines / "
        f"{dataset.invoice_count} invoices on {'postgres' if dataset.is_postgres else 'sqlite'} "
        f"seeded in {dataset.seed_seconds:.1f}s (budgets at {dataset.budget_multiplier}x)"
    )
    return dataset


@pytest.fixture
async def perf_engine(perf_dataset: PerfDataset) -> AsyncIterator[AsyncEngine]:
    engine = build_engine(perf_dataset.database_url)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def perf_session(perf_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with build_session_factory(perf_engine)() as session:
        yield session


@pytest.fixture
async def perf_client(
    perf_engine: AsyncEngine, perf_dataset: PerfDataset
) -> AsyncIterator[AsyncClient]:
    """A real bearer-token client against the seeded database (the tests/conftest.py app
    pattern rebuilt on the perf engine) — the journal-list timing includes auth + RBAC +
    serialization, the user-perceived path."""
    application = create_app()
    factory = build_session_factory(perf_engine)

    async def _override_get_session() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    application.dependency_overrides[get_session] = _override_get_session
    application.dependency_overrides[get_session_factory] = lambda: factory
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="https://test") as client:
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "tenant_slug": perf_dataset.tenant_slug,
                "email": perf_dataset.email,
                "password": perf_dataset.password,
            },
        )
        assert response.status_code == 200, response.text
        client.headers["Authorization"] = f"Bearer {response.json()['access_token']}"
        yield client


@pytest.fixture
def timed() -> TimedFn:
    """Run a callable ``warmup`` + ``runs`` times and return the MEDIAN wall-clock seconds
    (with 5 samples the median is far stabler than a p95 estimate — the budget multiplier
    in :class:`PerfDataset` carries the resulting slack). Always prints a ``[perf]`` report
    line so CI logs show the trend even when the budget passes."""

    async def _timed(
        name: str,
        call: Callable[[], Awaitable[None]],
        *,
        warmup: int = 1,
        runs: int = 5,
    ) -> float:
        for _ in range(warmup):
            await call()
        samples: list[float] = []
        for _ in range(runs):
            started = time.perf_counter()
            await call()
            samples.append(time.perf_counter() - started)
        median = statistics.median(samples)
        print(
            f"\n[perf] {name}: median {median * 1000:.1f} ms over {runs} runs "
            f"(min {min(samples) * 1000:.1f} / max {max(samples) * 1000:.1f} ms)"
        )
        return median

    return _timed
