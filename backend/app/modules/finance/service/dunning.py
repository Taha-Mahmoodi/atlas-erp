"""Dunning: advance the reminder level on overdue open customer invoices (PLAN 4.6, AR).

Dunning is the AR-only escalation step (AP has no mirror). ``run_dunning(as_of)`` scans every OPEN
overdue invoice, computes the dunning level its days-overdue earns from ``DUNNING_THRESHOLDS``
(level 1 at 7 days, 2 at 30, 3 at 60), and — when that level EXCEEDS the invoice's current
``dunning_level`` — raises the invoice to it and stamps ``last_dunned_date = as_of``. It returns the
dunning run: the list of (partner, invoice, new level) it advanced — a "proposal / notice list".

This posts NO journal: it updates dunning STATE only (D-029 — finance owns the open item but not
the notice delivery). It is idempotent-ish per day: re-running the same ``as_of`` never advances an
invoice already at/above the level its age earns, so a second run that day returns an empty list. A
current (not-yet-overdue) invoice earns level 0 and is left untouched. Finance stays the bottom
dependency; partner ids stay opaque (D-029).
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.finance.constants import InvoiceStatus, dunning_level_for
from app.modules.finance.models import CustomerInvoice


async def run_dunning(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    as_of: date,
    partner_id: uuid.UUID | None = None,
) -> dict[str, object]:
    """Run a dunning pass as of ``as_of`` (PLAN 4.6). For each OPEN overdue invoice (optionally one
    ``partner_id``), compute the level its days-overdue earns; if it exceeds the invoice's current
    ``dunning_level``, raise it + set ``last_dunned_date = as_of`` and record a notice. Posts no
    journal. Idempotent per day: a re-run never re-advances a level already earned. Returns a dict
    the router maps to ``DunningRunResult`` (the ``notices`` list is the proposal / notice list)."""
    stmt = (
        select(CustomerInvoice)
        .where(
            CustomerInvoice.tenant_id == tenant_id,
            CustomerInvoice.status.in_(
                (InvoiceStatus.POSTED.value, InvoiceStatus.PARTIALLY_PAID.value)
            ),
            CustomerInvoice.open_amount > 0,
            CustomerInvoice.due_date < as_of,
        )
        .order_by(CustomerInvoice.partner_name, CustomerInvoice.due_date)
    )
    if partner_id is not None:
        stmt = stmt.where(CustomerInvoice.partner_id == partner_id)
    invoices = list((await session.execute(stmt)).scalars().all())

    notices: list[dict[str, object]] = []
    for invoice in invoices:
        days_overdue = (as_of - invoice.due_date).days
        earned_level = dunning_level_for(days_overdue)
        if earned_level <= invoice.dunning_level:
            continue
        previous_level = invoice.dunning_level
        invoice.dunning_level = earned_level
        invoice.last_dunned_date = as_of
        notices.append(
            {
                "partner_id": invoice.partner_id,
                "partner_name": invoice.partner_name,
                "invoice_id": invoice.id,
                "invoice_number": invoice.invoice_number,
                "currency_code": invoice.currency_code,
                "open_amount": invoice.open_amount,
                "due_date": invoice.due_date,
                "days_overdue": days_overdue,
                "previous_level": previous_level,
                "new_level": earned_level,
            }
        )
    if notices:
        await session.flush()
    return {"as_of": as_of, "notices": notices}
