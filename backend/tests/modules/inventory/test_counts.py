"""Physical & cycle count engine (PLAN 5.4, D-038): snapshot → count → post-variance-as-adjustment.

These service-level tests drive the REAL count + move services inside a uow (D-025); the COGS
handler is registered by the inventory conftest's autouse fixture, so a posted variance's price-diff
journal posts in the same transaction and these tests assert the move + on-hand + journal directly.

The load-bearing invariants: variances post EXCLUSIVELY through ADJUSTMENT moves (never a bespoke
journal); the post RE-READS live on-hand (a move between snapshot and post can't post a wrong
variance — resulting on-hand always equals the counted qty); POSTED is terminal; a closed-period
count_date rolls the whole post back.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.core.events import run_in_uow
from app.core.tenancy import tenant_context
from app.modules.finance.constants import DocumentType
from app.modules.finance.models import JournalEntry
from app.modules.inventory import queries, service
from app.modules.inventory.constants import (
    STOCK_COUNT_ADJUSTMENT_LINK,
    CountStatus,
    CountType,
    MoveType,
)
from app.modules.inventory.count_schemas import StockCountCreate
from app.modules.inventory.models import StockCount, StockCountLine
from tests.modules.inventory.factories import build_count, build_stock, build_stock_setup


async def _create_count(
    session: AsyncSession, tenant_id: uuid.UUID, payload: StockCountCreate
) -> StockCount:
    return await build_count(session, tenant_id, payload)


async def _lines(
    session: AsyncSession, tenant_id: uuid.UUID, count_id: uuid.UUID
) -> list[StockCountLine]:
    with tenant_context(tenant_id):
        return list(
            (
                await session.execute(
                    select(StockCountLine)
                    .where(StockCountLine.count_id == count_id)
                    .order_by(StockCountLine.line_number.asc())
                )
            )
            .scalars()
            .all()
        )


async def _record(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    count_id: uuid.UUID,
    line_id: uuid.UUID,
    qty: Decimal,
) -> None:
    async def work() -> None:
        with tenant_context(tenant_id):
            await service.record_counted(session, tenant_id, count_id, line_id, qty)

    with tenant_context(tenant_id):
        await run_in_uow(session, work)


async def _post(
    session: AsyncSession, tenant_id: uuid.UUID, count_id: uuid.UUID
) -> StockCount:
    async def work() -> None:
        with tenant_context(tenant_id):
            await service.post_count(session, tenant_id, count_id)

    with tenant_context(tenant_id):
        await run_in_uow(session, work)
        return await service.get_count(session, tenant_id, count_id)


# --- Snapshot -----------------------------------------------------------------


async def test_physical_count_snapshots_all_warehouse_quants(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """A PHYSICAL count snapshots every warehouse quant as a line with system_qty = on-hand."""
    setup = await build_stock_setup(db_session, tenant_a)
    await build_stock(db_session, tenant_a, setup.item_id, setup.bin_a_id, Decimal(7))
    await build_stock(db_session, tenant_a, setup.item_id, setup.bin_b_id, Decimal(3))

    count = await _create_count(
        db_session,
        tenant_a,
        StockCountCreate(count_type=CountType.PHYSICAL, warehouse_id=setup.warehouse_id),
    )
    lines = await _lines(db_session, tenant_a, count.id)
    assert len(lines) == 2
    by_bin = {line.bin_id: Decimal(line.system_qty) for line in lines}
    assert by_bin[setup.bin_a_id] == Decimal(7)
    assert by_bin[setup.bin_b_id] == Decimal(3)
    assert all(line.counted_qty is None for line in lines)
    assert CountStatus(count.status) == CountStatus.DRAFT
    assert count.count_number.startswith("CNT-")


async def test_cycle_count_snapshots_only_chosen_bins(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """A CYCLE count narrows the snapshot to the chosen bins (here only bin A)."""
    setup = await build_stock_setup(db_session, tenant_a)
    await build_stock(db_session, tenant_a, setup.item_id, setup.bin_a_id, Decimal(5))
    await build_stock(db_session, tenant_a, setup.item_id, setup.bin_b_id, Decimal(9))

    count = await _create_count(
        db_session,
        tenant_a,
        StockCountCreate(
            count_type=CountType.CYCLE,
            warehouse_id=setup.warehouse_id,
            bin_ids=[setup.bin_a_id],
        ),
    )
    lines = await _lines(db_session, tenant_a, count.id)
    assert len(lines) == 1
    assert lines[0].bin_id == setup.bin_a_id


# --- Variance preview ---------------------------------------------------------


async def test_variance_preview_shows_counted_minus_system(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    setup = await build_stock_setup(db_session, tenant_a)
    await build_stock(
        db_session, tenant_a, setup.item_id, setup.bin_a_id, Decimal(10), unit_cost=Decimal(4)
    )
    count = await _create_count(
        db_session,
        tenant_a,
        StockCountCreate(count_type=CountType.PHYSICAL, warehouse_id=setup.warehouse_id),
    )
    line = (await _lines(db_session, tenant_a, count.id))[0]
    await _record(db_session, tenant_a, count.id, line.id, Decimal(12))

    with tenant_context(tenant_a):
        preview = await service.variance_preview(db_session, tenant_a, count.id)
    assert len(preview.lines) == 1
    pl = preview.lines[0]
    assert pl.system_qty == Decimal(10)
    assert pl.counted_qty == Decimal(12)
    assert pl.variance_qty == Decimal(2)
    # +2 units at the moving-average book cost 4 = +8 value impact.
    assert pl.estimated_value_impact == Decimal(8)
    assert preview.total_value_impact == Decimal(8)


# --- Post: positive / negative / zero variance --------------------------------


async def test_positive_variance_posts_adjustment_in_and_journal(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """A positive variance posts an ADJUSTMENT-in move (on-hand rises) AND a price-difference
    journal via the 5.3 path; on-hand after post equals the counted qty; the count→move docflow
    link exists."""
    setup = await build_stock_setup(db_session, tenant_a)
    await build_stock(
        db_session, tenant_a, setup.item_id, setup.bin_a_id, Decimal(10), unit_cost=Decimal(4)
    )
    count = await _create_count(
        db_session,
        tenant_a,
        StockCountCreate(count_type=CountType.PHYSICAL, warehouse_id=setup.warehouse_id),
    )
    line = (await _lines(db_session, tenant_a, count.id))[0]
    await _record(db_session, tenant_a, count.id, line.id, Decimal(13))
    await _post(db_session, tenant_a, count.id)

    posted_line = (await _lines(db_session, tenant_a, count.id))[0]
    assert posted_line.variance_qty == Decimal(3)
    assert posted_line.adjustment_move_id is not None
    # On-hand after post equals the counted qty (13), not system+something.
    with tenant_context(tenant_a):
        on_hand = await queries.on_hand(db_session, tenant_a, setup.item_id, setup.bin_a_id)
    assert on_hand == Decimal(13)
    # The generated move is an ADJUSTMENT-in (to_bin set).
    with tenant_context(tenant_a):
        move = await service.get_move(db_session, tenant_a, posted_line.adjustment_move_id)
    assert MoveType(move.move_type) == MoveType.ADJUSTMENT
    assert move.to_bin_id == setup.bin_a_id and move.from_bin_id is None
    # A price-difference journal exists (the adjustment posted via the 5.3 path).
    assert await _cogs_entry_count(db_session, tenant_a) >= 1
    # The count→move docflow link ('counts') exists.
    assert await _count_links_to_move(db_session, tenant_a, count.document_id, move.document_id)


async def test_negative_variance_posts_adjustment_out(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    setup = await build_stock_setup(db_session, tenant_a)
    await build_stock(
        db_session, tenant_a, setup.item_id, setup.bin_a_id, Decimal(10), unit_cost=Decimal(4)
    )
    count = await _create_count(
        db_session,
        tenant_a,
        StockCountCreate(count_type=CountType.PHYSICAL, warehouse_id=setup.warehouse_id),
    )
    line = (await _lines(db_session, tenant_a, count.id))[0]
    await _record(db_session, tenant_a, count.id, line.id, Decimal(6))
    await _post(db_session, tenant_a, count.id)

    posted_line = (await _lines(db_session, tenant_a, count.id))[0]
    assert posted_line.variance_qty == Decimal(-4)
    with tenant_context(tenant_a):
        move = await service.get_move(db_session, tenant_a, posted_line.adjustment_move_id)
        on_hand = await queries.on_hand(db_session, tenant_a, setup.item_id, setup.bin_a_id)
    assert move.from_bin_id == setup.bin_a_id and move.to_bin_id is None
    assert on_hand == Decimal(6)


async def test_zero_variance_line_creates_no_move(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    setup = await build_stock_setup(db_session, tenant_a)
    await build_stock(db_session, tenant_a, setup.item_id, setup.bin_a_id, Decimal(10))
    count = await _create_count(
        db_session,
        tenant_a,
        StockCountCreate(count_type=CountType.PHYSICAL, warehouse_id=setup.warehouse_id),
    )
    line = (await _lines(db_session, tenant_a, count.id))[0]
    await _record(db_session, tenant_a, count.id, line.id, Decimal(10))
    await _post(db_session, tenant_a, count.id)

    posted_line = (await _lines(db_session, tenant_a, count.id))[0]
    assert posted_line.variance_qty == Decimal(0)
    assert posted_line.adjustment_move_id is None


# --- Concurrency / re-validation ----------------------------------------------


async def test_post_uses_live_on_hand_not_stale_snapshot(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """If on-hand changes AFTER the snapshot but BEFORE posting, the posted variance uses the LIVE
    on-hand at post time — the resulting on-hand equals the counted qty, not counted − stale."""
    setup = await build_stock_setup(db_session, tenant_a)
    await build_stock(
        db_session, tenant_a, setup.item_id, setup.bin_a_id, Decimal(10), unit_cost=Decimal(4)
    )
    count = await _create_count(
        db_session,
        tenant_a,
        StockCountCreate(count_type=CountType.PHYSICAL, warehouse_id=setup.warehouse_id),
    )
    line = (await _lines(db_session, tenant_a, count.id))[0]
    assert Decimal(line.system_qty) == Decimal(10)  # snapshot at 10
    await _record(db_session, tenant_a, count.id, line.id, Decimal(15))

    # A concurrent receipt lands AFTER the count was created: live on-hand is now 18.
    await build_stock(
        db_session, tenant_a, setup.item_id, setup.bin_a_id, Decimal(8), unit_cost=Decimal(4)
    )
    await _post(db_session, tenant_a, count.id)

    posted_line = (await _lines(db_session, tenant_a, count.id))[0]
    # Variance is counted(15) − LIVE(18) = -3, NOT counted(15) − stale(10) = +5.
    assert posted_line.variance_qty == Decimal(-3)
    with tenant_context(tenant_a):
        on_hand = await queries.on_hand(db_session, tenant_a, setup.item_id, setup.bin_a_id)
    assert on_hand == Decimal(15)  # the counted qty, exactly


# --- Guards: all-counted, re-post, cancel -------------------------------------


async def test_post_requires_all_lines_counted(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    setup = await build_stock_setup(db_session, tenant_a)
    await build_stock(db_session, tenant_a, setup.item_id, setup.bin_a_id, Decimal(5))
    await build_stock(db_session, tenant_a, setup.item_id, setup.bin_b_id, Decimal(5))
    count = await _create_count(
        db_session,
        tenant_a,
        StockCountCreate(count_type=CountType.PHYSICAL, warehouse_id=setup.warehouse_id),
    )
    lines = await _lines(db_session, tenant_a, count.id)
    await _record(db_session, tenant_a, count.id, lines[0].id, Decimal(5))  # only one counted
    with pytest.raises(Exception) as exc:  # noqa: PT011
        await _post(db_session, tenant_a, count.id)
    assert "uncounted" in str(getattr(exc.value, "code", ""))


async def test_reposting_a_posted_count_is_rejected(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    setup = await build_stock_setup(db_session, tenant_a)
    await build_stock(db_session, tenant_a, setup.item_id, setup.bin_a_id, Decimal(10))
    count = await _create_count(
        db_session,
        tenant_a,
        StockCountCreate(count_type=CountType.PHYSICAL, warehouse_id=setup.warehouse_id),
    )
    line = (await _lines(db_session, tenant_a, count.id))[0]
    await _record(db_session, tenant_a, count.id, line.id, Decimal(12))
    await _post(db_session, tenant_a, count.id)
    moves_after_first = await _move_count(db_session, tenant_a)

    with pytest.raises(Exception) as exc:  # noqa: PT011
        await _post(db_session, tenant_a, count.id)
    assert "already_posted" in str(getattr(exc.value, "code", ""))
    # No double adjustment.
    assert await _move_count(db_session, tenant_a) == moves_after_first


async def test_cancel_on_draft_works(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    setup = await build_stock_setup(db_session, tenant_a)
    await build_stock(db_session, tenant_a, setup.item_id, setup.bin_a_id, Decimal(10))
    count = await _create_count(
        db_session,
        tenant_a,
        StockCountCreate(count_type=CountType.PHYSICAL, warehouse_id=setup.warehouse_id),
    )

    async def cancel() -> None:
        with tenant_context(tenant_a):
            await service.cancel_count(db_session, tenant_a, count.id)

    with tenant_context(tenant_a):
        await run_in_uow(db_session, cancel)
        refreshed = await service.get_count(db_session, tenant_a, count.id)
    assert CountStatus(refreshed.status) == CountStatus.CANCELLED


async def test_cancel_on_posted_count_is_rejected(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """A POSTED count is terminal — cancelling it is a 409 (corrections are new counts)."""
    setup = await build_stock_setup(db_session, tenant_a)
    await build_stock(db_session, tenant_a, setup.item_id, setup.bin_a_id, Decimal(10))
    count = await _create_count(
        db_session,
        tenant_a,
        StockCountCreate(count_type=CountType.PHYSICAL, warehouse_id=setup.warehouse_id),
    )
    line = (await _lines(db_session, tenant_a, count.id))[0]
    await _record(db_session, tenant_a, count.id, line.id, Decimal(11))
    await _post(db_session, tenant_a, count.id)

    async def cancel_posted() -> None:
        with tenant_context(tenant_a):
            await service.cancel_count(db_session, tenant_a, count.id)

    with pytest.raises(Exception) as exc, tenant_context(tenant_a):  # noqa: PT011
        await run_in_uow(db_session, cancel_posted)
    assert "not_cancellable" in str(getattr(exc.value, "code", ""))


# --- Closed period ------------------------------------------------------------


async def test_closed_period_count_date_rolls_back_the_post(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """A closed-period count_date makes the variance adjustment's journal trip the period trigger,
    rolling the whole post back — the count stays unposted (D-038/D-018)."""
    setup = await build_stock_setup(db_session, tenant_a)
    await build_stock(
        db_session, tenant_a, setup.item_id, setup.bin_a_id, Decimal(10),
        unit_cost=Decimal(4), move_date=date(2026, 6, 1),
    )
    count = await _create_count(
        db_session,
        tenant_a,
        StockCountCreate(
            count_type=CountType.PHYSICAL,
            warehouse_id=setup.warehouse_id,
            count_date=date(2026, 6, 15),
        ),
    )
    count_id = count.id  # plain local: the rollback below expires the ORM object
    line = (await _lines(db_session, tenant_a, count_id))[0]
    await _record(db_session, tenant_a, count_id, line.id, Decimal(13))
    await _close_june_2026(db_session, tenant_a)
    moves_before = await _move_count(db_session, tenant_a)

    with pytest.raises(Exception):  # noqa: PT011, B017 - period trigger / service error
        await _post(db_session, tenant_a, count_id)
    # The post rolled back: no new move, the count is not POSTED.
    assert await _move_count(db_session, tenant_a) == moves_before
    with tenant_context(tenant_a):
        refreshed = await service.get_count(db_session, tenant_a, count_id)
    assert CountStatus(refreshed.status) != CountStatus.POSTED


# --- Lot-tracked --------------------------------------------------------------


async def test_lot_tracked_count_adjusts_the_right_lot(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    setup = await build_stock_setup(db_session, tenant_a, tracking_mode="LOT")
    await build_stock(
        db_session, tenant_a, setup.item_id, setup.bin_a_id, Decimal(10),
        lot_code="LOT-1", unit_cost=Decimal(4),
    )
    count = await _create_count(
        db_session,
        tenant_a,
        StockCountCreate(count_type=CountType.PHYSICAL, warehouse_id=setup.warehouse_id),
    )
    line = (await _lines(db_session, tenant_a, count.id))[0]
    assert line.lot_id is not None
    await _record(db_session, tenant_a, count.id, line.id, Decimal(14))
    await _post(db_session, tenant_a, count.id)

    posted_line = (await _lines(db_session, tenant_a, count.id))[0]
    with tenant_context(tenant_a):
        move = await service.get_move(db_session, tenant_a, posted_line.adjustment_move_id)
        on_hand = await queries.on_hand(
            db_session, tenant_a, setup.item_id, setup.bin_a_id, lot_id=line.lot_id
        )
    assert move.lot_id == line.lot_id
    assert on_hand == Decimal(14)


# --- Tenant isolation ---------------------------------------------------------


async def test_get_count_is_tenant_scoped(
    db_session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    setup = await build_stock_setup(db_session, tenant_a)
    await build_stock(db_session, tenant_a, setup.item_id, setup.bin_a_id, Decimal(10))
    count = await _create_count(
        db_session,
        tenant_a,
        StockCountCreate(count_type=CountType.PHYSICAL, warehouse_id=setup.warehouse_id),
    )
    with pytest.raises(Exception) as exc, tenant_context(tenant_b):  # noqa: PT011 - cross-tenant
        await service.get_count(db_session, tenant_b, count.id)
    assert "not_found" in str(getattr(exc.value, "code", ""))


# --- Helpers ------------------------------------------------------------------


async def _move_count(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    from sqlalchemy import func

    from app.modules.inventory.models import StockMove

    with tenant_context(tenant_id):
        return (
            await session.execute(
                select(func.count(StockMove.id)).where(StockMove.tenant_id == tenant_id)
            )
        ).scalar_one()


async def _cogs_entry_count(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    from sqlalchemy import func

    with tenant_context(tenant_id):
        return (
            await session.execute(
                select(func.count(JournalEntry.id)).where(
                    JournalEntry.tenant_id == tenant_id,
                    JournalEntry.document_type == DocumentType.COGS.value,
                )
            )
        ).scalar_one()


async def _count_links_to_move(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    count_document_id: uuid.UUID,
    move_document_id: uuid.UUID,
) -> bool:
    with tenant_context(tenant_id):
        chain = await docflow.get_document_chain(session, tenant_id, count_document_id)
    return any(
        edge.link_type == STOCK_COUNT_ADJUSTMENT_LINK
        and edge.predecessor_document_id == count_document_id
        and edge.successor_document_id == move_document_id
        for edge in chain.edges
    )


async def _close_june_2026(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    from app.modules.finance import queries as finance_queries
    from app.modules.finance import service as finance_service

    with tenant_context(tenant_id):
        period = await finance_queries.find_period_for_date(
            session, tenant_id, date(2026, 6, 15)
        )
        await finance_service.close_period(session, tenant_id, period.id)
        await session.commit()
