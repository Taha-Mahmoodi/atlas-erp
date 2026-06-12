"""The universal-journal posting engine (D-017): draft creation, two-flush posting, reversal.

Every invariant lives at BOTH the service (here, for a clean 422) and the DB (migration 0009
triggers, the bypass-proof backstop). Three load-bearing mechanisms (D-017): (1) TWO-FLUSH
posting — the uow does not guarantee cross-table UPDATE order, so we flush the loaded lines'
``is_posted`` while the entry is still DRAFT (the line trigger keys on OLD.is_posted=FALSE),
THEN flush the header POSTED (balance + period triggers fire there); (2) LOADED-object mutation,
never bulk ``update()``, so audit diffs are captured and the audit bulk-write assertion holds
(D-010); (3) REVERSAL-only correction — a posted entry is never edited/deleted, only reversed.

For v1 functional amounts EQUAL transaction amounts (single functional currency; FX in 4.3). The
balance check sums functional amounts, exact on both engines (MoneyType stores NUMERIC / micro-unit
ints, D-015).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.core.events import publish
from app.core.exceptions import ConflictError, ValidationFailedError
from app.core.numbering import claim_number, ensure_sequence
from app.modules.finance import queries
from app.modules.finance.constants import (
    JOURNAL_ENTRY_DOC_TYPE,
    JOURNAL_NUMBER_PADDING,
    JOURNAL_NUMBER_PREFIX,
    JOURNAL_SEQUENCE_NAME,
    DocumentType,
    EntryStatus,
    PeriodStatus,
)
from app.modules.finance.events import JournalEntryPosted, JournalEntryReversed
from app.modules.finance.models import Account, JournalEntry, JournalLine
from app.modules.finance.schemas import JournalEntryCreate, JournalLineCreate
from app.modules.finance.service.fx_translation import translate_entry_lines
from app.modules.finance.service.journal_read import (
    entry_totals,
    get_entry,
    load_lines,
)

# core/docflow link type for the reverses-edge (D-012 vocabulary).
_REVERSES_LINK = "reverses"


def _assert_line_one_sided(payload: JournalLineCreate, line_number: int) -> None:
    debit = payload.transaction_debit_amount
    credit = payload.transaction_credit_amount
    one_sided = (debit > 0 and credit == 0) or (credit > 0 and debit == 0)
    if not one_sided:
        raise ValidationFailedError(
            message=(
                f"Line {line_number} must have exactly one of debit/credit positive "
                "(the other zero)"
            ),
            code="finance.journal_line_not_one_sided",
            details={"line_number": line_number},
        )


async def _require_postable_accounts(
    session: AsyncSession, tenant_id: uuid.UUID, account_ids: set[uuid.UUID]
) -> None:
    """Every referenced account must exist in this tenant AND be postable (leaf). One query."""
    rows = (
        await session.execute(
            select(Account.id, Account.is_postable).where(
                Account.tenant_id == tenant_id, Account.id.in_(account_ids)
            )
        )
    ).all()
    found = {row[0]: row[1] for row in rows}
    missing = [str(aid) for aid in account_ids if aid not in found]
    if missing:
        raise ValidationFailedError(
            message="One or more lines reference an unknown account",
            code="finance.journal_account_not_found",
            details={"account_ids": missing},
        )
    not_postable = [str(aid) for aid, postable in found.items() if not postable]
    if not_postable:
        raise ValidationFailedError(
            message="One or more lines reference a non-postable account",
            code="finance.journal_account_not_postable",
            details={"account_ids": not_postable},
        )


async def create_draft_entry(
    session: AsyncSession, tenant_id: uuid.UUID, payload: JournalEntryCreate
) -> JournalEntry:
    """Create a DRAFT entry + lines (D-017). Validates: >= 2 lines, each one-sided, all accounts
    exist + postable + same tenant, and the entry balances (sum debits == sum credits). Registers
    the document in core_documents with NO number (claimed at posting per D-012). Sets functional
    == transaction for now (single functional currency, FX in 4.3). Does NOT claim a number and
    does NOT resolve the period — both happen at posting."""
    if len(payload.lines) < 2:
        raise ValidationFailedError(
            message="A journal entry needs at least two lines",
            code="finance.journal_too_few_lines",
        )

    total_debit = Decimal(0)
    total_credit = Decimal(0)
    for index, line in enumerate(payload.lines, start=1):
        _assert_line_one_sided(line, index)
        total_debit += line.transaction_debit_amount
        total_credit += line.transaction_credit_amount
    if total_debit != total_credit:
        raise ValidationFailedError(
            message="Journal entry debits and credits must balance",
            code="finance.journal_unbalanced",
            details={"total_debit": str(total_debit), "total_credit": str(total_credit)},
        )

    account_ids = {line.account_id for line in payload.lines}
    await _require_postable_accounts(session, tenant_id, account_ids)

    entry_id = uuid.uuid4()
    document = await docflow.register_document(
        session,
        tenant_id,
        JOURNAL_ENTRY_DOC_TYPE,
        entry_id,
        doc_number=None,
        status=EntryStatus.DRAFT.value,
    )
    entry = JournalEntry(
        id=entry_id,
        tenant_id=tenant_id,
        document_id=document.id,
        posting_date=payload.posting_date,
        currency_code=payload.currency_code,
        description=payload.description,
        document_type=DocumentType(payload.document_type).value,
        status=EntryStatus.DRAFT.value,
    )
    session.add(entry)
    for index, line in enumerate(payload.lines, start=1):
        session.add(
            JournalLine(
                tenant_id=tenant_id,
                journal_entry_id=entry_id,
                line_number=index,
                account_id=line.account_id,
                description=line.description,
                transaction_debit_amount=line.transaction_debit_amount,
                transaction_credit_amount=line.transaction_credit_amount,
                # v1: functional == transaction (FX translation in 4.3).
                functional_debit_amount=line.transaction_debit_amount,
                functional_credit_amount=line.transaction_credit_amount,
                currency_code=payload.currency_code,
                cost_center_id=line.cost_center_id,
                profit_center_id=line.profit_center_id,
                project_id=line.project_id,
                item_id=line.item_id,
                partner_type=line.partner_type,
                partner_id=line.partner_id,
            )
        )
    await session.flush()
    return entry


async def post_entry(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    entry_id: uuid.UUID,
    *,
    rate_override: Decimal | None = None,
) -> JournalEntry:
    """THE posting protocol (D-017 two-flush). Validates DRAFT + balanced, resolves + checks the
    open period from posting_date (422 before touching the DB), translates foreign-currency
    functional amounts (D-019; an explicit ``rate_override`` wins over the looked-up SPOT rate),
    claims the gapless number in this transaction, then flushes the loaded lines (still DRAFT) and
    finally the POSTED header (balance + period triggers fire there). Publishes JournalEntryPosted;
    the caller commits via uow."""
    entry = await get_entry(session, tenant_id, entry_id)
    if entry.status != EntryStatus.DRAFT.value:
        raise ConflictError(
            message="Only a draft journal entry can be posted",
            code="finance.journal_not_draft",
            details={"status": entry.status},
        )

    lines = await load_lines(session, tenant_id, entry_id)
    if len(lines) < 2:
        raise ValidationFailedError(
            message="A journal entry needs at least two lines",
            code="finance.journal_too_few_lines",
        )

    # FX translation (D-019): recompute functional amounts at the posting rate when the entry is in
    # a foreign currency, balancing the functional residual into the largest line. After this the
    # functional sums (which the balance trigger checks) are exact and equal.
    await translate_entry_lines(session, tenant_id, entry, lines, rate_override)

    debit, credit = entry_totals(lines)
    if debit != credit or debit <= 0:
        raise ValidationFailedError(
            message="Journal entry debits and credits must balance and be positive",
            code="finance.journal_unbalanced",
            details={"total_debit": str(debit), "total_credit": str(credit)},
        )

    # Period resolution + open check FIRST (service-level half of D-018); the trigger backstops.
    period = await queries.find_period_for_date(session, tenant_id, entry.posting_date)
    if period is None or period.status != PeriodStatus.OPEN.value:
        raise ValidationFailedError(
            message="The posting date is not within an open fiscal period",
            code="finance.period_closed",
            details={"posting_date": entry.posting_date.isoformat()},
        )

    # Claim the gapless number in this transaction (D-012): gapless because the claim and the
    # POSTED commit succeed or roll back together.
    await ensure_sequence(
        session,
        tenant_id,
        JOURNAL_SEQUENCE_NAME,
        JOURNAL_NUMBER_PREFIX,
        JOURNAL_NUMBER_PADDING,
        year_reset=True,
    )
    entry_number = await claim_number(
        session, tenant_id, JOURNAL_SEQUENCE_NAME, on_date=entry.posting_date
    )

    # Flush 1: denormalize onto the loaded lines while the entry is still DRAFT.
    for line in lines:
        line.is_posted = True
        line.posting_date = entry.posting_date
        line.fiscal_period_id = period.id
    await session.flush()

    # Flush 2: promote the header. The period + balance triggers fire on this DRAFT->POSTED UPDATE.
    entry.entry_number = entry_number
    entry.fiscal_period_id = period.id
    entry.status = EntryStatus.POSTED.value
    entry.posted_at = datetime.now(UTC)
    await session.flush()

    await docflow.set_document_status(
        session,
        tenant_id,
        entry.document_id,
        status=EntryStatus.POSTED.value,
        doc_number=entry_number,
    )

    publish(
        session,
        JournalEntryPosted(
            tenant_id=tenant_id,
            entry_id=entry.id,
            entry_number=entry_number,
            document_type=entry.document_type,
            posting_date=entry.posting_date.isoformat(),
            currency_code=entry.currency_code,
            total_functional_amount=debit,
            account_ids=tuple(line.account_id for line in lines),
        ),
    )
    return entry


async def reverse_entry(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    entry_id: uuid.UUID,
    reversal_date: date,
    description: str | None = None,
) -> JournalEntry:
    """Reverse a POSTED entry (D-017). Creates a NEW same-document_type entry with each line's
    debit/credit SWAPPED, posts it into ``reversal_date``'s open period (its own number), then
    sets the original REVERSED + reversed_by_entry_id — the ONLY mutation the immutability trigger
    permits. Links the two documents ('reverses'), publishes JournalEntryReversed, returns the
    reversing entry."""
    original = await get_entry(session, tenant_id, entry_id)
    if original.status != EntryStatus.POSTED.value:
        raise ConflictError(
            message="Only a posted journal entry can be reversed",
            code="finance.journal_not_posted",
            details={"status": original.status},
        )
    if original.reversed_by_entry_id is not None:
        raise ConflictError(
            message="This journal entry has already been reversed",
            code="finance.journal_already_reversed",
        )

    original_lines = await load_lines(session, tenant_id, entry_id)

    reversal_id = uuid.uuid4()
    reversal_document = await docflow.register_document(
        session,
        tenant_id,
        JOURNAL_ENTRY_DOC_TYPE,
        reversal_id,
        doc_number=None,
        status=EntryStatus.DRAFT.value,
    )
    reversal = JournalEntry(
        id=reversal_id,
        tenant_id=tenant_id,
        document_id=reversal_document.id,
        posting_date=reversal_date,
        currency_code=original.currency_code,
        description=description
        or f"Reversal of {original.entry_number or original.id}",
        document_type=original.document_type,
        status=EntryStatus.DRAFT.value,
        reverses_entry_id=original.id,
    )
    session.add(reversal)
    for line in original_lines:
        session.add(
            JournalLine(
                tenant_id=tenant_id,
                journal_entry_id=reversal_id,
                line_number=line.line_number,
                account_id=line.account_id,
                description=line.description,
                # Swap debit <-> credit in both currency pairs (frozen functional amounts).
                transaction_debit_amount=line.transaction_credit_amount,
                transaction_credit_amount=line.transaction_debit_amount,
                functional_debit_amount=line.functional_credit_amount,
                functional_credit_amount=line.functional_debit_amount,
                currency_code=line.currency_code,
                cost_center_id=line.cost_center_id,
                profit_center_id=line.profit_center_id,
                project_id=line.project_id,
                item_id=line.item_id,
                partner_type=line.partner_type,
                partner_id=line.partner_id,
            )
        )
    await session.flush()

    # Post the reversing entry (claims its own number, runs the same period/balance checks).
    await post_entry(session, tenant_id, reversal_id)

    # The single sanctioned mutation on a POSTED original (immutability trigger permits exactly
    # this: status POSTED->REVERSED with reversed_by_entry_id set).
    original.reversed_by_entry_id = reversal_id
    original.status = EntryStatus.REVERSED.value
    await session.flush()

    await docflow.set_document_status(
        session, tenant_id, original.document_id, status=EntryStatus.REVERSED.value
    )
    await docflow.link_documents(
        session,
        tenant_id,
        predecessor=original.document_id,
        successor=reversal.document_id,
        link_type=_REVERSES_LINK,
    )

    await session.refresh(reversal)
    publish(
        session,
        JournalEntryReversed(
            tenant_id=tenant_id,
            entry_id=original.id,
            reversal_entry_id=reversal.id,
            reversal_entry_number=reversal.entry_number or "",
            document_type=original.document_type,
            reversal_date=reversal_date.isoformat(),
        ),
    )
    return reversal
