"""Invoice-match reads + tolerance config (PLAN 6.4, D-042), split from ``invoice_matches.py`` at
the 400-line cap (the goods_receipts reads precedent). Re-exported with the writes from the package
``__init__`` as one ``service`` surface.

The match get/lines/list reads plus the per-tenant tolerance resolution + upsert:
``resolve_tolerances`` returns the active (price%, quantity%) the create step evaluates each line
against, falling back to the constants DEFAULTS when a tenant has not configured a row (the
strict-0% default — a price change must be a deliberate decision).
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
from app.modules.procurement.constants import (
    DEFAULT_PRICE_TOLERANCE_PERCENT,
    DEFAULT_QUANTITY_TOLERANCE_PERCENT,
    MatchStatus,
)
from app.modules.procurement.models import InvoiceMatch, InvoiceMatchLine, MatchTolerance
from app.modules.procurement.schemas import MatchToleranceUpsert


async def get_invoice_match(
    session: AsyncSession, tenant_id: uuid.UUID, match_id: uuid.UUID
) -> InvoiceMatch:
    match = await session.get(InvoiceMatch, match_id)
    if match is None or match.tenant_id != tenant_id:
        raise NotFoundError(
            message="Invoice match not found", code="procurement.invoice_match_not_found"
        )
    return match


async def get_invoice_match_lines(
    session: AsyncSession, tenant_id: uuid.UUID, match_id: uuid.UUID
) -> list[InvoiceMatchLine]:
    stmt = (
        select(InvoiceMatchLine)
        .where(InvoiceMatchLine.tenant_id == tenant_id, InvoiceMatchLine.match_id == match_id)
        .order_by(InvoiceMatchLine.line_number)
    )
    return list((await session.execute(stmt)).scalars().all())


async def list_invoice_matches(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    purchase_order_id: uuid.UUID | None = None,
    status: str | None = None,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Page[InvoiceMatch]:
    """Keyset-paginated match list, newest first (D-014). purchase_order_id + status filters fold
    into the cursor fingerprint; the (tenant, status) / (tenant, po) indexes serve the filtered
    page (PERFORMANCE §1)."""
    stmt = select(InvoiceMatch).where(InvoiceMatch.tenant_id == tenant_id)
    if purchase_order_id is not None:
        stmt = stmt.where(InvoiceMatch.purchase_order_id == purchase_order_id)
    if status is not None:
        stmt = stmt.where(InvoiceMatch.status == MatchStatus(status).value)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(InvoiceMatch.created_at, SortDirection.DESC)],
        pk=InvoiceMatch.id,
        cursor=cursor,
        limit=limit,
        filters=filter_fingerprint(purchase_order_id, status),
    )


# --- Tolerance config ---------------------------------------------------------


async def _get_tolerance_row(
    session: AsyncSession, tenant_id: uuid.UUID
) -> MatchTolerance | None:
    stmt = select(MatchTolerance).where(MatchTolerance.tenant_id == tenant_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def resolve_tolerances(
    session: AsyncSession, tenant_id: uuid.UUID
) -> tuple[Decimal, Decimal]:
    """The active (price%, quantity%) tolerance band for a tenant (PLAN 6.4, D-042): the configured
    ``proc_match_tolerances`` row if present, else the constants DEFAULTS (strict 0%). Returned as
    Decimals the create step evaluates each line's deviation against."""
    row = await _get_tolerance_row(session, tenant_id)
    if row is None:
        return (
            Decimal(DEFAULT_PRICE_TOLERANCE_PERCENT),
            Decimal(DEFAULT_QUANTITY_TOLERANCE_PERCENT),
        )
    return Decimal(str(row.price_tolerance_percent)), Decimal(str(row.quantity_tolerance_percent))


async def get_match_tolerance(
    session: AsyncSession, tenant_id: uuid.UUID
) -> MatchTolerance | None:
    """The tenant's configured tolerance row, or None when it runs on the defaults (PLAN 6.4). The
    read the GET endpoint returns."""
    return await _get_tolerance_row(session, tenant_id)


async def upsert_match_tolerance(
    session: AsyncSession, tenant_id: uuid.UUID, payload: MatchToleranceUpsert
) -> MatchTolerance:
    """Set (or replace) the tenant's single tolerance row (PLAN 6.4). Loaded-object mutation on an
    existing row so audit captures the change; inserts when absent. The DB CHECK guarantees the
    percentages are non-negative on both engines."""
    row = await _get_tolerance_row(session, tenant_id)
    if row is not None:
        row.price_tolerance_percent = payload.price_tolerance_percent
        row.quantity_tolerance_percent = payload.quantity_tolerance_percent
        await session.flush()
        return row
    row = MatchTolerance(
        tenant_id=tenant_id,
        price_tolerance_percent=payload.price_tolerance_percent,
        quantity_tolerance_percent=payload.quantity_tolerance_percent,
    )
    session.add(row)
    await session.flush()
    return row
