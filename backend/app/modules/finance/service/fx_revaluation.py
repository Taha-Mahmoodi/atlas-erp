"""Unrealized-FX revaluation run with auto-reversal (D-019).

At period end, foreign-currency MONETARY balances must be restated at the period-end CLOSING rate
so the balance sheet reflects current exchange rates; the unrealized gain/loss is posted to
fx_unrealized_gain/loss against a balance-sheet adjustment account. Because the adjustment is a
period-end snapshot (not a permanent rebasing of carrying values), each adjustment entry is
AUTO-REVERSED on day 1 of the next period — so clearing-time realized FX still computes from the
original invoice rate with no double counting (D-019).

Entry model (per account with a non-zero foreign balance): one ADJUSTMENT entry dated at
``rate_date`` (in the revalued period) and one independent REVERSAL entry dated day 1 of the next
period with the lines swapped. Both are FX_REVAL, both stay POSTED, and they are linked by a
docflow ``'revalues'`` edge — so a RE-RUN can reverse BOTH (append-only, never delete) before it
reposts. (The auto-reversal is a standalone swapped-line entry rather than ``reverse_entry`` of the
adjustment precisely so the adjustment stays POSTED and re-runnable.)

V1 SCOPE (documented, tractable): revalue every account flagged ``is_monetary`` with a non-null
``currency_code`` that differs from the functional currency and carries a non-zero foreign balance
as of ``rate_date``. Per-open-item AP/AR revaluation granularity is bounded OUT of v1 (it needs the
AP/AR open-item model, PLAN 4.4+) and noted 'partial' in the parity doc; revaluing the per-account
monetary balance uses exactly the same rates table + FX-account machinery and is the correct,
testable subset.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.core.docflow import DocumentLink
from app.core.exceptions import ValidationFailedError
from app.core.jobs import register_job
from app.core.pagination import DEFAULT_LIMIT, OrderKey, SortDirection, paginate
from app.core.schemas import Page
from app.modules.finance import queries
from app.modules.finance.constants import (
    FX_REVALUATION_ADJUSTMENT,
    FX_REVALUATION_JOB,
    FX_REVALUES_LINK,
    FX_UNREALIZED_GAIN,
    FX_UNREALIZED_LOSS,
    DocumentType,
    EntryStatus,
    FxRunStatus,
    PeriodStatus,
    RateKind,
)
from app.modules.finance.models import (
    Account,
    FiscalPeriod,
    FxRevaluationRun,
    JournalEntry,
    JournalLine,
)
from app.modules.finance.schemas import JournalEntryCreate, JournalLineCreate
from app.modules.finance.service import fx
from app.modules.finance.service.journal import (
    create_draft_entry,
    post_entry,
    reverse_entry,
)
from app.modules.finance.service.posting_defaults import get_posting_default


async def _require_next_period_open(
    session: AsyncSession, tenant_id: uuid.UUID, period: FiscalPeriod
) -> date:
    """Day 1 of the period AFTER ``period`` — where the auto-reversal posts (D-019). Validates the
    next period EXISTS and is OPEN up front (the period trigger rejects the reversal otherwise),
    raising a clear 422 BEFORE any entry posts."""
    next_start = date.fromordinal(period.end_date.toordinal() + 1)
    next_period = await queries.find_period_for_date(session, tenant_id, next_start)
    if next_period is None or next_period.status != PeriodStatus.OPEN.value:
        raise ValidationFailedError(
            message=(
                "The next fiscal period must exist and be open to post the revaluation "
                "auto-reversal"
            ),
            code="finance.fx_reval_next_period_not_open",
            details={"next_period_start": next_start.isoformat()},
        )
    return next_start


async def _account_balances(
    session: AsyncSession, tenant_id: uuid.UUID, account_id: uuid.UUID, as_of: date
) -> tuple[Decimal, Decimal]:
    """(foreign transaction balance, functional carrying balance) for an account as of ``as_of``
    (D-019). Both are Σ(debit − credit) over POSTED lines on the account dated on or before
    ``as_of`` — foreign from the transaction columns, carrying from the functional columns. The
    FX_REVAL adjustments themselves post to the ADJUSTMENT account (a different account), so they
    do not pollute the revalued account's balance — re-runs read the same clean balance each time.
    MoneyType sums are exact on both engines (D-015)."""
    row = (
        await session.execute(
            select(
                func.coalesce(func.sum(JournalLine.transaction_debit_amount), 0)
                - func.coalesce(func.sum(JournalLine.transaction_credit_amount), 0),
                func.coalesce(func.sum(JournalLine.functional_debit_amount), 0)
                - func.coalesce(func.sum(JournalLine.functional_credit_amount), 0),
            ).where(
                JournalLine.tenant_id == tenant_id,
                JournalLine.account_id == account_id,
                JournalLine.is_posted.is_(True),
                JournalLine.posting_date <= as_of,
            )
        )
    ).one()
    return Decimal(str(row[0])), Decimal(str(row[1]))


async def _monetary_foreign_accounts(
    session: AsyncSession, tenant_id: uuid.UUID, functional_code: str
) -> list[Account]:
    """Accounts in scope: ``is_monetary`` with a non-null foreign ``currency_code`` (D-019)."""
    stmt = (
        select(Account)
        .where(
            Account.tenant_id == tenant_id,
            Account.is_monetary.is_(True),
            Account.currency_code.is_not(None),
            Account.currency_code != functional_code,
        )
        .order_by(Account.code)
    )
    return list((await session.execute(stmt)).scalars().all())


def _adjustment_lines(
    delta: Decimal,
    adjustment_account_id: uuid.UUID,
    gain_loss_account_id: uuid.UUID,
) -> list[JournalLineCreate]:
    """The two balanced lines for a ``delta`` (D-019). A positive delta (account worth MORE in
    functional terms) debits the adjustment account and credits the unrealized GAIN account; a
    negative delta debits the unrealized LOSS account and credits the adjustment account."""
    amount = abs(delta)
    if delta > 0:
        debit_account, credit_account = adjustment_account_id, gain_loss_account_id
    else:
        debit_account, credit_account = gain_loss_account_id, adjustment_account_id
    return [
        JournalLineCreate(account_id=debit_account, transaction_debit_amount=amount),
        JournalLineCreate(account_id=credit_account, transaction_credit_amount=amount),
    ]


async def _post_entry_with_lines(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    functional_code: str,
    posting_date: date,
    description: str,
    lines: list[JournalLineCreate],
) -> JournalEntry:
    """Create + post one balanced functional-currency FX_REVAL entry (D-019). Functional-currency,
    so the posting protocol's translation is a no-op (functional == transaction)."""
    draft = await create_draft_entry(
        session,
        tenant_id,
        JournalEntryCreate(
            posting_date=posting_date,
            currency_code=functional_code,
            description=description,
            document_type=DocumentType.FX_REVAL,
            lines=lines,
        ),
    )
    await post_entry(session, tenant_id, draft.id)
    return draft


