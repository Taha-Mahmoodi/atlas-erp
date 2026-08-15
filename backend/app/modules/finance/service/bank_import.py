"""Bank-statement import + statement reads/progress (PLAN 4.9).

The CSV contract (header, row validation, parsing) lives in ``service/bank_csv.py``;
reconciliation (suggest/confirm/reject/clear) in ``service/bank_reconcile.py`` — STRUCTURE §3
split, one concept per file. ``import_statement`` validates the statement balances
(``closing == opening + Σ(line amounts)`` or 422 ``finance.statement_unbalanced``) before
anything persists.

**Bulk insert** (PERFORMANCE §2): lines are written with ONE ORM-enabled ``insert()``
executemany over plain row dicts — never per-row ORM adds. tenant_id is set explicitly per row
(flush-time stamping only covers ORM instances); the composite tenant FK backstops it.
ORM-enabled inserts pass the D-007 listener (it filters selects/updates/deletes) and the
D-007 grep gate (no Core insert-attribute call on a Table, no raw SQL).

**Size routing** (PERFORMANCE §3): the ROUTER runs imports up to
``BANK_IMPORT_SYNC_MAX_LINES`` inline (201) and submits anything larger as a
``finance.bank_statement_import`` job (202 {job_id}); the handler calls the SAME
``import_statement``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.core.exceptions import NotFoundError, ValidationFailedError
from app.core.jobs import register_job
from app.core.money import currency_decimals, quantize_money
from app.core.pagination import (
    DEFAULT_LIMIT,
    OrderKey,
    SortDirection,
    filter_fingerprint,
    paginate,
)
from app.core.schemas import Page
from app.modules.finance.constants import (
    BANK_STATEMENT_DOC_TYPE,
    BANK_STATEMENT_IMPORT_JOB,
    LineStatus,
    StatementStatus,
)
from app.modules.finance.models import Account, BankStatement, BankStatementLine
from app.modules.finance.service.bank_csv import parse_statement_csv


@dataclass(frozen=True)
class StatementProgress:
    """Line counts by status; a line is RESOLVED when MATCHED or CLEARED."""

    total: int
    unmatched: int
    suggested: int
    matched: int
    cleared: int

    @property
    def resolved(self) -> int:
        return self.matched + self.cleared


async def _require_bank_account(
    session: AsyncSession, tenant_id: uuid.UUID, bank_account_id: uuid.UUID
) -> Account:
    """The statement's account must exist in the tenant AND be flagged is_cash_equivalent —
    the service-level half of the model's composite FK (no flag-scoped FK exists)."""
    account = (
        await session.execute(
            select(Account).where(Account.tenant_id == tenant_id, Account.id == bank_account_id)
        )
    ).scalar_one_or_none()
    if account is None:
        raise ValidationFailedError(
            message="The bank account does not exist in this tenant",
            code="finance.bank_account_not_found",
            details={"bank_account_id": str(bank_account_id)},
        )
    if not account.is_cash_equivalent:
        raise ValidationFailedError(
            message="Bank statements can only be imported against a cash-equivalent account",
            code="finance.bank_account_not_cash_equivalent",
            details={"bank_account_id": str(bank_account_id)},
        )
    return account


