"""Stock-move engine tests (PLAN 5.2, D-020/D-036): the heart.

Receipt increments to_bin; issue decrements from_bin and is blocked beyond on-hand (422 +
CHECK backstop); transfer conserves total; adjustment; lot/serial behaviour; reversal restores
quants; numbering is gapless; create_move runs a bounded number of statements (not N+1).

Moves go through the real service inside a uow (numbering, docflow, quant maintenance fire as in
production). The ``build_move`` factory wraps that; tests assert against the on-hand projection via
``inventory.queries``.
"""

import uuid
from collections.abc import Callable
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import tenant_context
from app.modules.inventory import queries, service
from app.modules.inventory.constants import MoveType
from app.modules.inventory.models import StockQuant
from app.modules.inventory.schemas import StockMoveCreate
from app.modules.inventory.service.stock_quants import InsufficientStockError
from tests.modules.inventory.conftest import StockSetup
from tests.modules.inventory.factories import build_move, build_stock, build_stock_setup


async def test_receipt_increments_to_bin_quant(
    db_session: AsyncSession, stock_setup: StockSetup
) -> None:
    await build_stock(
        db_session, stock_setup.tenant_id, stock_setup.item_id, stock_setup.bin_a_id, Decimal(10)
    )
    with tenant_context(stock_setup.tenant_id):
        on_hand = await queries.on_hand(
            db_session, stock_setup.tenant_id, stock_setup.item_id, stock_setup.bin_a_id
        )
    assert on_hand == Decimal(10)


