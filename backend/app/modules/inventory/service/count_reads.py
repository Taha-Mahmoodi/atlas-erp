"""Stock-count READ paths (PLAN 5.4, D-038), split from ``counts.py`` (the writes) at the STRUCTURE
§3 cap — the stock_moves/stock_reads split precedent, writes-vs-reads from the start.

``get_count`` / ``list_counts`` / ``list_count_lines`` back the count read endpoints; ``get_line``
+ ``variance_preview`` back the per-line count + the pre-post preview. The write engine
(``counts.py``) imports ``get_count`` / ``get_line`` / ``current_system_qty`` from here, so the
read/write split is one-directional.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.pagination import (
    DEFAULT_LIMIT,
    OrderKey,
    SortDirection,
    filter_fingerprint,
    paginate,
)
from app.core.schemas import Page
from app.modules.inventory.constants import CountType
from app.modules.inventory.count_schemas import (
    StockCountFilter,
    StockCountVarianceLine,
    StockCountVariancePreview,
)
from app.modules.inventory.models import (
    CostLayer,
    ItemValuation,
    StockCount,
    StockCountLine,
    StockQuant,
)


async def get_count(
    session: AsyncSession, tenant_id: uuid.UUID, count_id: uuid.UUID
) -> StockCount:
    count = await session.get(StockCount, count_id)
    if count is None or count.tenant_id != tenant_id:
        raise NotFoundError(message="Stock count not found", code="inventory.count_not_found")
    return count


async def get_line(
    session: AsyncSession, tenant_id: uuid.UUID, count_id: uuid.UUID, line_id: uuid.UUID
) -> StockCountLine:
    line = await session.get(StockCountLine, line_id)
    if line is None or line.tenant_id != tenant_id or line.count_id != count_id:
        raise NotFoundError(
            message="Stock count line not found", code="inventory.count_line_not_found"
        )
    return line


async def current_system_qty(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    item_id: uuid.UUID,
    bin_id: uuid.UUID,
    lot_id: uuid.UUID | None,
) -> Decimal:
    """The LIVE on-hand of one (item, bin, lot) quant (PLAN 5.4): the authoritative system qty the
    post re-reads (D-038 re-validation) and the preview shows. A missing quant reads 0 (the system
    thinks the slot is empty). ``lot_id IS NULL`` is matched explicitly (the fungible-stock quant),
    so a NULL-lot line never collides with a lotted quant of the same (item, bin)."""
    stmt = select(StockQuant.on_hand_qty).where(
        StockQuant.tenant_id == tenant_id,
        StockQuant.item_id == item_id,
        StockQuant.bin_id == bin_id,
        StockQuant.lot_id.is_(None) if lot_id is None else StockQuant.lot_id == lot_id,
    )
    value = (await session.execute(stmt)).scalar_one_or_none()
    return Decimal(value) if value is not None else Decimal(0)


async def list_counts(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    filters: StockCountFilter,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Page[StockCount]:
    """Keyset-paginated counts (D-014), newest first by (count_date DESC, id). Filters narrow by
    status, warehouse and type and fold into the cursor fingerprint so a cursor cannot bleed across
    filtered views. count_date is an immutable Date (no SQLite fractional-seconds keyset hazard,
    D-033)."""
    stmt = select(StockCount).where(StockCount.tenant_id == tenant_id)
    if filters.status is not None:
        stmt = stmt.where(StockCount.status == filters.status.value)
    if filters.warehouse_id is not None:
        stmt = stmt.where(StockCount.warehouse_id == filters.warehouse_id)
    if filters.count_type is not None:
        stmt = stmt.where(StockCount.count_type == CountType(filters.count_type).value)
    fingerprint = filter_fingerprint(
        filters.status, filters.warehouse_id, filters.count_type
    )
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(StockCount.count_date, SortDirection.DESC)],
        pk=StockCount.id,
        cursor=cursor,
        limit=limit,
        filters=fingerprint,
    )


async def list_count_lines(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    count_id: uuid.UUID,
    *,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Page[StockCountLine]:
    """Keyset-paginated lines of a count (D-014), ordered by line_number for stable display.
    Index-served by ``(tenant, count)`` (PERFORMANCE §6)."""
    stmt = select(StockCountLine).where(
        StockCountLine.tenant_id == tenant_id, StockCountLine.count_id == count_id
    )
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(StockCountLine.line_number, SortDirection.ASC)],
        pk=StockCountLine.id,
        cursor=cursor,
        limit=limit,
        filters=filter_fingerprint(count_id),
    )


async def _bulk_system_qty(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    item_ids: list[uuid.UUID],
    bin_ids: list[uuid.UUID],
) -> dict[tuple[uuid.UUID, uuid.UUID, uuid.UUID | None], Decimal]:
    """LIVE on-hand for every quant touching the count's items × bins — ONE query (#78), keyed
    ``(item_id, bin_id, lot_id)``. Superset rows (an item in a bin the count doesn't pair it
    with) are harmless: callers only look up their own keys; a missing key reads 0 (the system
    thinks the slot is empty), matching :func:`current_system_qty`."""
    if not item_ids or not bin_ids:
        return {}
    rows = (
        await session.execute(
            select(
                StockQuant.item_id, StockQuant.bin_id, StockQuant.lot_id, StockQuant.on_hand_qty
            ).where(
                StockQuant.tenant_id == tenant_id,
                StockQuant.item_id.in_(item_ids),
                StockQuant.bin_id.in_(bin_ids),
            )
        )
    ).all()
    return {(item, bin_, lot): Decimal(qty) for item, bin_, lot, qty in rows}


async def _bulk_unit_costs(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    item_ids: list[uuid.UUID],
    warehouse_id: uuid.UUID,
) -> dict[uuid.UUID, Decimal]:
    """Current per-unit BOOK cost for a batch of items in one warehouse — the bulk mirror of
    ``queries.current_unit_cost`` (#78): the moving-average row when present, else the weighted
    average of the live FIFO layers (multiplied in PYTHON, D-015), else 0. One valuation query +
    one layer query for the items lacking a valuation row."""
    if not item_ids:
        return {}
    costs: dict[uuid.UUID, Decimal] = {}
    valuation_rows = (
        await session.execute(
            select(ItemValuation.item_id, ItemValuation.avg_unit_cost).where(
                ItemValuation.tenant_id == tenant_id,
                ItemValuation.item_id.in_(item_ids),
                ItemValuation.warehouse_id == warehouse_id,
            )
        )
    ).all()
    for item_id, avg_unit_cost in valuation_rows:
        costs[item_id] = Decimal(avg_unit_cost)
    fifo_item_ids = [item_id for item_id in item_ids if item_id not in costs]
    if fifo_item_ids:
        layer_rows = (
            await session.execute(
                select(CostLayer.item_id, CostLayer.remaining_qty, CostLayer.unit_cost).where(
                    CostLayer.tenant_id == tenant_id,
                    CostLayer.item_id.in_(fifo_item_ids),
                    CostLayer.warehouse_id == warehouse_id,
                    CostLayer.remaining_qty > 0,
                )
            )
        ).all()
        totals: dict[uuid.UUID, tuple[Decimal, Decimal]] = {}
        for item_id, qty, cost in layer_rows:
            total_qty, total_value = totals.get(item_id, (Decimal(0), Decimal(0)))
            totals[item_id] = (
                total_qty + Decimal(qty),
                total_value + Decimal(qty) * Decimal(cost),
            )
        for item_id, (total_qty, total_value) in totals.items():
            if total_qty > 0:
                costs[item_id] = total_value / total_qty
    return costs


async def variance_preview(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    count_id: uuid.UUID,
    *,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> StockCountVariancePreview:
    """Per-line system-vs-counted-vs-variance + estimated value impact BEFORE posting (PLAN 5.4).

    Re-reads LIVE on-hand (the same authority the post uses, D-038) and the items' current unit
    costs, computing variance = counted − live-system (NULL for uncounted lines) and value impact
    = variance × unit_cost. ``total_value_impact`` sums the WHOLE count; ``lines`` is a keyset
    page (a physical count routinely has thousands of lines — PERFORMANCE §3). Read-only.

    Query budget (#78, PERFORMANCE §2): CONSTANT regardless of line count — the count header, one
    slim all-lines read (totals + bulk keys), one bulk quant read, one valuation + one FIFO-layer
    read, and the page select. No per-line queries."""
    count = await get_count(session, tenant_id, count_id)
    all_lines = (
        await session.execute(
            select(
                StockCountLine.item_id,
                StockCountLine.bin_id,
                StockCountLine.lot_id,
                StockCountLine.counted_qty,
            ).where(
                StockCountLine.tenant_id == tenant_id,
                StockCountLine.count_id == count_id,
            )
        )
    ).all()
    system_by_key = await _bulk_system_qty(
        session,
        tenant_id,
        list({row.item_id for row in all_lines}),
        list({row.bin_id for row in all_lines}),
    )
    cost_by_item = await _bulk_unit_costs(
        session, tenant_id, list({row.item_id for row in all_lines}), count.warehouse_id
    )

    def _compute(
        item_id: uuid.UUID,
        bin_id: uuid.UUID,
        lot_id: uuid.UUID | None,
        counted_qty: object,
    ) -> tuple[Decimal, Decimal | None, Decimal | None, Decimal, Decimal]:
        system = system_by_key.get((item_id, bin_id, lot_id), Decimal(0))
        unit_cost = cost_by_item.get(item_id, Decimal(0))
        counted = Decimal(counted_qty) if counted_qty is not None else None  # type: ignore[arg-type]
        variance = (counted - system) if counted is not None else None
        impact = (variance * unit_cost) if variance is not None else Decimal(0)
        return system, counted, variance, unit_cost, impact

    total_impact = sum(
        (
            _compute(row.item_id, row.bin_id, row.lot_id, row.counted_qty)[4]
            for row in all_lines
        ),
        Decimal(0),
    )

    page = await paginate(
        session,
        select(StockCountLine).where(
            StockCountLine.tenant_id == tenant_id, StockCountLine.count_id == count_id
        ),
        order_by=[OrderKey(StockCountLine.line_number, SortDirection.ASC)],
        pk=StockCountLine.id,
        cursor=cursor,
        limit=limit,
        filters=filter_fingerprint(count_id),
    )
    preview_lines: list[StockCountVarianceLine] = []
    for line in page.items:
        system, counted, variance, unit_cost, impact = _compute(
            line.item_id, line.bin_id, line.lot_id, line.counted_qty
        )
        preview_lines.append(
            StockCountVarianceLine(
                line_id=line.id,
                item_id=line.item_id,
                bin_id=line.bin_id,
                lot_id=line.lot_id,
                system_qty=system,
                counted_qty=counted,
                variance_qty=variance,
                unit_cost=unit_cost,
                estimated_value_impact=impact,
            )
        )
    return StockCountVariancePreview(
        count_id=count.id,
        status=count.status,  # type: ignore[arg-type]
        lines=Page(items=preview_lines, next_cursor=page.next_cursor, limit=page.limit),
        total_value_impact=total_impact,
    )
