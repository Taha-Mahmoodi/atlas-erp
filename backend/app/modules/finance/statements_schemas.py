"""Financial-statement response schemas (PLAN 4.8, D-021, Pydantic v2 ApiModel base).

Read-only mirrors of the ``service.statements`` result dataclasses, snake_case field-for-field;
money fields are Decimal, serialized as strings (D-015). A separate file from ``schemas.py`` because
that file is at the STRUCTURE §3 size cap — the same split ``controlling_schemas.py`` /
``payables_schemas.py`` use. ``from_attributes`` (ApiModel) lets the router validate the dataclasses
straight into these schemas. Every statement carries its self-check flag (``is_balanced`` /
``is_reconciled``) so the universal-journal guarantee is visible on the wire.
"""

import uuid
from datetime import date
from decimal import Decimal

from app.core.schemas import ApiModel
from app.modules.finance.constants import AccountType, CashFlowCategory

# --- Trial balance ------------------------------------------------------------


class TrialBalanceRowRead(ApiModel):
    account_id: uuid.UUID
    account_code: str
    account_name: str
    account_type: AccountType
    debit: Decimal
    credit: Decimal


class TrialBalanceRead(ApiModel):
    as_of: date
    rows: list[TrialBalanceRowRead]
    total_debit: Decimal
    total_credit: Decimal
    is_balanced: bool


# --- Grouped statements (P&L, balance sheet) shared shapes --------------------


class StatementLineRead(ApiModel):
    account_id: uuid.UUID
    account_code: str
    account_name: str
    amount: Decimal


class StatementGroupRead(ApiModel):
    group_code: str
    group_name: str
    lines: list[StatementLineRead]
    subtotal: Decimal


# --- Profit & loss ------------------------------------------------------------


class ProfitAndLossRead(ApiModel):
    date_from: date
    date_to: date
    revenue_groups: list[StatementGroupRead]
    expense_groups: list[StatementGroupRead]
    revenue_total: Decimal
    expense_total: Decimal
    net_income: Decimal


# --- Balance sheet ------------------------------------------------------------


class BalanceSheetRead(ApiModel):
    as_of: date
    asset_groups: list[StatementGroupRead]
    liability_groups: list[StatementGroupRead]
    equity_groups: list[StatementGroupRead]
    asset_total: Decimal
    liability_total: Decimal
    equity_total: Decimal
    retained_earnings: Decimal
    is_balanced: bool


# --- Cash flow (indirect) -----------------------------------------------------


class CashFlowLineRead(ApiModel):
    account_id: uuid.UUID
    account_code: str
    account_name: str
    amount: Decimal


class CashFlowCategorySectionRead(ApiModel):
    category: CashFlowCategory
    lines: list[CashFlowLineRead]
    subtotal: Decimal


class CashFlowStatementRead(ApiModel):
    date_from: date
    date_to: date
    net_income: Decimal
    sections: list[CashFlowCategorySectionRead]
    net_change_from_activities: Decimal
    cash_account_movement: Decimal
    is_reconciled: bool


# --- Cost-centre report -------------------------------------------------------


class CostCenterAccountLineRead(ApiModel):
    account_id: uuid.UUID
    account_code: str
    account_name: str
    amount: Decimal


class CostCenterSectionRead(ApiModel):
    cost_center_id: uuid.UUID | None
    cost_center_code: str | None
    cost_center_name: str | None
    lines: list[CostCenterAccountLineRead]
    total: Decimal


class CostCenterReportRead(ApiModel):
    date_from: date
    date_to: date
    sections: list[CostCenterSectionRead]


# --- Margin by item -----------------------------------------------------------


class ItemMarginRead(ApiModel):
    item_id: uuid.UUID | None
    revenue: Decimal
    cogs: Decimal
    margin: Decimal
    margin_percent: Decimal | None


class MarginByItemRead(ApiModel):
    date_from: date
    date_to: date
    items: list[ItemMarginRead]
