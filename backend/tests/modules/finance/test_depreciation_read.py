"""The asset-register projection (PLAN 4.10, service/depreciation_read.py): cost /
accumulated-to-date / NBV recomputed from the depreciation entries per as-of date — no stored
totals anywhere (D-021 spirit)."""

from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import tenant_context
from app.modules.finance import service
from app.modules.finance.assets_schemas import AssetCreate
from app.modules.finance.constants import DepreciationMethod
from tests.modules.finance.factories_assets import (
    AssetSetup,
    create_active_asset,
    fiscal_periods,
    run_period_depreciation,
)


async def test_register_recomputes_accumulated_and_nbv_per_as_of(
    db_session: AsyncSession, asset_setup: AssetSetup
) -> None:
    """The register is a projection over the entries: the same asset shows period-1 totals
    as of Jan 31 and period-2 totals as of Feb 28 — recomputed from SUM, no stored NBV; a
    DRAFT asset never appears; an as_of before acquisition shows nothing."""
    asset = await create_active_asset(
        db_session, asset_setup, name="A", cost="12000", life=12
    )
    with tenant_context(asset_setup.tenant_id):
        await service.create_asset(
            db_session,
            asset_setup.tenant_id,
            AssetCreate(
                name="Draft only",
                acquisition_date=date(2026, 1, 5),
                acquisition_cost=Decimal("500"),
                useful_life_months=5,
                depreciation_method=DepreciationMethod.STRAIGHT_LINE,
                asset_account_id=asset_setup.accounts["1500"],
                accumulated_depreciation_account_id=asset_setup.accounts["1510"],
                depreciation_expense_account_id=asset_setup.accounts["5100"],
                currency_code="USD",
            ),
        )
        await db_session.commit()
    periods = await fiscal_periods(db_session, asset_setup)
    await run_period_depreciation(db_session, asset_setup, periods[0])
    await run_period_depreciation(db_session, asset_setup, periods[1])

    with tenant_context(asset_setup.tenant_id):
        as_of_january = await service.asset_register(
            db_session, asset_setup.tenant_id, date(2026, 1, 31)
        )
        as_of_february = await service.asset_register(
            db_session, asset_setup.tenant_id, date(2026, 2, 28)
        )
        before_acquisition = await service.asset_register(
            db_session, asset_setup.tenant_id, date(2025, 12, 31)
        )

    assert [line.asset.id for line in as_of_january] == [asset.id]
    january = as_of_january[0]
    assert Decimal(str(january.asset.acquisition_cost)) == Decimal("12000.00")
    assert january.accumulated_depreciation == Decimal("1000.00")
    assert january.net_book_value == Decimal("11000.00")

    february = as_of_february[0]
    assert february.accumulated_depreciation == Decimal("2000.00")
    assert february.net_book_value == Decimal("10000.00")

    assert before_acquisition == []
