"""Cost-centre report: the base aggregate grouped by the cost_center_id line dimension (D-021).

Controlling is a projection of the same universal journal as FI (D-021): the cost-centre report
reads ``cost_center_id`` straight off the posted line and groups balances by (cost centre, account).
Because it sums the SAME functional debit/credit columns as the trial balance, each cost centre's
per-account balances sum to that account's posting that carried the dimension — there is no separate
CO ledger to reconcile. No stored totals: a new posting tagged with a cost centre shows up
immediately on the next read.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.finance.models import CostCenter
from app.modules.finance.models.journal import JournalLine
from app.modules.finance.service.statements.base import (
    ZERO,
    _dimension_balances,
    load_account_meta,
    presentation_amount,
)


@dataclass(frozen=True)
class CostCenterAccountLine:
    """One account's net balance within a cost centre (presentation-signed)."""

    account_id: uuid.UUID
    account_code: str
    account_name: str
    amount: Decimal


@dataclass
class CostCenterSection:
    """A cost centre's per-account balances + its total over the period (D-021). ``cost_center_id``
    is None for the bucket of postings carrying no cost-centre dimension."""

    cost_center_id: uuid.UUID | None
    cost_center_code: str | None
    cost_center_name: str | None
    lines: list[CostCenterAccountLine] = field(default_factory=list)
    total: Decimal = ZERO


@dataclass
class CostCenterReport:
    """The cost-centre report for a period (D-021): one section per cost centre (optionally a single
    one when filtered), each with its per-account lines and total."""

    date_from: date
    date_to: date
    sections: list[CostCenterSection] = field(default_factory=list)


async def _cost_center_names(
    session: AsyncSession, tenant_id: uuid.UUID
) -> dict[uuid.UUID, tuple[str, str]]:
    """``{cost_center_id: (code, name)}`` for the tenant — labels for the report sections."""
    from sqlalchemy import select

    stmt = select(CostCenter.id, CostCenter.code, CostCenter.name).where(
        CostCenter.tenant_id == tenant_id
    )
    return {row.id: (row.code, row.name) for row in (await session.execute(stmt)).all()}


async def cost_center_report(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    date_from: date,
    date_to: date,
    cost_center_id: uuid.UUID | None = None,
) -> CostCenterReport:
    """Balances grouped by cost centre and account over ``[date_from, date_to]`` (D-021).

    Uses the dimension aggregate on ``JournalLine.cost_center_id``; ``cost_center_id`` narrows to
    one centre. Each line's signed base balance is re-signed to its natural magnitude. Sections are
    sorted by cost-centre code (the unassigned bucket last)."""
    balances = await _dimension_balances(
        session,
        tenant_id,
        JournalLine.cost_center_id,
        date_from=date_from,
        date_to=date_to,
        dimension_filter=cost_center_id,
    )
    meta = await load_account_meta(session, tenant_id)
    names = await _cost_center_names(session, tenant_id)

    sections: dict[uuid.UUID | None, CostCenterSection] = {}
    for (dim_value, account_id), signed in balances.items():
        account = meta.get(account_id)
        if account is None:
            continue
        amount = presentation_amount(account, signed)
        if amount == ZERO:
            continue
        section = sections.get(dim_value)
        if section is None:
            code, name = names.get(dim_value, (None, None)) if dim_value else (None, None)
            section = CostCenterSection(
                cost_center_id=dim_value, cost_center_code=code, cost_center_name=name
            )
            sections[dim_value] = section
        section.lines.append(
            CostCenterAccountLine(
                account_id=account_id,
                account_code=account.code,
                account_name=account.name,
                amount=amount,
            )
        )
        section.total += amount

    ordered = sorted(
        sections.values(),
        # Unassigned (None code) sorts last via a high sentinel key.
        key=lambda s: (s.cost_center_code is None, s.cost_center_code or ""),
    )
    for section in ordered:
        section.lines.sort(key=lambda line: line.account_code)
    return CostCenterReport(date_from=date_from, date_to=date_to, sections=ordered)
