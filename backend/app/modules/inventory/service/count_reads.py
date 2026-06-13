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
from app.modules.inventory import queries
from app.modules.inventory.constants import CountType
from app.modules.inventory.count_schemas import (
    StockCountFilter,
    StockCountVarianceLine,
    StockCountVariancePreview,
)
from app.modules.inventory.models import StockCount, StockCountLine, StockQuant


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


async def variance_preview(
    session: AsyncSession, tenant_id: uuid.UUID, count_id: uuid.UUID
) -> StockCountVariancePreview:
    """Per-line system-vs-counted-vs-variance + estimated value impact BEFORE posting (PLAN 5.4).

    For each line it re-reads LIVE on-hand (the same authority the post uses, D-038), the item's
    current unit cost, and computes variance = counted − live-system (NULL for uncounted lines) and
    value impact = variance × unit_cost. The net total is the sum over counted lines. Read-only — it
    never writes; it is what a reviewer inspects to decide whether to post. Query budget: lines
    page, then per-line a quant read + a unit-cost read; bounded per line, no nested N+1 beyond
    that."""
    count = await get_count(session, tenant_id, count_id)
    lines = (
        await session.execute(
            select(StockCountLine)
            .where(
                StockCountLine.tenant_id == tenant_id,
                StockCountLine.count_id == count_id,
            )
            .order_by(StockCountLine.line_number.asc())
        )
    ).scalars().all()
    preview_lines: list[StockCountVarianceLine] = []
    total_impact = Decimal(0)
    for line in lines:
        system = await current_system_qty(
            session, tenant_id, line.item_id, line.bin_id, line.lot_id
        )
        unit_cost = await queries.current_unit_cost(
            session, tenant_id, line.item_id, count.warehouse_id
        )
        counted = Decimal(line.counted_qty) if line.counted_qty is not None else None
        variance = (counted - system) if counted is not None else None
        impact = (variance * unit_cost) if variance is not None else Decimal(0)
        total_impact += impact
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
        lines=preview_lines,
        total_value_impact=total_impact,
    )
