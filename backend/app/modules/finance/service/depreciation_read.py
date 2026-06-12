"""Depreciation reads + the asset-register projection (PLAN 4.10), split out of
``service/depreciation.py`` to keep both under the STRUCTURE §8.4 cap (the
journal.py/journal_read.py precedent).

**asset_register** is a pure projection: cost / accumulated-to-date / NBV recomputed from
SUM(fin_depreciation_entries.amount) bounded by the fiscal periods ENDING on or before
``as_of`` — the entries' ``*_after`` columns are per-entry audit trail only, never read as
totals, and no NBV is stored on the asset row (D-021 spirit: reports are projections).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.pagination import DEFAULT_LIMIT, OrderKey, SortDirection, filter_fingerprint, paginate
from app.core.schemas import Page
from app.modules.finance.constants import AssetStatus, DepreciationRunStatus
from app.modules.finance.models import Asset, DepreciationEntry, DepreciationRun, FiscalPeriod


async def get_depreciation_run(
    session: AsyncSession, tenant_id: uuid.UUID, run_id: uuid.UUID
) -> DepreciationRun:
    run = await session.get(DepreciationRun, run_id)
    if run is None or run.tenant_id != tenant_id:
        raise NotFoundError(
            message="Depreciation run not found", code="finance.depreciation_run_not_found"
        )
    return run


async def existing_posted_run(
    session: AsyncSession, tenant_id: uuid.UUID, period_id: uuid.UUID
) -> DepreciationRun | None:
    """The newest POSTED run for a period, or None — the run engine's idempotency probe."""
    stmt = (
        select(DepreciationRun)
        .where(
            DepreciationRun.tenant_id == tenant_id,
            DepreciationRun.fiscal_period_id == period_id,
            DepreciationRun.status == DepreciationRunStatus.POSTED.value,
        )
        .order_by(DepreciationRun.created_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalars().first()


async def list_depreciation_runs(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
    fiscal_period_id: uuid.UUID | None = None,
) -> Page[DepreciationRun]:
    """Keyset-paginated runs, newest run_date first (D-014)."""
    stmt = select(DepreciationRun).where(DepreciationRun.tenant_id == tenant_id)
    if fiscal_period_id is not None:
        stmt = stmt.where(DepreciationRun.fiscal_period_id == fiscal_period_id)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(DepreciationRun.run_date, SortDirection.DESC)],
        pk=DepreciationRun.id,
        cursor=cursor,
        limit=limit,
        filters=filter_fingerprint(fiscal_period_id),
    )


async def list_depreciation_entries(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    run_id: uuid.UUID,
    *,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Page[DepreciationEntry]:
    """Keyset-paginated entries of one run (covered by the (tenant, run_id) index)."""
    stmt = select(DepreciationEntry).where(
        DepreciationEntry.tenant_id == tenant_id, DepreciationEntry.run_id == run_id
    )
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(DepreciationEntry.asset_id, SortDirection.ASC)],
        pk=DepreciationEntry.id,
        cursor=cursor,
        limit=limit,
        filters=filter_fingerprint(run_id),
    )


@dataclass(frozen=True)
class AssetRegisterLine:
    """One register row: accumulated/NBV recomputed from the entries (module docstring)."""

    asset: Asset
    accumulated_depreciation: Decimal

    @property
    def net_book_value(self) -> Decimal:
        return Decimal(str(self.asset.acquisition_cost)) - self.accumulated_depreciation


async def asset_register(
    session: AsyncSession, tenant_id: uuid.UUID, as_of: date
) -> list[AssetRegisterLine]:
    """The register report as of a date: every activated asset acquired by ``as_of`` with
    cost, accumulated depreciation to date (SUM over entries of periods ENDING on or before
    ``as_of``) and NBV — ONE statement, a pure projection with no stored totals."""
    bounded_periods = select(FiscalPeriod.id).where(
        FiscalPeriod.tenant_id == tenant_id, FiscalPeriod.end_date <= as_of
    )
    accumulated = (
        select(
            DepreciationEntry.asset_id.label("asset_id"),
            func.sum(DepreciationEntry.amount).label("accumulated"),
        )
        .where(
            DepreciationEntry.tenant_id == tenant_id,
            DepreciationEntry.fiscal_period_id.in_(bounded_periods),
        )
        .group_by(DepreciationEntry.asset_id)
        .subquery()
    )
    stmt = (
        select(Asset, func.coalesce(accumulated.c.accumulated, 0))
        .outerjoin(accumulated, accumulated.c.asset_id == Asset.id)
        .where(
            Asset.tenant_id == tenant_id,
            Asset.status != AssetStatus.DRAFT.value,
            Asset.acquisition_date <= as_of,
        )
        .order_by(Asset.asset_number)
    )
    rows = (await session.execute(stmt)).all()
    return [
        AssetRegisterLine(asset=asset, accumulated_depreciation=Decimal(str(total)))
        for asset, total in rows
    ]
