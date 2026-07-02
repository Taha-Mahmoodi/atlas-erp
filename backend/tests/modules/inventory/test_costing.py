"""Inventory costing math (PLAN 5.3, D-020/D-037): moving-average and FIFO valuation correctness.

These are the most-tested invariants in the codebase (the inventory<->finance seam). Moves go
through the REAL service inside a uow (D-025), so the valuation/layer tables are maintained exactly
as in production and the COGS journal posts in the same transaction. This file asserts the
arithmetic (avg, COGS, zero-quantity flush, FIFO layer consumption + exhaustion); the journal/event
atomicity lives in test_costing_events.py.
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import tenant_context
from app.modules.inventory import queries
from app.modules.inventory.constants import CostingMethod, MoveType
from app.modules.inventory.models import (
    CostLayer,
    ItemValuation,
    LayerConsumption,
    StockMove,
)
from app.modules.inventory.schemas import StockMoveCreate
from tests.modules.inventory.factories import build_move, build_stock, build_stock_setup


async def _valuation(
    session: AsyncSession, setup, *, warehouse_id: uuid.UUID | None = None
) -> ItemValuation:
    stmt = select(ItemValuation).where(
        ItemValuation.tenant_id == setup.tenant_id,
        ItemValuation.item_id == setup.item_id,
    )
    if warehouse_id is not None:
        stmt = stmt.where(ItemValuation.warehouse_id == warehouse_id)
    with tenant_context(setup.tenant_id):
        return (await session.execute(stmt)).scalars().one()


async def _issue(session: AsyncSession, setup, qty: str, bin_id: uuid.UUID) -> None:
    await build_move(
        session,
        setup.tenant_id,
        StockMoveCreate(
            move_type=MoveType.ISSUE,
            item_id=setup.item_id,
            quantity=Decimal(qty),
            from_bin_id=bin_id,
        ),
    )


# --- Moving average -----------------------------------------------------------


async def test_moving_average_two_receipts_average_cost(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """Receive 10@2 then 10@4 → avg 3, value 60, on_hand 20 (D-020 moving average)."""
    setup = await build_stock_setup(db_session, tenant_a, costing=CostingMethod.MOVING_AVERAGE)
    await build_stock(
        db_session, tenant_a, setup.item_id, setup.bin_a_id, Decimal(10), unit_cost=Decimal(2)
    )
    await build_stock(
        db_session, tenant_a, setup.item_id, setup.bin_a_id, Decimal(10), unit_cost=Decimal(4)
    )
    valuation = await _valuation(db_session, setup)
    assert valuation.on_hand_qty == Decimal(20)
    assert valuation.avg_unit_cost == Decimal(3)
    assert valuation.total_value == Decimal(60)


async def test_moving_average_issue_computes_cogs_at_average(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """After avg 3, issue 5 → COGS 15, value 45, on_hand 15 (D-020)."""
    setup = await build_stock_setup(db_session, tenant_a, costing=CostingMethod.MOVING_AVERAGE)
    await build_stock(
        db_session, tenant_a, setup.item_id, setup.bin_a_id, Decimal(10), unit_cost=Decimal(2)
    )
    await build_stock(
        db_session, tenant_a, setup.item_id, setup.bin_a_id, Decimal(10), unit_cost=Decimal(4)
    )
    await _issue(db_session, setup, "5", setup.bin_a_id)
    valuation = await _valuation(db_session, setup)
    assert valuation.on_hand_qty == Decimal(15)
    assert valuation.total_value == Decimal(45)
    # The issue move recorded its per-unit cost (the average).
    with tenant_context(tenant_a):
        move = (
            await db_session.execute(
                select(StockMove).where(
                    StockMove.tenant_id == tenant_a,
                    StockMove.move_type == MoveType.ISSUE.value,
                )
            )
        ).scalars().one()
    assert Decimal(move.unit_cost) == Decimal(3)


async def test_moving_average_issue_all_flushes_value_to_zero(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """Issue ALL stock → value flushes to EXACTLY 0 (no residual), on_hand 0 (D-020 zero-qty
    flush)."""
    setup = await build_stock_setup(db_session, tenant_a, costing=CostingMethod.MOVING_AVERAGE)
    await build_stock(
        db_session, tenant_a, setup.item_id, setup.bin_a_id, Decimal(10), unit_cost=Decimal(2)
    )
    await build_stock(
        db_session, tenant_a, setup.item_id, setup.bin_a_id, Decimal(10), unit_cost=Decimal(4)
    )
    await _issue(db_session, setup, "20", setup.bin_a_id)
    valuation = await _valuation(db_session, setup)
    assert valuation.on_hand_qty == Decimal(0)
    assert valuation.total_value == Decimal(0)


async def test_moving_average_non_terminating_average_flushes_to_zero(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """A non-terminating average (10 units at total 10 → avg 1; but receive 3@1 then 3@2 → avg
    1.5 exact; use 1@1 + 2@1 ... pick a real non-terminating: 3 units total value 10 → avg
    3.3333...). Issue piecewise so quantize leaves a residual, then issue the rest: value lands at
    EXACTLY 0 via the zero-quantity flush (D-020 rounding-drift absorption)."""
    setup = await build_stock_setup(db_session, tenant_a, costing=CostingMethod.MOVING_AVERAGE)
    # 3 units for a total value of 10 → avg 3.333333... (non-terminating).
    await build_stock(
        db_session, tenant_a, setup.item_id, setup.bin_a_id, Decimal(1), unit_cost=Decimal(4)
    )
    await build_stock(
        db_session, tenant_a, setup.item_id, setup.bin_a_id, Decimal(2), unit_cost=Decimal(3)
    )
    valuation = await _valuation(db_session, setup)
    assert valuation.total_value == Decimal(10)
    # Issue 1 (COGS quantizes 3.33), then issue the remaining 2 → value flushes to exactly 0.
    await _issue(db_session, setup, "1", setup.bin_a_id)
    await _issue(db_session, setup, "2", setup.bin_a_id)
    valuation = await _valuation(db_session, setup)
    assert valuation.on_hand_qty == Decimal(0)
    assert valuation.total_value == Decimal(0), "residual must flush to exactly zero"


async def test_cross_warehouse_transfer_conserves_total_value(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """Regression for #84: a cross-warehouse MAV transfer that empties the source used to DROP
    the issue rounding residual (mav_issue's zero-qty flush), so the destination received only
    the quantized cost and the subledger drifted from the GL. The residual must move with the
    stock: source flushes to exactly 0, destination holds the exact received value."""
    from tests.modules.inventory.factories import build_bin, build_warehouse

    setup = await build_stock_setup(db_session, tenant_a, costing=CostingMethod.MOVING_AVERAGE)
    # 1.5 units @ 2.01 → total_value 3.015 (three decimals): issuing all 1.5 quantizes COGS to
    # 3.02 and flushes a -0.005 residual out of the source.
    await build_stock(
        db_session, tenant_a, setup.item_id, setup.bin_a_id, Decimal("1.5"),
        unit_cost=Decimal("2.01"),
    )
    warehouse_b = await build_warehouse(db_session, tenant_a, code="WH-B", name="B")
    bin_b = await build_bin(db_session, tenant_a, warehouse_b.id, code="B1", name="B1")
    await build_move(
        db_session,
        tenant_a,
        StockMoveCreate(
            move_type=MoveType.TRANSFER,
            item_id=setup.item_id,
            quantity=Decimal("1.5"),
            from_bin_id=setup.bin_a_id,
            to_bin_id=bin_b.id,
        ),
    )
    source = await _valuation(db_session, setup, warehouse_id=setup.warehouse_id)
    destination = await _valuation(db_session, setup, warehouse_id=warehouse_b.id)
    assert source.on_hand_qty == Decimal(0)
    assert source.total_value == Decimal(0)
    assert destination.on_hand_qty == Decimal("1.5")
    # The exact value received into stock — NOT the 3.02 quantized issue cost.
    assert Decimal(destination.total_value) == Decimal("3.015")


# --- FIFO ---------------------------------------------------------------------


async def test_fifo_partial_consumption_two_layers(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """The #23-class test. Receive 10@2 then 10@4; issue 15 → consumes 10@2 + 5@4 = COGS 40, two
    LayerConsumption rows, first layer remaining 0, second remaining 5 (D-020 FIFO)."""
    setup = await build_stock_setup(db_session, tenant_a, costing=CostingMethod.FIFO)
    # Distinct receipt dates make the FIFO order unambiguous (oldest layer first).
    await build_stock(
        db_session, tenant_a, setup.item_id, setup.bin_a_id, Decimal(10),
        unit_cost=Decimal(2), move_date=date(2026, 6, 1),
    )
    await build_stock(
        db_session, tenant_a, setup.item_id, setup.bin_a_id, Decimal(10),
        unit_cost=Decimal(4), move_date=date(2026, 6, 2),
    )
    await _issue(db_session, setup, "15", setup.bin_a_id)

    with tenant_context(tenant_a):
        layers = (
            await db_session.execute(
                select(CostLayer)
                .where(CostLayer.tenant_id == tenant_a, CostLayer.item_id == setup.item_id)
                .order_by(CostLayer.received_at.asc(), CostLayer.id.asc())
            )
        ).scalars().all()
        assert len(layers) == 2
        assert Decimal(layers[0].remaining_qty) == Decimal(0)
        assert Decimal(layers[1].remaining_qty) == Decimal(5)

        issue_move = (
            await db_session.execute(
                select(StockMove).where(
                    StockMove.tenant_id == tenant_a,
                    StockMove.move_type == MoveType.ISSUE.value,
                )
            )
        ).scalars().one()
        consumptions = (
            await db_session.execute(
                select(LayerConsumption).where(
                    LayerConsumption.tenant_id == tenant_a,
                    LayerConsumption.issue_move_id == issue_move.id,
                )
            )
        ).scalars().all()
    assert len(consumptions) == 2
    assert sum(Decimal(c.cost) for c in consumptions) == Decimal(40)


async def test_fifo_second_issue_exhausts_remaining_layer(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """Continuing the partial test: issue 5 more → 5@4 = COGS 20; both layers exhausted (D-020)."""
    setup = await build_stock_setup(db_session, tenant_a, costing=CostingMethod.FIFO)
    # Distinct receipt dates make the FIFO order unambiguous (oldest layer first).
    await build_stock(
        db_session, tenant_a, setup.item_id, setup.bin_a_id, Decimal(10),
        unit_cost=Decimal(2), move_date=date(2026, 6, 1),
    )
    await build_stock(
        db_session, tenant_a, setup.item_id, setup.bin_a_id, Decimal(10),
        unit_cost=Decimal(4), move_date=date(2026, 6, 2),
    )
    await _issue(db_session, setup, "15", setup.bin_a_id)
    await _issue(db_session, setup, "5", setup.bin_a_id)

    with tenant_context(tenant_a):
        layers = (
            await db_session.execute(
                select(CostLayer).where(
                    CostLayer.tenant_id == tenant_a, CostLayer.item_id == setup.item_id
                )
            )
        ).scalars().all()
        assert all(Decimal(layer.remaining_qty) == Decimal(0) for layer in layers)
        total_value = await queries.item_value(db_session, tenant_a, setup.item_id)
    assert total_value == Decimal(0)


async def test_fifo_item_value_query_sums_live_layers(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """queries.item_value sums remaining_qty × unit_cost over the live FIFO layers (PLAN 5.3
    KPI)."""
    setup = await build_stock_setup(db_session, tenant_a, costing=CostingMethod.FIFO)
    # Distinct receipt dates make the FIFO order unambiguous (oldest layer first).
    await build_stock(
        db_session, tenant_a, setup.item_id, setup.bin_a_id, Decimal(10),
        unit_cost=Decimal(2), move_date=date(2026, 6, 1),
    )
    await build_stock(
        db_session, tenant_a, setup.item_id, setup.bin_a_id, Decimal(10),
        unit_cost=Decimal(4), move_date=date(2026, 6, 2),
    )
    await _issue(db_session, setup, "15", setup.bin_a_id)  # leaves 5@4 = 20
    with tenant_context(tenant_a):
        value = await queries.item_value(db_session, tenant_a, setup.item_id)
    assert value == Decimal(20)
