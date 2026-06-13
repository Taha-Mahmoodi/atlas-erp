"""Finance's cross-module read interface (STRUCTURE §5).

Finance is the bottom of the dependency order: every other module (inventory, sales, ...)
may import THIS file to read finance state synchronously, and finance imports no other
module's queries. Keep this surface thin and stable — it is a contract. The journal posting
flow (4.2) calls ``find_period_for_date`` to resolve an entry's period from its posting_date;
inventory/sales call ``get_period_status`` to refuse stock/sales documents dated into a closed
period before they reach the GL.

Every function takes an explicit ``tenant_id`` and runs under the caller's tenant context, so
the D-007 filter applies on top of the explicit predicate — these are ordinary tenant-scoped
ORM reads, not a bypass.
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.finance.constants import (
    BillStatus,
    InvoiceStatus,
    PeriodStatus,
    RateKind,
    TaxDirection,
)
from app.modules.finance.models import (
    Account,
    CostCenter,
    CustomerInvoice,
    FiscalPeriod,
    JournalLine,
    ProfitCenter,
    TaxCode,
    VendorBill,
)
from app.modules.finance.service import fx as _fx
from app.modules.finance.service import tax as _tax
from app.modules.finance.service.tax import TaxCalculation


async def find_period_for_date(
    session: AsyncSession, tenant_id: uuid.UUID, on_date: date
) -> FiscalPeriod | None:
    """The fiscal period whose [start_date, end_date] (inclusive) covers ``on_date``, or
    None if no period does. Periods within a year are contiguous and non-overlapping (the
    service enforces that on generation), so at most one matches. This is the date->period
    lookup the journal uses on every posting (4.2)."""
    stmt = select(FiscalPeriod).where(
        FiscalPeriod.tenant_id == tenant_id,
        FiscalPeriod.start_date <= on_date,
        FiscalPeriod.end_date >= on_date,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_period_status(
    session: AsyncSession, tenant_id: uuid.UUID, on_date: date
) -> PeriodStatus | None:
    """The OPEN/CLOSED status of the period covering ``on_date``, or None when no period
    covers it. Callers posting financial or stock documents check this up front: None or
    CLOSED means the date is not in an open period and the document must be rejected
    (the DB-level period trigger on the journal in 4.2 is the bypass-proof backstop)."""
    period = await find_period_for_date(session, tenant_id, on_date)
    if period is None:
        return None
    return PeriodStatus(period.status)


async def account_exists(
    session: AsyncSession, tenant_id: uuid.UUID, code: str
) -> bool:
    """Whether an account with ``code`` exists in the tenant's chart of accounts. Lets
    another module validate a referenced account code without importing finance models."""
    stmt = select(Account.id).where(
        Account.tenant_id == tenant_id, Account.code == code
    )
    return (await session.execute(stmt)).first() is not None


async def account_exists_by_id(
    session: AsyncSession, tenant_id: uuid.UUID, account_id: uuid.UUID
) -> bool:
    """Whether an account with ``account_id`` exists in the tenant's chart of accounts.

    The by-id companion to ``account_exists`` (sanctioned cross-module read, STRUCTURE §5 / D-029):
    inventory item categories reference finance GL accounts by OPAQUE uuid — never a cross-module
    FK — so the inventory service validates each referenced account id through this contract before
    storing it on a category. Tenant-scoped, so the D-007 filter applies on top of the explicit
    predicate (an ordinary tenant read, not a bypass)."""
    stmt = select(Account.id).where(
        Account.tenant_id == tenant_id, Account.id == account_id
    )
    return (await session.execute(stmt)).first() is not None


async def get_rate(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    from_code: str,
    to_code: str,
    on_date: date,
    rate_type: RateKind = RateKind.SPOT,
) -> Decimal:
    """The exchange rate to convert ``from_code`` into ``to_code`` on ``on_date`` (D-019). Exposed
    here so other modules price in functional terms (AP/AR/inventory translate at this rate); a
    missing rate raises (postings never guess). Same contract as service/fx.get_rate."""
    return await _fx.get_rate(session, tenant_id, from_code, to_code, on_date, rate_type)


async def functional_currency(session: AsyncSession, tenant_id: uuid.UUID) -> str:
    """The tenant's functional (reporting) currency code (D-019). Exposed so other modules know the
    currency every functional amount is denominated in. Raises if none is configured."""
    return await _fx.functional_currency(session, tenant_id)


async def functional_currency_or_none(
    session: AsyncSession, tenant_id: uuid.UUID
) -> str | None:
    """The tenant's functional currency code, or None when unconfigured (the v1 single-currency
    default — D-019). Exposed so other modules (inventory costing, 5.3) can pick the currency the
    valuation journal posts in without raising when no currency is set up."""
    return await _fx.functional_currency_or_none(session, tenant_id)


async def get_tax_code(
    session: AsyncSession, tenant_id: uuid.UUID, code: str
) -> TaxCode | None:
    """The tax code with ``code`` in the tenant's catalog, or None (PLAN 4.4). Sales/Procurement
    resolve a line's tax code by its short key (e.g. ``'VAT20'``) through this contract rather than
    importing finance models — finance is the bottom of the dependency order (STRUCTURE §5)."""
    stmt = select(TaxCode).where(TaxCode.tenant_id == tenant_id, TaxCode.code == code)
    return (await session.execute(stmt)).scalar_one_or_none()


def calculate_line_tax(
    base_amount: Decimal,
    tax_code: TaxCode,
    *,
    direction: TaxDirection,
    currency_code: str = "USD",
) -> TaxCalculation:
    """Tax one line consistently for any module (PLAN 4.4). A thin, pure re-export of
    ``service.tax.calculate_line_tax`` so Sales/Procurement compute net/tax/gross + the tax account
    exactly as finance does — one tax engine, no duplicated math. ``base_amount`` is the gross when
    the code is inclusive else the net; all amounts quantize to ``currency_code``'s minor unit."""
    return _tax.calculate_line_tax(
        base_amount, tax_code, direction=direction, currency_code=currency_code
    )


