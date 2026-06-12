"""Financial-statement HTTP layer (PLAN 4.8, D-021), included into the finance router.

Six read-only GET endpoints, all guarded by the single ``finance.statements.read`` key (D-009) and
all pure projections of the universal journal — no writes, no idempotency, no uow. Split out of
router.py and mounted via ``router.include_router(statements_router)`` so the module stays ONE
surface at ``/api/v1/finance`` (the fx/tax/ap/ar/co sub-router pattern). The service returns plain
dataclasses; ``model_validate`` lifts them into the Read schemas (ApiModel ``from_attributes``).
Query params are plain typed args (the project convention; required when they have no default) — the
date params are required, ``cost_center_id`` optional. Tenant scoping rides the D-007 filter plus
the explicit ``current.tenant_id``.
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends

from app.core.deps import CurrentUserDep, SessionDep
from app.core.rbac import require_permission
from app.modules.finance import service
from app.modules.finance.constants import FINANCE_STATEMENTS_READ
from app.modules.finance.statements_schemas import (
    BalanceSheetRead,
    CashFlowStatementRead,
    CostCenterReportRead,
    MarginByProductRead,
    ProfitAndLossRead,
    TrialBalanceRead,
)

statements_router = APIRouter(
    prefix="/statements",
    tags=["finance-statements"],
    dependencies=[Depends(require_permission(FINANCE_STATEMENTS_READ))],
)


@statements_router.get("/trial-balance", response_model=TrialBalanceRead)
async def get_trial_balance(
    current: CurrentUserDep,
    session: SessionDep,
    as_of: date,
) -> TrialBalanceRead:
    """The trial balance as of ``as_of`` (D-021): per-account debit/credit totals + the
    universal-journal debit==credit self-check (``is_balanced``)."""
    result = await service.trial_balance(session, current.tenant_id, as_of)
    return TrialBalanceRead.model_validate(result)


@statements_router.get("/profit-loss", response_model=ProfitAndLossRead)
async def get_profit_loss(
    current: CurrentUserDep,
    session: SessionDep,
    date_from: date,
    date_to: date,
) -> ProfitAndLossRead:
    """The P&L over ``[date_from, date_to]`` (D-021): revenue and expense grouped by account group,
    with net income = revenue - expense."""
    result = await service.profit_and_loss(
        session, current.tenant_id, date_from, date_to
    )
    return ProfitAndLossRead.model_validate(result)


@statements_router.get("/balance-sheet", response_model=BalanceSheetRead)
async def get_balance_sheet(
    current: CurrentUserDep,
    session: SessionDep,
    as_of: date,
) -> BalanceSheetRead:
    """The balance sheet as of ``as_of`` (D-021): assets/liabilities/equity with retained earnings
    derived on the fly, and the Assets == Liabilities + Equity self-check (``is_balanced``)."""
    result = await service.balance_sheet(session, current.tenant_id, as_of)
    return BalanceSheetRead.model_validate(result)


@statements_router.get("/cash-flow", response_model=CashFlowStatementRead)
async def get_cash_flow(
    current: CurrentUserDep,
    session: SessionDep,
    date_from: date,
    date_to: date,
) -> CashFlowStatementRead:
    """The indirect cash-flow statement over ``[date_from, date_to]`` (D-021): net income + working-
    capital deltas by category, with the cash-equivalent reconciliation self-check
    (``is_reconciled``)."""
    result = await service.cash_flow_indirect(
        session, current.tenant_id, date_from, date_to
    )
    return CashFlowStatementRead.model_validate(result)


@statements_router.get("/cost-center-report", response_model=CostCenterReportRead)
async def get_cost_center_report(
    current: CurrentUserDep,
    session: SessionDep,
    date_from: date,
    date_to: date,
    cost_center_id: uuid.UUID | None = None,
) -> CostCenterReportRead:
    """Balances grouped by cost centre and account over the period (D-021), a projection of the
    journal's ``cost_center_id`` dimension. ``cost_center_id`` narrows to one centre."""
    result = await service.cost_center_report(
        session, current.tenant_id, date_from, date_to, cost_center_id
    )
    return CostCenterReportRead.model_validate(result)


@statements_router.get("/margin-by-product", response_model=MarginByProductRead)
async def get_margin_by_product(
    current: CurrentUserDep,
    session: SessionDep,
    date_from: date,
    date_to: date,
) -> MarginByProductRead:
    """Revenue - COGS per item over the period (D-021), a projection of the journal's ``item_id``
    dimension (sparse until inventory posts COGS with item_id)."""
    result = await service.margin_by_product(
        session, current.tenant_id, date_from, date_to
    )
    return MarginByProductRead.model_validate(result)