async def import_statement(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    bank_account_id: uuid.UUID,
    statement_date: date,
    opening_balance: Decimal,
    closing_balance: Decimal,
    currency_code: str,
    csv_text: str,
    source_filename: str | None = None,
    import_job_id: uuid.UUID | None = None,
) -> BankStatement:
    """Parse, validate and persist one statement (module docstring): cash-equivalent check,
    CSV parse with per-row errors, the balance check, document registration (D-012, doc_number
    NULL — external document), then ONE bulk executemany insert for the lines (PERFORMANCE §2).
    Caller commits via uow; serves both the inline path and the background job.

    IDEMPOTENT ON ``import_job_id`` (P0 Task 1): ``core/job_sweeper.py`` re-dispatches an import
    whose runner died mid-flight, and the job id the router already stamps into the payload is the
    natural key — no new column. A re-import under the same job returns the statement that job
    created, instead of a second statement with a duplicate set of lines that a reconciler would
    have to spot by eye. The INLINE path passes no job id and is unaffected: importing the same
    CSV twice by hand stays two statements, which is a human decision, not a lost runner."""
    if import_job_id is not None:
        already = (
            await session.execute(
                select(BankStatement).where(
                    BankStatement.tenant_id == tenant_id,
                    BankStatement.import_job_id == import_job_id,
                )
            )
        ).scalar_one_or_none()
        if already is not None:
            return already
    await _require_bank_account(session, tenant_id, bank_account_id)
    parsed = parse_statement_csv(csv_text, currency_code)

    decimals = currency_decimals(currency_code)
    opening = quantize_money(opening_balance, decimals)
    closing = quantize_money(closing_balance, decimals)
    lines_total = sum((line.amount for line in parsed), Decimal(0))
    if opening + lines_total != closing:
        raise ValidationFailedError(
            message="closing_balance must equal opening_balance plus the sum of line amounts",
            code="finance.statement_unbalanced",
            details={
                "opening_balance": str(opening),
                "closing_balance": str(closing),
                "lines_total": str(lines_total),
            },
        )

    statement_id = uuid.uuid4()
    document = await docflow.register_document(
        session,
        tenant_id,
        BANK_STATEMENT_DOC_TYPE,
        statement_id,
        doc_number=None,
        status=StatementStatus.IMPORTED.value,
    )
    statement = BankStatement(
        id=statement_id,
        tenant_id=tenant_id,
        document_id=document.id,
        bank_account_id=bank_account_id,
        statement_date=statement_date,
        opening_balance=opening,
        closing_balance=closing,
        currency_code=currency_code,
        status=StatementStatus.IMPORTED.value,
        line_count=len(parsed),
        import_job_id=import_job_id,
        source_filename=source_filename,
    )
    session.add(statement)
    await session.flush()

    # The PERFORMANCE §2 bulk insert: one ORM-enabled executemany, explicit tenant_id per row.
    await session.execute(
        insert(BankStatementLine),
        [
            {
                "id": uuid.uuid4(),
                "tenant_id": tenant_id,
                "statement_id": statement_id,
                "line_number": line.line_number,
                "value_date": line.value_date,
                "amount": line.amount,
                "description": line.description,
                "counterparty_ref": line.counterparty_ref,
                "status": LineStatus.UNMATCHED.value,
            }
            for line in parsed
        ],
    )
    return statement


@register_job(BANK_STATEMENT_IMPORT_JOB)
async def bank_statement_import_job(
    session: AsyncSession, tenant_id: uuid.UUID, payload: dict[str, Any]
) -> dict[str, Any]:
    """Background-job handler (PERFORMANCE §3): a >1k-line import would blow a request's
    proxy-timeout budget, so the router submits this job and returns 202. Delegates to
    :func:`import_statement`; ``job_id`` rides the payload (stamped by the router after
    submit) so the statement records which job imported it."""
    raw_job_id = payload.get("job_id")
    statement = await import_statement(
        session,
        tenant_id,
        bank_account_id=uuid.UUID(payload["bank_account_id"]),
        statement_date=date.fromisoformat(payload["statement_date"]),
        opening_balance=Decimal(payload["opening_balance"]),
        closing_balance=Decimal(payload["closing_balance"]),
        currency_code=payload["currency_code"],
        csv_text=payload["csv_text"],
        source_filename=payload.get("source_filename"),
        import_job_id=uuid.UUID(raw_job_id) if raw_job_id else None,
    )
    return {"statement_id": str(statement.id), "line_count": statement.line_count}


# --- Reads + progress -----------------------------------------------------------


