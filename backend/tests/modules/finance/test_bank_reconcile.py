"""Bank reconciliation service behavior (PLAN 4.9), SQLite: matching, transitions, clearing.

Proves the two match rules (exact amount+date, exact amount ±3 days, nearest-wins) with
single-consumption of journal lines tenant-wide, the confirm/reject transitions, the clearing
posting (suspense default + explicit contra, both signs) with its docflow link, and the
derived statement status flips. Shares the import builders with test_bank_rec.py (the file
split mirrors the bank_import/bank_reconcile service split).
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.docflow import DocumentLink
from app.core.exceptions import ConflictError
from app.core.tenancy import tenant_context
from app.modules.finance import service
from app.modules.finance.constants import (
    BANK_CLEARING_POSTS_LINK,
    DocumentType,
    EntryStatus,
    LineStatus,
    StatementStatus,
)
from app.modules.finance.models import BankStatement, JournalEntry, JournalLine
from tests.modules.finance.conftest import BankSetup
from tests.modules.finance.test_bank_rec import _csv, _import, _lines, _post_bank_entry

# --- match suggestions ----------------------------------------------------------


async def test_suggest_matches_exact_amount_and_date(
    db_session: AsyncSession, bank_setup: BankSetup
) -> None:
    journal_line_id = await _post_bank_entry(db_session, bank_setup, "100.00", date(2026, 3, 10))
    statement = await _import(
        db_session, bank_setup, _csv(["2026-03-10,100.00,Payment,"]), closing="100.00"
    )
    with tenant_context(bank_setup.tenant_id):
        result = await service.suggest_matches(db_session, bank_setup.tenant_id, statement.id)
        await db_session.commit()
    assert result == {"suggested": 1, "unmatched": 0}
    line = (await _lines(db_session, bank_setup, statement.id))[0]
    assert line.status == LineStatus.SUGGESTED.value
    assert line.matched_journal_line_id == journal_line_id


async def test_suggest_matches_within_three_days_prefers_nearest(
    db_session: AsyncSession, bank_setup: BankSetup
) -> None:
    far_id = await _post_bank_entry(db_session, bank_setup, "80.00", date(2026, 3, 13))
    near_id = await _post_bank_entry(db_session, bank_setup, "80.00", date(2026, 3, 12))
    statement = await _import(
        db_session, bank_setup, _csv(["2026-03-10,80.00,Payment,"]), closing="80.00"
    )
    with tenant_context(bank_setup.tenant_id):
        await service.suggest_matches(db_session, bank_setup.tenant_id, statement.id)
        await db_session.commit()
    line = (await _lines(db_session, bank_setup, statement.id))[0]
    assert line.status == LineStatus.SUGGESTED.value
    assert line.matched_journal_line_id == near_id
    assert line.matched_journal_line_id != far_id


async def test_suggest_leaves_lines_without_candidates_unmatched(
    db_session: AsyncSession, bank_setup: BankSetup
) -> None:
    # One posting matches nothing by amount; one is outside the ±3-day window.
    await _post_bank_entry(db_session, bank_setup, "70.00", date(2026, 3, 20))
    statement = await _import(
        db_session,
        bank_setup,
        _csv(["2026-03-10,55.55,No such amount,", "2026-03-10,70.00,Too far away,"]),
        closing="125.55",
    )
    with tenant_context(bank_setup.tenant_id):
        result = await service.suggest_matches(db_session, bank_setup.tenant_id, statement.id)
        await db_session.commit()
    assert result == {"suggested": 0, "unmatched": 2}
    assert all(
        line.status == LineStatus.UNMATCHED.value
        for line in await _lines(db_session, bank_setup, statement.id)
    )


async def test_suggest_matches_money_out_against_credit_side(
    db_session: AsyncSession, bank_setup: BankSetup
) -> None:
    # A negative statement amount (money out) must match a CREDIT on the bank account.
    journal_line_id = await _post_bank_entry(
        db_session, bank_setup, "45.00", date(2026, 3, 11), money_in=False
    )
    statement = await _import(
        db_session, bank_setup, _csv(["2026-03-11,-45.00,Rent,"]), closing="-45.00"
    )
    with tenant_context(bank_setup.tenant_id):
        await service.suggest_matches(db_session, bank_setup.tenant_id, statement.id)
        await db_session.commit()
    line = (await _lines(db_session, bank_setup, statement.id))[0]
    assert line.matched_journal_line_id == journal_line_id


async def test_journal_line_is_never_suggested_twice(
    db_session: AsyncSession, bank_setup: BankSetup
) -> None:
    """One bank journal line, two statement lines wanting it (one in a SECOND statement):
    exactly one suggestion total — consumed journal lines are excluded tenant-wide."""
    await _post_bank_entry(db_session, bank_setup, "100.00", date(2026, 3, 10))
    first = await _import(
        db_session,
        bank_setup,
        _csv(["2026-03-10,100.00,Payment A,", "2026-03-10,100.00,Payment B,"]),
        closing="200.00",
    )
    with tenant_context(bank_setup.tenant_id):
        result = await service.suggest_matches(db_session, bank_setup.tenant_id, first.id)
        await db_session.commit()
    assert result == {"suggested": 1, "unmatched": 1}

    second = await _import(
        db_session, bank_setup, _csv(["2026-03-10,100.00,Payment C,"]), closing="100.00"
    )
    with tenant_context(bank_setup.tenant_id):
        result = await service.suggest_matches(db_session, bank_setup.tenant_id, second.id)
        await db_session.commit()
    assert result == {"suggested": 0, "unmatched": 1}


# --- confirm / reject -----------------------------------------------------------


async def test_confirm_and_reject_transitions(
    db_session: AsyncSession, bank_setup: BankSetup
) -> None:
    await _post_bank_entry(db_session, bank_setup, "100.00", date(2026, 3, 10))
    statement = await _import(
        db_session, bank_setup, _csv(["2026-03-10,100.00,Payment,"]), closing="100.00"
    )
    with tenant_context(bank_setup.tenant_id):
        await service.suggest_matches(db_session, bank_setup.tenant_id, statement.id)
        await db_session.commit()
    line = (await _lines(db_session, bank_setup, statement.id))[0]

    with tenant_context(bank_setup.tenant_id):
        # Reject releases the journal line and resets the link.
        rejected = await service.reject_suggestion(db_session, bank_setup.tenant_id, line.id)
        assert rejected.status == LineStatus.UNMATCHED.value
        assert rejected.matched_journal_line_id is None
        # The released journal line is suggestible again.
        await service.suggest_matches(db_session, bank_setup.tenant_id, statement.id)
        confirmed = await service.confirm_match(db_session, bank_setup.tenant_id, line.id)
        assert confirmed.status == LineStatus.MATCHED.value
        await db_session.commit()


async def test_confirm_and_reject_require_suggested_state(
    db_session: AsyncSession, bank_setup: BankSetup
) -> None:
    statement = await _import(
        db_session, bank_setup, _csv(["2026-03-10,9.99,Orphan,"]), closing="9.99"
    )
    line = (await _lines(db_session, bank_setup, statement.id))[0]
    with tenant_context(bank_setup.tenant_id):
        with pytest.raises(ConflictError) as confirm_exc:
            await service.confirm_match(db_session, bank_setup.tenant_id, line.id)
        with pytest.raises(ConflictError) as reject_exc:
            await service.reject_suggestion(db_session, bank_setup.tenant_id, line.id)
    assert confirm_exc.value.code == "finance.bank_line_not_suggested"
    assert reject_exc.value.code == "finance.bank_line_not_suggested"


# --- clearing -------------------------------------------------------------------


async def test_clear_unmatched_posts_balanced_entry_to_suspense(
    db_session: AsyncSession, bank_setup: BankSetup
) -> None:
    """A bank fee (money out): Dr suspense / Cr bank, JOURNAL type, posted, docflow-linked."""
    statement = await _import(
        db_session, bank_setup, _csv(["2026-03-05,-12.50,Bank fee,"]), closing="-12.50"
    )
    line = (await _lines(db_session, bank_setup, statement.id))[0]
    with tenant_context(bank_setup.tenant_id):
        cleared = await service.clear_unmatched_line(db_session, bank_setup.tenant_id, line.id)
        await db_session.commit()
    assert cleared.status == LineStatus.CLEARED.value
    assert cleared.cleared_journal_entry_id is not None

    with tenant_context(bank_setup.tenant_id):
        entry = (
            await db_session.execute(
                select(JournalEntry).where(JournalEntry.id == cleared.cleared_journal_entry_id)
            )
        ).scalar_one()
        assert entry.status == EntryStatus.POSTED.value
        assert entry.document_type == DocumentType.JOURNAL.value
        assert entry.posting_date == date(2026, 3, 5)
        journal_lines = (
            (
                await db_session.execute(
                    select(JournalLine).where(JournalLine.journal_entry_id == entry.id)
                )
            )
            .scalars()
            .all()
        )
        by_account = {jl.account_id: jl for jl in journal_lines}
        bank_jl = by_account[bank_setup.bank_account_id]
        suspense_jl = by_account[bank_setup.suspense_account_id]
        assert Decimal(str(bank_jl.transaction_credit_amount)) == Decimal("12.50")
        assert Decimal(str(suspense_jl.transaction_debit_amount)) == Decimal("12.50")
        # docflow statement -> 'posts' -> clearing entry (D-012).
        statement_row = await db_session.get(BankStatement, statement.id)
        link = (
            await db_session.execute(
                select(DocumentLink).where(
                    DocumentLink.predecessor_document_id == statement_row.document_id,
                    DocumentLink.successor_document_id == entry.document_id,
                )
            )
        ).scalar_one()
        assert link.link_type == BANK_CLEARING_POSTS_LINK


async def test_clear_money_in_with_explicit_contra_account(
    db_session: AsyncSession, bank_setup: BankSetup
) -> None:
    """Interest received (money in) against an explicit contra: Dr bank / Cr contra."""
    statement = await _import(
        db_session, bank_setup, _csv(["2026-03-07,5.00,Interest,"]), closing="5.00"
    )
    line = (await _lines(db_session, bank_setup, statement.id))[0]
    contra = bank_setup.accounts["4000"]
    with tenant_context(bank_setup.tenant_id):
        cleared = await service.clear_unmatched_line(
            db_session, bank_setup.tenant_id, line.id, contra_account_id=contra
        )
        await db_session.commit()
        journal_lines = (
            (
                await db_session.execute(
                    select(JournalLine).where(
                        JournalLine.journal_entry_id == cleared.cleared_journal_entry_id
                    )
                )
            )
            .scalars()
            .all()
        )
    by_account = {jl.account_id: jl for jl in journal_lines}
    assert Decimal(str(by_account[bank_setup.bank_account_id].transaction_debit_amount)) == (
        Decimal("5.00")
    )
    assert Decimal(str(by_account[contra].transaction_credit_amount)) == Decimal("5.00")


async def test_clear_requires_unmatched_state(
    db_session: AsyncSession, bank_setup: BankSetup
) -> None:
    await _post_bank_entry(db_session, bank_setup, "100.00", date(2026, 3, 10))
    statement = await _import(
        db_session, bank_setup, _csv(["2026-03-10,100.00,Payment,"]), closing="100.00"
    )
    with tenant_context(bank_setup.tenant_id):
        await service.suggest_matches(db_session, bank_setup.tenant_id, statement.id)
        await db_session.commit()
    line = (await _lines(db_session, bank_setup, statement.id))[0]
    with tenant_context(bank_setup.tenant_id), pytest.raises(ConflictError) as exc:
        await service.clear_unmatched_line(db_session, bank_setup.tenant_id, line.id)
    assert exc.value.code == "finance.bank_line_not_unmatched"


# --- statement status -----------------------------------------------------------


async def test_statement_status_flips_as_lines_resolve(
    db_session: AsyncSession, bank_setup: BankSetup
) -> None:
    await _post_bank_entry(db_session, bank_setup, "100.00", date(2026, 3, 10))
    statement = await _import(
        db_session,
        bank_setup,
        _csv(["2026-03-10,100.00,Payment,", "2026-03-05,-12.50,Bank fee,"]),
        closing="87.50",
    )
    lines = await _lines(db_session, bank_setup, statement.id)

    with tenant_context(bank_setup.tenant_id):
        # Clearing the fee resolves 1 of 2 -> PARTIALLY_RECONCILED.
        await service.clear_unmatched_line(db_session, bank_setup.tenant_id, lines[1].id)
        await db_session.commit()
        statement_row = await db_session.get(BankStatement, statement.id)
        assert statement_row.status == StatementStatus.PARTIALLY_RECONCILED.value

        # Suggesting alone resolves nothing (SUGGESTED is not resolved).
        await service.suggest_matches(db_session, bank_setup.tenant_id, statement.id)
        await db_session.commit()
        await db_session.refresh(statement_row)
        assert statement_row.status == StatementStatus.PARTIALLY_RECONCILED.value

        # Confirming the suggestion resolves 2 of 2 -> RECONCILED.
        await service.confirm_match(db_session, bank_setup.tenant_id, lines[0].id)
        await db_session.commit()
        await db_session.refresh(statement_row)
        assert statement_row.status == StatementStatus.RECONCILED.value

        progress = await service.statement_progress(
            db_session, bank_setup.tenant_id, statement.id
        )
    assert (progress.total, progress.matched, progress.cleared) == (2, 1, 1)
    assert progress.resolved == 2


