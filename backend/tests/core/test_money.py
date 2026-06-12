"""D-015 exact money types + allocation.

The round-trip tests bind a Decimal through MoneyType/QuantityType/RateType into a real table
column and read it back, proving exactness on the storage layer each engine actually uses
(INTEGER micro-units on SQLite, NUMERIC on Postgres). The pure-Python tests cover quantize
HALF_UP and the largest-remainder allocator. A `-m pg` variant re-runs the round trip on
Postgres so NUMERIC storage is proven on the production engine too.
"""

import os
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.money import (
    MoneyType,
    QuantityType,
    RateType,
    allocate,
    currency_decimals,
    quantize_money,
)

_metadata = sa.MetaData()
_money_probe = sa.Table(
    "money_probe",
    _metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("amount", MoneyType()),
    sa.Column("qty", QuantityType()),
    sa.Column("rate", RateType()),
)


async def _round_trip(engine: AsyncEngine, amount: Decimal, qty: Decimal, rate: Decimal):
    async with engine.begin() as conn:
        await conn.run_sync(_metadata.create_all)
        result = await conn.execute(
            _money_probe.insert().values(amount=amount, qty=qty, rate=rate).returning(
                _money_probe.c.id
            )
        )
        row_id = result.scalar_one()
        row = (
            await conn.execute(
                sa.select(_money_probe.c.amount, _money_probe.c.qty, _money_probe.c.rate).where(
                    _money_probe.c.id == row_id
                )
            )
        ).one()
    return row


# --- SQLite storage exactness (micro-unit integers) ---------------------------


async def test_money_type_round_trips_exactly_on_sqlite(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path/'money.sqlite'}")
    try:
        amount, qty, rate = await _round_trip(
            engine, Decimal("123.45"), Decimal("7.250000"), Decimal("1.2345678901")
        )
    finally:
        await engine.dispose()
    assert amount == Decimal("123.45")
    assert qty == Decimal("7.250000")
    assert rate == Decimal("1.2345678901")


async def test_money_sums_have_no_float_drift_on_sqlite(tmp_path) -> None:
    """0.10 + 0.20 stored as micro-unit integers sums to exactly 0.30 — the property the
    balance trigger relies on (a float-backed Numeric would yield 0.30000000000000004)."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path/'sums.sqlite'}")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(_metadata.create_all)
            await conn.execute(
                _money_probe.insert(),
                [
                    {"amount": Decimal("0.10"), "qty": Decimal("0"), "rate": Decimal("1")},
                    {"amount": Decimal("0.20"), "qty": Decimal("0"), "rate": Decimal("1")},
                ],
            )
            total = (
                await conn.execute(sa.select(sa.func.sum(_money_probe.c.amount)))
            ).scalar_one()
        # SUM over the stored micro-unit ints is exact; the result processor converts back.
        assert Decimal(str(total)) == Decimal("0.30") or total == Decimal("0.30") or total == 300000
        # Read the rows back and add in Python to prove no float drift in storage either.
        async with engine.connect() as conn:
            amounts = (
                await conn.execute(sa.select(_money_probe.c.amount).order_by(_money_probe.c.id))
            ).scalars().all()
        assert sum(amounts, Decimal(0)) == Decimal("0.30")
    finally:
        await engine.dispose()


async def test_rate_type_keeps_ten_decimal_places_on_sqlite(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path/'rate.sqlite'}")
    try:
        _, _, rate = await _round_trip(
            engine, Decimal("0"), Decimal("0"), Decimal("0.0000000001")
        )
    finally:
        await engine.dispose()
    assert rate == Decimal("0.0000000001")


# --- quantize HALF_UP ---------------------------------------------------------


def test_quantize_money_rounds_half_up() -> None:
    assert quantize_money(Decimal("2.005"), 2) == Decimal("2.01")
    assert quantize_money(Decimal("2.004"), 2) == Decimal("2.00")
    # ROUND_HALF_UP rounds the .5 case AWAY from zero on both signs.
    assert quantize_money(Decimal("-2.005"), 2) == Decimal("-2.01")
    assert quantize_money(Decimal("100"), 2) == Decimal("100.00")


def test_currency_decimals_lookup() -> None:
    assert currency_decimals("USD") == 2
    assert currency_decimals("jpy") == 0  # case-insensitive
    assert currency_decimals("BHD") == 3
    assert currency_decimals("XYZ") == 2  # default


# --- allocate: parts sum EXACTLY to total -------------------------------------


def test_allocate_one_third_splits_sum_to_total() -> None:
    parts = allocate(Decimal("100"), [Decimal(1), Decimal(1), Decimal(1)])
    assert sum(parts, Decimal(0)) == Decimal("100.00")
    # Largest-remainder hands the residual cent to the earliest part.
    assert parts == [Decimal("33.34"), Decimal("33.33"), Decimal("33.33")]


@pytest.mark.parametrize(
    ("total", "weights"),
    [
        (Decimal("100"), [Decimal(1), Decimal(1), Decimal(1)]),
        (Decimal("0.01"), [Decimal(1), Decimal(1), Decimal(1)]),
        (Decimal("9.99"), [Decimal(3), Decimal(3), Decimal(3)]),
        (Decimal("100"), [Decimal(7), Decimal(11), Decimal(13)]),
        (Decimal("-50"), [Decimal(1), Decimal(1), Decimal(1)]),
        (Decimal("1234.56"), [Decimal("1.5"), Decimal("2.5"), Decimal(0)]),
    ],
)
def test_allocate_always_reconstitutes_total(total: Decimal, weights: list[Decimal]) -> None:
    parts = allocate(total, weights)
    assert sum(parts, Decimal(0)) == total.quantize(Decimal("0.01"))
    assert len(parts) == len(weights)


def test_allocate_handles_zero_total_weight() -> None:
    parts = allocate(Decimal("10"), [Decimal(0), Decimal(0)])
    assert sum(parts, Decimal(0)) == Decimal("10.00")


def test_allocate_empty_weights() -> None:
    assert allocate(Decimal("10"), []) == []


# --- pg variant ---------------------------------------------------------------

_PG_URL = os.environ.get("ATLAS_DATABASE_URL", "")


@pytest.mark.pg
@pytest.mark.skipif(
    not _PG_URL.startswith("postgresql"),
    reason="pg-marked test requires a PostgreSQL ATLAS_DATABASE_URL",
)
async def test_money_type_stores_numeric_exactly_on_postgres() -> None:
    """MoneyType stores/reads NUMERIC exactly on Postgres (the production storage path)."""
    engine = create_async_engine(_PG_URL)
    probe_md = sa.MetaData()
    probe = sa.Table(
        "money_probe_pg",
        probe_md,
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("amount", MoneyType()),
        sa.Column("rate", RateType()),
    )
    try:
        async with engine.begin() as conn:
            await conn.run_sync(probe_md.drop_all)
            await conn.run_sync(probe_md.create_all)
            await conn.execute(
                probe.insert(),
                [
                    {"amount": Decimal("0.10"), "rate": Decimal("1.2345678901")},
                    {"amount": Decimal("0.20"), "rate": Decimal("1")},
                ],
            )
            total = (await conn.execute(sa.select(sa.func.sum(probe.c.amount)))).scalar_one()
            first_rate = (
                await conn.execute(sa.select(probe.c.rate).order_by(probe.c.id).limit(1))
            ).scalar_one()
        assert total == Decimal("0.30")
        assert first_rate == Decimal("1.2345678901")
        async with engine.begin() as conn:
            await conn.run_sync(probe_md.drop_all)
    finally:
        await engine.dispose()
