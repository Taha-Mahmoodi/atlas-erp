"""AP aging: a pure projection over open vendor bills (PLAN 4.5, D-021 spirit).

Split out of ``vendor_payments.py`` to keep both under the STRUCTURE §3 400-line cap. The aging
report derives entirely from the open bills' ``open_amount`` + ``due_date`` — no stored totals.
Each bill's open balance lands in the bucket for ``as_of - due_date`` days: current (not yet due),
1-30, 31-60, 61-90, over-90; per partner and rolled up. Open amounts are transaction-currency, so a
partner with bills in two currencies appears as two rows (currency rides the grouping key).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.finance.constants import BillStatus
from app.modules.finance.models import VendorBill

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


async def vendor_aging(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    as_of: date,
    partner_id: uuid.UUID | None = None,
) -> dict[str, object]:
    """AP aging as of ``as_of`` (PLAN 4.5): bucket each open bill's open_amount by (as_of -
    due_date) into current / 1-30 / 31-60 / 61-90 / over-90, per partner and rolled up. A pure
    projection over open bills — no stored totals. Returns a dict the router maps to
    ``AgingReportRead``; each partner row keeps its currency (open amounts are transaction-side).
    """
    stmt = (
        select(VendorBill)
        .where(
            VendorBill.tenant_id == tenant_id,
            VendorBill.status.in_(
                (BillStatus.POSTED.value, BillStatus.PARTIALLY_PAID.value)
            ),
            VendorBill.open_amount > 0,
        )
        .order_by(VendorBill.partner_name)
    )
    if partner_id is not None:
        stmt = stmt.where(VendorBill.partner_id == partner_id)
    bills = list((await session.execute(stmt)).scalars().all())

    rows: dict[tuple[uuid.UUID, str], tuple[str, list[Decimal]]] = {}
    totals = [Decimal(0)] * 5
    for bill in bills:
        days_overdue = (as_of - bill.due_date).days
        bucket = _aging_bucket_index(days_overdue)
        key = (bill.partner_id, bill.currency_code)
        if key not in rows:
            rows[key] = (bill.partner_name, [Decimal(0)] * 5)
        amount = Decimal(str(bill.open_amount))
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
