"""Bank-statement reconciliation: match suggestions, confirm/reject, clearing (PLAN 4.9).

**Match rules** (priority order, applied as SET-BASED passes over in-memory candidate maps
built from TWO queries — no per-line lookups):

1. exact signed amount + same date (value_date == posting_date);
2. exact signed amount within ±3 days (nearest date wins; ties take the earlier posting).

Candidates are POSTED journal lines on the statement's bank account in the statement currency,
excluding lines already referenced by ANY statement line (``matched_journal_line_id``) — a
journal line is consumed by at most one statement line, tenant-wide. The signed comparison key
is ``transaction_debit_amount − transaction_credit_amount`` (a debit to the bank account is
money in, matching a positive statement amount). **v1 boundary** (documented in the parity
doc): no rule 3 document-number-in-description heuristic, no partial/many-to-one matching, no
configurable tolerance — rules 1+2 cover the dominant exact-amount case; MT940/CAMT and an
auto-clearing rules engine are explicit laters.

**Clearing** posts a real journal entry (Dr/Cr bank vs a contra account — the
``bank_unmatched_clearing`` posting default unless an explicit contra is given) through the
unchanged D-017 posting protocol, links statement->entry in docflow (D-012), and resolves the
line CLEARED. Suggestion marking mutates the LOADED lines; the flush batches the identical
two-column UPDATEs into executemany, so a rerun-safe suggestion pass stays O(1) statements.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.core.exceptions import ConflictError, NotFoundError
from app.modules.finance.constants import (
    BANK_CLEARING_POSTS_LINK,
    BANK_UNMATCHED_CLEARING,
    DocumentType,
    LineStatus,
)
from app.modules.finance.models import BankStatement, BankStatementLine, JournalLine
from app.modules.finance.schemas import JournalEntryCreate, JournalLineCreate
from app.modules.finance.service.bank_import import (
    get_bank_statement,
    refresh_statement_status,
)
from app.modules.finance.service.journal import create_draft_entry, post_entry
from app.modules.finance.service.posting_defaults import get_posting_default

# Rule 2's date window: exact amount within this many days of the value date.
MATCH_WINDOW_DAYS = 3


async def _get_line(
    session: AsyncSession, tenant_id: uuid.UUID, line_id: uuid.UUID
) -> BankStatementLine:
    line = await session.get(BankStatementLine, line_id)
    if line is None or line.tenant_id != tenant_id:
        raise NotFoundError(
            message="Bank statement line not found",
            code="finance.bank_statement_line_not_found",
        )
    return line


async def _candidate_pool(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    statement: BankStatement,
    window_lo: date,
    window_hi: date,
) -> dict[Decimal, list[tuple[date, uuid.UUID]]]:
    """Unconsumed posted journal lines on the bank account, keyed by signed amount —
    ONE query; the already-consumed exclusion is a NOT-IN subquery over non-NULL
    ``matched_journal_line_id`` (NULLs filtered inside, or NOT IN would match nothing)."""
    consumed = select(BankStatementLine.matched_journal_line_id).where(
        BankStatementLine.tenant_id == tenant_id,
        BankStatementLine.matched_journal_line_id.is_not(None),
    )
    rows = (
        await session.execute(
            select(
                JournalLine.id,
                JournalLine.posting_date,
                JournalLine.transaction_debit_amount,
                JournalLine.transaction_credit_amount,
            ).where(
                JournalLine.tenant_id == tenant_id,
                JournalLine.account_id == statement.bank_account_id,
                JournalLine.is_posted.is_(True),
                JournalLine.currency_code == statement.currency_code,
                JournalLine.posting_date >= window_lo,
                JournalLine.posting_date <= window_hi,
                JournalLine.id.not_in(consumed),
            )
        )
    ).all()
    pool: dict[Decimal, list[tuple[date, uuid.UUID]]] = {}
    for line_id, posting_date, debit, credit in rows:
        signed = Decimal(str(debit)) - Decimal(str(credit))
        pool.setdefault(signed, []).append((posting_date, line_id))
    for bucket in pool.values():
        bucket.sort()  # (date, id): deterministic claim order
    return pool


def _claim_exact(
    pool: dict[Decimal, list[tuple[date, uuid.UUID]]], amount: Decimal, on_date: date
) -> uuid.UUID | None:
    """Rule 1: pop the first candidate with this exact signed amount AND posting date."""
    bucket = pool.get(amount, [])
    for index, (posting_date, candidate_id) in enumerate(bucket):
        if posting_date == on_date:
            del bucket[index]
            return candidate_id
    return None


def _claim_window(
    pool: dict[Decimal, list[tuple[date, uuid.UUID]]], amount: Decimal, on_date: date
) -> uuid.UUID | None:
    """Rule 2: pop the NEAREST candidate within ±MATCH_WINDOW_DAYS (ties: earlier posting —
    the bucket is date-sorted, so the first minimal delta is the earlier one)."""
    bucket = pool.get(amount, [])
    best_index: int | None = None
    best_delta = MATCH_WINDOW_DAYS + 1
    for index, (posting_date, _candidate_id) in enumerate(bucket):
        delta = abs((posting_date - on_date).days)
        if delta <= MATCH_WINDOW_DAYS and delta < best_delta:
            best_index, best_delta = index, delta
    if best_index is None:
        return None
    _posting_date, candidate_id = bucket.pop(best_index)
    return candidate_id


async def suggest_matches(
    session: AsyncSession, tenant_id: uuid.UUID, statement_id: uuid.UUID
) -> dict[str, int]:
    """Run the match rules over every UNMATCHED line (module docstring). Safe to re-run:
    already SUGGESTED/MATCHED/CLEARED lines are untouched and their journal lines stay
    consumed. Two data queries + one batched UPDATE flush, regardless of line count."""
    statement = await get_bank_statement(session, tenant_id, statement_id)
    lines = (
        (
            await session.execute(
                select(BankStatementLine)
                .where(
                    BankStatementLine.tenant_id == tenant_id,
                    BankStatementLine.statement_id == statement_id,
                    BankStatementLine.status == LineStatus.UNMATCHED.value,
                )
                .order_by(BankStatementLine.line_number)
            )
        )
        .scalars()
        .all()
    )
    if not lines:
        return {"suggested": 0, "unmatched": 0}

    window = timedelta(days=MATCH_WINDOW_DAYS)
    window_lo = min(line.value_date for line in lines) - window
    window_hi = max(line.value_date for line in lines) + window
    pool = await _candidate_pool(session, tenant_id, statement, window_lo, window_hi)

    suggested: dict[uuid.UUID, uuid.UUID] = {}  # statement line -> journal line
    # Rule 1 pass (exact date) over ALL lines first, so a same-day candidate is never stolen
    # by an earlier line's ±3-day match.
    for line in lines:
        match = _claim_exact(pool, Decimal(str(line.amount)), line.value_date)
        if match is not None:
            suggested[line.id] = match
    # Rule 2 pass (±window) over the remainder.
    for line in lines:
        if line.id in suggested:
            continue
        match = _claim_window(pool, Decimal(str(line.amount)), line.value_date)
        if match is not None:
            suggested[line.id] = match

    for line in lines:
        match = suggested.get(line.id)
        if match is not None:
            line.status = LineStatus.SUGGESTED.value
            line.matched_journal_line_id = match
    await session.flush()
    return {"suggested": len(suggested), "unmatched": len(lines) - len(suggested)}


async def confirm_match(
    session: AsyncSession, tenant_id: uuid.UUID, line_id: uuid.UUID
) -> BankStatementLine:
    """SUGGESTED -> MATCHED (the manual confirmation). 409 on any other state."""
    line = await _get_line(session, tenant_id, line_id)
    if line.status != LineStatus.SUGGESTED.value:
        raise ConflictError(
            message="Only a suggested line can be confirmed",
            code="finance.bank_line_not_suggested",
            details={"status": line.status},
        )
    line.status = LineStatus.MATCHED.value
    await session.flush()
    statement = await get_bank_statement(session, tenant_id, line.statement_id)
    await refresh_statement_status(session, tenant_id, statement)
    return line


async def reject_suggestion(
    session: AsyncSession, tenant_id: uuid.UUID, line_id: uuid.UUID
) -> BankStatementLine:
    """SUGGESTED -> UNMATCHED, releasing the journal line for other matches. 409 otherwise."""
    line = await _get_line(session, tenant_id, line_id)
    if line.status != LineStatus.SUGGESTED.value:
        raise ConflictError(
            message="Only a suggested line can be rejected",
            code="finance.bank_line_not_suggested",
            details={"status": line.status},
        )
    line.status = LineStatus.UNMATCHED.value
    line.matched_journal_line_id = None
    await session.flush()
    statement = await get_bank_statement(session, tenant_id, line.statement_id)
    await refresh_statement_status(session, tenant_id, statement)
    return line


async def clear_unmatched_line(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    line_id: uuid.UUID,
    contra_account_id: uuid.UUID | None = None,
) -> BankStatementLine:
    """Post a clearing entry for an UNMATCHED line with no system-side counterpart (a bank fee,
    interest, ...): money in = Dr bank / Cr contra, money out = Dr contra / Cr bank, contra =
    the ``bank_unmatched_clearing`` posting default unless given. The entry goes through the
    unchanged D-017 posting protocol (JOURNAL document type, gapless number, period + balance
    guards), docflow links statement->'posts'->entry, the line resolves CLEARED. Endpoint-level
    idempotency (D-013) makes the retried request replay, not double-post."""
    line = await _get_line(session, tenant_id, line_id)
    if line.status != LineStatus.UNMATCHED.value:
        raise ConflictError(
            message="Only an unmatched line can be cleared",
            code="finance.bank_line_not_unmatched",
            details={"status": line.status},
        )
    statement = await get_bank_statement(session, tenant_id, line.statement_id)
    if contra_account_id is None:
        contra_account_id = await get_posting_default(session, tenant_id, BANK_UNMATCHED_CLEARING)

    signed = Decimal(str(line.amount))
    magnitude = abs(signed)
    bank_line = JournalLineCreate(
        account_id=statement.bank_account_id,
        description=line.description,
        transaction_debit_amount=magnitude if signed > 0 else Decimal(0),
        transaction_credit_amount=magnitude if signed < 0 else Decimal(0),
    )
    contra_line = JournalLineCreate(
        account_id=contra_account_id,
        description=line.description,
        transaction_debit_amount=magnitude if signed < 0 else Decimal(0),
        transaction_credit_amount=magnitude if signed > 0 else Decimal(0),
    )
    entry = await create_draft_entry(
        session,
        tenant_id,
        JournalEntryCreate(
            posting_date=line.value_date,
            currency_code=statement.currency_code,
            description=f"Bank statement clearing: {line.description}"[:500],
            document_type=DocumentType.JOURNAL,
            lines=[bank_line, contra_line],
        ),
    )
    await post_entry(session, tenant_id, entry.id)
    await docflow.link_documents(
        session,
        tenant_id,
        predecessor=statement.document_id,
        successor=entry.document_id,
        link_type=BANK_CLEARING_POSTS_LINK,
    )

    line.status = LineStatus.CLEARED.value
    line.cleared_journal_entry_id = entry.id
    await session.flush()
    await refresh_statement_status(session, tenant_id, statement)
    return line
