"""The inventory->finance same-transaction COGS seam (PLAN 5.3, D-020/D-011): event flow, atomic
rollback, the GL postings per move type, the closed-period interaction, and reversal.

This is the most load-bearing invariant in the codebase: a stock move and its COGS/inventory journal
commit or roll back as ONE transaction. Moves go through the REAL service inside a uow (D-025), the
COGS handler is registered by the inventory conftest's autouse fixture, and these tests assert the
posted journal directly.
"""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import run_in_uow
from app.core.tenancy import tenant_context
from app.modules.finance.constants import DocumentType, EntryStatus
from app.modules.finance.models import JournalEntry, JournalLine
from app.modules.inventory import service
from app.modules.inventory.constants import CostingMethod, MoveType
from app.modules.inventory.models import StockMove
from app.modules.inventory.schemas import StockMoveCreate
from tests.modules.inventory.factories import build_stock, build_stock_setup


async def _post_move(session: AsyncSession, tenant_id: uuid.UUID, payload: StockMoveCreate):
    holder: dict[str, uuid.UUID] = {}

    async def work() -> None:
        with tenant_context(tenant_id):
            move = await service.create_move(session, tenant_id, payload)
            holder["id"] = move.id

    with tenant_context(tenant_id):
        await run_in_uow(session, work)
        return await service.get_move(session, tenant_id, holder["id"])


async def _entries(
    session: AsyncSession, tenant_id: uuid.UUID
) -> list[JournalEntry]:
    with tenant_context(tenant_id):
        return (
            await session.execute(
                select(JournalEntry).where(
                    JournalEntry.tenant_id == tenant_id,
                    JournalEntry.document_type == DocumentType.COGS.value,
                )
            )
        ).scalars().all()


async def _lines(
    session: AsyncSession, tenant_id: uuid.UUID, entry_id: uuid.UUID
) -> list[JournalLine]:
    with tenant_context(tenant_id):
        return (
            await session.execute(
                select(JournalLine).where(JournalLine.journal_entry_id == entry_id)
            )
        ).scalars().all()


def _debit(lines: list[JournalLine], account_id: uuid.UUID) -> Decimal:
    return sum(
        (Decimal(line.transaction_debit_amount) for line in lines if line.account_id == account_id),
        Decimal(0),
    )


def _credit(lines: list[JournalLine], account_id: uuid.UUID) -> Decimal:
    return sum(
        (
            Decimal(line.transaction_credit_amount)
            for line in lines
            if line.account_id == account_id
        ),
        Decimal(0),
    )


# --- Same-transaction COGS ----------------------------------------------------


