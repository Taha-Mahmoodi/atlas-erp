"""DB-level guards for the inventory stock schema (PLAN 5.2, D-020/D-036), proven on BOTH engines.

The default (`not pg`) variant runs against the per-test migrated SQLite copy; the `-m pg` variant
runs the SAME assertions against a real Postgres (D-022), so the portable
``CHECK(on_hand_qty >= 0)`` and the ``with_for_update`` locking path are proven where they actually
matter — Postgres takes the row lock, SQLite omits FOR UPDATE as a no-op (D-020). Raw Core
inserts/SELECTs bypass the service layer deliberately (the grep gate bans raw SQL under app/, not
tests/).
"""

import os
import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.core.tenancy import system_context
from app.modules.inventory.models import Bin, Item, ItemCategory, StockQuant, Uom, Warehouse

_URL = os.environ.get("ATLAS_DATABASE_URL", "")


@pytest.fixture
async def pg_engine() -> AsyncEngine:
    """A freshly-migrated Postgres engine for the -m pg variant (the journal-guards precedent).
    Skipped when the URL is not Postgres so the default SQLite run never touches it."""
    if not _URL.startswith("postgresql"):
        pytest.skip("pg-marked test requires a PostgreSQL ATLAS_DATABASE_URL")
    engine = create_async_engine(_URL)
    yield engine
    await engine.dispose()


def _typed(sql: str, **params: object) -> sa.TextClause:
    """A ``text()`` whose UUID params bind through ``sa.Uuid`` so a uuid.UUID adapts to each
    engine's storage (the journal-guard helper pattern)."""
    typed = [
        sa.bindparam(key, value=value, type_=sa.Uuid)
        if isinstance(value, uuid.UUID)
        else sa.bindparam(key, value=value)
        for key, value in params.items()
    ]
    return text(sql).bindparams(*typed)


async def _seed_topology(session: AsyncSession) -> dict[str, uuid.UUID]:
    """Insert a tenant + warehouse + bin + category + uom + item via Core inserts so a quant row
    can satisfy its composite tenant FKs. Returns the ids the guard assertions need."""
    now = datetime.now(UTC)
    ids = {k: uuid.uuid4() for k in ("tenant", "wh", "bin", "cat", "uom", "item")}

    await session.execute(
        _typed(
            "INSERT INTO adm_tenants (id, slug, name, created_at, updated_at) "
            "VALUES (:id, :slug, :name, :now, :now)",
            id=ids["tenant"],
            slug=f"g-{ids['tenant'].hex[:8]}",
            name="Guard",
            now=now,
        )
    )
    await session.execute(
        sa.insert(Warehouse.__table__).values(
            id=ids["wh"], tenant_id=ids["tenant"], code="WH", name="WH",
            is_active=True, created_at=now, updated_at=now,
        )
    )
    await session.execute(
        sa.insert(Bin.__table__).values(
            id=ids["bin"], tenant_id=ids["tenant"], warehouse_id=ids["wh"], code="A1",
            name="A1", is_default=False, is_active=True, created_at=now, updated_at=now,
        )
    )
    await session.execute(
        sa.insert(ItemCategory.__table__).values(
            id=ids["cat"], tenant_id=ids["tenant"], code="C", name="C",
            default_costing_method="MOVING_AVERAGE", created_at=now, updated_at=now,
        )
    )
    await session.execute(
        sa.insert(Uom.__table__).values(
            id=ids["uom"], tenant_id=ids["tenant"], code="EA", name="EA",
            created_at=now, updated_at=now,
        )
    )
    await session.execute(
        sa.insert(Item.__table__).values(
            id=ids["item"], tenant_id=ids["tenant"], item_code="I", name="I",
            item_type="STOCKED", category_id=ids["cat"], base_uom_id=ids["uom"],
            costing_method="MOVING_AVERAGE", tracking_mode="NONE", is_active=True,
            created_at=now, updated_at=now,
        )
    )
    return ids


def _insert_quant(ids: dict[str, uuid.UUID], qty: object) -> sa.Insert:
    now = datetime.now(UTC)
    return sa.insert(StockQuant.__table__).values(
        id=uuid.uuid4(), tenant_id=ids["tenant"], item_id=ids["item"], bin_id=ids["bin"],
        lot_id=None, on_hand_qty=qty, created_at=now, updated_at=now,
    )


async def _assert_check_rejects_negative(session: AsyncSession) -> None:
    ids = await _seed_topology(session)
    # A non-negative quant inserts fine.
    await session.execute(_insert_quant(ids, 5))
    await session.flush()
    # A negative on_hand_qty violates ck_inv_stock_quants_on_hand_non_negative (D-020).
    with pytest.raises(IntegrityError):
        await session.execute(_insert_quant(ids, -1))
        await session.flush()


async def _assert_for_update_select_runs(session: AsyncSession) -> None:
    ids = await _seed_topology(session)
    await session.execute(_insert_quant(ids, 7))
    await session.flush()
    # The with_for_update locking path (PG takes the row lock; SQLite omits the clause as a no-op).
    # system_context bypasses the D-007 ORM filter for this raw guard select (the sanctioned
    # bypass — the where-clause carries the explicit tenant_id).
    stmt = (
        select(StockQuant)
        .where(
            StockQuant.tenant_id == ids["tenant"],
            StockQuant.item_id == ids["item"],
            StockQuant.bin_id == ids["bin"],
            StockQuant.lot_id.is_(None),
        )
        .with_for_update()
    )
    with system_context():
        quant = (await session.execute(stmt)).scalar_one()
    assert quant.on_hand_qty == 7


async def test_on_hand_check_rejects_negative_sqlite(db_session: AsyncSession) -> None:
    await _assert_check_rejects_negative(db_session)
    await db_session.rollback()


async def test_for_update_select_runs_sqlite(db_session: AsyncSession) -> None:
    await _assert_for_update_select_runs(db_session)


@pytest.mark.pg
async def test_on_hand_check_rejects_negative_postgres(pg_engine: AsyncEngine) -> None:
    async with AsyncSession(pg_engine) as session:
        await _assert_check_rejects_negative(session)
        await session.rollback()


@pytest.mark.pg
async def test_for_update_select_runs_postgres(pg_engine: AsyncEngine) -> None:
    async with AsyncSession(pg_engine) as session:
        await _assert_for_update_select_runs(session)
        await session.rollback()
