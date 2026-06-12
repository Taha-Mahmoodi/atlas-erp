"""Fiscal year/period business logic and the open/close lifecycle (D-018).

- ``create_fiscal_year`` generates ``period_count`` contiguous, non-overlapping monthly
  periods (D-018); the generated periods exactly tile the year.
- period lifecycle: ``close_period`` / ``open_period`` flip a period's status; the
  "cannot close a period while unposted drafts exist in it" rule and the DB-level
  posting-rejection trigger arrive with the journal (4.2) — see ``assert_period_closable``
  for the clearly-marked seam. ``close_fiscal_year`` requires all the year's periods closed.
"""

from __future__ import annotations

import calendar
import uuid
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.pagination import (
    DEFAULT_LIMIT,
    OrderKey,
    SortDirection,
    filter_fingerprint,
    paginate,
)
from app.core.schemas import Page
from app.modules.finance.constants import EntryStatus, PeriodStatus
from app.modules.finance.models import FiscalPeriod, FiscalYear, JournalEntry
from app.modules.finance.schemas import FiscalYearCreate


def _add_months(anchor: date, months: int) -> date:
    """``anchor`` shifted forward by ``months`` calendar months, clamped to the target
    month's last valid day (so 2026-01-31 + 1 month = 2026-02-28). Used to walk monthly
    period boundaries without an external date library."""
    total = anchor.month - 1 + months
    year = anchor.year + total // 12
    month = total % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(anchor.day, last_day))


def generate_periods(start_date: date, period_count: int) -> list[tuple[int, date, date]]:
    """Build ``period_count`` contiguous, non-overlapping monthly period boundaries from
    ``start_date`` (D-018). Returns ``(period_number, start, end)`` tuples where each period
    runs from its start to the day before the next period's start, so the periods exactly
    tile [start_date, last period end] with no gaps and no overlaps."""
    if period_count < 1:
        raise ValidationFailedError(
            message="A fiscal year needs at least one period",
            code="finance.invalid_period_count",
        )
    boundaries: list[tuple[int, date, date]] = []
    period_start = start_date
    for number in range(1, period_count + 1):
        next_start = _add_months(start_date, number)
        period_end = next_start - timedelta(days=1)
        boundaries.append((number, period_start, period_end))
        period_start = next_start
    return boundaries


