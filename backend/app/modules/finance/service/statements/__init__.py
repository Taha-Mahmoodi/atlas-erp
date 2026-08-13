"""Financial-statement projections (D-021): every statement is a projection of ONE base aggregate
over ``fin_journal_lines`` — no stored totals, ever (CLAUDE.md rule 1).

Split into one file per statement (each well under the 400-line cap) plus a shared ``base`` (the
single ``_account_balances`` aggregate + account metadata + re-signing) and ``grouping`` (the
presentation-hierarchy layout the P&L and balance sheet share). Re-exported here so callers use one
surface: ``from app.modules.finance.service import statements`` then ``statements.trial_balance``.
"""

from app.modules.finance.service.statements.balance_sheet import (
    BalanceSheet,
    balance_sheet,
)
from app.modules.finance.service.statements.base import (
    _account_balances,
    net_income_signed,
)
from app.modules.finance.service.statements.cash_flow import (
    CashFlowCategorySection,
    CashFlowLine,
    CashFlowStatement,
    cash_flow_indirect,
)
from app.modules.finance.service.statements.cost_center import (
    CostCenterAccountLine,
    CostCenterReport,
    CostCenterSection,
    cost_center_report,
)
from app.modules.finance.service.statements.grouping import (
    StatementGroup,
    StatementLine,
)
from app.modules.finance.service.statements.margin import (
    ItemMargin,
    MarginByItem,
    margin_by_item,
)
from app.modules.finance.service.statements.profit_loss import (
    ProfitAndLoss,
    profit_and_loss,
)
from app.modules.finance.service.statements.trial_balance import (
    TrialBalance,
    TrialBalanceRow,
    trial_balance,
)

__all__ = [
    "BalanceSheet",
    "CashFlowCategorySection",
    "CashFlowLine",
    "CashFlowStatement",
    "CostCenterAccountLine",
    "CostCenterReport",
    "CostCenterSection",
    "ItemMargin",
    "MarginByItem",
    "ProfitAndLoss",
    "StatementGroup",
    "StatementLine",
    "TrialBalance",
    "TrialBalanceRow",
    "_account_balances",
    "balance_sheet",
    "cash_flow_indirect",
    "cost_center_report",
    "margin_by_item",
    "net_income_signed",
    "profit_and_loss",
    "trial_balance",
]
