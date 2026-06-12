"""THE single base aggregate every financial statement projects from (D-021).

The Universal-Journal payoff (CLAUDE.md rule 1): there are NO stored totals, no balance tables,
no materialized views. Every statement — trial balance, P&L, balance sheet, cash flow, cost-centre
report, margin — is a projection of ``_account_balances`` over ``fin_journal_lines`` only. One
predicate (tenant + ``is_posted`` + date), one projection (functional debit minus credit), one
covering index (``ix_fin_journal_lines_proj``); so every statement is provably consistent with the
trial balance because they read the SAME query.

No header join is needed: the line denormalizes ``tenant_id``/``posting_date``/``is_posted`` during
the two-flush posting protocol (D-017), so the aggregate touches the line table alone. MoneyType
type propagation keeps the SUM exact on both engines (D-015): NUMERIC on Postgres, scaled-integer
micro-units on SQLite, converted back to ``Decimal`` on read.

The signed balance is debit-positive: ASSET/EXPENSE accounts (normal DEBIT) carry a positive
balance, LIABILITY/EQUITY/REVENUE (normal CREDIT) a negative one. Each statement re-signs per
account type as needed (a liability is presented as its credit-positive magnitude, etc.).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.finance.constants import AccountType, CashFlowCategory, NormalBalance
from app.modules.finance.models import Account, AccountGroup, JournalLine

# A zero Decimal at the money scale; statement maths reduces onto this so an empty journal yields
# explicit zeros rather than None.
ZERO = Decimal("0")


@dataclass(frozen=True)
class AccountMeta:
    """The statement-relevant metadata of one account (D-021), loaded once per statement.

    Carries everything a projection needs to classify and present a balance: the five-way
    ``account_type`` drives which statement the account belongs to; ``normal_balance`` re-signs the
    debit-positive base balance into a presentation magnitude; ``cash_flow_category`` and
    ``is_cash_equivalent`` feed the indirect cash-flow statement; ``group_id``/``group_code``/
    ``group_name`` place the account in the presentation hierarchy."""

    account_id: uuid.UUID
    code: str
    name: str
    account_type: AccountType
    normal_balance: NormalBalance
    cash_flow_category: CashFlowCategory | None
    is_cash_equivalent: bool
    group_id: uuid.UUID | None
    group_code: str | None
    group_name: str | None


async def _account_balances(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    date_to: date,
    date_from: date | None = None,
    posted_only: bool = True,
) -> dict[uuid.UUID, Decimal]:
    """THE base aggregate (D-021): signed (debit-positive) balance per account over the journal.

    ``select(account_id, sum(functional_debit - functional_credit)) WHERE tenant, is_posted,
    posting_date <= date_to [and >= date_from] GROUP BY account_id``. Every statement builds on
    exactly this — same predicate, same projection, same index (``ix_fin_journal_lines_proj``).
    Returns ``{account_id: signed_balance}``; accounts with no posting in range are simply absent
    (the caller treats a missing key as zero). ``posted_only`` defaults True (statements never show
    unposted drafts); it is a parameter only so a future audit view could pass False — it never
    does in v1.
    """
    signed = func.sum(
        JournalLine.functional_debit_amount - JournalLine.functional_credit_amount
    )
    stmt = select(JournalLine.account_id, signed).where(
        JournalLine.tenant_id == tenant_id,
        JournalLine.posting_date <= date_to,
    )
    if posted_only:
        stmt = stmt.where(JournalLine.is_posted.is_(True))
    if date_from is not None:
        stmt = stmt.where(JournalLine.posting_date >= date_from)
    stmt = stmt.group_by(JournalLine.account_id)

    balances: dict[uuid.UUID, Decimal] = {}
    for account_id, total in (await session.execute(stmt)).all():
        balances[account_id] = Decimal(str(total)) if total is not None else ZERO
    return balances


async def _dimension_balances(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    dimension: object,
    *,
    date_from: date,
    date_to: date,
    dimension_filter: uuid.UUID | None = None,
) -> dict[tuple[uuid.UUID | None, uuid.UUID], Decimal]:
    """The base aggregate re-grouped by a line dimension AND account (D-021).

    Same predicate and projection as ``_account_balances`` (tenant + ``is_posted`` + date range,
    functional debit minus credit), but grouped by ``(dimension_column, account_id)`` so cost-centre
    and margin reports read a dimension straight off the journal line. ``dimension`` is the
    ``JournalLine`` column object (``JournalLine.cost_center_id`` / ``JournalLine.item_id``);
    ``dimension_filter`` narrows to a single dimension value when given. Returns ``{(dim_value,
    account_id): signed_balance}``; ``dim_value`` may be None for lines carrying no dimension."""
    signed = func.sum(
        JournalLine.functional_debit_amount - JournalLine.functional_credit_amount
    )
    stmt = select(dimension, JournalLine.account_id, signed).where(
        JournalLine.tenant_id == tenant_id,
        JournalLine.is_posted.is_(True),
        JournalLine.posting_date >= date_from,
        JournalLine.posting_date <= date_to,
    )
    if dimension_filter is not None:
        stmt = stmt.where(dimension == dimension_filter)
    stmt = stmt.group_by(dimension, JournalLine.account_id)

    balances: dict[tuple[uuid.UUID | None, uuid.UUID], Decimal] = {}
    for dim_value, account_id, total in (await session.execute(stmt)).all():
        balances[(dim_value, account_id)] = (
            Decimal(str(total)) if total is not None else ZERO
        )
    return balances


async def load_account_meta(
    session: AsyncSession, tenant_id: uuid.UUID
) -> dict[uuid.UUID, AccountMeta]:
    """Every account's statement metadata for a tenant, keyed by id (D-021).

    One LEFT JOIN to ``fin_account_groups`` so an account with no group still appears (its group
    fields are None). Loaded once per statement and shared across the projection so a statement is
    one aggregate query + one metadata query, never per-account lookups."""
    stmt = (
        select(
            Account.id,
            Account.code,
            Account.name,
            Account.account_type,
            Account.normal_balance,
            Account.cash_flow_category,
            Account.is_cash_equivalent,
            Account.account_group_id,
            AccountGroup.code.label("group_code"),
            AccountGroup.name.label("group_name"),
        )
        .outerjoin(AccountGroup, Account.account_group_id == AccountGroup.id)
        .where(Account.tenant_id == tenant_id)
    )
    meta: dict[uuid.UUID, AccountMeta] = {}
    for row in (await session.execute(stmt)).all():
        meta[row.id] = AccountMeta(
            account_id=row.id,
            code=row.code,
            name=row.name,
            account_type=AccountType(row.account_type),
            normal_balance=NormalBalance(row.normal_balance),
            cash_flow_category=(
                CashFlowCategory(row.cash_flow_category)
                if row.cash_flow_category is not None
                else None
            ),
            is_cash_equivalent=bool(row.is_cash_equivalent),
            group_id=row.account_group_id,
            group_code=row.group_code,
            group_name=row.group_name,
        )
    return meta


def presentation_amount(meta: AccountMeta, signed_balance: Decimal) -> Decimal:
    """Re-sign the debit-positive base balance into the account's natural presentation magnitude.

    ASSET/EXPENSE (normal DEBIT) keep the signed balance; LIABILITY/EQUITY/REVENUE (normal CREDIT)
    flip it, so a liability with a -500 base balance presents as +500. Statement bodies show these
    natural magnitudes (a positive revenue, a positive liability), while balance/reconciliation
    checks run on the raw signed balances where the debit==credit identity holds."""
    if meta.normal_balance is NormalBalance.CREDIT:
        return -signed_balance
    return signed_balance


def net_income_signed(
    balances: dict[uuid.UUID, Decimal], meta: dict[uuid.UUID, AccountMeta]
) -> Decimal:
    """Net income (revenue - expense) over whatever range produced ``balances`` (D-021).

    Computed straight from the base aggregate: revenue accounts (normal CREDIT) carry a negative
    debit-positive balance, expense accounts (normal DEBIT) a positive one, so revenue minus expense
    is ``-(Σ revenue signed) - (Σ expense signed)`` = ``-(Σ P&L signed balances)``. Returned as a
    credit-positive figure (a profit is positive) — the value the balance sheet folds into retained
    earnings and the cash-flow statement starts from."""
    pl_signed = ZERO
    for account_id, balance in balances.items():
        account = meta.get(account_id)
        if account is None:
            continue
        if account.account_type in (AccountType.REVENUE, AccountType.EXPENSE):
            pl_signed += balance
    return -pl_signed