async def get_open_vendor_bills(
    session: AsyncSession, tenant_id: uuid.UUID, partner_id: uuid.UUID
) -> list[VendorBill]:
    """A partner's POSTED vendor bills that still have an open balance (PLAN 4.5, D-029). Exposed
    so procurement (later) can read a vendor's open AP without importing finance models — finance
    is the bottom of the dependency order (STRUCTURE §5). Keyed by the opaque ``partner_id``; never
    an FK to a vendor master. Ordered by due date so the oldest-due bills surface first."""
    stmt = (
        select(VendorBill)
        .where(
            VendorBill.tenant_id == tenant_id,
            VendorBill.partner_id == partner_id,
            VendorBill.status.in_(
                (BillStatus.POSTED.value, BillStatus.PARTIALLY_PAID.value)
            ),
            VendorBill.open_amount > 0,
        )
        .order_by(VendorBill.due_date)
    )
    return list((await session.execute(stmt)).scalars().all())


def _open_customer_invoices_stmt(tenant_id: uuid.UUID, partner_id: uuid.UUID):
    """The SELECT for a partner's open customer invoices (PLAN 4.6, D-029): POSTED/PARTIALLY_PAID
    with a positive open balance, oldest-due first. Shared by the list + the balance sum so they
    can never disagree."""
    return (
        select(CustomerInvoice)
        .where(
            CustomerInvoice.tenant_id == tenant_id,
            CustomerInvoice.partner_id == partner_id,
            CustomerInvoice.status.in_(
                (InvoiceStatus.POSTED.value, InvoiceStatus.PARTIALLY_PAID.value)
            ),
            CustomerInvoice.open_amount > 0,
        )
        .order_by(CustomerInvoice.due_date)
    )


async def get_open_customer_invoices(
    session: AsyncSession, tenant_id: uuid.UUID, partner_id: uuid.UUID
) -> list[CustomerInvoice]:
    """A partner's POSTED customer invoices that still have an open balance (PLAN 4.6, D-029).
    Exposed so sales (later) can read a customer's open AR without importing finance models —
    finance is the bottom of the dependency order (STRUCTURE §5). Keyed by the opaque
    ``partner_id``; never an FK to a customer master. Ordered oldest-due first."""
    stmt = _open_customer_invoices_stmt(tenant_id, partner_id)
    return list((await session.execute(stmt)).scalars().all())


async def customer_open_balance(
    session: AsyncSession, tenant_id: uuid.UUID, partner_id: uuid.UUID
) -> Decimal:
    """The total still-owed AR for a partner across all open invoices (PLAN 4.6, D-029): the sum of
    their ``open_amount`` in transaction currency. Exposed so Sales' credit-limit block can ask
    finance "how much does this customer currently owe?" without importing finance models — the
    bottom-dependency contract (STRUCTURE §5). Sums in Python over the (typically small) open set so
    the exact-decimal MoneyType round-trips identically on both engines (D-015). Returns 0 for a
    partner with no open invoices."""
    invoices = await get_open_customer_invoices(session, tenant_id, partner_id)
    return sum((Decimal(str(inv.open_amount)) for inv in invoices), Decimal(0))


# --- Controlling: dimension validation + cost-centre balance (PLAN 4.7) -------


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


# --- Statements: the base aggregate, exposed for reporting reuse (PLAN 4.8, D-021) -----------


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

    balances = await account_balances(
        session, tenant_id, date_to=date_to, date_from=date_from
    )
    meta = await load_account_meta(session, tenant_id)
    return net_income_signed(balances, meta)
