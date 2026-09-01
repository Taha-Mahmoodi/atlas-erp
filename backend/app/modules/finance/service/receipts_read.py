"""Customer-receipt READS (PLAN 4.6): one receipt, its allocations, the paginated list.

Split out of ``customer_receipts.py`` at the STRUCTURE §8.4 400-line cap, the way
``journal_read.py`` and ``depreciation_read.py`` were split from their write engines: the write
file keeps the posting/clearing spine, this one keeps the projections over what it wrote. No
behaviour change — the three functions moved verbatim and are re-exported from the same
``service`` package surface, so every existing call site is unaffected.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.modules.finance.models import CustomerReceipt, CustomerReceiptAllocation


async def get_customer_receipt(
    session: AsyncSession, tenant_id: uuid.UUID, receipt_id: uuid.UUID, *, for_update: bool = False
) -> CustomerReceipt:
    """One receipt, or 404. ``for_update`` takes the row lock before the caller reads
    ``unapplied_amount`` to spend it (D-086): on Postgres a second application waits and then reads
    the drawn-down balance, on SQLite FOR UPDATE is a no-op (D-020/D-036, the ``inv_stock_quants``
    precedent) and the DB CHECK is the backstop. ``populate_existing`` is not optional here — a
    plain re-SELECT returns the session's already-loaded row with its STALE balance, which is the
    lost update the lock exists to prevent."""
    if for_update:
        stmt = (
            select(CustomerReceipt)
            .where(CustomerReceipt.tenant_id == tenant_id, CustomerReceipt.id == receipt_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        receipt = (await session.execute(stmt)).scalar_one_or_none()
    else:
        receipt = await session.get(CustomerReceipt, receipt_id)
    if receipt is None or receipt.tenant_id != tenant_id:
        raise NotFoundError(
            message="Customer receipt not found", code="finance.customer_receipt_not_found"
        )
    return receipt


async def get_receipt_allocations(
    session: AsyncSession, tenant_id: uuid.UUID, receipt_id: uuid.UUID
) -> list[CustomerReceiptAllocation]:
    stmt = (
        select(CustomerReceiptAllocation)
        .where(
            CustomerReceiptAllocation.tenant_id == tenant_id,
            CustomerReceiptAllocation.receipt_id == receipt_id,
        )
        .order_by(CustomerReceiptAllocation.created_at)
    )
    return list((await session.execute(stmt)).scalars().all())


async def list_customer_receipts(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    cursor: str | None,
    limit: int,
    partner_id: uuid.UUID | None = None,
) -> object:
    """Keyset-paginated receipt list, newest receipt_date first (D-014). ``partner_id`` folds into
    the cursor fingerprint."""
    from app.core.pagination import OrderKey, SortDirection, filter_fingerprint, paginate

    stmt = select(CustomerReceipt).where(CustomerReceipt.tenant_id == tenant_id)
    if partner_id is not None:
        stmt = stmt.where(CustomerReceipt.partner_id == partner_id)
    return await paginate(
        session,
        stmt,
        order_by=[
            OrderKey(CustomerReceipt.receipt_date, SortDirection.DESC),
            OrderKey(CustomerReceipt.created_at, SortDirection.DESC),
        ],
        pk=CustomerReceipt.id,
        cursor=cursor,
        limit=limit,
        filters=filter_fingerprint(partner_id),
    )
