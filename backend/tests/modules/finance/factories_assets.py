"""Asset-accounting test data builders (PLAN 4.10), a sibling of factories.py — that file is
at the STRUCTURE §8.4 cap, so the 4.10 setup splits out exactly as the app-side schemas/router
siblings did. Builders go through the REAL service layer under the tenant context (D-025)."""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import tenant_context
from app.modules.finance import service
from app.modules.finance.assets_schemas import AssetCreate
from app.modules.finance.constants import (
    ASSET_ACQUISITION_CLEARING,
    AccountType,
    DepreciationMethod,
)
from app.modules.finance.models import Asset, DepreciationRun, FiscalPeriod
from app.modules.finance.schemas import AccountCreate
from tests.modules.finance.factories import seed_fiscal_year, seed_small_coa


@dataclass(frozen=True)
class AssetSetup:
    """A tenant ready for asset accounting (PLAN 4.10): the small COA + a fixed-asset BS
    account (1500), an accumulated-depreciation contra account (1510), a depreciation-expense
    account (5100), an acquisition-clearing liability (2900) wired as the
    ``asset_acquisition_clearing`` posting default, and the open 2026 fiscal year. Plain ids
    so a rollback (expiring loaded objects) cannot break a follow-up payload."""

    tenant_id: uuid.UUID
    accounts: dict[str, uuid.UUID]
    fiscal_year_id: uuid.UUID


_ASSET_ACCOUNTS: tuple[tuple[str, str, AccountType], ...] = (
    ("1500", "Fixed Assets", AccountType.ASSET),
    ("1510", "Accumulated Depreciation", AccountType.ASSET),
    ("5100", "Depreciation Expense", AccountType.EXPENSE),
    ("2900", "Asset Acquisition Clearing", AccountType.LIABILITY),
)


async def build_asset_setup(session: AsyncSession, tenant_id: uuid.UUID) -> AssetSetup:
    """COA + the three asset accounts + the acquisition-clearing posting default + open 2026
    year (PLAN 4.10)."""
    accounts = await seed_small_coa(session, tenant_id)
    by_code = {a.code: a.id for a in accounts}
    with tenant_context(tenant_id):
        for code, name, atype in _ASSET_ACCOUNTS:
            account = await service.create_account(
                session, tenant_id, AccountCreate(code=code, name=name, account_type=atype)
            )
            by_code[code] = account.id
        await service.set_posting_default(
            session, tenant_id, ASSET_ACQUISITION_CLEARING, by_code["2900"]
        )
        await session.commit()
    year = await seed_fiscal_year(session, tenant_id)
    return AssetSetup(tenant_id=tenant_id, accounts=by_code, fiscal_year_id=year.id)


async def fiscal_periods(session: AsyncSession, setup: AssetSetup) -> list[FiscalPeriod]:
    """The 2026 fiscal periods, earliest first."""
    with tenant_context(setup.tenant_id):
        page = await service.list_fiscal_periods(session, setup.tenant_id, limit=12)
    return list(page.items)


async def create_active_asset(
    session: AsyncSession,
    setup: AssetSetup,
    *,
    name: str,
    cost: str,
    life: int,
    method: DepreciationMethod = DepreciationMethod.STRAIGHT_LINE,
    rate: str | None = None,
    salvage: str = "0",
    cost_center_id: uuid.UUID | None = None,
) -> Asset:
    """Create + activate (capitalize=False) an asset through the real services (D-025)."""
    with tenant_context(setup.tenant_id):
        asset = await service.create_asset(
            session,
            setup.tenant_id,
            AssetCreate(
                name=name,
                acquisition_date=date(2026, 1, 10),
                acquisition_cost=Decimal(cost),
                salvage_value=Decimal(salvage),
                useful_life_months=life,
                depreciation_method=method,
                declining_rate_percent=Decimal(rate) if rate is not None else None,
                asset_account_id=setup.accounts["1500"],
                accumulated_depreciation_account_id=setup.accounts["1510"],
                depreciation_expense_account_id=setup.accounts["5100"],
                cost_center_id=cost_center_id,
                currency_code="USD",
            ),
        )
        await service.activate_asset(session, setup.tenant_id, asset.id, capitalize=False)
        await session.commit()
    return asset


async def run_period_depreciation(
    session: AsyncSession, setup: AssetSetup, period: FiscalPeriod
) -> DepreciationRun:
    """Run depreciation for one period (run_date = the period end) and commit."""
    with tenant_context(setup.tenant_id):
        run = await service.run_depreciation(
            session, setup.tenant_id, period.id, period.end_date
        )
        await session.commit()
    return run
