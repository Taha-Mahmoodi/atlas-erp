"""Balance sheet: ASSET/LIABILITY/EQUITY cumulative to a date, retained earnings derived (D-021).

The hallmark of the universal-journal design: there is no retained-earnings ledger account and no
year-end carryforward in v1. Retained earnings is computed ON THE FLY from the SAME base aggregate
as ``net_income_signed`` over ALL history up to the as-of date (every posted REVENUE/EXPENSE line
ever), then presented as a single synthetic 'Current & accumulated earnings' equity line. This is
exact by construction: assets - liabilities - posted-equity is precisely net income to date, because
every balanced posting moved equal debits and credits. So Assets == Liabilities + Equity holds
identically, asserted into ``is_balanced`` + the totals. No stored totals, ever.
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
    net_income_signed,
)
from app.modules.finance.service.statements.grouping import (
    StatementGroup,
    StatementLine,
    group_accounts,
)

# The synthetic equity line that carries derived retained earnings (D-021). Not a real account;
# computed from the journal's full-history P&L net, so v1 needs no year-end carryforward.
_RETAINED_EARNINGS_GROUP = "EARNINGS"
_RETAINED_EARNINGS_LABEL = "Current & accumulated earnings"


@dataclass
class BalanceSheet:
    """The balance sheet as of a date (D-021): the three sections + the accounting-equation check.

    All section totals are natural magnitudes (assets positive, liabilities positive, equity
    positive). ``retained_earnings`` is the derived net-income-to-date folded into ``equity_total``.
    ``is_balanced`` is the Assets == Liabilities + Equity identity."""

    as_of: date
    asset_groups: list[StatementGroup] = field(default_factory=list)
    liability_groups: list[StatementGroup] = field(default_factory=list)
    equity_groups: list[StatementGroup] = field(default_factory=list)
    asset_total: Decimal = ZERO
    liability_total: Decimal = ZERO
    equity_total: Decimal = ZERO
    retained_earnings: Decimal = ZERO
    is_balanced: bool = True


async def balance_sheet(
    session: AsyncSession, tenant_id: uuid.UUID, as_of_date: date
) -> BalanceSheet:
    """The balance sheet as of ``as_of_date`` (D-021).

    Cumulative ASSET/LIABILITY/EQUITY balances from the base aggregate over all history to the date,
    grouped under the presentation hierarchy. Retained earnings is derived as net income to date
    (``net_income_signed`` over the same cumulative balances) and presented as a synthetic equity
    line in an EARNINGS group, so posted equity + derived earnings == total equity. Asserts Assets
    == Liabilities + Equity into ``is_balanced`` + the totals."""
    balances = await _account_balances(session, tenant_id, date_to=as_of_date)
    meta = await load_account_meta(session, tenant_id)

    asset_ids = {
        aid for aid, a in meta.items() if a.account_type is AccountType.ASSET
    }
    liability_ids = {
        aid for aid, a in meta.items() if a.account_type is AccountType.LIABILITY
    }
    equity_ids = {
        aid for aid, a in meta.items() if a.account_type is AccountType.EQUITY
    }

    asset_groups, asset_total = group_accounts(balances, meta, asset_ids)
    liability_groups, liability_total = group_accounts(balances, meta, liability_ids)
    equity_groups, equity_total = group_accounts(balances, meta, equity_ids)

    # Retained earnings = net income to date, derived from the same aggregate (D-021). A profit is
    # credit-positive, i.e. a positive equity magnitude, so it folds straight into equity_total.
    retained_earnings = net_income_signed(balances, meta)
    if retained_earnings != ZERO:
        equity_groups.append(
            StatementGroup(
                group_code=_RETAINED_EARNINGS_GROUP,
                group_name=_RETAINED_EARNINGS_LABEL,
                lines=[
                    StatementLine(
                        account_id=uuid.UUID(int=0),
                        account_code=_RETAINED_EARNINGS_GROUP,
                        account_name=_RETAINED_EARNINGS_LABEL,
                        amount=retained_earnings,
                    )
                ],
                subtotal=retained_earnings,
            )
        )
        equity_groups.sort(key=lambda g: g.group_code)
        equity_total += retained_earnings

    return BalanceSheet(
        as_of=as_of_date,
        asset_groups=asset_groups,
        liability_groups=liability_groups,
        equity_groups=equity_groups,
        asset_total=asset_total,
        liability_total=liability_total,
        equity_total=equity_total,
        retained_earnings=retained_earnings,
        is_balanced=asset_total == liability_total + equity_total,
    )
