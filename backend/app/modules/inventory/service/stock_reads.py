"""Stock-move + on-hand read paths (PLAN 5.2), split from stock_moves.py at the 400-line cap.

``get_move`` (single move), ``list_moves`` (the keyset-paginated move ledger) and ``list_on_hand``
(the keyset-paginated quant projection) back the router's read endpoints. The write engine
(stock_moves.py) imports ``get_move`` from here, so the read/write split is one-directional.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.docflow import DocumentLink
from app.core.exceptions import NotFoundError
from app.core.pagination import (
    DEFAULT_LIMIT,
    OrderKey,
    SortDirection,
    filter_fingerprint,
    paginate,
)
from app.core.schemas import Page
from app.modules.inventory.constants import MoveType
from app.modules.inventory.models import CostLayer, ItemValuation, StockMove, StockQuant
from app.modules.inventory.schemas import StockMoveFilter


async def get_move(
    session: AsyncSession, tenant_id: uuid.UUID, move_id: uuid.UUID
) -> StockMove:
    move = await session.get(StockMove, move_id)
    if move is None or move.tenant_id != tenant_id:
        raise NotFoundError(message="Stock move not found", code="inventory.move_not_found")
    return move


async def list_moves(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    filters: StockMoveFilter,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Page[StockMove]:
    """Keyset-paginated move ledger (D-014), newest first by (move_date DESC, id). Filters narrow by
    item, bin (either side), type and date range and fold into the cursor fingerprint so a cursor
    cannot bleed across filtered views. The append-only ledger view procurement/sales audit from."""
    stmt = select(StockMove).where(StockMove.tenant_id == tenant_id)
    if filters.item_id is not None:
        stmt = stmt.where(StockMove.item_id == filters.item_id)
    if filters.bin_id is not None:
        stmt = stmt.where(
            (StockMove.from_bin_id == filters.bin_id)
            | (StockMove.to_bin_id == filters.bin_id)
        )
    if filters.move_type is not None:
        stmt = stmt.where(StockMove.move_type == MoveType(filters.move_type).value)
    if filters.date_from is not None:
        stmt = stmt.where(StockMove.move_date >= filters.date_from)
    if filters.date_to is not None:
        stmt = stmt.where(StockMove.move_date <= filters.date_to)

    fingerprint = filter_fingerprint(
        filters.item_id,
        filters.bin_id,
        filters.move_type,
        filters.date_from,
        filters.date_to,
    )
    return await paginate(
        session,
        stmt,
        # Newest move_date first; ``paginate`` appends the id PK as the unique tiebreaker, so
        # same-date moves order deterministically. move_date is an immutable Date (no SQLite
        # fractional-seconds keyset hazard, unlike created_at — D-033).
        order_by=[OrderKey(StockMove.move_date, SortDirection.DESC)],
        pk=StockMove.id,
        cursor=cursor,
        limit=limit,
        filters=fingerprint,
    )


async def list_on_hand(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    item_id: uuid.UUID | None = None,
    bin_id: uuid.UUID | None = None,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Page[StockQuant]:
    """Keyset-paginated on-hand projection (PLAN 5.2): the maintained quant rows (D-036), optionally
    filtered to one item and/or one bin. Ordered by item_id for stability (the natural key has no
    business sort). Filters fold into the cursor fingerprint. The on-hand view a stock-overview
    screen reads; sales ATP / procurement use the queries.on_hand* helpers instead."""
    stmt = select(StockQuant).where(StockQuant.tenant_id == tenant_id)
    if item_id is not None:
        stmt = stmt.where(StockQuant.item_id == item_id)
    if bin_id is not None:
        stmt = stmt.where(StockQuant.bin_id == bin_id)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(StockQuant.item_id, SortDirection.ASC)],
        pk=StockQuant.id,
        cursor=cursor,
        limit=limit,
        filters=filter_fingerprint(item_id, bin_id),
    )


async def list_valuations(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    item_id: uuid.UUID | None = None,
    warehouse_id: uuid.UUID | None = None,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Page[ItemValuation]:
    """Keyset-paginated moving-average valuation rows (PLAN 5.3): per (item, warehouse) value, qty
    and avg cost, optionally filtered to one item and/or warehouse. Ordered by item_id for
    stability. Reads the maintained value SSOT (inv_item_valuations), index-served (PERF §6)."""
    stmt = select(ItemValuation).where(ItemValuation.tenant_id == tenant_id)
    if item_id is not None:
        stmt = stmt.where(ItemValuation.item_id == item_id)
    if warehouse_id is not None:
        stmt = stmt.where(ItemValuation.warehouse_id == warehouse_id)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(ItemValuation.item_id, SortDirection.ASC)],
        pk=ItemValuation.id,
        cursor=cursor,
        limit=limit,
        filters=filter_fingerprint(item_id, warehouse_id),
    )


async def list_cost_layers(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    item_id: uuid.UUID,
    *,
    warehouse_id: uuid.UUID | None = None,
    include_exhausted: bool = False,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Page[CostLayer]:
    """Keyset-paginated FIFO cost layers for an item (PLAN 5.3), oldest-first by received_at — the
    consumption order. ``include_exhausted`` widens to fully-consumed layers (default: live layers
    only). Optional warehouse filter. The cost-layer drill-down for a FIFO item; index-served by
    ``(tenant, item, warehouse, received_at)`` (PERFORMANCE §6)."""
    stmt = select(CostLayer).where(
        CostLayer.tenant_id == tenant_id, CostLayer.item_id == item_id
    )
    if warehouse_id is not None:
        stmt = stmt.where(CostLayer.warehouse_id == warehouse_id)
    if not include_exhausted:
        stmt = stmt.where(CostLayer.remaining_qty > 0)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(CostLayer.received_at, SortDirection.ASC)],
        pk=CostLayer.id,
        cursor=cursor,
        limit=limit,
        filters=filter_fingerprint(item_id, warehouse_id, include_exhausted),
    )


async def items_already_moved_for_document(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    predecessor_document_id: uuid.UUID,
    link_type: str,
) -> set[uuid.UUID]:
    """The item ids a driving document has ALREADY moved through ``link_type`` edges (P0 Task 1).

    The natural idempotency key for a goods movement a background job may re-dispatch, and the
    reason it is per ITEM rather than per document: one driving document may be moved by SEVERAL
    jobs over disjoint item sets (a fired restaurant ticket is chunked at
    ``DEPLETE_MAX_COMPONENTS_PER_JOB``), so a document-level "already moved?" flag would silently
    skip every chunk after the first and lose most of the movement. Reading the moves themselves
    needs no new column and no new status.

    ONE query: the document's outgoing links of this type, joined to the moves whose registry
    entry they point at. Index-served — the doc-link unique constraint leads with
    ``(tenant_id, predecessor_document_id)`` and a move is unique on ``(tenant_id, document_id)``.
    """
    successors = select(DocumentLink.successor_document_id).where(
        DocumentLink.tenant_id == tenant_id,
        DocumentLink.predecessor_document_id == predecessor_document_id,
        DocumentLink.link_type == link_type,
    )
    rows = await session.execute(
        select(StockMove.item_id).where(
            StockMove.tenant_id == tenant_id, StockMove.document_id.in_(successors)
        )
    )
    return set(rows.scalars().all())
