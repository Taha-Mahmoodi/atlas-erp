"""The valuation-offset OVERRIDE on create_move (PLAN 6.3, D-041): a RECEIPT's Cr leg.

A STANDALONE receipt credits the price-difference account (unchanged behaviour); when the caller
passes ``valuation_offset_account_id`` (the procurement goods-receipt path), the same receipt
credits that account instead (the GR/IR clearing account) — proving the override threads create_move
→ costing → StockValued.offset_account_id → the finance handler without touching the default path.
"""

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import run_in_uow
from app.core.tenancy import tenant_context
from app.modules.finance.constants import AccountType, DocumentType
from app.modules.finance.models import JournalEntry, JournalLine
from app.modules.finance.schemas import AccountCreate
from app.modules.finance.service import create_account
from app.modules.inventory import service
from app.modules.inventory.constants import MoveType
from app.modules.inventory.schemas import StockMoveCreate
from tests.modules.inventory.factories import build_stock_setup


async def _receipt_lines(
    session: AsyncSession, tenant_id: uuid.UUID
) -> list[JournalLine]:
    """The journal lines of the single RECEIPT (COGS-typed) entry just posted."""
    with tenant_context(tenant_id):
        entry = (
            await session.execute(
                select(JournalEntry).where(
                    JournalEntry.tenant_id == tenant_id,
                    JournalEntry.document_type == DocumentType.COGS.value,
                )
            )
        ).scalar_one()
        return list(
            (
                await session.execute(
                    select(JournalLine).where(JournalLine.journal_entry_id == entry.id)
                )
            )
            .scalars()
            .all()
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


def _debit(lines: list[JournalLine], account_id: uuid.UUID) -> Decimal:
    return sum(
        (Decimal(line.transaction_debit_amount) for line in lines if line.account_id == account_id),
        Decimal(0),
    )


async def _post_receipt(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    bin_id: uuid.UUID,
    item_id: uuid.UUID,
    *,
    offset_account_id: uuid.UUID | None,
) -> None:
    async def work() -> None:
        with tenant_context(tenant_id):
            await service.create_move(
                session,
                tenant_id,
                StockMoveCreate(
                    move_type=MoveType.RECEIPT,
                    item_id=item_id,
                    quantity=Decimal(10),
                    to_bin_id=bin_id,
                    unit_cost=Decimal(4),
                ),
                valuation_offset_account_id=offset_account_id,
            )

    with tenant_context(tenant_id):
        await run_in_uow(session, work)


async def test_receipt_without_override_credits_price_difference(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """A RECEIPT with NO override credits the price-difference account (the standalone default,
    unchanged) — Dr Inventory 40 / Cr price-difference 40."""
    setup = await build_stock_setup(db_session, tenant_a)
    await _post_receipt(
        db_session, tenant_a, setup.bin_a_id, setup.item_id, offset_account_id=None
    )
    lines = await _receipt_lines(db_session, tenant_a)
    assert _debit(lines, setup.inventory_account_id) == Decimal(40)
    assert _credit(lines, setup.price_difference_account_id) == Decimal(40)


async def test_receipt_with_override_credits_given_account(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """A RECEIPT WITH the override credits the supplied account (GR/IR), NOT price-difference —
    Dr Inventory 40 / Cr GR-IR 40 (D-041). Proves the offset threads end-to-end to the handler."""
    setup = await build_stock_setup(db_session, tenant_a)
    with tenant_context(tenant_a):
        gr_ir = await create_account(
            db_session,
            tenant_a,
            AccountCreate(code="2150", name="GR/IR", account_type=AccountType.LIABILITY),
        )
        await db_session.commit()
    await _post_receipt(
        db_session, tenant_a, setup.bin_a_id, setup.item_id, offset_account_id=gr_ir.id
    )
    lines = await _receipt_lines(db_session, tenant_a)
    assert _debit(lines, setup.inventory_account_id) == Decimal(40)
    assert _credit(lines, gr_ir.id) == Decimal(40)
    # The price-difference account was NOT touched (override replaced it).
    assert _credit(lines, setup.price_difference_account_id) == Decimal(0)
