"""Reporting service (PLAN 13.1, D-058): the role-based dashboard KPI aggregator.

``dashboard_kpis`` computes the KPIs the CALLER is permitted to see by reading each SOURCE module's
``queries`` DOWNWARD (STRUCTURE §5 — never their service/models). Each KPI is gated by the source
module's read permission via the ``KPI_PERMISSIONS`` map: the gate passes ⇒ the KPI is computed and
included; the gate fails ⇒ the KPI is omitted entirely. So the response shape IS the role (D-058).

BOUNDED, NEVER N+1 (PERFORMANCE §6). The dashboard runs a FIXED set of aggregates — one (or, for
inventory value, two) per PERMITTED KPI, each O(1) over its module's covering index. It is
N-aggregates-for-N-KPIs by design (so the internal query count exceeds 3), but the CLIENT makes ONE
call (PERFORMANCE §4: one screen ≤ 3 calls — satisfied because the screen is a single endpoint). All
figures are PROJECTIONS read off existing queries (D-021), never new stored totals.
"""

import uuid
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.finance import queries as finance_queries
from app.modules.inventory import queries as inventory_queries
from app.modules.procurement import queries as procurement_queries
from app.modules.reporting.constants import (
    KPI_AP_AGING,
    KPI_AR_AGING,
    KPI_CASH_POSITION,
    KPI_INVENTORY_VALUE,
    KPI_OPEN_PURCHASE_ORDERS,
    KPI_OPEN_SALES_ORDERS,
    KPI_OTD_PERCENT,
    KPI_PERMISSIONS,
    KPI_WIP_VALUE,
)
from app.modules.reporting.schemas import (
    AgingSummary,
    CountValueKpi,
    DashboardResponse,
    MoneyKpi,
    OtdKpi,
)
from app.modules.sales import queries as sales_queries

# The currency code a money KPI falls back to when the tenant has no functional currency configured
# (an un-set-up tenant still gets a well-formed, all-zero dashboard rather than a 500).
_UNSET_CURRENCY = "—"


def _permitted(kpi_key: str, permissions: frozenset[str]) -> bool:
    """Whether the caller may see ``kpi_key``: they hold the SOURCE module's read permission for it
    (the KPI→permission gate, D-058)."""
    return KPI_PERMISSIONS[kpi_key] in permissions


async def dashboard_kpis(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    permissions: frozenset[str],
    *,
    as_of: date | None = None,
) -> DashboardResponse:
    """Compute the dashboard KPIs the caller is permitted to see (PLAN 13.1, D-058).

    Reads each source module's ``queries`` downward, gated per KPI by ``KPI_PERMISSIONS``. ``as_of``
    bounds the date-bounded figures (cash / aging / WIP) to that date; defaults to today. Returns a
    ``DashboardResponse`` with only the permitted KPIs populated (the rest ``None``, omitted from
    the JSON). An empty tenant (no postings, no orders) yields well-formed ZERO KPIs."""
    effective_date = as_of or date.today()
    currency = (
        await finance_queries.functional_currency_or_none(session, tenant_id)
    ) or _UNSET_CURRENCY

    response = DashboardResponse()

    if _permitted(KPI_CASH_POSITION, permissions):
        value = await finance_queries.cash_position(session, tenant_id, as_of=effective_date)
        response.cash_position = MoneyKpi(value=value, currency=currency)

    if _permitted(KPI_AR_AGING, permissions):
        buckets = await finance_queries.ar_aging_summary(
            session, tenant_id, as_of=effective_date
        )
        response.ar_aging = _aging(buckets, currency)

    if _permitted(KPI_AP_AGING, permissions):
        buckets = await finance_queries.ap_aging_summary(
            session, tenant_id, as_of=effective_date
        )
        response.ap_aging = _aging(buckets, currency)

    if _permitted(KPI_INVENTORY_VALUE, permissions):
        # inventory value = Σ inv_item_valuations.total_value (+ FIFO live layers), summed over the
        # per-item dict the existing valuation_summary query returns (D-058: read the existing
        # query, never a new stored total). Two internal reads (MAV totals + FIFO layers), no N+1.
        per_item = await inventory_queries.valuation_summary(session, tenant_id)
        total = sum(per_item.values(), Decimal(0))
        response.inventory_value = MoneyKpi(value=total, currency=currency)

    if _permitted(KPI_OPEN_SALES_ORDERS, permissions):
        open_so = await sales_queries.open_sales_orders(session, tenant_id)
        response.open_sales_orders = CountValueKpi(
            count=open_so.count, total=open_so.total, currency=currency
        )

    if _permitted(KPI_OPEN_PURCHASE_ORDERS, permissions):
        open_po = await procurement_queries.open_purchase_orders(session, tenant_id)
        response.open_purchase_orders = CountValueKpi(
            count=open_po.count, total=open_po.total, currency=currency
        )

    if _permitted(KPI_OTD_PERCENT, permissions):
        otd = await sales_queries.on_time_delivery(session, tenant_id)
        response.otd_percent = OtdKpi(
            percent=_otd_percent(otd.on_time, otd.total),
            on_time=otd.on_time,
            total=otd.total,
        )

    if _permitted(KPI_WIP_VALUE, permissions):
        value = await finance_queries.wip_balance(session, tenant_id, as_of=effective_date)
        response.wip_value = MoneyKpi(value=value, currency=currency)

    return response


def _aging(buckets: finance_queries.AgingBuckets, currency: str) -> AgingSummary:
    """Map a finance ``AgingBuckets`` (current / d30 / d60 / d90plus / total) to the dashboard
    ``AgingSummary`` card, attaching the display currency."""
    return AgingSummary(
        current=buckets.current,
        d30=buckets.d30,
        d60=buckets.d60,
        d90plus=buckets.d90plus,
        total=buckets.total,
        currency=currency,
    )


def _otd_percent(on_time: int, total: int) -> float:
    """The on-time-delivery percentage (0-100, one decimal). ``total`` 0 ⇒ 0.0 (no measurable
    deliveries — never a divide-by-zero). Quantized HALF_UP on the exact ratio so the card reads
    cleanly (e.g. 2/3 ⇒ 66.7)."""
    if total == 0:
        return 0.0
    ratio = (Decimal(on_time) / Decimal(total) * Decimal(100)).quantize(
        Decimal("0.1"), rounding=ROUND_HALF_UP
    )
    return float(ratio)
