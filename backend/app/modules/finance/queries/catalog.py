"""Master-data existence + FX + tax reads (part of finance's cross-module read contract, §5).

Split out of ``queries/__init__.py`` at the 400-line cap (STRUCTURE §8.4) and re-exported from the
package ``__init__`` so every ``from app.modules.finance.queries import X`` import keeps working
from one surface. These functions let a module ABOVE finance validate a referenced account /
currency /
tax code, read an exchange rate, learn the functional currency, or tax a line — all without
importing finance/service or finance models (finance is the bottom of the dependency order).

Every function takes an explicit ``tenant_id`` and runs under the caller's tenant context, so the
D-007 filter applies on top of the explicit predicate — ordinary tenant-scoped reads, not a bypass.
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.finance.constants import RateKind, TaxDirection
from app.modules.finance.models import Account, Currency, TaxCode
from app.modules.finance.service import fx as _fx
from app.modules.finance.service import tax as _tax
from app.modules.finance.service.tax import TaxCalculation


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


async def currency_exists(
    session: AsyncSession, tenant_id: uuid.UUID, code: str
) -> bool:
    """Whether a currency with ISO ``code`` exists in the tenant's currency catalog.

    Sanctioned cross-module read (STRUCTURE §5 / D-029): the procurement vendor master defaults a
    ``default_currency_code`` onto each vendor and validates it exists in finance through THIS
    contract before storing it — never a cross-module FK (finance is below procurement in the
    dependency order). Tenant-scoped, so the D-007 filter applies on top of the explicit predicate
    (an ordinary tenant read, not a bypass). Mirrors ``account_exists`` for the currency table."""
    stmt = select(Currency.id).where(
        Currency.tenant_id == tenant_id, Currency.code == code
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
