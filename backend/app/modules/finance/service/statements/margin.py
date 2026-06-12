"""Margin-by-product: revenue - COGS grouped by the item_id line dimension (D-021).

Another projection of the universal journal: revenue and COGS postings tagged with ``item_id`` are
read straight off the line and netted per item. This is sparse until inventory posts COGS with an
``item_id`` (PLAN 5) — but the structure is correct now and tested with manually item-tagged journal
lines, so it works unchanged once inventory lands. Margin = item revenue - item COGS; margin % =
margin / revenue (None when an item has no revenue, to avoid a divide-by-zero). No stored totals.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.finance.constants import AccountType
from app.modules.finance.models.journal import JournalLine
from app.modules.finance.service.statements.base import (
    ZERO,
    _dimension_balances,
    load_account_meta,
    presentation_amount,
)

# Two decimal places for the margin-percent figure (a ratio, presented to 2dp).
_PERCENT_QUANTUM = Decimal("0.01")


@dataclass(frozen=True)
class ItemMargin:
    """One item's revenue, COGS, margin and margin percent over the period (D-021). ``item_id`` is
    None for the bucket of revenue/COGS postings carrying no item dimension. ``margin_percent`` is
    None when the item has zero revenue (undefined ratio)."""

    item_id: uuid.UUID | None
    revenue: Decimal
    cogs: Decimal
    margin: Decimal
    margin_percent: Decimal | None


@dataclass
class MarginByProduct:
    """The margin-by-product report for a period (D-021): one row per item with revenue/COGS/margin.

    ``items`` are sorted by descending margin so the most profitable items surface first; the
    unassigned (item_id None) bucket, if present, sorts among them by its margin."""

    date_from: date
    date_to: date
    items: list[ItemMargin] = field(default_factory=list)


async def margin_by_product(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    date_from: date,
    date_to: date,
) -> MarginByProduct:
    """Revenue - COGS per item over ``[date_from, date_to]`` (D-021).

    Uses the dimension aggregate on ``JournalLine.item_id``, splitting each (item, account) balance
    into revenue (REVENUE accounts) and COGS (EXPENSE accounts) by account type. Both are presented
    as natural positive magnitudes; margin = revenue - cogs; margin % = margin / revenue. Items with
    no revenue and no COGS are omitted."""
    balances = await _dimension_balances(
        session,
        tenant_id,
        JournalLine.item_id,
        date_from=date_from,
        date_to=date_to,
    )
    meta = await load_account_meta(session, tenant_id)

    revenue_by_item: dict[uuid.UUID | None, Decimal] = {}
    cogs_by_item: dict[uuid.UUID | None, Decimal] = {}
    for (item_id, account_id), signed in balances.items():
        account = meta.get(account_id)
        if account is None:
            continue
        amount = presentation_amount(account, signed)
        if account.account_type is AccountType.REVENUE:
            revenue_by_item[item_id] = revenue_by_item.get(item_id, ZERO) + amount
        elif account.account_type is AccountType.EXPENSE:
            cogs_by_item[item_id] = cogs_by_item.get(item_id, ZERO) + amount

    items: list[ItemMargin] = []
    for item_id in set(revenue_by_item) | set(cogs_by_item):
        revenue = revenue_by_item.get(item_id, ZERO)
        cogs = cogs_by_item.get(item_id, ZERO)
        if revenue == ZERO and cogs == ZERO:
            continue
        margin = revenue - cogs
        margin_percent = (
            (margin / revenue * Decimal(100)).quantize(
                _PERCENT_QUANTUM, rounding=ROUND_HALF_UP
            )
            if revenue != ZERO
            else None
        )
        items.append(
            ItemMargin(
                item_id=item_id,
                revenue=revenue,
                cogs=cogs,
                margin=margin,
                margin_percent=margin_percent,
            )
        )

    items.sort(key=lambda row: row.margin, reverse=True)
    return MarginByProduct(date_from=date_from, date_to=date_to, items=items)
