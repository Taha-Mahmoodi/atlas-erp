"""The depreciation run engine (PLAN 4.10): per-period computation + the posting run.

**compute_depreciation** is the pure per-asset/per-period formula. ``period_index`` is the
asset's 1-based position in ITS OWN schedule (prior entry count + 1 — depreciation periods,
not calendar months), ``prior_accumulated`` the sum of its prior entries:

- STRAIGHT_LINE: drift-free cumulative formulation — amount(n) =
  quantize((cost - salvage) x n / life) - prior_accumulated, and the FINAL period (n >= life)
  takes exactly (cost - salvage) - prior_accumulated, so the schedule sums to cost - salvage
  EXACTLY (largest-remainder-style: per-period rounding can never drift because each period is
  cumulative-to-date minus what was already taken).
- DECLINING_BALANCE: amount(n) = quantize(NBV_start x annual_rate / 12), floored so NBV never
  crosses salvage (the crossing period takes NBV_start - salvage and lands EXACTLY on salvage);
  when the schedule exhausts (n >= life) the remainder to salvage is taken.

**run_depreciation** is set-based (PERFORMANCE §2): eligible ACTIVE assets are selected with a
NOT EXISTS anti-join on fin_depreciation_entries (an asset depreciates once per period — the
UNIQUE(tenant, asset, period) backbone makes overlapping runs collide at the DB); prior
accumulated amounts come from ONE grouped aggregate (no per-asset N+1); the entries are written
with ONE bulk executemany insert; and the run posts ONE journal entry with lines GROUPED per
(expense account, cost centre) on the debit side and per accumulated-depreciation account on
the credit side (document_type DEPRECIATION). Assets reaching cost - salvage flip
FULLY_DEPRECIATED. A re-run for a fully-depreciated period finds nothing eligible and returns
the existing POSTED run unchanged (the allocation-run idempotency pattern); the HTTP endpoint
is additionally Idempotent (D-013). Runs above DEPRECIATION_RUN_SYNC_MAX_ASSETS execute as a
``finance.depreciation_run`` background job (PERFORMANCE §3).

Reads + the asset-register projection live in ``service/depreciation_read.py`` (STRUCTURE
§8.4 split, the journal.py/journal_read.py precedent).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.core.exceptions import ValidationFailedError
from app.core.jobs import register_job
from app.core.money import currency_decimals, quantize_money
from app.core.numbering import claim_number, ensure_sequence
from app.modules.finance.constants import (
    DEPRECIATION_NUMBER_PADDING,
    DEPRECIATION_NUMBER_PREFIX,
    DEPRECIATION_POSTS_LINK,
    DEPRECIATION_RUN_DOC_TYPE,
    DEPRECIATION_RUN_JOB,
    DEPRECIATION_SEQUENCE_NAME,
    AssetStatus,
    DepreciationMethod,
    DepreciationRunStatus,
    DocumentType,
    PeriodStatus,
)
from app.modules.finance.models import Asset, DepreciationEntry, DepreciationRun, FiscalPeriod
from app.modules.finance.schemas import JournalEntryCreate, JournalLineCreate
from app.modules.finance.service.depreciation_read import existing_posted_run
from app.modules.finance.service.journal import create_draft_entry, post_entry


def compute_depreciation(
    asset: Asset, period_index: int, prior_accumulated: Decimal
) -> Decimal:
    """The per-period charge for ``asset`` at schedule position ``period_index`` (module
    docstring). Pure; quantized to the asset currency's minor unit; never negative and never
    takes NBV below salvage."""
    places = currency_decimals(asset.currency_code)
    cost = Decimal(str(asset.acquisition_cost))
    salvage = Decimal(str(asset.salvage_value))
    depreciable = cost - salvage
    if depreciable <= 0 or prior_accumulated >= depreciable:
        return Decimal(0)

    if asset.depreciation_method == DepreciationMethod.STRAIGHT_LINE.value:
        if period_index >= asset.useful_life_months:
            return depreciable - prior_accumulated
        cumulative = quantize_money(
            depreciable * period_index / asset.useful_life_months, places
        )
        return max(cumulative - prior_accumulated, Decimal(0))

    # DECLINING_BALANCE: NBV_start x (annual rate / 12), floored at salvage.
    nbv_start = cost - prior_accumulated
    if period_index >= asset.useful_life_months:
        return nbv_start - salvage
    annual_rate = Decimal(str(asset.declining_rate_percent)) / Decimal(100)
    amount = quantize_money(nbv_start * annual_rate / Decimal(12), places)
    if nbv_start - amount < salvage:
        amount = nbv_start - salvage
    return max(amount, Decimal(0))


def _eligible_assets_stmt(tenant_id: uuid.UUID, period_id: uuid.UUID):
    """ACTIVE assets NOT yet depreciated for ``period_id`` — the set-based anti-join."""
    already = select(DepreciationEntry.id).where(
        DepreciationEntry.tenant_id == tenant_id,
        DepreciationEntry.asset_id == Asset.id,
        DepreciationEntry.fiscal_period_id == period_id,
    )
    return select(Asset).where(
        Asset.tenant_id == tenant_id,
        Asset.status == AssetStatus.ACTIVE.value,
        ~already.exists(),
    )


async def count_eligible_assets(
    session: AsyncSession, tenant_id: uuid.UUID, period_id: uuid.UUID
) -> int:
    """How many assets a run for ``period_id`` would touch — the router's sync/background
    threshold probe (PERFORMANCE §3), one COUNT query."""
    stmt = select(func.count()).select_from(
        _eligible_assets_stmt(tenant_id, period_id).subquery()
    )
    return (await session.execute(stmt)).scalar_one()


async def _require_open_period(
    session: AsyncSession, tenant_id: uuid.UUID, period_id: uuid.UUID, run_date: date
) -> FiscalPeriod:
    """The target period must exist, be OPEN (service half of D-018; the journal's period
    trigger is the bypass-proof backstop) and contain ``run_date`` (the posted entry's date —
    the trigger re-derives the period from it, so a mismatch would post elsewhere)."""
    period = await session.get(FiscalPeriod, period_id)
    if period is None or period.tenant_id != tenant_id:
        raise ValidationFailedError(
            message="The fiscal period does not exist in this tenant",
            code="finance.depreciation_period_not_found",
            details={"fiscal_period_id": str(period_id)},
        )
    if period.status != PeriodStatus.OPEN.value:
        raise ValidationFailedError(
            message="Depreciation cannot post into a closed period",
            code="finance.period_closed",
            details={"fiscal_period_id": str(period_id)},
        )
    if not period.start_date <= run_date <= period.end_date:
        raise ValidationFailedError(
            message="run_date must fall inside the fiscal period being depreciated",
            code="finance.depreciation_run_date_outside_period",
            details={"run_date": run_date.isoformat()},
        )
    return period


def _grouped_lines(
    debits: dict[tuple[uuid.UUID, uuid.UUID | None], Decimal],
    credits: dict[uuid.UUID, Decimal],
) -> list[JournalLineCreate]:
    """One compact entry: Dr per (expense account, cost centre), Cr per accumulated account —
    aggregated, never per-asset lines. Sorted for deterministic line numbering."""
    lines = [
        JournalLineCreate(
            account_id=account_id,
            description="Depreciation expense",
            transaction_debit_amount=amount,
            cost_center_id=cost_center_id,
        )
        for (account_id, cost_center_id), amount in sorted(
            debits.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1] or ""))
        )
    ]
    lines.extend(
        JournalLineCreate(
            account_id=account_id,
            description="Accumulated depreciation",
            transaction_credit_amount=amount,
        )
        for account_id, amount in sorted(credits.items(), key=lambda kv: str(kv[0]))
    )
    return lines


async def _nothing_to_depreciate(
    session: AsyncSession, tenant_id: uuid.UUID, period_id: uuid.UUID
) -> DepreciationRun:
    """Nothing eligible: return the period's existing POSTED run unchanged (idempotent
    re-run, the allocation pattern) or raise a clear 422 when the period never ran."""
    existing = await existing_posted_run(session, tenant_id, period_id)
    if existing is not None:
        return existing
    raise ValidationFailedError(
        message="No active assets to depreciate for this period",
        code="finance.depreciation_nothing_to_depreciate",
        details={"fiscal_period_id": str(period_id)},
    )


async def run_depreciation(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    period_id: uuid.UUID,
    run_date: date,
) -> DepreciationRun:
    """Depreciate every eligible ACTIVE asset for one period (module docstring). The SQL
    statement count is CONSTANT in the asset count (selection, ONE grouped prior aggregate,
    ONE bulk entry insert, one grouped journal entry, run bookkeeping) plus one status write
    per asset that flips FULLY_DEPRECIATED. Caller commits via uow (D-011)."""
    period = await _require_open_period(session, tenant_id, period_id, run_date)
    assets = list(
        (
            await session.execute(
                _eligible_assets_stmt(tenant_id, period_id).order_by(Asset.asset_number)
            )
        )
        .scalars()
        .all()
    )
    if not assets:
        return await _nothing_to_depreciate(session, tenant_id, period_id)
    currencies = {asset.currency_code for asset in assets}
    if len(currencies) > 1:
        raise ValidationFailedError(
            message="All assets in a depreciation run must share one currency",
            code="finance.depreciation_mixed_currencies",
            details={"currencies": sorted(currencies)},
        )
    currency_code = assets[0].currency_code

    # Prior schedule position + accumulated per asset, in ONE grouped query (no N+1).
    prior_rows = (
        await session.execute(
            select(
                DepreciationEntry.asset_id,
                func.count(DepreciationEntry.id),
                func.coalesce(func.sum(DepreciationEntry.amount), 0),
            )
            .where(
                DepreciationEntry.tenant_id == tenant_id,
                DepreciationEntry.asset_id.in_([asset.id for asset in assets]),
            )
            .group_by(DepreciationEntry.asset_id)
        )
    ).all()
    prior = {asset_id: (count, Decimal(str(total))) for asset_id, count, total in prior_rows}

    entry_rows: list[dict[str, Any]] = []
    debits: dict[tuple[uuid.UUID, uuid.UUID | None], Decimal] = {}
    credits: dict[uuid.UUID, Decimal] = {}
    flipped: list[Asset] = []
    total = Decimal(0)
    for asset in assets:
        prior_count, prior_accumulated = prior.get(asset.id, (0, Decimal(0)))
        amount = compute_depreciation(asset, prior_count + 1, prior_accumulated)
        if amount <= 0:  # nothing this period; the asset stays eligible for later runs
            continue
        accumulated_after = prior_accumulated + amount
        nbv_after = Decimal(str(asset.acquisition_cost)) - accumulated_after
        entry_rows.append(
            {
                "id": uuid.uuid4(),
                "tenant_id": tenant_id,
                "asset_id": asset.id,
                "fiscal_period_id": period_id,
                "amount": amount,
                "accumulated_after": accumulated_after,
                "nbv_after": nbv_after,
            }
        )
        debit_key = (asset.depreciation_expense_account_id, asset.cost_center_id)
        debits[debit_key] = debits.get(debit_key, Decimal(0)) + amount
        credit_key = asset.accumulated_depreciation_account_id
        credits[credit_key] = credits.get(credit_key, Decimal(0)) + amount
        total += amount
        if nbv_after == Decimal(str(asset.salvage_value)):
            flipped.append(asset)

    if not entry_rows:
        return await _nothing_to_depreciate(session, tenant_id, period_id)

    # ONE grouped journal entry for the whole run (Dr expense / Cr accumulated).
    entry = await create_draft_entry(
        session,
        tenant_id,
        JournalEntryCreate(
            posting_date=run_date,
            currency_code=currency_code,
            description=f"Depreciation {period.name}",
            document_type=DocumentType.DEPRECIATION,
            lines=_grouped_lines(debits, credits),
        ),
    )
    await post_entry(session, tenant_id, entry.id)

    run = await _track_run(
        session, tenant_id, period_id, run_date, entry.id, total, len(entry_rows)
    )
    # The PERFORMANCE §2 bulk insert: one ORM-enabled executemany, explicit tenant_id per row.
    # The UNIQUE(tenant, asset, period) backbone rejects any overlapping run here.
    await session.execute(
        insert(DepreciationEntry), [{**row, "run_id": run.id} for row in entry_rows]
    )
    await docflow.link_documents(
        session,
        tenant_id,
        predecessor=run.document_id,
        successor=entry.document_id,
        link_type=DEPRECIATION_POSTS_LINK,
    )

    # Loaded-object status flips (audited, D-010); registry status follows.
    for asset in flipped:
        asset.status = AssetStatus.FULLY_DEPRECIATED.value
        await docflow.set_document_status(
            session, tenant_id, asset.document_id, status=AssetStatus.FULLY_DEPRECIATED.value
        )
    await session.flush()
    return run


async def _track_run(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    period_id: uuid.UUID,
    run_date: date,
    journal_entry_id: uuid.UUID,
    total_amount: Decimal,
    asset_count: int,
) -> DepreciationRun:
    """Register the run document, claim its gapless DEP number, persist the run row (D-012)."""
    run_id = uuid.uuid4()
    document = await docflow.register_document(
        session,
        tenant_id,
        DEPRECIATION_RUN_DOC_TYPE,
        run_id,
        doc_number=None,
        status=DepreciationRunStatus.POSTED.value,
    )
    await ensure_sequence(
        session,
        tenant_id,
        DEPRECIATION_SEQUENCE_NAME,
        DEPRECIATION_NUMBER_PREFIX,
        DEPRECIATION_NUMBER_PADDING,
        year_reset=True,
    )
    run_number = await claim_number(
        session, tenant_id, DEPRECIATION_SEQUENCE_NAME, on_date=run_date
    )
    run = DepreciationRun(
        id=run_id,
        tenant_id=tenant_id,
        document_id=document.id,
        fiscal_period_id=period_id,
        run_number=run_number,
        run_date=run_date,
        status=DepreciationRunStatus.POSTED.value,
        journal_entry_id=journal_entry_id,
        total_amount=total_amount,
        asset_count=asset_count,
    )
    session.add(run)
    await session.flush()
    await docflow.set_document_status(
        session,
        tenant_id,
        document.id,
        status=DepreciationRunStatus.POSTED.value,
        doc_number=run_number,
    )
    return run


@register_job(DEPRECIATION_RUN_JOB)
async def depreciation_run_job(
    session: AsyncSession, tenant_id: uuid.UUID, payload: dict[str, Any]
) -> dict[str, Any]:
    """Background-job handler (PERFORMANCE §3): a run over >100 assets executes as a job and
    the endpoint returns 202 {job_id}. Delegates to :func:`run_depreciation`."""
    run = await run_depreciation(
        session,
        tenant_id,
        uuid.UUID(payload["fiscal_period_id"]),
        date.fromisoformat(payload["run_date"]),
    )
    await session.refresh(run)
    return {
        "run_id": str(run.id),
        "run_number": run.run_number,
        "journal_entry_id": str(run.journal_entry_id),
        "asset_count": run.asset_count,
        "total_amount": str(run.total_amount),
    }