async def _post_adjustment_pair(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    functional_code: str,
    rate_date: date,
    reversal_date: date,
    description: str,
    lines: list[JournalLineCreate],
) -> None:
    """Post the ADJUSTMENT entry (dated rate_date) and its independent swapped-line auto-REVERSAL
    (dated next-period day 1), linked by a 'revalues' docflow edge (D-019). Both stay POSTED so a
    re-run can reverse them."""
    adjustment = await _post_entry_with_lines(
        session, tenant_id, functional_code, rate_date, description, lines
    )
    swapped = [
        JournalLineCreate(
            account_id=line.account_id,
            transaction_debit_amount=line.transaction_credit_amount,
            transaction_credit_amount=line.transaction_debit_amount,
        )
        for line in lines
    ]
    reversal = await _post_entry_with_lines(
        session,
        tenant_id,
        functional_code,
        reversal_date,
        f"Auto-reversal of {description}",
        swapped,
    )
    await docflow.link_documents(
        session,
        tenant_id,
        predecessor=adjustment.document_id,
        successor=reversal.document_id,
        link_type=FX_REVALUES_LINK,
    )


async def _reverse_previous_run(
    session: AsyncSession, tenant_id: uuid.UUID, period: FiscalPeriod, next_start: date
) -> None:
    """Reverse a prior COMPLETED run's entries before reposting (D-019 re-run rule: append-only,
    never delete). Scoped to THIS period's run only (#71): its adjustments are the still-POSTED
    FX_REVAL entries dated inside the re-run period that are the PREDECESSOR of a 'revalues'
    docflow edge (the predecessor test excludes the previous period's auto-reversal, which is
    dated day 1 of this period but is only ever a successor); each adjustment's paired
    auto-reversal is the edge's successor. Both halves are reversed into their own period and
    the prior run row(s) are marked REVERSED, netting the prior run fully out so the fresh run
    starts clean — without touching other periods' still-active revaluations."""
    prior_runs = (
        await session.execute(
            select(FxRevaluationRun).where(
                FxRevaluationRun.tenant_id == tenant_id,
                FxRevaluationRun.fiscal_period_id == period.id,
                FxRevaluationRun.status == FxRunStatus.COMPLETED.value,
            )
        )
    ).scalars().all()
    if not prior_runs:
        return
    pair_rows = (
        await session.execute(
            select(JournalEntry, DocumentLink.successor_document_id)
            .join(
                DocumentLink,
                DocumentLink.predecessor_document_id == JournalEntry.document_id,
            )
            .where(
                DocumentLink.tenant_id == tenant_id,
                DocumentLink.link_type == FX_REVALUES_LINK,
                JournalEntry.tenant_id == tenant_id,
                JournalEntry.document_type == DocumentType.FX_REVAL.value,
                JournalEntry.status == EntryStatus.POSTED.value,
                JournalEntry.reverses_entry_id.is_(None),
                JournalEntry.posting_date >= period.start_date,
                JournalEntry.posting_date <= period.end_date,
            )
        )
    ).all()
    prior_entries = [row[0] for row in pair_rows]
    partner_document_ids = [row[1] for row in pair_rows]
    if partner_document_ids:
        prior_entries += list(
            (
                await session.execute(
                    select(JournalEntry).where(
                        JournalEntry.tenant_id == tenant_id,
                        JournalEntry.document_id.in_(partner_document_ids),
                        JournalEntry.status == EntryStatus.POSTED.value,
                        JournalEntry.reverses_entry_id.is_(None),
                    )
                )
            ).scalars().all()
        )
    for entry in prior_entries:
        in_revalued_period = period.start_date <= entry.posting_date <= period.end_date
        reversal_date = entry.posting_date if in_revalued_period else next_start
        await reverse_entry(
            session,
            tenant_id,
            entry.id,
            reversal_date,
            description=f"Re-run reversal of {entry.entry_number or entry.id}",
        )
    for run in prior_runs:
        run.status = FxRunStatus.REVERSED.value
    await session.flush()


