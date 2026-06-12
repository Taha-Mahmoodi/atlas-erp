"""Trial balance: the base aggregate split into per-account debit/credit totals (D-021).

The universal-journal guarantee made visible: because every posted entry balances (the DB balance
trigger, D-017), the sum of all debit balances equals the sum of all credit balances across the
whole ledger. The trial balance asserts exactly that — ``is_balanced`` + the two totals — over the
SAME base aggregate every other statement reads, so a balanced trial balance certifies the data the
P&L and balance sheet then project.

A debit-positive base balance becomes a debit total (and zero credit); a credit-positive one becomes
a credit total. No stored totals: re-running after a new posting reflects it immediately.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.finance.constants import AccountType
from app.modules.finance.service.statements.base import (
    ZERO,
    _account_balances,
    load_account_meta,
)


@dataclass(frozen=True)
class TrialBalanceRow:
    """One account's line on the trial balance: its code/name/type and the side its net balance
    lands on. Exactly one of ``debit``/``credit`` is non-zero (a perfectly netted account is
    omitted upstream)."""

    account_id: uuid.UUID
    account_code: str
    account_name: str
    account_type: AccountType
    debit: Decimal
    credit: Decimal


@dataclass
class TrialBalance:
    """The trial balance as of a date (D-021): per-account rows plus the universal-journal
    self-check. ``is_balanced`` is the debit==credit identity every posted ledger must satisfy."""

    as_of: date
    rows: list[TrialBalanceRow] = field(default_factory=list)
    total_debit: Decimal = ZERO
    total_credit: Decimal = ZERO
    is_balanced: bool = True


async def trial_balance(
    session: AsyncSession, tenant_id: uuid.UUID, date_to: date
) -> TrialBalance:
    """The trial balance for all activity up to and including ``date_to`` (D-021).

    Splits each account's signed base balance onto its natural side (a positive debit-positive
    balance is a debit total, a negative one a credit total), tagged with the account's code/name/
    type. Accounts that net exactly to zero are omitted. Asserts the debit==credit identity into
    ``is_balanced`` + the totals — the universal-journal guarantee, not a stored figure."""
    balances = await _account_balances(session, tenant_id, date_to=date_to)
    meta = await load_account_meta(session, tenant_id)

    rows: list[TrialBalanceRow] = []
    total_debit = ZERO
    total_credit = ZERO
    for account_id, signed in balances.items():
        account = meta.get(account_id)
        if account is None or signed == ZERO:
            continue
        debit = signed if signed > ZERO else ZERO
        credit = -signed if signed < ZERO else ZERO
        total_debit += debit
        total_credit += credit
        rows.append(
            TrialBalanceRow(
                account_id=account_id,
                account_code=account.code,
                account_name=account.name,
                account_type=account.account_type,
                debit=debit,
                credit=credit,
            )
        )

    rows.sort(key=lambda r: r.account_code)
    return TrialBalance(
        as_of=date_to,
        rows=rows,
        total_debit=total_debit,
        total_credit=total_credit,
        is_balanced=total_debit == total_credit,
    )
