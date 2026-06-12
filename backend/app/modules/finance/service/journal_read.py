"""Journal read surface (D-017/D-021): entry/line loaders + the paginated list.

Split out of ``service/journal.py`` so the write engine (create/post/reverse) stays under the
STRUCTURE §3 400-line cap; both halves are the one journal aggregate. The write engine imports the
loaders from here; the router imports the read functions through the ``service`` package surface.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.pagination import OrderKey, SortDirection, filter_fingerprint, paginate
from app.core.schemas import Page
from app.modules.finance.constants import EntryStatus
from app.modules.finance.models import JournalEntry, JournalLine


async def load_lines(
    session: AsyncSession, tenant_id: uuid.UUID, entry_id: uuid.UUID
) -> list[JournalLine]:
    """Lines of an entry ordered by line_number (the order posting/reversal iterate in)."""
    stmt = (
        select(JournalLine)
        .where(
            JournalLine.tenant_id == tenant_id,
            JournalLine.journal_entry_id == entry_id,
        )
        .order_by(JournalLine.line_number)
    )
    return list((await session.execute(stmt)).scalars().all())


async def get_entry(
    session: AsyncSession, tenant_id: uuid.UUID, entry_id: uuid.UUID
) -> JournalEntry:
    entry = await session.get(JournalEntry, entry_id)
    if entry is None or entry.tenant_id != tenant_id:
        raise NotFoundError(
            message="Journal entry not found", code="finance.journal_entry_not_found"
        )
    return entry


async def get_entry_with_lines(
    session: AsyncSession, tenant_id: uuid.UUID, entry_id: uuid.UUID
) -> tuple[JournalEntry, list[JournalLine]]:
    """The entry plus its ordered lines (the GET /{id} and post/reverse response shape). 404 if
    the entry is unknown to this tenant."""
    entry = await get_entry(session, tenant_id, entry_id)
    lines = await load_lines(session, tenant_id, entry_id)
    return entry, lines


def entry_totals(lines: list[JournalLine]) -> tuple[Decimal, Decimal]:
    """(total functional debit, total functional credit) over the lines — the balance check
    operand. MoneyType result values are Decimal, so the sum is exact (D-015)."""
    debit = sum((line.functional_debit_amount for line in lines), Decimal(0))
    credit = sum((line.functional_credit_amount for line in lines), Decimal(0))
    return debit, credit


async def list_entries(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    cursor: str | None,
    limit: int,
    status: str | None = None,
) -> Page[JournalEntry]:
    """Keyset-paginated entry list, newest posting first (D-014). Status filter folds into the
    cursor fingerprint."""
    stmt = select(JournalEntry).where(JournalEntry.tenant_id == tenant_id)
    if status is not None:
        stmt = stmt.where(JournalEntry.status == EntryStatus(status).value)
    return await paginate(
        session,
        stmt,
        order_by=[
            OrderKey(JournalEntry.posting_date, SortDirection.DESC),
            OrderKey(JournalEntry.created_at, SortDirection.DESC),
        ],
        pk=JournalEntry.id,
        cursor=cursor,
        limit=limit,
        filters=filter_fingerprint(status),
    )
