"""Reporting dashboard service behaviour (PLAN 13.1, D-058), SQLite.

Proves ``dashboard_kpis`` computes each KPI off the right source query (cash from a posted journal,
AR/AP aging buckets, inventory value, open sales/purchase orders, WIP, OTD) AND that the role-based
gate omits a KPI the caller lacks the source permission for. The over-the-wire RBAC + bundle is in
test_dashboard_api.py.
"""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import tenant_context
from app.modules.finance.constants import (
    FINANCE_AP_READ,
    FINANCE_AR_READ,
    FINANCE_STATEMENTS_READ,
)
from app.modules.inventory.constants import INVENTORY_VALUATION_READ
from app.modules.procurement.constants import PROCUREMENT_PO_READ
from app.modules.reporting import service
from app.modules.sales.constants import SALES_ORDER_READ
from tests.modules.reporting.conftest import ReportingSetup

pytestmark = pytest.mark.asyncio

# Every gating permission — a caller holding all of them sees every KPI (the service ignores the
# base dashboard key; that gate is enforced by the router, exercised in the API tests).
_ALL_SOURCE_KEYS = frozenset(
    {
        FINANCE_STATEMENTS_READ,
        FINANCE_AR_READ,
        FINANCE_AP_READ,
        INVENTORY_VALUATION_READ,
        SALES_ORDER_READ,
        PROCUREMENT_PO_READ,
    }
)


async def _kpis(session: AsyncSession, setup: ReportingSetup, permissions: frozenset[str]):
    with tenant_context(setup.tenant_id):
        return await service.dashboard_kpis(
            session, setup.tenant_id, permissions, as_of=setup.as_of
        )


async def test_cash_position_sums_cash_equivalent_balances(
    db_session: AsyncSession, reporting_setup: ReportingSetup
) -> None:
    result = await _kpis(db_session, reporting_setup, _ALL_SOURCE_KEYS)
    assert result.cash_position is not None
    assert Decimal(result.cash_position.value) == reporting_setup.cash_position


async def test_ar_aging_buckets_total_the_open_invoice(
    db_session: AsyncSession, reporting_setup: ReportingSetup
) -> None:
    result = await _kpis(db_session, reporting_setup, _ALL_SOURCE_KEYS)
    assert result.ar_aging is not None
    # The seeded invoice (due 2026-05-31, as-of 2026-06-14) is 14 days past due → 1-30 bucket.
    assert Decimal(result.ar_aging.d30) == reporting_setup.ar_total
    assert Decimal(result.ar_aging.total) == reporting_setup.ar_total
    assert Decimal(result.ar_aging.current) == Decimal(0)


async def test_ap_aging_buckets_total_the_open_bill(
    db_session: AsyncSession, reporting_setup: ReportingSetup
) -> None:
    result = await _kpis(db_session, reporting_setup, _ALL_SOURCE_KEYS)
    assert result.ap_aging is not None
    assert Decimal(result.ap_aging.d30) == reporting_setup.ap_total
    assert Decimal(result.ap_aging.total) == reporting_setup.ap_total


async def test_wip_value_is_the_wip_clearing_balance(
    db_session: AsyncSession, reporting_setup: ReportingSetup
) -> None:
    result = await _kpis(db_session, reporting_setup, _ALL_SOURCE_KEYS)
    assert result.wip_value is not None
    assert Decimal(result.wip_value.value) == reporting_setup.wip_value


async def test_inventory_value_is_positive(
    db_session: AsyncSession, reporting_setup: ReportingSetup
) -> None:
    # The combined setup seeds two receipts then a delivery consumes some, so assert > 0 (the
    # exact-value path is test_inventory_value_exact below, with no consuming delivery).
    result = await _kpis(db_session, reporting_setup, _ALL_SOURCE_KEYS)
    assert result.inventory_value is not None
    assert Decimal(result.inventory_value.value) > 0


async def test_open_sales_orders_count_and_value(
    db_session: AsyncSession, reporting_setup: ReportingSetup
) -> None:
    result = await _kpis(db_session, reporting_setup, _ALL_SOURCE_KEYS)
    assert result.open_sales_orders is not None
    assert result.open_sales_orders.count == reporting_setup.open_sales_count
    assert Decimal(result.open_sales_orders.total) == reporting_setup.open_sales_total


async def test_open_purchase_orders_count_and_value(
    db_session: AsyncSession, reporting_setup: ReportingSetup
) -> None:
    result = await _kpis(db_session, reporting_setup, _ALL_SOURCE_KEYS)
    assert result.open_purchase_orders is not None
    assert result.open_purchase_orders.count == reporting_setup.open_po_count
    assert Decimal(result.open_purchase_orders.total) == reporting_setup.open_po_total