async def create_fiscal_year(
    session: AsyncSession, tenant_id: uuid.UUID, payload: FiscalYearCreate
) -> FiscalYear:
    """Create a fiscal year and auto-generate its monthly periods (D-018). The year's
    end_date is set to the last generated period's end so the periods exactly tile the year.
    All periods (and the year) start OPEN. Rejects a duplicate year code with a ConflictError."""
    existing = (
        await session.execute(
            select(FiscalYear).where(
                FiscalYear.tenant_id == tenant_id, FiscalYear.code == payload.code
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError(
            message=f"A fiscal year with code {payload.code} already exists",
            code="finance.fiscal_year_code_conflict",
            details={"code": payload.code},
        )

    boundaries = generate_periods(payload.start_date, payload.period_count)
    year_end = boundaries[-1][2]
    year = FiscalYear(
        tenant_id=tenant_id,
        code=payload.code,
        name=payload.name,
        start_date=payload.start_date,
        end_date=year_end,
        status=PeriodStatus.OPEN.value,
    )
    session.add(year)
    await session.flush()  # year.id needed for the period FKs below

    for number, period_start, period_end in boundaries:
        session.add(
            FiscalPeriod(
                tenant_id=tenant_id,
                fiscal_year_id=year.id,
                period_number=number,
                name=f"{payload.code}-{number:02d}",
                start_date=period_start,
                end_date=period_end,
                status=PeriodStatus.OPEN.value,
            )
        )
    await session.flush()
    return year


async def list_fiscal_years(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Page[FiscalYear]:
    """Keyset-paginated fiscal years, earliest first (start_date + id tiebreaker; #27)."""
    stmt = select(FiscalYear).where(FiscalYear.tenant_id == tenant_id)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(FiscalYear.start_date, SortDirection.ASC)],
        pk=FiscalYear.id,
        cursor=cursor,
        limit=limit,
    )


async def list_fiscal_periods(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    fiscal_year_id: uuid.UUID | None = None,
    *,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Page[FiscalPeriod]:
    """Keyset-paginated fiscal periods, earliest first (start_date + id tiebreaker). The
    fiscal_year_id filter folds into the cursor fingerprint (D-014; #27)."""
    stmt = select(FiscalPeriod).where(FiscalPeriod.tenant_id == tenant_id)
    if fiscal_year_id is not None:
        stmt = stmt.where(FiscalPeriod.fiscal_year_id == fiscal_year_id)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(FiscalPeriod.start_date, SortDirection.ASC)],
        pk=FiscalPeriod.id,
        cursor=cursor,
        limit=limit,
        filters=filter_fingerprint(fiscal_year_id),
    )


async def _require_period(
    session: AsyncSession, tenant_id: uuid.UUID, period_id: uuid.UUID
) -> FiscalPeriod:
    period = await session.get(FiscalPeriod, period_id)
    if period is None or period.tenant_id != tenant_id:
        raise NotFoundError(
            message="Fiscal period not found", code="finance.fiscal_period_not_found"
        )
    return period


async def assert_period_closable(
    session: AsyncSession, tenant_id: uuid.UUID, period: FiscalPeriod
) -> None:
    """The close-time invariant (D-018): a period may close only if it is not already closed
    AND it holds no DRAFT journal entries dated within it.

    Closing a period asserts it is settled; a DRAFT entry dated inside it is unfinished work
    that would become unpostable (the period trigger would then reject its posting). So we
    refuse the close until every draft in the period is posted or removed. Posted/reversed
    entries are fine — they are immutable settled facts. This is the service-level half of
    D-018; the DB-level period-posting trigger on ``fin_journal_entries`` is the bypass-proof
    backstop for postings themselves.
    """
    if period.status == PeriodStatus.CLOSED.value:
        raise ValidationFailedError(
            message="Fiscal period is already closed",
            code="finance.period_already_closed",
        )
    draft_in_period = (
        await session.execute(
            select(JournalEntry.id).where(
                JournalEntry.tenant_id == tenant_id,
                JournalEntry.status == EntryStatus.DRAFT.value,
                JournalEntry.posting_date >= period.start_date,
                JournalEntry.posting_date <= period.end_date,
            )
        )
    ).first()
    if draft_in_period is not None:
        raise ValidationFailedError(
            message="Cannot close a period that contains draft journal entries",
            code="finance.period_has_draft_entries",
        )


async def close_period(
    session: AsyncSession, tenant_id: uuid.UUID, period_id: uuid.UUID
) -> FiscalPeriod:
    """Close a fiscal period (D-018). Runs the closable check (the journal seam above) then
    sets status CLOSED. Once the journal exists, postings dated into this period are rejected
    at both the service and DB level."""
    period = await _require_period(session, tenant_id, period_id)
    await assert_period_closable(session, tenant_id, period)
    period.status = PeriodStatus.CLOSED.value
    await session.flush()
    return period


async def open_period(
    session: AsyncSession, tenant_id: uuid.UUID, period_id: uuid.UUID
) -> FiscalPeriod:
    """Reopen a closed fiscal period (D-018). Reopening a period whose year is already CLOSED
    is refused — a closed year asserts every period in it is settled."""
    period = await _require_period(session, tenant_id, period_id)
    year = await session.get(FiscalYear, period.fiscal_year_id)
    if year is not None and year.status == PeriodStatus.CLOSED.value:
        raise ValidationFailedError(
            message="Cannot reopen a period whose fiscal year is closed",
            code="finance.fiscal_year_closed",
        )
    period.status = PeriodStatus.OPEN.value
    await session.flush()
    return period


async def close_fiscal_year(
    session: AsyncSession, tenant_id: uuid.UUID, fiscal_year_id: uuid.UUID
) -> FiscalYear:
    """Close a fiscal year, allowed only once every one of its periods is CLOSED (D-018) — a
    closed year is the assertion that the whole year is settled."""
    year = await session.get(FiscalYear, fiscal_year_id)
    if year is None or year.tenant_id != tenant_id:
        raise NotFoundError(
            message="Fiscal year not found", code="finance.fiscal_year_not_found"
        )
    open_periods = (
        await session.execute(
            select(FiscalPeriod.id).where(
                FiscalPeriod.tenant_id == tenant_id,
                FiscalPeriod.fiscal_year_id == fiscal_year_id,
                FiscalPeriod.status == PeriodStatus.OPEN.value,
            )
        )
    ).first()
    if open_periods is not None:
        raise ValidationFailedError(
            message="Cannot close a fiscal year while any of its periods is open",
            code="finance.fiscal_year_has_open_periods",
        )
    year.status = PeriodStatus.CLOSED.value
    await session.flush()
    return year
