"""Profit & loss: REVENUE and EXPENSE accounts over a date range (D-021).

A projection of the base aggregate restricted to the date range and to P&L account types, laid out
under the presentation-group hierarchy with a subtotal per group and a section total for revenue and
for expense. Net income = revenue - expense, hand-checkable against any posted dataset and equal to
the figure the balance sheet folds into retained earnings (same aggregate, ``net_income_signed``).
No stored totals: a new posting in range changes the P&L immediately on the next read.
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
from app.modules.finance.service.statements.grouping import StatementGroup, group_accounts


@dataclass
class ProfitAndLoss:
    """The P&L for a period (D-021): revenue and expense groups + the net-income identity.

    ``revenue_total`` and ``expense_total`` are natural magnitudes (both positive); ``net_income``
    is ``revenue_total - expense_total`` — a profit is positive, a loss negative."""

    date_from: date
    date_to: date
    revenue_groups: list[StatementGroup] = field(default_factory=list)
    expense_groups: list[StatementGroup] = field(default_factory=list)
    revenue_total: Decimal = ZERO
    expense_total: Decimal = ZERO
    net_income: Decimal = ZERO


async def profit_and_loss(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    date_from: date,
    date_to: date,
) -> ProfitAndLoss:
    """The P&L over ``[date_from, date_to]`` inclusive (D-021).

    Restricts the base aggregate to the range, partitions accounts into REVENUE and EXPENSE, groups
    each under its presentation hierarchy, and computes net income = revenue - expense. Both section
    totals are natural magnitudes (``group_accounts`` re-signs revenue/expense onto the positive
    side), so net income reads as a signed profit/loss."""
    balances = await _account_balances(
        session, tenant_id, date_from=date_from, date_to=date_to
    )
    meta = await load_account_meta(session, tenant_id)

    revenue_ids = {
        aid
        for aid, account in meta.items()
        if account.account_type is AccountType.REVENUE
    }
    expense_ids = {
        aid
        for aid, account in meta.items()
        if account.account_type is AccountType.EXPENSE
    }
    revenue_groups, revenue_total = group_accounts(balances, meta, revenue_ids)
    expense_groups, expense_total = group_accounts(balances, meta, expense_ids)

    return ProfitAndLoss(
        date_from=date_from,
        date_to=date_to,
        revenue_groups=revenue_groups,
        expense_groups=expense_groups,
        revenue_total=revenue_total,
        expense_total=expense_total,
        net_income=revenue_total - expense_total,
    )