async def test_otd_percent_is_full_when_every_delivery_on_time(
    db_session: AsyncSession, reporting_setup: ReportingSetup
) -> None:
    result = await _kpis(db_session, reporting_setup, _ALL_SOURCE_KEYS)
    assert result.otd_percent is not None
    assert result.otd_percent.on_time == reporting_setup.otd_on_time
    assert result.otd_percent.total == reporting_setup.otd_total
    assert result.otd_percent.percent == 100.0


async def test_role_gate_omits_unpermitted_kpis(
    db_session: AsyncSession, reporting_setup: ReportingSetup
) -> None:
    """A finance-only role (statements + AR + AP) sees the finance KPIs but NOT inventory value or
    the open-orders / OTD KPIs (their source read keys are absent) — the role-based gate, D-058."""
    finance_only = frozenset({FINANCE_STATEMENTS_READ, FINANCE_AR_READ, FINANCE_AP_READ})
    result = await _kpis(db_session, reporting_setup, finance_only)
    # Permitted (finance source keys held):
    assert result.cash_position is not None
    assert result.ar_aging is not None
    assert result.ap_aging is not None
    assert result.wip_value is not None
    # Omitted (no inventory / sales / procurement read key):
    assert result.inventory_value is None
    assert result.open_sales_orders is None
    assert result.open_purchase_orders is None
    assert result.otd_percent is None


async def test_missing_inventory_permission_drops_inventory_value(
    db_session: AsyncSession, reporting_setup: ReportingSetup
) -> None:
    """A role with every source key EXCEPT inventory.valuation.read does not get inventory_value,
    but keeps every other KPI (the per-KPI gate is independent)."""
    without_inventory = _ALL_SOURCE_KEYS - {INVENTORY_VALUATION_READ}
    result = await _kpis(db_session, reporting_setup, without_inventory)
    assert result.inventory_value is None
    assert result.cash_position is not None
    assert result.open_sales_orders is not None


async def test_no_source_permissions_yields_empty_dashboard(
    db_session: AsyncSession, reporting_setup: ReportingSetup
) -> None:
    """Holding only the base dashboard key (no source keys) computes NO KPIs — every field None."""
    result = await _kpis(db_session, reporting_setup, frozenset())
    assert result.model_dump(exclude_none=True) == {}


async def test_empty_tenant_yields_zero_kpis(
    db_session: AsyncSession, tenant_b: uuid.UUID
) -> None:
    """A fresh tenant with no postings / orders still produces well-formed ZERO KPIs (no crash, no
    None for a permitted KPI) — the divide-by-zero and coalesce paths."""
    from tests.modules.reporting.factories import build_finance_base

    # The finance base gives the tenant a functional currency so the money KPIs render a currency;
    # the other source modules need no setup to return zeros.
    await build_finance_base(db_session, tenant_b)
    with tenant_context(tenant_b):
        result = await service.dashboard_kpis(db_session, tenant_b, _ALL_SOURCE_KEYS)
    assert result.cash_position is not None
    assert Decimal(result.cash_position.value) == Decimal(0)
    assert result.ar_aging is not None
    assert Decimal(result.ar_aging.total) == Decimal(0)
    assert result.open_sales_orders is not None
    assert result.open_sales_orders.count == 0
    assert result.otd_percent is not None
    assert result.otd_percent.total == 0
    assert result.otd_percent.percent == 0.0


async def test_inventory_value_exact(
    db_session: AsyncSession, tenant_b: uuid.UUID
) -> None:
    """Inventory value sums inv_item_valuations exactly when no delivery consumes stock: one 8-unit
    receipt at cost 5 ⇒ 40 (D-058). Uses the inventory stock setup (which wires the category's
    inventory/COGS accounts a valued move requires)."""
    from tests.modules.inventory.factories import build_stock, build_stock_setup

    stock = await build_stock_setup(db_session, tenant_b)
    await build_stock(
        db_session,
        tenant_b,
        stock.item_id,
        stock.bin_a_id,
        Decimal("8"),
        unit_cost=Decimal("5"),
    )
    with tenant_context(tenant_b):
        result = await service.dashboard_kpis(
            db_session, tenant_b, frozenset({INVENTORY_VALUATION_READ})
        )
    assert result.inventory_value is not None
    assert Decimal(result.inventory_value.value) == Decimal("40")