async def run_fx_revaluation(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    period_id: uuid.UUID,
    rate_date: date,
) -> FxRevaluationRun:
    """Run unrealized-FX revaluation for ``period_id`` at ``rate_date`` (D-019).

    1. Resolve the functional currency (422 if unconfigured) and validate the period exists.
    2. Validate the NEXT period exists and is OPEN up front (the auto-reversal posts there) — a
       clear 422 BEFORE any entry posts.
    3. If a prior COMPLETED run exists for this period, reverse its entries first (append-only).
    4. For each monetary foreign account with a non-zero foreign balance as of ``rate_date``:
       delta = quantize(foreign_balance × CLOSING_rate, functional_decimals) − functional carrying.
       Post ONE balanced FX_REVAL adjustment (adjustment vs fx_unrealized_gain/loss) plus its
       next-period auto-reversal, linked 'revalues'.
    5. Record the run COMPLETED. The caller commits via run_in_uow.
    """
    functional_code = await fx.functional_currency(session, tenant_id)
    period = await session.get(FiscalPeriod, period_id)
    if period is None or period.tenant_id != tenant_id:
        raise ValidationFailedError(
            message="Fiscal period not found", code="finance.fiscal_period_not_found"
        )
    next_start = await _require_next_period_open(session, tenant_id, period)

    await _reverse_previous_run(session, tenant_id, period, next_start)

    run = FxRevaluationRun(
        tenant_id=tenant_id,
        fiscal_period_id=period_id,
        rate_date=rate_date,
        status=FxRunStatus.COMPLETED.value,
    )
    session.add(run)
    await session.flush()

    decimals = (await fx.get_currency(session, tenant_id, functional_code)).decimal_places

    for account in await _monetary_foreign_accounts(session, tenant_id, functional_code):
        foreign_balance, carrying = await _account_balances(
            session, tenant_id, account.id, rate_date
        )
        if foreign_balance == 0:
            continue
        rate = await fx.get_rate(
            session,
            tenant_id,
            account.currency_code,
            functional_code,
            rate_date,
            RateKind.CLOSING,
        )
        delta = fx.translate(foreign_balance, rate, decimals) - carrying
        if delta == 0:
            continue
        # Resolve the posting defaults lazily — only a run with an actual delta needs them, so a
        # nothing-to-revalue run never requires the FX accounts to be wired (clear 422 otherwise).
        adjustment_account_id = await get_posting_default(
            session, tenant_id, FX_REVALUATION_ADJUSTMENT
        )
        gain_loss = await get_posting_default(
            session,
            tenant_id,
            FX_UNREALIZED_GAIN if delta > 0 else FX_UNREALIZED_LOSS,
        )
        await _post_adjustment_pair(
            session,
            tenant_id,
            functional_code,
            rate_date,
            next_start,
            f"FX revaluation {account.code} @ {rate_date.isoformat()}",
            _adjustment_lines(delta, adjustment_account_id, gain_loss),
        )
    return run


@register_job(FX_REVALUATION_JOB)
async def fx_revaluation_job(
    session: AsyncSession, tenant_id: uuid.UUID, payload: dict[str, Any]
) -> dict[str, Any]:
    """Background-job handler (PLAN 4P.5, closes #26): a revaluation posts an adjustment +
    reversal pair PER monetary account, so at scale it would blow a request's proxy-timeout
    budget (PERFORMANCE §3). The endpoint submits this job; the runner executes it under the
    submitting tenant + actor inside run_in_uow, so postings/audit/events behave exactly as
    the old in-request call. Delegates to the unchanged :func:`run_fx_revaluation`."""
    run = await run_fx_revaluation(
        session,
        tenant_id,
        uuid.UUID(payload["fiscal_period_id"]),
        date.fromisoformat(payload["rate_date"]),
    )
    return {"run_id": str(run.id), "status": run.status}


async def list_revaluation_runs(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Page[FxRevaluationRun]:
    """Keyset-paginated revaluation runs, newest first (created_at DESC + id tiebreaker; #27)."""
    stmt = select(FxRevaluationRun).where(FxRevaluationRun.tenant_id == tenant_id)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(FxRevaluationRun.created_at, SortDirection.DESC)],
        pk=FxRevaluationRun.id,
        cursor=cursor,
        limit=limit,
    )