async def test_issue_decrements_from_bin_quant(
    db_session: AsyncSession, stock_setup: StockSetup
) -> None:
    await build_stock(
        db_session, stock_setup.tenant_id, stock_setup.item_id, stock_setup.bin_a_id, Decimal(10)
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
        on_hand = await queries.on_hand(
            db_session, stock_setup.tenant_id, stock_setup.item_id, stock_setup.bin_a_id
        )
    assert on_hand == Decimal(6)


async def test_issue_beyond_on_hand_raises_insufficient_stock(
    db_session: AsyncSession, stock_setup: StockSetup
) -> None:
    await build_stock(
        db_session, stock_setup.tenant_id, stock_setup.item_id, stock_setup.bin_a_id, Decimal(3)
    )
    with tenant_context(stock_setup.tenant_id), pytest.raises(InsufficientStockError) as exc:
        await service.create_move(
            db_session,
            stock_setup.tenant_id,
            StockMoveCreate(
                move_type=MoveType.ISSUE,
                item_id=stock_setup.item_id,
                quantity=Decimal(5),
                from_bin_id=stock_setup.bin_a_id,
            ),
        )
    assert exc.value.code == "inventory.insufficient_stock"
    assert exc.value.status_code == 422


async def test_negative_quant_check_backstops_at_db(
    db_session: AsyncSession, stock_setup: StockSetup
) -> None:
    """The CHECK(on_hand_qty >= 0) fires even if the service pre-flight is bypassed (D-020):
    inserting a negative quant directly is rejected by the DB on both engines."""
    await build_stock(
        db_session, stock_setup.tenant_id, stock_setup.item_id, stock_setup.bin_a_id, Decimal(1)
    )
    with tenant_context(stock_setup.tenant_id):
        db_session.add(
            StockQuant(
                tenant_id=stock_setup.tenant_id,
                item_id=stock_setup.item_id,
                bin_id=stock_setup.bin_b_id,
                lot_id=None,
                on_hand_qty=Decimal(-1),
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.flush()
    await db_session.rollback()


async def test_transfer_conserves_total_on_hand(
    db_session: AsyncSession, stock_setup: StockSetup
) -> None:
    await build_stock(
        db_session, stock_setup.tenant_id, stock_setup.item_id, stock_setup.bin_a_id, Decimal(10)
    )
    await build_move(
        db_session,
        stock_setup.tenant_id,
        StockMoveCreate(
            move_type=MoveType.TRANSFER,
            item_id=stock_setup.item_id,
            quantity=Decimal(4),
            from_bin_id=stock_setup.bin_a_id,
            to_bin_id=stock_setup.bin_b_id,
        ),
    )
    with tenant_context(stock_setup.tenant_id):
        a = await queries.on_hand(
            db_session, stock_setup.tenant_id, stock_setup.item_id, stock_setup.bin_a_id
        )
        b = await queries.on_hand(
            db_session, stock_setup.tenant_id, stock_setup.item_id, stock_setup.bin_b_id
        )
        total = await queries.total_on_hand(
            db_session, stock_setup.tenant_id, stock_setup.item_id
        )
    assert a == Decimal(6)
    assert b == Decimal(4)
    assert total == Decimal(10)


async def test_transfer_same_bin_rejected(
    db_session: AsyncSession, stock_setup: StockSetup
) -> None:
    await build_stock(
        db_session, stock_setup.tenant_id, stock_setup.item_id, stock_setup.bin_a_id, Decimal(5)
    )
    with tenant_context(stock_setup.tenant_id), pytest.raises(Exception) as exc:
        await service.create_move(
            db_session,
            stock_setup.tenant_id,
            StockMoveCreate(
                move_type=MoveType.TRANSFER,
                item_id=stock_setup.item_id,
                quantity=Decimal(1),
                from_bin_id=stock_setup.bin_a_id,
                to_bin_id=stock_setup.bin_a_id,
            ),
        )
    assert getattr(exc.value, "code", "") == "inventory.transfer_same_bin"


async def test_adjustment_increase_and_decrease(
    db_session: AsyncSession, stock_setup: StockSetup
) -> None:
    """An ADJUSTMENT sets exactly one side: to_bin increases, from_bin decreases."""
    await build_move(
        db_session,
        stock_setup.tenant_id,
        StockMoveCreate(
            move_type=MoveType.ADJUSTMENT,
            item_id=stock_setup.item_id,
            quantity=Decimal(8),
            to_bin_id=stock_setup.bin_a_id,
            unit_cost=Decimal(1),
        ),
    )
    await build_move(
        db_session,
        stock_setup.tenant_id,
        StockMoveCreate(
            move_type=MoveType.ADJUSTMENT,
            item_id=stock_setup.item_id,
            quantity=Decimal(3),
            from_bin_id=stock_setup.bin_a_id,
        ),
    )
    with tenant_context(stock_setup.tenant_id):
        on_hand = await queries.on_hand(
            db_session, stock_setup.tenant_id, stock_setup.item_id, stock_setup.bin_a_id
        )
    assert on_hand == Decimal(5)


async def test_adjustment_two_sides_rejected(
    db_session: AsyncSession, stock_setup: StockSetup
) -> None:
    with tenant_context(stock_setup.tenant_id), pytest.raises(Exception) as exc:
        await service.create_move(
            db_session,
            stock_setup.tenant_id,
            StockMoveCreate(
                move_type=MoveType.ADJUSTMENT,
                item_id=stock_setup.item_id,
                quantity=Decimal(1),
                from_bin_id=stock_setup.bin_a_id,
                to_bin_id=stock_setup.bin_b_id,
            ),
        )
    assert getattr(exc.value, "code", "") == "inventory.adjustment_one_side"


async def test_receipt_must_not_set_from_bin(
    db_session: AsyncSession, stock_setup: StockSetup
) -> None:
    """A RECEIPT sets to_bin only — a from_bin is forbidden (the bin-side rule, MOVE_BIN_SIDES)."""
    with tenant_context(stock_setup.tenant_id), pytest.raises(Exception) as exc:
        await service.create_move(
            db_session,
            stock_setup.tenant_id,
            StockMoveCreate(
                move_type=MoveType.RECEIPT,
                item_id=stock_setup.item_id,
                quantity=Decimal(1),
                from_bin_id=stock_setup.bin_a_id,
            ),
        )
    assert getattr(exc.value, "code", "") == "inventory.move_from_bin_forbidden"


async def test_receipt_requires_to_bin(
    db_session: AsyncSession, stock_setup: StockSetup
) -> None:
    """A RECEIPT with neither bin fails on the missing required to_bin."""
    with tenant_context(stock_setup.tenant_id), pytest.raises(Exception) as exc:
        await service.create_move(
            db_session,
            stock_setup.tenant_id,
            StockMoveCreate(
                move_type=MoveType.RECEIPT,
                item_id=stock_setup.item_id,
                quantity=Decimal(1),
            ),
        )
    assert getattr(exc.value, "code", "") == "inventory.move_to_bin_required"


async def test_lot_receipt_creates_master_and_issue_reduces_lot(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    setup = await build_stock_setup(db_session, tenant_a, tracking_mode="LOT")
    # Receipt with a new lot code creates the lot master and stocks it.
    receipt = await build_stock(
        db_session,
        tenant_a,
        setup.item_id,
        setup.bin_a_id,
        Decimal(10),
        lot_code="LOT-001",
    )
    assert receipt.lot_id is not None
    with tenant_context(tenant_a):
        by_lot = await queries.on_hand_by_lot(db_session, tenant_a, setup.item_id)
    assert by_lot[receipt.lot_id] == Decimal(10)

    # Issue the lot reduces that lot's quant.
    await build_move(
        db_session,
        tenant_a,
        StockMoveCreate(
            move_type=MoveType.ISSUE,
            item_id=setup.item_id,
            quantity=Decimal(4),
            from_bin_id=setup.bin_a_id,
            lot_id=receipt.lot_id,
        ),
    )
    with tenant_context(tenant_a):
        remaining = await queries.on_hand(
            db_session, tenant_a, setup.item_id, lot_id=receipt.lot_id
        )
    assert remaining == Decimal(6)


async def test_lot_required_for_lot_tracked_item(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    setup = await build_stock_setup(db_session, tenant_a, tracking_mode="LOT")
    with tenant_context(tenant_a), pytest.raises(Exception) as exc:
        await service.create_move(
            db_session,
            tenant_a,
            StockMoveCreate(
                move_type=MoveType.RECEIPT,
                item_id=setup.item_id,
                quantity=Decimal(1),
                to_bin_id=setup.bin_a_id,
                unit_cost=Decimal(1),
            ),
        )
    assert getattr(exc.value, "code", "") == "inventory.lot_required"


async def test_serial_move_quantity_must_be_one(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    setup = await build_stock_setup(db_session, tenant_a, tracking_mode="SERIAL")
    # Valid: a serial receipt of qty 1 creates the serial master.
    receipt = await build_stock(
        db_session,
        tenant_a,
        setup.item_id,
        setup.bin_a_id,
        Decimal(1),
        serial_code="SN-001",
    )
    assert receipt.serial_id is not None
    # Invalid: qty != 1 for a serial-tracked item.
    with tenant_context(tenant_a), pytest.raises(Exception) as exc:
        await service.create_move(
            db_session,
            tenant_a,
            StockMoveCreate(
                move_type=MoveType.RECEIPT,
                item_id=setup.item_id,
                quantity=Decimal(2),
                to_bin_id=setup.bin_a_id,
                serial_code="SN-002",
                unit_cost=Decimal(1),
            ),
        )
    assert getattr(exc.value, "code", "") == "inventory.serial_quantity_invalid"


async def test_non_stocked_item_rejected(
    db_session: AsyncSession, stock_setup: StockSetup
) -> None:
    """A SERVICE/NON_STOCKED item cannot move stock."""
    from app.modules.inventory.models import Item
    from app.modules.inventory.schemas import ItemCreate

    with tenant_context(stock_setup.tenant_id):
        # Build a SERVICE item in the same tenant (reuse the stocked item's category + uom).
        stocked = await service.get_item(db_session, stock_setup.tenant_id, stock_setup.item_id)
        service_item: Item = await service.create_item(
            db_session,
            stock_setup.tenant_id,
            ItemCreate(
                item_code="SVC-1",
                name="A service",
                item_type="SERVICE",
                category_id=stocked.category_id,
                base_uom_id=stocked.base_uom_id,
            ),
        )
        await db_session.commit()
        with pytest.raises(Exception) as exc:
            await service.create_move(
                db_session,
                stock_setup.tenant_id,
                StockMoveCreate(
                    move_type=MoveType.RECEIPT,
                    item_id=service_item.id,
                    quantity=Decimal(1),
                    to_bin_id=stock_setup.bin_a_id,
                ),
            )
    assert getattr(exc.value, "code", "") == "inventory.item_not_stocked"


async def test_reverse_move_restores_quants(
    db_session: AsyncSession, stock_setup: StockSetup
) -> None:
    receipt = await build_stock(
        db_session, stock_setup.tenant_id, stock_setup.item_id, stock_setup.bin_a_id, Decimal(10)
    )
    # Issue 6, then reverse the issue → on-hand back to 10.
    issue = await build_move(
        db_session,
        stock_setup.tenant_id,
        StockMoveCreate(
            move_type=MoveType.ISSUE,
            item_id=stock_setup.item_id,
            quantity=Decimal(6),
            from_bin_id=stock_setup.bin_a_id,
        ),
    )

    holder: dict[str, uuid.UUID] = {}

    async def work() -> None:
        with tenant_context(stock_setup.tenant_id):
            reversal = await service.reverse_move(
                db_session, stock_setup.tenant_id, issue.id
            )
            holder["id"] = reversal.id

    from app.core.events import run_in_uow

    with tenant_context(stock_setup.tenant_id):
        await run_in_uow(db_session, work)
        reversal = await service.get_move(db_session, stock_setup.tenant_id, holder["id"])
        on_hand = await queries.on_hand(
            db_session, stock_setup.tenant_id, stock_setup.item_id, stock_setup.bin_a_id
        )
    # The reversing move is a RECEIPT (the issue's from_bin becomes its to_bin), restoring stock.
    assert reversal.move_type == MoveType.RECEIPT.value
    assert reversal.to_bin_id == stock_setup.bin_a_id
    assert on_hand == Decimal(10)
    assert receipt.id != reversal.id


async def test_double_reverse_rejected(
    db_session: AsyncSession, stock_setup: StockSetup
) -> None:
    await build_stock(
        db_session, stock_setup.tenant_id, stock_setup.item_id, stock_setup.bin_a_id, Decimal(10)
    )
    issue = await build_move(
        db_session,
        stock_setup.tenant_id,
        StockMoveCreate(
            move_type=MoveType.ISSUE,
            item_id=stock_setup.item_id,
            quantity=Decimal(2),
            from_bin_id=stock_setup.bin_a_id,
        ),
    )

    from app.core.events import run_in_uow

    async def reverse_once() -> None:
        with tenant_context(stock_setup.tenant_id):
            await service.reverse_move(db_session, stock_setup.tenant_id, issue.id)

    with tenant_context(stock_setup.tenant_id):
        await run_in_uow(db_session, reverse_once)
        with pytest.raises(Exception) as exc:
            await service.reverse_move(db_session, stock_setup.tenant_id, issue.id)
    assert getattr(exc.value, "code", "") == "inventory.move_already_reversed"
    await db_session.rollback()


async def test_move_numbers_are_gapless(
    db_session: AsyncSession, stock_setup: StockSetup
) -> None:
    m1 = await build_stock(
        db_session, stock_setup.tenant_id, stock_setup.item_id, stock_setup.bin_a_id, Decimal(1)
    )
    m2 = await build_stock(
        db_session, stock_setup.tenant_id, stock_setup.item_id, stock_setup.bin_a_id, Decimal(1)
    )
    m3 = await build_stock(
        db_session, stock_setup.tenant_id, stock_setup.item_id, stock_setup.bin_a_id, Decimal(1)
    )
    seqs = [int(m.move_number.rsplit("-", 1)[-1]) for m in (m1, m2, m3)]
    assert seqs == [seqs[0], seqs[0] + 1, seqs[0] + 2]


async def test_create_move_is_bounded_statement_count(
    db_session: AsyncSession,
    stock_setup: StockSetup,
    query_counter: Callable[..., object],
) -> None:
    """create_move runs a BOUNDED number of statements regardless of history (no N+1): one move,
    constant quant + numbering + docflow writes, the moving-average valuation update, and the
    same-transaction COGS journal posting (PLAN 5.3). The budget is generous slack above that
    constant shape — any growth with MOVE history (or, for FIFO, beyond the layers actually
    consumed) is a regression."""
    await build_stock(
        db_session, stock_setup.tenant_id, stock_setup.item_id, stock_setup.bin_a_id, Decimal(50)
    )

    from app.core.events import run_in_uow

    async def issue() -> None:
        with tenant_context(stock_setup.tenant_id):
            await service.create_move(
                db_session,
                stock_setup.tenant_id,
                StockMoveCreate(
                    move_type=MoveType.ISSUE,
                    item_id=stock_setup.item_id,
                    quantity=Decimal(1),
                    from_bin_id=stock_setup.bin_a_id,
                ),
            )

    with query_counter() as qc, tenant_context(stock_setup.tenant_id):  # type: ignore[operator]
        await run_in_uow(db_session, issue)
    # The budget covers the move write + valuation + the COGS journal posting (draft + lines +
    # period/numbering/docflow/balance), all constant — a single-layer issue is O(1).
    assert qc.count <= 45, qc.statements  # type: ignore[attr-defined]
