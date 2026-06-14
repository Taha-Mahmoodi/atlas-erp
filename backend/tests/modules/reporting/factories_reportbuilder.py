"""Report-builder test data builder (PLAN 13.2, D-059; STRUCTURE §6/§8.4).

Seeds a tenant with a DETERMINISTIC set of SALES ORDERS through the REAL sales service (D-025) so
the report-builder tests can assert exact rows / group-by counts / aggregation sums over a
whitelisted entity (``sales.orders``). Three CONFIRMED orders + one DRAFT order, totals 50 / 50 /
100 / 30 — so a status group-by yields CONFIRMED (3 rows, Σ200) + DRAFT (1 row, Σ30), and a
status-filtered count is exact. Built on the sales ``build_order_setup`` foundation (currency / item
/ customer / stock).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from tests.modules.sales.factories import (
    build_order_setup,
    build_sales_order,
    confirm_sales_order,
)

# (quantity, unit_price, confirm?) — three confirmed (50/50/100) + one draft (30).
_ORDERS: tuple[tuple[str, str, bool], ...] = (
    ("5", "10", True),
    ("5", "10", True),
    ("10", "10", True),
    ("3", "10", False),
)


@dataclass(frozen=True)
class ReportBuilderSetup:
    """A tenant with a known sales-order population for the report-builder tests (D-059)."""

    tenant_id: uuid.UUID
    confirmed_count: int
    draft_count: int
    confirmed_total: Decimal
    draft_total: Decimal


async def build_report_builder_setup(
    session: AsyncSession, tenant_id: uuid.UUID
) -> ReportBuilderSetup:
    """Seed the deterministic sales-order set (D-025) and return the expected aggregates the
    report-builder tests assert (status group-by counts/sums, status filter counts)."""
    setup = await build_order_setup(session, tenant_id)
    for quantity, unit_price, do_confirm in _ORDERS:
        order = await build_sales_order(
            session,
            tenant_id,
            customer_id=setup.customer_id,
            item_id=setup.item_id,
            uom_id=setup.uom_id,
            quantity=quantity,
            unit_price=unit_price,
        )
        if do_confirm:
            await confirm_sales_order(session, tenant_id, order.id)

    confirmed = [o for o in _ORDERS if o[2]]
    drafts = [o for o in _ORDERS if not o[2]]
    confirmed_total = sum(
        (Decimal(q) * Decimal(p) for q, p, _ in confirmed), Decimal(0)
    )
    draft_total = sum((Decimal(q) * Decimal(p) for q, p, _ in drafts), Decimal(0))
    return ReportBuilderSetup(
        tenant_id=tenant_id,
        confirmed_count=len(confirmed),
        draft_count=len(drafts),
        confirmed_total=confirmed_total,
        draft_total=draft_total,
    )