async def test_issue_posts_cogs_journal_in_same_transaction(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """An ISSUE posts a balanced Dr COGS / Cr Inventory entry at the computed cost (D-020). The
    entry
    is POSTED and dimension-tagged with the item."""
    setup = await build_stock_setup(db_session, tenant_a)
    await build_stock(
        db_session, tenant_a, setup.item_id, setup.bin_a_id, Decimal(10), unit_cost=Decimal(3)
    )
    await _post_move(
        db_session,
        tenant_a,
        StockMoveCreate(
            move_type=MoveType.ISSUE,
            item_id=setup.item_id,
            quantity=Decimal(4),
            from_bin_id=setup.bin_a_id,
        ),
    )
    entries = await _entries(db_session, tenant_a)
    # One receipt entry + one issue entry.
    assert len(entries) == 2
    issue_entry = max(entries, key=lambda e: e.created_at)
    assert issue_entry.status == EntryStatus.POSTED.value
    lines = await _lines(db_session, tenant_a, issue_entry.id)
    assert _debit(lines, setup.cogs_account_id) == Decimal(12)
    assert _credit(lines, setup.inventory_account_id) == Decimal(12)
    assert all(line.item_id == setup.item_id for line in lines)


async def test_handler_failure_rolls_back_the_stock_move(
    db_session: AsyncSession, tenant_a: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A forced COGS-handler failure rolls back EVERYTHING: the move + quant change are gone (the
    atomic guarantee, D-011/D-020). Proves a stock move can never commit without its journal."""
    setup = await build_stock_setup(db_session, tenant_a)
    await build_stock(
        db_session, tenant_a, setup.item_id, setup.bin_a_id, Decimal(10), unit_cost=Decimal(3)
    )
    moves_before = await _count_moves(db_session, tenant_a)

    async def _boom(session, event):
        raise RuntimeError("forced COGS handler failure")

    monkeypatch.setattr(
        "app.modules.finance.handlers.post_stock_valuation_journal", _boom
    )
    # Re-register so the bus dispatches the patched handler.
    from app.core.events import clear_subscriptions, subscribe
    from app.modules.inventory.events import StockValued

    clear_subscriptions()
    subscribe(StockValued.key, _boom)

    with pytest.raises(RuntimeError, match="forced COGS handler failure"):
        await _post_move(
            db_session,
            tenant_a,
            StockMoveCreate(
                move_type=MoveType.ISSUE,
                item_id=setup.item_id,
                quantity=Decimal(4),
                from_bin_id=setup.bin_a_id,
            ),
        )
    # The move (and its quant decrement) never committed.
    assert await _count_moves(db_session, tenant_a) == moves_before
    with tenant_context(tenant_a):
        from app.modules.inventory import queries

        on_hand = await queries.total_on_hand(db_session, tenant_a, setup.item_id)
    assert on_hand == Decimal(10)


async def _count_moves(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    with tenant_context(tenant_id):
        return len(
            (
                await session.execute(
                    select(StockMove.id).where(StockMove.tenant_id == tenant_id)
                )
            ).all()
        )


# --- Postings per move type ---------------------------------------------------


async def test_receipt_posts_inventory_against_adjustment(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """A standalone RECEIPT posts Dr Inventory / Cr price-difference at qty × unit_cost (D-020)."""
    setup = await build_stock_setup(db_session, tenant_a)
    await build_stock(
        db_session, tenant_a, setup.item_id, setup.bin_a_id, Decimal(5), unit_cost=Decimal(2)
    )
    entries = await _entries(db_session, tenant_a)
    assert len(entries) == 1
    lines = await _lines(db_session, tenant_a, entries[0].id)
    assert _debit(lines, setup.inventory_account_id) == Decimal(10)
    assert _credit(lines, setup.price_difference_account_id) == Decimal(10)


async def test_adjustment_down_posts_price_difference_against_inventory(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """A stock-decrease ADJUSTMENT posts Dr price-difference / Cr inventory at the computed cost: it
    removes value with no business document behind it, so it hits the adjustment account, not COGS
    (D-020)."""
    setup = await build_stock_setup(db_session, tenant_a)
    await build_stock(
        db_session, tenant_a, setup.item_id, setup.bin_a_id, Decimal(10), unit_cost=Decimal(3)
    )
    await _post_move(
        db_session,
        tenant_a,
        StockMoveCreate(
            move_type=MoveType.ADJUSTMENT,
            item_id=setup.item_id,
            quantity=Decimal(2),
            from_bin_id=setup.bin_a_id,
        ),
    )
    entries = await _entries(db_session, tenant_a)
    adjust_entry = max(entries, key=lambda e: e.created_at)
    lines = await _lines(db_session, tenant_a, adjust_entry.id)
    # A decrease is the outbound path to price-difference: Dr price-difference / Cr inventory at 6.
    assert _debit(lines, setup.price_difference_account_id) == Decimal(6)
    assert _credit(lines, setup.inventory_account_id) == Decimal(6)


async def test_transfer_within_warehouse_posts_no_journal(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """A TRANSFER between two bins of ONE warehouse is value-neutral → NO journal, but the stock
    moves between bins (D-037)."""
    setup = await build_stock_setup(db_session, tenant_a)
    await build_stock(
        db_session, tenant_a, setup.item_id, setup.bin_a_id, Decimal(10), unit_cost=Decimal(3)
    )
    entries_before = len(await _entries(db_session, tenant_a))
    await _post_move(
        db_session,
        tenant_a,
        StockMoveCreate(
            move_type=MoveType.TRANSFER,
            item_id=setup.item_id,
            quantity=Decimal(4),
            from_bin_id=setup.bin_a_id,
            to_bin_id=setup.bin_b_id,
        ),
    )
    # No new journal entry — value-neutral within one inventory account.
    assert len(await _entries(db_session, tenant_a)) == entries_before
    with tenant_context(tenant_a):
        from app.modules.inventory import queries

        a = await queries.on_hand(db_session, tenant_a, setup.item_id, setup.bin_a_id)
        b = await queries.on_hand(db_session, tenant_a, setup.item_id, setup.bin_b_id)
    assert a == Decimal(6)
    assert b == Decimal(4)


# --- Closed period ------------------------------------------------------------


async def test_issue_into_closed_period_fails_and_rolls_back(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """A move whose COGS journal would land in a CLOSED period fails (the period trigger fires in
    the
    same transaction) and the whole move rolls back — you cannot move stock into a closed period."""
    setup = await build_stock_setup(db_session, tenant_a)
    await build_stock(
        db_session, tenant_a, setup.item_id, setup.bin_a_id, Decimal(10), unit_cost=Decimal(3)
    )
    # Close the period covering the issue date (June 2026).
    await _close_june_2026(db_session, tenant_a)
    moves_before = await _count_moves(db_session, tenant_a)

    from datetime import date

    with pytest.raises(Exception) as exc:  # noqa: PT011 - period trigger / service error
        await _post_move(
            db_session,
            tenant_a,
            StockMoveCreate(
                move_type=MoveType.ISSUE,
                item_id=setup.item_id,
                quantity=Decimal(2),
                from_bin_id=setup.bin_a_id,
                move_date=date(2026, 6, 15),
            ),
        )
    assert "period" in str(getattr(exc.value, "code", "")) or "PERIOD" in str(exc.value)
    # The move rolled back.
    assert await _count_moves(db_session, tenant_a) == moves_before


async def _close_june_2026(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    from datetime import date

    from app.modules.finance import queries as finance_queries
    from app.modules.finance import service as finance_service

    with tenant_context(tenant_id):
        period = await finance_queries.find_period_for_date(
            session, tenant_id, date(2026, 6, 15)
        )
        await finance_service.close_period(session, tenant_id, period.id)
        await session.commit()


# --- Reversal -----------------------------------------------------------------


async def test_reverse_fifo_issue_restores_layers_and_reverses_journal(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """Reversing a FIFO issue restores the consumed layers' remaining_qty exactly AND posts the
    reversing COGS journal (Cr COGS / Dr Inventory) in the same transaction (D-020)."""
    from datetime import date

    from app.modules.inventory.models import CostLayer

    setup = await build_stock_setup(db_session, tenant_a, costing=CostingMethod.FIFO)
    await build_stock(
        db_session, tenant_a, setup.item_id, setup.bin_a_id, Decimal(10),
        unit_cost=Decimal(2), move_date=date(2026, 6, 1),
    )
    issue = await _post_move(
        db_session,
        tenant_a,
        StockMoveCreate(
            move_type=MoveType.ISSUE,
            item_id=setup.item_id,
            quantity=Decimal(4),
            from_bin_id=setup.bin_a_id,
        ),
    )
    holder: dict[str, uuid.UUID] = {}

    async def work() -> None:
        with tenant_context(tenant_a):
            reversal = await service.reverse_move(db_session, tenant_a, issue.id)
            holder["id"] = reversal.id

    with tenant_context(tenant_a):
        await run_in_uow(db_session, work)
        layer = (
            await db_session.execute(
                select(CostLayer).where(
                    CostLayer.tenant_id == tenant_a, CostLayer.item_id == setup.item_id
                )
            )
        ).scalars().one()
    # The consumed layer is restored to full.
    assert Decimal(layer.remaining_qty) == Decimal(10)
    # Three COGS entries: receipt, issue, reversal of the issue.
    entries = await _entries(db_session, tenant_a)
    assert len(entries) == 3
    reversal_entry = max(entries, key=lambda e: e.created_at)
    lines = await _lines(db_session, tenant_a, reversal_entry.id)
    # The reversal flips the issue: Dr Inventory / Cr COGS at 4 × 2 = 8.
    assert _debit(lines, setup.inventory_account_id) == Decimal(8)
    assert _credit(lines, setup.cogs_account_id) == Decimal(8)


async def test_reverse_mav_issue_restores_valuation(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """Reversing a moving-average issue restores the valuation (value + on_hand) it removed."""
    from app.modules.inventory.models import ItemValuation

    setup = await build_stock_setup(db_session, tenant_a, costing=CostingMethod.MOVING_AVERAGE)
    await build_stock(
        db_session, tenant_a, setup.item_id, setup.bin_a_id, Decimal(10), unit_cost=Decimal(3)
    )
    issue = await _post_move(
        db_session,
        tenant_a,
        StockMoveCreate(
            move_type=MoveType.ISSUE,
            item_id=setup.item_id,
            quantity=Decimal(4),
            from_bin_id=setup.bin_a_id,
        ),
    )

    async def work() -> None:
        with tenant_context(tenant_a):
            await service.reverse_move(db_session, tenant_a, issue.id)

    with tenant_context(tenant_a):
        await run_in_uow(db_session, work)
        valuation = (
            await db_session.execute(
                select(ItemValuation).where(
                    ItemValuation.tenant_id == tenant_a,
                    ItemValuation.item_id == setup.item_id,
                )
            )
        ).scalars().one()
    # Back to the pre-issue state: 10 on hand at value 30.
    assert valuation.on_hand_qty == Decimal(10)
    assert valuation.total_value == Decimal(30)


# --- RBAC + tenant isolation --------------------------------------------------


async def test_valuation_endpoints_require_permission(
    inventory_user_factory, client
) -> None:
    """The valuation read endpoints are gated by inventory.valuation.read (D-009): a principal
    without it gets 403."""
    principal = await inventory_user_factory(
        slug="inv-noval", email="noval@inv.test", keys=("inventory.move.read",)
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": principal.tenant_slug,
            "email": principal.email,
            "password": principal.password,
        },
    )
    token = login.json()["access_token"]
    response = await client.get(
        "/api/v1/inventory/stock-valuations",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


async def test_valuation_tenant_isolation(
    db_session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """Tenant A's valuation rows are invisible to tenant B (D-007)."""
    from app.modules.inventory import queries

    setup_a = await build_stock_setup(db_session, tenant_a)
    await build_stock(
        db_session, tenant_a, setup_a.item_id, setup_a.bin_a_id, Decimal(5), unit_cost=Decimal(4)
    )
    with tenant_context(tenant_a):
        value_a = await queries.item_value(db_session, tenant_a, setup_a.item_id)
    with tenant_context(tenant_b):
        value_b = await queries.item_value(db_session, tenant_b, setup_a.item_id)
    assert value_a == Decimal(20)
    assert value_b == Decimal(0)


# --- Query budget on the read endpoints ---------------------------------------


async def test_valuation_read_endpoints_within_budget(
    inventory_client, query_counter, stock_setup
) -> None:
    """The valuation list + cost-layer list endpoints are within the PERFORMANCE §6 query budget."""
    from tests.conftest import assert_query_budget

    await assert_query_budget(
        inventory_client, query_counter, "/api/v1/inventory/stock-valuations"
    )
    await assert_query_budget(
        inventory_client,
        query_counter,
        f"/api/v1/inventory/items/{stock_setup.item_id}/cost-layers",
    )
