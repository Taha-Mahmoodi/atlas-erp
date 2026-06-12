"""The depreciation engine (PLAN 4.10): the two formulas' exactness guarantees, the
set-based run (one grouped journal, bulk entries, constant query count), idempotency via the
UNIQUE(asset, period) backbone, FULLY_DEPRECIATED flips, closed-period rejection, and the
register-as-projection."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationFailedError
from app.core.tenancy import tenant_context
from app.modules.finance import service
from app.modules.finance.constants import (
    AssetStatus,
    DepreciationMethod,
    DocumentType,
)
from app.modules.finance.controlling_schemas import CostCenterCreate
from app.modules.finance.models import (
    Asset,
    DepreciationEntry,
    JournalEntry,
    JournalLine,
)
from app.modules.finance.service.depreciation import compute_depreciation
from tests.modules.finance.factories_assets import (
    AssetSetup,
    create_active_asset,
    fiscal_periods,
    run_period_depreciation,
)

# --- compute_depreciation: the pure formulas --------------------------------------


def _asset(
    method: DepreciationMethod,
    cost: str,
    salvage: str,
    life: int,
    rate: str | None = None,
) -> Asset:
    """An unsaved Asset carrying just the fields the formula reads."""
    return Asset(
        currency_code="USD",
        acquisition_cost=Decimal(cost),
        salvage_value=Decimal(salvage),
        useful_life_months=life,
        depreciation_method=method.value,
        declining_rate_percent=Decimal(rate) if rate is not None else None,
    )


def _schedule(asset: Asset, periods: int) -> list[Decimal]:
    amounts: list[Decimal] = []
    accumulated = Decimal(0)
    for index in range(1, periods + 1):
        amount = compute_depreciation(asset, index, accumulated)
        amounts.append(amount)
        accumulated += amount
    return amounts


def test_straight_line_even_schedule_is_constant() -> None:
    """12000 / 0 salvage / 12 months -> exactly 1000 every period."""
    asset = _asset(DepreciationMethod.STRAIGHT_LINE, "12000", "0", 12)
    amounts = _schedule(asset, 12)
    assert amounts == [Decimal("1000.00")] * 12


def test_straight_line_awkward_total_is_exact() -> None:
    """10000 / 12 months does not divide evenly; the cumulative formulation alternates
    833.33/833.34 and the FINAL period absorbs the residual so the total == 10000 EXACTLY."""
    asset = _asset(DepreciationMethod.STRAIGHT_LINE, "10000", "0", 12)
    amounts = _schedule(asset, 12)
    expected = [
        Decimal("833.33"),
        Decimal("833.34"),
        Decimal("833.33"),
        Decimal("833.33"),
        Decimal("833.34"),
        Decimal("833.33"),
        Decimal("833.33"),
        Decimal("833.34"),
        Decimal("833.33"),
        Decimal("833.33"),
        Decimal("833.34"),
        Decimal("833.33"),
    ]
    assert amounts == expected
    assert sum(amounts) == Decimal("10000.00")
    # The 13th period charges nothing — the schedule is complete.
    assert compute_depreciation(asset, 13, Decimal("10000.00")) == Decimal(0)


def test_straight_line_respects_salvage_in_total() -> None:
    """Cost 1000 / salvage 100 / 3 months -> 300 + 300 + 300 == cost - salvage exactly."""
    asset = _asset(DepreciationMethod.STRAIGHT_LINE, "1000", "100", 3)
    amounts = _schedule(asset, 3)
    assert sum(amounts) == Decimal("900.00")


def test_declining_balance_monthly_amounts() -> None:
    """20%/yr on 12000: month 1 = 12000 x 0.2 / 12 = 200.00; the base declines monthly."""
    asset = _asset(DepreciationMethod.DECLINING_BALANCE, "12000", "0", 60, rate="20")
    amounts = _schedule(asset, 3)
    assert amounts[0] == Decimal("200.00")
    assert amounts[1] == Decimal("196.67")  # 11800 x 0.2 / 12 = 196.666..., HALF_UP
    assert amounts[2] == Decimal("193.39")  # 11603.33 x 0.2 / 12 = 193.388...
    assert amounts[0] > amounts[1] > amounts[2]


def test_declining_balance_floors_exactly_at_salvage() -> None:
    """Cost 1000 / salvage 900 / 50%/yr: the naive month-3 charge (38.27) would cross the
    salvage floor, so the period takes the remainder and NBV lands EXACTLY on salvage."""
    asset = _asset(DepreciationMethod.DECLINING_BALANCE, "1000", "900", 24, rate="50")
    amounts = _schedule(asset, 4)
    assert amounts[0] == Decimal("41.67")
    assert amounts[1] == Decimal("39.93")
    assert amounts[2] == Decimal("18.40")  # remainder to salvage, not the naive 38.27
    assert amounts[3] == Decimal(0)  # fully depreciated to the floor
    assert sum(amounts) == Decimal("100.00")  # == cost - salvage exactly


def test_declining_balance_exhausts_to_salvage_at_end_of_life() -> None:
    """When the schedule runs out (n >= life) the final period takes NBV - salvage so the
    asset lands exactly on salvage instead of asymptotically approaching it."""
    asset = _asset(DepreciationMethod.DECLINING_BALANCE, "1200", "0", 3, rate="20")
    amounts = _schedule(asset, 3)
    assert amounts[0] == Decimal("20.00")  # 1200 x 0.2 / 12
    assert amounts[1] == Decimal("19.67")
    assert amounts[2] == Decimal("1160.33")  # the exhaust remainder
    assert sum(amounts) == Decimal("1200.00")


# --- run_depreciation: the posting run ---------------------------------------------


async def test_run_posts_one_grouped_journal_entry(
    db_session: AsyncSession, asset_setup: AssetSetup
) -> None:
    """3 assets -> ONE balanced DEPRECIATION entry with lines GROUPED per (expense account,
    cost centre) and per accumulated account — never per-asset lines — plus the DEP number
    and the run->entry docflow bookkeeping."""
    with tenant_context(asset_setup.tenant_id):
        centre = await service.create_cost_center(
            db_session, asset_setup.tenant_id, CostCenterCreate(code="CC1", name="Assembly")
        )
        await db_session.commit()
    await create_active_asset(db_session, asset_setup, name="A", cost="12000", life=12)
    await create_active_asset(db_session, asset_setup, name="B", cost="6000", life=12)
    await create_active_asset(
        db_session, asset_setup, name="C", cost="2400", life=12, cost_center_id=centre.id
    )
    period = (await fiscal_periods(db_session, asset_setup))[0]

    run = await run_period_depreciation(db_session, asset_setup, period)
    assert run.run_number == "DEP-2026-00001"
    assert run.asset_count == 3
    assert Decimal(str(run.total_amount)) == Decimal("1700.00")  # 1000 + 500 + 200

    with tenant_context(asset_setup.tenant_id):
        entry = await service.get_entry(
            db_session, asset_setup.tenant_id, run.journal_entry_id
        )
        assert entry.document_type == DocumentType.DEPRECIATION.value
        lines = list(
            (
                await db_session.execute(
                    select(JournalLine).where(JournalLine.journal_entry_id == entry.id)
                )
            )
            .scalars()
            .all()
        )
    # Grouped: Dr (5100, no centre) 1500, Dr (5100, CC1) 200, Cr 1510 1700 — three lines.
    assert len(lines) == 3
    debits = {
        (line.account_id, line.cost_center_id): Decimal(str(line.transaction_debit_amount))
        for line in lines
        if Decimal(str(line.transaction_debit_amount)) > 0
    }
    credits = {
        line.account_id: Decimal(str(line.transaction_credit_amount))
        for line in lines
        if Decimal(str(line.transaction_credit_amount)) > 0
    }
    assert debits == {
        (asset_setup.accounts["5100"], None): Decimal("1500.00"),
        (asset_setup.accounts["5100"], centre.id): Decimal("200.00"),
    }
    assert credits == {asset_setup.accounts["1510"]: Decimal("1700.00")}
    assert sum(debits.values()) == sum(credits.values())


async def test_run_is_idempotent_per_period_and_next_period_works(
    db_session: AsyncSession, asset_setup: AssetSetup
) -> None:
    """A second run for the same period depreciates NOTHING (the UNIQUE(asset, period)
    backbone leaves no eligible assets) and returns the SAME run; the next period runs."""
    await create_active_asset(db_session, asset_setup, name="A", cost="12000", life=12)
    periods = await fiscal_periods(db_session, asset_setup)

    first = await run_period_depreciation(db_session, asset_setup, periods[0])
    replay = await run_period_depreciation(db_session, asset_setup, periods[0])
    assert replay.id == first.id

    with tenant_context(asset_setup.tenant_id):
        entry_count = (
            await db_session.execute(
                select(func.count(DepreciationEntry.id)).where(
                    DepreciationEntry.tenant_id == asset_setup.tenant_id
                )
            )
        ).scalar_one()
        journal_count = (
            await db_session.execute(
                select(func.count(JournalEntry.id)).where(
                    JournalEntry.tenant_id == asset_setup.tenant_id,
                    JournalEntry.document_type == DocumentType.DEPRECIATION.value,
                )
            )
        ).scalar_one()
    assert entry_count == 1  # one asset, one period — the replay added nothing
    assert journal_count == 1

    second = await run_period_depreciation(db_session, asset_setup, periods[1])
    assert second.id != first.id
    assert second.run_number == "DEP-2026-00002"


async def test_run_entries_carry_running_totals_and_bulk_insert_is_constant_queries(
    db_session: AsyncSession, asset_setup: AssetSetup, query_counter
) -> None:
    """Entries freeze accumulated_after/nbv_after per asset, and the run's SQL statement
    count is CONSTANT in the asset count (set-based selection + ONE grouped prior aggregate +
    ONE bulk insert — a per-asset loop would blow this budget at 8 assets)."""
    for index in range(8):
        await create_active_asset(
            db_session, asset_setup, name=f"A{index}", cost="1200", life=12
        )
    period = (await fiscal_periods(db_session, asset_setup))[0]

    with tenant_context(asset_setup.tenant_id):
        with query_counter() as qc:
            run = await service.run_depreciation(
                db_session, asset_setup.tenant_id, period.id, period.end_date
            )
        await db_session.commit()
    # Measured 33 on the warm path — entirely fixed-cost bookkeeping (journal, numbering,
    # docflow, audit). A per-asset loop would add >= 2 statements per asset and blow this.
    assert qc.count <= 35, f"run used {qc.count} statements:\n" + "\n".join(qc.statements)

    with tenant_context(asset_setup.tenant_id):
        entries = list(
            (
                await db_session.execute(
                    select(DepreciationEntry).where(DepreciationEntry.run_id == run.id)
                )
            )
            .scalars()
            .all()
        )
    assert len(entries) == 8
    for entry in entries:
        assert Decimal(str(entry.amount)) == Decimal("100.00")
        assert Decimal(str(entry.accumulated_after)) == Decimal("100.00")
        assert Decimal(str(entry.nbv_after)) == Decimal("1100.00")


async def test_assets_flip_fully_depreciated_and_drop_out(
    db_session: AsyncSession, asset_setup: AssetSetup
) -> None:
    """An asset reaching cost - salvage flips FULLY_DEPRECIATED; once every asset is done a
    later period has nothing to depreciate (422 — no run ever existed for it)."""
    asset = await create_active_asset(db_session, asset_setup, name="Short", cost="1200", life=2)
    periods = await fiscal_periods(db_session, asset_setup)

    await run_period_depreciation(db_session, asset_setup, periods[0])
    with tenant_context(asset_setup.tenant_id):
        mid = await service.get_asset(db_session, asset_setup.tenant_id, asset.id)
        assert mid.status == AssetStatus.ACTIVE.value
    await run_period_depreciation(db_session, asset_setup, periods[1])
    with tenant_context(asset_setup.tenant_id):
        done = await service.get_asset(db_session, asset_setup.tenant_id, asset.id)
        assert done.status == AssetStatus.FULLY_DEPRECIATED.value

        with pytest.raises(ValidationFailedError) as err:
            await service.run_depreciation(
                db_session, asset_setup.tenant_id, periods[2].id, periods[2].end_date
            )
    assert err.value.code == "finance.depreciation_nothing_to_depreciate"


async def test_run_into_closed_period_rejected(
    db_session: AsyncSession, asset_setup: AssetSetup
) -> None:
    """Service check first (422 finance.period_closed); the journal's period trigger is the
    bypass-proof DB backstop (proven in test_journal_db_guards on both engines)."""
    await create_active_asset(db_session, asset_setup, name="A", cost="1200", life=12)
    period = (await fiscal_periods(db_session, asset_setup))[0]
    with tenant_context(asset_setup.tenant_id):
        await service.close_period(db_session, asset_setup.tenant_id, period.id)
        await db_session.commit()
        with pytest.raises(ValidationFailedError) as err:
            await service.run_depreciation(
                db_session, asset_setup.tenant_id, period.id, period.end_date
            )
    assert err.value.code == "finance.period_closed"


async def test_run_date_must_fall_inside_the_period(
    db_session: AsyncSession, asset_setup: AssetSetup
) -> None:
    await create_active_asset(db_session, asset_setup, name="A", cost="1200", life=12)
    period = (await fiscal_periods(db_session, asset_setup))[0]
    with tenant_context(asset_setup.tenant_id), pytest.raises(ValidationFailedError) as err:
        await service.run_depreciation(
            db_session, asset_setup.tenant_id, period.id, date(2026, 2, 15)
        )
    assert err.value.code == "finance.depreciation_run_date_outside_period"
