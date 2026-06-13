"""AR aging: a pure projection over open customer invoices (PLAN 4.6, D-021 spirit).

The AP ``ap_aging.py`` mirror over the receivable side. The aging report derives entirely from the
open invoices' ``open_amount`` + ``due_date`` — no stored totals. Each invoice's open balance lands
in the bucket for ``as_of - due_date`` days: current (not yet due), 1-30, 31-60, 61-90, over-90; per
partner and rolled up. Open amounts are transaction-currency, so a partner with invoices in two
currencies appears as two rows (currency rides the grouping key).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.finance.constants import InvoiceStatus
from app.modules.finance.models import CustomerInvoice

# Aging bucket upper bounds (days past due) for buckets 1-30 / 31-60 / 61-90; over-90 is the tail.
_AGING_BOUNDS: tuple[int, ...] = (30, 60, 90)


def _aging_bucket_index(days_overdue: int) -> int:
    """Index into (current, 1-30, 31-60, 61-90, over-90) for ``days_overdue`` (as_of - due_date).
    <= 0 is 'current' (index 0); 1..30 -> 1; 31..60 -> 2; 61..90 -> 3; > 90 -> 4."""
    if days_overdue <= 0:
        return 0
    for index, bound in enumerate(_AGING_BOUNDS, start=1):
        if days_overdue <= bound:
            return index
    return 4


async def customer_aging(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    as_of: date,
    partner_id: uuid.UUID | None = None,
) -> dict[str, object]:
    """AR aging as of ``as_of`` (PLAN 4.6): bucket each open invoice's open_amount by (as_of -
    due_date) into current / 1-30 / 31-60 / 61-90 / over-90, per partner and rolled up. A pure
    projection over open invoices — no stored totals. Returns a dict the router maps to
    ``ArAgingReportRead``; each partner row keeps its currency (open amounts are transaction-side).
    """
    stmt = (
        select(CustomerInvoice)
        .where(
            CustomerInvoice.tenant_id == tenant_id,
            CustomerInvoice.status.in_(
                (InvoiceStatus.POSTED.value, InvoiceStatus.PARTIALLY_PAID.value)
            ),
            CustomerInvoice.open_amount > 0,
        )
        .order_by(CustomerInvoice.partner_name)
    )
    if partner_id is not None:
        stmt = stmt.where(CustomerInvoice.partner_id == partner_id)
    invoices = list((await session.execute(stmt)).scalars().all())

    rows: dict[tuple[uuid.UUID, str], tuple[str, list[Decimal]]] = {}
    totals = [Decimal(0)] * 5
    for invoice in invoices:
        days_overdue = (as_of - invoice.due_date).days
        bucket = _aging_bucket_index(days_overdue)
        key = (invoice.partner_id, invoice.currency_code)
        if key not in rows:
            rows[key] = (invoice.partner_name, [Decimal(0)] * 5)
        amount = Decimal(str(invoice.open_amount))
        rows[key][1][bucket] += amount
        totals[bucket] += amount

    partners = [
        {
            "partner_id": key[0],
            "partner_name": name,
            "currency_code": key[1],
            "current": buckets[0],
            "days_1_30": buckets[1],
            "days_31_60": buckets[2],
            "days_61_90": buckets[3],
            "days_over_90": buckets[4],
            "total": sum(buckets, Decimal(0)),
        }
        for key, (name, buckets) in rows.items()
    ]
    return {
        "as_of": as_of,
        "partners": partners,
        "current": totals[0],
        "days_1_30": totals[1],
        "days_31_60": totals[2],
        "days_61_90": totals[3],
        "days_over_90": totals[4],
        "total": sum(totals, Decimal(0)),
    }
