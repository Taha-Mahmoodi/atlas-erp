"""Controlling dimensions + statement aggregates (finance's cross-module read contract, §5).

Split out of ``queries/__init__.py`` at the 400-line cap (STRUCTURE §8.4) and re-exported from the
package ``__init__`` so every ``from app.modules.finance.queries import X`` import keeps working
from one surface. These functions validate the cost-centre / profit-centre dimensions a journal line
carries, project per-dimension balances off the POSTED journal (cost-centre balance, project-
dimension costs), and expose the statement base aggregate (``account_balances`` / ``net_income``) so
reporting builds its views as projections of the SAME query — CO is a projection of the journal
(D-021), never a stored total.

Every function takes an explicit ``tenant_id`` and runs under the caller's tenant context, so the
D-007 filter applies on top of the explicit predicate — ordinary tenant-scoped reads, not a bypass.
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.finance.models import CostCenter, JournalLine, ProfitCenter


async def cost_center_exists(
    session: AsyncSession, tenant_id: uuid.UUID, cost_center_id: uuid.UUID
) -> bool:
    """Whether a cost centre with ``cost_center_id`` exists in the tenant. The journal posting flow
    calls this to validate a line's ``cost_center_id`` dimension before the line is written —
    service-level dimension integrity replacing the absent FK on the trigger-bearing journal-lines
    table (D-022)."""
    stmt = select(CostCenter.id).where(
        CostCenter.tenant_id == tenant_id, CostCenter.id == cost_center_id
    )
    return (await session.execute(stmt)).first() is not None


async def profit_center_exists(
    session: AsyncSession, tenant_id: uuid.UUID, profit_center_id: uuid.UUID
) -> bool:
    """Whether a profit centre with ``profit_center_id`` exists in the tenant. The companion to
    ``cost_center_exists`` for the journal line's ``profit_center_id`` dimension (D-022)."""
    stmt = select(ProfitCenter.id).where(
        ProfitCenter.tenant_id == tenant_id, ProfitCenter.id == profit_center_id
    )
    return (await session.execute(stmt)).first() is not None


async def cost_center_balance(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    cost_center_id: uuid.UUID,
    period_id: uuid.UUID,
) -> Decimal:
    """The cost centre's NET functional balance for a fiscal period (PLAN 4.7): SUM over POSTED
    journal lines carrying this ``cost_center_id`` in ``period_id`` of (functional debit minus
    functional credit). This is the amount ``run_allocation`` redistributes — CO is a projection of
    the journal (D-021), so the balance is derived from journal lines, never a stored total.
    MoneyType type propagation keeps the SUM exact on both engines (D-015); returns 0 when none."""
    debit = func.coalesce(
        func.sum(JournalLine.functional_debit_amount), 0
    )
    credit = func.coalesce(
        func.sum(JournalLine.functional_credit_amount), 0
    )
    stmt = select(debit - credit).where(
        JournalLine.tenant_id == tenant_id,
        JournalLine.cost_center_id == cost_center_id,
        JournalLine.fiscal_period_id == period_id,
        JournalLine.is_posted.is_(True),
    )
    result = (await session.execute(stmt)).scalar_one()
    return Decimal(str(result)) if result is not None else Decimal(0)


async def costs_by_project_dimension(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    project_dimension_ids: list[uuid.UUID],
    *,
    date_to: date | None = None,
) -> dict[uuid.UUID, Decimal]:
    """Net functional cost per project dimension over the POSTED journal (PLAN 11.1, D-056).

    The journal projection the PROJECT COST REPORT reads for actuals: SUM over POSTED journal lines
    whose ``project_id`` dimension (the OPAQUE WBS-element tag a posting carries when work/purchases
    are "posted to a WBS", D-017/D-029) is one of ``project_dimension_ids``, of (functional debit
    minus functional credit), grouped by that dimension. ONE set-based aggregate over all the ids
    (PERFORMANCE §6: no per-WBS N+1) — the cost report passes a project's whole WBS-id list at once.
    CO is a projection of the journal (D-021), so the cost is derived from journal lines, never a
    stored total; MoneyType type propagation keeps the SUM exact on both engines (D-015).

    Returns a dict keyed only by the dimension ids that actually have postings; a WBS id with no
    postings is ABSENT (the caller defaults it to zero). An empty ``project_dimension_ids`` returns
    ``{}`` with no query. ``date_to`` bounds the actuals cumulatively to that posting date (the cost
    report's optional as-of); omit it for all postings.

    This is a SANCTIONED finance/queries addition (STRUCTURE §5 / D-056): finance owns the journal
    projection, and projects reads it DOWNWARD by the opaque dimension — finance never imports
    projects, so finance stays at the bottom of the dependency order (D-029)."""
    if not project_dimension_ids:
        return {}
    debit = func.coalesce(func.sum(JournalLine.functional_debit_amount), 0)
    credit = func.coalesce(func.sum(JournalLine.functional_credit_amount), 0)
    stmt = (
        select(JournalLine.project_id, (debit - credit))
        .where(
            JournalLine.tenant_id == tenant_id,
            JournalLine.project_id.in_(project_dimension_ids),
            JournalLine.is_posted.is_(True),
        )
        .group_by(JournalLine.project_id)
    )
    if date_to is not None:
        stmt = stmt.where(JournalLine.posting_date <= date_to)
    rows = (await session.execute(stmt)).all()
    return {
        dimension_id: Decimal(str(net))
        for dimension_id, net in rows
        if dimension_id is not None
    }


async def account_balances(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    date_to: date,
    date_from: date | None = None,
) -> dict[uuid.UUID, Decimal]:
    """Signed (debit-positive) net balance per account over the posted journal (D-021). The single
    statement base aggregate, exposed here so the reporting module (PLAN 13) builds its own views as
    projections of the SAME query the statements use — never a stored total. ``date_from`` bounds
    the range (a P&L-style window); omit it for cumulative-to-date balances (balance-sheet-style).
    Thin re-export of ``service.statements._account_balances`` — one aggregate, one index."""
    from app.modules.finance.service.statements import _account_balances

    return await _account_balances(
        session, tenant_id, date_to=date_to, date_from=date_from
    )


async def net_income(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    date_to: date,
    date_from: date | None = None,
) -> Decimal:
    """Net income (revenue - expense, credit-positive so a profit is positive) over the range
    (D-021). Derived from ``account_balances`` + account types so reporting reads it as a projection
    of the journal — the same figure the balance sheet folds into retained earnings. Cumulative to
    ``date_to`` when ``date_from`` is omitted."""
    from app.modules.finance.service.statements import net_income_signed
    from app.modules.finance.service.statements.base import load_account_meta

    balances = await account_balances(session, tenant_id, date_to=date_to, date_from=date_from)
    meta = await load_account_meta(session, tenant_id)
    return net_income_signed(balances, meta)
