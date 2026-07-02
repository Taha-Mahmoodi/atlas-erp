"""On-hand projection query tests (PLAN 5.2, D-036): total, by-bin and by-lot correctness after a
sequence of moves. These are the helpers sales ATP / procurement call."""

import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import tenant_context
from app.modules.inventory import queries
from app.modules.inventory.constants import MoveType
from app.modules.inventory.schemas import StockMoveCreate
from tests.modules.inventory.conftest import StockSetup
from tests.modules.inventory.factories import build_move, build_stock, build_stock_setup


async def test_total_and_by_bin_after_sequence(
    db_session: AsyncSession, stock_setup: StockSetup
) -> None:
    """Receive 10 into A1 + 5 into A2, transfer 3 A1→A2, issue 2 from A2: total nets correctly and
    the per-bin split matches."""
    await build_stock(
        db_session, stock_setup.tenant_id, stock_setup.item_id, stock_setup.bin_a_id, Decimal(10)
    )
    await build_stock(
        db_session, stock_setup.tenant_id, stock_setup.item_id, stock_setup.bin_b_id, Decimal(5)
    )
    await build_move(
        db_session,
        stock_setup.tenant_id,
        StockMoveCreate(
            move_type=MoveType.TRANSFER,
            item_id=stock_setup.item_id,
            quantity=Decimal(3),
            from_bin_id=stock_setup.bin_a_id,
            to_bin_id=stock_setup.bin_b_id,
        ),
    )
    await build_move(
        db_session,
        stock_setup.tenant_id,
        StockMoveCreate(
            move_type=MoveType.ISSUE,
            item_id=stock_setup.item_id,
            quantity=Decimal(2),
            from_bin_id=stock_setup.bin_b_id,
        ),
    )
    with tenant_context(stock_setup.tenant_id):
        total = await queries.total_on_hand(
            db_session, stock_setup.tenant_id, stock_setup.item_id
        )
        by_bin = await queries.on_hand_by_bin(
            db_session, stock_setup.tenant_id, stock_setup.item_id
        )
    # A1: 10 - 3 = 7; A2: 5 + 3 - 2 = 6; total 13.
    assert total == Decimal(13)
    assert by_bin[stock_setup.bin_a_id] == Decimal(7)
    assert by_bin[stock_setup.bin_b_id] == Decimal(6)


async def test_emptied_bin_absent_from_projection(
    db_session: AsyncSession, stock_setup: StockSetup
) -> None:
    """Issuing all stock from a bin removes the quant row (the projection holds only live stock)."""
    await build_stock(
        db_session, stock_setup.tenant_id, stock_setup.item_id, stock_setup.bin_a_id, Decimal(4)
    )
    await build_move(
        db_session,
        stock_setup.tenant_id,
        StockMoveCreate(
            move_type=MoveType.ISSUE,
            item_id=stock_setup.item_id,
            quantity=Decimal(4),
            from_bin_id=stock_setup.bin_a_id,
        ),
    )
    with tenant_context(stock_setup.tenant_id):
        by_bin = await queries.on_hand_by_bin(
            db_session, stock_setup.tenant_id, stock_setup.item_id
        )
        total = await queries.total_on_hand(
            db_session, stock_setup.tenant_id, stock_setup.item_id
        )
    assert stock_setup.bin_a_id not in by_bin
    assert total == Decimal(0)


async def test_on_hand_by_lot_after_two_lots(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """Two lots of a LOT-tracked item land in one bin; by-lot splits them, the bin total sums."""
    setup = await build_stock_setup(db_session, tenant_a, tracking_mode="LOT")
    r1 = await build_stock(
        db_session, tenant_a, setup.item_id, setup.bin_a_id, Decimal(10), lot_code="L1"
    )
    r2 = await build_stock(
        db_session, tenant_a, setup.item_id, setup.bin_a_id, Decimal(7), lot_code="L2"
    )
    with tenant_context(tenant_a):
        by_lot = await queries.on_hand_by_lot(db_session, tenant_a, setup.item_id)
        bin_total = await queries.on_hand(
            db_session, tenant_a, setup.item_id, setup.bin_a_id
        )
    assert by_lot[r1.lot_id] == Decimal(10)
    assert by_lot[r2.lot_id] == Decimal(7)
    assert bin_total == Decimal(17)


async def test_total_on_hand_zero_for_unstocked_item(
    db_session: AsyncSession, stock_setup: StockSetup
) -> None:
    """An item with no moves reads 0, not None (coalesce)."""
    with tenant_context(stock_setup.tenant_id):
        total = await queries.total_on_hand(
            db_session, stock_setup.tenant_id, stock_setup.item_id
        )
    assert total == Decimal(0)