async def get_bank_statement(
    session: AsyncSession, tenant_id: uuid.UUID, statement_id: uuid.UUID
) -> BankStatement:
    statement = await session.get(BankStatement, statement_id)
    if statement is None or statement.tenant_id != tenant_id:
        raise NotFoundError(
            message="Bank statement not found", code="finance.bank_statement_not_found"
        )
    return statement


async def list_bank_statements(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
    bank_account_id: uuid.UUID | None = None,
) -> Page[BankStatement]:
    """Keyset-paginated statements, newest statement_date first (D-014). The id tiebreaker is
    the ONLY secondary key — deliberately not created_at: SQLite stores the server-defaulted
    CURRENT_TIMESTAMP without fractional seconds while a re-bound cursor datetime renders with
    ``.000000``, so a created_at seek key would lexicographically re-include the boundary row
    (PG is unaffected; the core-level fix is tracked separately)."""
    stmt = select(BankStatement).where(BankStatement.tenant_id == tenant_id)
    if bank_account_id is not None:
        stmt = stmt.where(BankStatement.bank_account_id == bank_account_id)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(BankStatement.statement_date, SortDirection.DESC)],
        pk=BankStatement.id,
        cursor=cursor,
        limit=limit,
        filters=filter_fingerprint(bank_account_id),
    )


async def list_statement_lines(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    statement_id: uuid.UUID,
    *,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
    status: str | None = None,
) -> Page[BankStatementLine]:
    """Keyset-paginated lines of one statement in line order, optionally filtered by status
    (the reconciliation work-list; covered by the statement+status composite index)."""
    stmt = select(BankStatementLine).where(
        BankStatementLine.tenant_id == tenant_id,
        BankStatementLine.statement_id == statement_id,
    )
    if status is not None:
        stmt = stmt.where(BankStatementLine.status == LineStatus(status).value)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(BankStatementLine.line_number, SortDirection.ASC)],
        pk=BankStatementLine.id,
        cursor=cursor,
        limit=limit,
        filters=filter_fingerprint(statement_id, status),
    )


async def statement_progress(
    session: AsyncSession, tenant_id: uuid.UUID, statement_id: uuid.UUID
) -> StatementProgress:
    """Line counts by status in ONE grouped query (no per-status round trips)."""
    rows = (
        await session.execute(
            select(BankStatementLine.status, func.count(BankStatementLine.id))
            .where(
                BankStatementLine.tenant_id == tenant_id,
                BankStatementLine.statement_id == statement_id,
            )
            .group_by(BankStatementLine.status)
        )
    ).all()
    by_status = {status: count for status, count in rows}
    return StatementProgress(
        total=sum(by_status.values()),
        unmatched=by_status.get(LineStatus.UNMATCHED.value, 0),
        suggested=by_status.get(LineStatus.SUGGESTED.value, 0),
        matched=by_status.get(LineStatus.MATCHED.value, 0),
        cleared=by_status.get(LineStatus.CLEARED.value, 0),
    )


async def refresh_statement_status(
    session: AsyncSession, tenant_id: uuid.UUID, statement: BankStatement
) -> StatementProgress:
    """Recompute the derived statement status from line resolution (RECONCILED when every line
    is MATCHED/CLEARED, PARTIALLY_RECONCILED when some are, else IMPORTED), writing it through
    the loaded object + the docflow registry when changed. Re-running it is a no-op."""
    progress = await statement_progress(session, tenant_id, statement.id)
    if progress.total > 0 and progress.resolved == progress.total:
        new_status = StatementStatus.RECONCILED.value
    elif progress.resolved > 0:
        new_status = StatementStatus.PARTIALLY_RECONCILED.value
    else:
        new_status = StatementStatus.IMPORTED.value
    if statement.status != new_status:
        statement.status = new_status
        await session.flush()
        await docflow.set_document_status(
            session, tenant_id, statement.document_id, status=new_status
        )
    return progress
