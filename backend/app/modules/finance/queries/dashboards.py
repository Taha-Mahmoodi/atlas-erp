"""Dashboard KPI aggregates (part of finance's cross-module read contract, STRUCTURE §5 / D-058).

Three SANCTIONED finance/queries additions the REPORTING module (PLAN 13.1) reads DOWNWARD for its
role-based dashboard cards — cash position, AR/AP aging summaries, and the WIP-clearing balance.
Reporting is the newest module and the top of the dependency order: it imports ONLY other modules'
``queries`` (never their service/models), so the aging projections the AR/AP routers build in
``finance/service/{ar,ap}_aging.py`` are re-exposed here as a thin BUCKET-SUMMARY (the dashboard
card needs the rolled-up buckets, not every partner line). Each is ONE bounded aggregate — a fixed
query count per KPI, never N+1 (PERFORMANCE §6); CO/cash figures are projections of the journal
(D-021), never stored totals.

Every function takes an explicit ``tenant_id`` and runs under the caller's tenant context, so the
D-007 filter applies on top of the explicit predicate — ordinary tenant-scoped reads, not a bypass.
"""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.finance.constants import WIP_CLEARING
from app.modules.finance.models import Account, JournalLine, PostingDefault

ZERO = Decimal("0")


@dataclass(frozen=True)
class AgingBuckets:
    """A rolled-up aging summary for the dashboard card (D-058): the four bucket totals + grand
    total in functional/transaction currency, no per-partner lines (the AR/AP routers serve those).
    The reporting ``AgingSummary`` schema maps from this — ``current`` (not yet due), ``d30`` (1-30
    days past due), ``d60`` (31-60), ``d90plus`` (61+; the dashboard collapses the AR/AP report's
    61-90 + over-90 tail into one 90+ bucket per the build-spec card shape)."""

    current: Decimal
    d30: Decimal
    d60: Decimal
    d90plus: Decimal
    total: Decimal


async def cash_position(
    session: AsyncSession, tenant_id: uuid.UUID, *, as_of: date
) -> Decimal:
    """The tenant's CASH POSITION as of ``as_of`` (PLAN 13.1, D-058): the summed presentation
    balance of every ``is_cash_equivalent`` account over the POSTED journal (cash + bank). A
    projection of the universal journal (D-021) — never a stored total: ONE aggregate joins the
    journal lines to their cash-equivalent accounts and sums (functional debit − credit), date-
    bounded to ``as_of`` (PERFORMANCE §1: date-bounded, the covering ``ix_fin_journal_lines_proj``
    index). Cash/bank are normal-DEBIT ASSET accounts, so the debit-positive signed balance IS the
    natural cash magnitude; returns 0 for a tenant with no cash postings. A sanctioned finance/
    queries addition — reporting reads it downward, finance never imports reporting (no cycle)."""
    signed = func.coalesce(
        func.sum(
            JournalLine.functional_debit_amount - JournalLine.functional_credit_amount
        ),
        0,
    )
    stmt = (
        select(signed)
        .join(
            Account,
            (JournalLine.tenant_id == Account.tenant_id)
            & (JournalLine.account_id == Account.id),
        )
        .where(
            JournalLine.tenant_id == tenant_id,
            JournalLine.is_posted.is_(True),
            JournalLine.posting_date <= as_of,
            Account.is_cash_equivalent.is_(True),
        )
    )
    result = (await session.execute(stmt)).scalar_one()
    return Decimal(str(result)) if result is not None else ZERO


async def ar_aging_summary(
    session: AsyncSession, tenant_id: uuid.UUID, *, as_of: date
) -> AgingBuckets:
    """AR aging BUCKET SUMMARY as of ``as_of`` for the dashboard card (PLAN 13.1, D-058): the
    rolled-up current / 1-30 / 31-60 / 90+ totals over open customer invoices, NO per-partner lines.
    A thin facade over ``service.ar_aging.customer_aging`` (the same pure projection the AR aging
    REPORT uses, D-021) that collapses the report's 61-90 + over-90 tail into one 90+ bucket. A
    sanctioned finance/queries addition: it imports the finance SERVICE projection internally (a
    same-module call — reporting reads only THIS queries surface, never finance/service)."""
    from app.modules.finance.service.ar_aging import customer_aging

    report = await customer_aging(session, tenant_id, as_of)
    return _summarise(report)


async def ap_aging_summary(
    session: AsyncSession, tenant_id: uuid.UUID, *, as_of: date
) -> AgingBuckets:
    """AP aging BUCKET SUMMARY as of ``as_of`` for the dashboard card (PLAN 13.1, D-058): the
    rolled-up current / 1-30 / 31-60 / 90+ totals over open vendor bills, NO per-partner lines. The
    AR mirror over ``service.ap_aging.vendor_aging`` (the same pure projection the AP aging REPORT
    uses, D-021); collapses the report's 61-90 + over-90 tail into one 90+ bucket."""
    from app.modules.finance.service.ap_aging import vendor_aging

    report = await vendor_aging(session, tenant_id, as_of)
    return _summarise(report)


def _summarise(report: dict[str, object]) -> AgingBuckets:
    """Collapse an AR/AP aging-report dict (current / 1-30 / 31-60 / 61-90 / over-90 totals) into
    the dashboard's four-bucket card, folding 61-90 + over-90 into one 90+ tail. The report totals
    are already Decimals (D-015)."""
    current = _as_decimal(report["current"])
    d30 = _as_decimal(report["days_1_30"])
    d60 = _as_decimal(report["days_31_60"])
    d90plus = _as_decimal(report["days_61_90"]) + _as_decimal(report["days_over_90"])
    return AgingBuckets(
        current=current,
        d30=d30,
        d60=d60,
        d90plus=d90plus,
        total=_as_decimal(report["total"]),
    )


def _as_decimal(value: object) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


async def wip_balance(session: AsyncSession, tenant_id: uuid.UUID, *, as_of: date) -> Decimal:
    """The OPEN WORK-IN-PROCESS value as of ``as_of`` (PLAN 13.1, D-048/D-058): the presentation
    balance of the tenant's WIP-clearing account over the POSTED journal — the authoritative open-
    WIP figure (a component issue debits WIP, the finished receipt credits it, so a non-zero balance
    is in-flight production). A projection of the journal (D-021), date-bounded (PERFORMANCE §1).
    WIP-clearing is an ASSET (normal DEBIT), so the debit-positive signed balance IS the natural WIP
    magnitude. Returns 0 when the tenant has NOT mapped a WIP-clearing posting default (a tenant
    running no manufacturing simply shows zero WIP — the dashboard never errors on an unmapped
    purpose). A sanctioned finance/queries addition for reporting (read downward, no cycle)."""
    account_id = (
        await session.execute(
            select(PostingDefault.account_id).where(
                PostingDefault.tenant_id == tenant_id,
                PostingDefault.purpose == WIP_CLEARING,
            )
        )
    ).scalar_one_or_none()
    if account_id is None:
        return ZERO
    signed = func.coalesce(
        func.sum(
            JournalLine.functional_debit_amount - JournalLine.functional_credit_amount
        ),
        0,
    )
    stmt = select(signed).where(
        JournalLine.tenant_id == tenant_id,
        JournalLine.account_id == account_id,
        JournalLine.is_posted.is_(True),
        JournalLine.posting_date <= as_of,
    )
    result = (await session.execute(stmt)).scalar_one()
    return Decimal(str(result)) if result is not None else ZERO
