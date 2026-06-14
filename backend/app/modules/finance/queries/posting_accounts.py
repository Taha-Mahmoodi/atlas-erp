"""Posting-default ACCOUNT resolvers (part of finance's cross-module read contract, STRUCTURE §5).

Split out of ``queries/__init__.py`` at the 400-line cap (STRUCTURE §8.4). Each function resolves
one per-tenant posting-default purpose to its mapped GL account id so a module ABOVE finance can
route a flow's leg to a CONFIGURED account without importing finance/service or finance models (the
data-driven account wiring, D-019). All RAISE 422 (``finance.posting_default_unmapped``) when the
purpose is unmapped — a flow that must post to a configured account fails loud, not guessing.
Tenant-scoped, so the D-007 filter applies on top of the explicit predicate (ordinary reads, not a
bypass).
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.finance.constants import (
    AP_CONTROL,
    AR_CONTROL,
    GR_IR_CLEARING,
    PAYROLL_TAX_PAYABLE,
    PRODUCTION_VARIANCE,
    PURCHASE_PRICE_VARIANCE,
    SALARY_EXPENSE,
    SALES_REVENUE,
    WAGES_PAYABLE,
    WIP_CLEARING,
)
from app.modules.finance.service import posting_defaults as _posting_defaults


async def gr_ir_clearing_account(
    session: AsyncSession, tenant_id: uuid.UUID
) -> uuid.UUID:
    """The tenant's GR/IR clearing account id (PLAN 6.3, D-041): a goods receipt credits it (the
    costing valuation-offset override), the matched vendor bill (6.4) debits it. Resolves the
    ``gr_ir_clearing`` posting default; RAISES 422 (``finance.posting_default_unmapped``) when
    unmapped. Exposed for procurement (STRUCTURE §5; no finance/service import)."""
    return await _posting_defaults.get_posting_default(session, tenant_id, GR_IR_CLEARING)


async def purchase_price_variance_account(
    session: AsyncSession, tenant_id: uuid.UUID
) -> uuid.UUID:
    """The tenant's PPV account id (PLAN 6.4, D-042): an in-tolerance price difference on a matched
    bill posts here so GR/IR clears at exactly the PO cost. Resolves the ``purchase_price_variance``
    posting default; RAISES 422 when unmapped. Exposed for procurement (STRUCTURE §5)."""
    return await _posting_defaults.get_posting_default(
        session, tenant_id, PURCHASE_PRICE_VARIANCE
    )


async def ap_control_account(session: AsyncSession, tenant_id: uuid.UUID) -> uuid.UUID:
    """The tenant's AP control account id (PLAN 6.4, D-042): the match-triggered vendor bill CREDITS
    it at the invoiced total (partner-keyed by the opaque vendor id, D-029). Resolves the
    ``ap_control`` posting default; RAISES 422 when unmapped. Exposed for procurement (STRUCTURE
    §5)."""
    return await _posting_defaults.get_posting_default(session, tenant_id, AP_CONTROL)


async def ar_control_account(session: AsyncSession, tenant_id: uuid.UUID) -> uuid.UUID:
    """The tenant's AR control account id (PLAN 7.4, D-046): the billing-triggered customer invoice
    DEBITS it at the invoiced total (partner-keyed by the opaque customer id, D-029), a return's
    credit note CREDITS it. Resolves the ``ar_control`` posting default; RAISES 422 when unmapped.
    Exposed for SALES (STRUCTURE §5; the AP_CONTROL mirror)."""
    return await _posting_defaults.get_posting_default(session, tenant_id, AR_CONTROL)


async def sales_revenue_account(session: AsyncSession, tenant_id: uuid.UUID) -> uuid.UUID:
    """The tenant's sales-revenue account id (PLAN 7.4, D-046): each billing-triggered invoice line
    CREDITS it at its net, a return's credit note DEBITS it. Resolves the ``sales_revenue`` posting
    default; RAISES 422 when unmapped. Exposed for SALES (STRUCTURE §5; v1 single revenue
    account)."""
    return await _posting_defaults.get_posting_default(session, tenant_id, SALES_REVENUE)


async def wip_clearing_account(session: AsyncSession, tenant_id: uuid.UUID) -> uuid.UUID:
    """The tenant's WIP clearing account id (PLAN 8.2, D-048): a component ISSUE debits it (Dr WIP /
    Cr Inventory, the valuation-offset OVERRIDE), the finished RECEIPT credits it, WIP nets to ZERO.
    Resolves the ``wip_clearing`` posting default; RAISES 422 when unmapped (for MANUFACTURING,
    STRUCTURE §5; the GR/IR mirror)."""
    return await _posting_defaults.get_posting_default(session, tenant_id, WIP_CLEARING)


async def production_variance_account(
    session: AsyncSession, tenant_id: uuid.UUID
) -> uuid.UUID:
    """The tenant's production-variance account id (PLAN 8.2, D-048): a finished order's residual
    WIP (over/under-absorption) flushes here so WIP nets to ZERO. Resolves the
    ``production_variance`` posting default; RAISES 422 when unmapped. Exposed for manufacturing
    (STRUCTURE §5; PPV mirror)."""
    return await _posting_defaults.get_posting_default(session, tenant_id, PRODUCTION_VARIANCE)


async def salary_expense_account(session: AsyncSession, tenant_id: uuid.UUID) -> uuid.UUID:
    """The tenant's salary-expense account id (PLAN 10.4, D-055): the consolidated payroll journal
    DEBITS it at total gross, carrying the per-line cost-centre dimension. Resolves the
    ``salary_expense`` posting default; RAISES 422 (``finance.posting_default_unmapped``) when
    unmapped. Exposed for HR (STRUCTURE §5; no finance/service import) — HR carries the purpose key
    on the PayrollPosted event and finance's handler resolves the account here."""
    return await _posting_defaults.get_posting_default(session, tenant_id, SALARY_EXPENSE)


async def wages_payable_account(session: AsyncSession, tenant_id: uuid.UUID) -> uuid.UUID:
    """The tenant's wages-payable (net-pay clearing) account id (PLAN 10.4, D-055): the payroll
    journal CREDITS it at total net (net pay owed to employees). Resolves the ``wages_payable``
    posting default; RAISES 422 when unmapped. Exposed for HR (STRUCTURE §5)."""
    return await _posting_defaults.get_posting_default(session, tenant_id, WAGES_PAYABLE)


async def payroll_tax_payable_account(
    session: AsyncSession, tenant_id: uuid.UUID
) -> uuid.UUID:
    """The tenant's payroll-tax-payable account id (PLAN 10.4, D-055): the payroll journal CREDITS
    it at total withheld tax (the flat-rate withholding owed to the authority). Resolves the
    ``payroll_tax_payable`` posting default; RAISES 422 when unmapped. Exposed for HR (STRUCTURE
    §5)."""
    return await _posting_defaults.get_posting_default(session, tenant_id, PAYROLL_TAX_PAYABLE)
