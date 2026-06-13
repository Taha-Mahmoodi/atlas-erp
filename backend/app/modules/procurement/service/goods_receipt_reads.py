"""Goods-receipt read paths (PLAN 6.3), split from the write engine (goods_receipts.py) at the
400-line cap (STRUCTURE §8.4). The service package and router import these via the package surface.

Keyset-paginated list (filter by PO / status / receipt-date range) + header/line point reads. The
list folds its filters into the cursor fingerprint so a cursor cannot cross filtered views (D-014).
"""

from __future__ import annotations

import uuid
from datetime import date

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
from app.modules.procurement.constants import GoodsReceiptStatus
from app.modules.procurement.models import GoodsReceipt, GoodsReceiptLine


async def get_goods_receipt(
    session: AsyncSession, tenant_id: uuid.UUID, gr_id: uuid.UUID
) -> GoodsReceipt:
    gr = await session.get(GoodsReceipt, gr_id)
    if gr is None or gr.tenant_id != tenant_id:
        raise NotFoundError(
            message="Goods receipt not found", code="procurement.goods_receipt_not_found"
        )
    return gr


async def get_goods_receipt_lines(
    session: AsyncSession, tenant_id: uuid.UUID, gr_id: uuid.UUID
) -> list[GoodsReceiptLine]:
    stmt = (
        select(GoodsReceiptLine)
        .where(GoodsReceiptLine.tenant_id == tenant_id, GoodsReceiptLine.gr_id == gr_id)
        .order_by(GoodsReceiptLine.line_number)
    )
    return list((await session.execute(stmt)).scalars().all())


async def list_goods_receipts(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    purchase_order_id: uuid.UUID | None = None,
    status: GoodsReceiptStatus | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Page[GoodsReceipt]:
    """Keyset-paginated GR list, newest first (D-014). The PO / status / date filters fold into the
    cursor fingerprint; the (tenant, status) and (tenant, purchase_order_id) indexes serve the
    filtered page (PERFORMANCE §1)."""
    stmt = select(GoodsReceipt).where(GoodsReceipt.tenant_id == tenant_id)
    if purchase_order_id is not None:
        stmt = stmt.where(GoodsReceipt.purchase_order_id == purchase_order_id)
    if status is not None:
        stmt = stmt.where(GoodsReceipt.status == GoodsReceiptStatus(status).value)
    if date_from is not None:
        stmt = stmt.where(GoodsReceipt.receipt_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(GoodsReceipt.receipt_date <= date_to)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(GoodsReceipt.created_at, SortDirection.DESC)],
        pk=GoodsReceipt.id,
        cursor=cursor,
        limit=limit,
        filters=filter_fingerprint(purchase_order_id, status, date_from, date_to),
    )


async def goods_receipts_for_po(
    session: AsyncSession, tenant_id: uuid.UUID, po_id: uuid.UUID
) -> list[GoodsReceipt]:
    """Every goods receipt raised against a PO (PLAN 6.3), newest first — the per-PO receipt history
    the PO detail / the 6.4 match read. Index-served by (tenant, purchase_order_id)."""
    stmt = (
        select(GoodsReceipt)
        .where(
            GoodsReceipt.tenant_id == tenant_id,
            GoodsReceipt.purchase_order_id == po_id,
        )
        .order_by(GoodsReceipt.created_at.desc())
    )
    return list((await session.execute(stmt)).scalars().all())
