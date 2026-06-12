"""The cost-allocation run engine (PLAN 4.7): redistribute a cost centre's period cost.

``run_allocation`` is the controlling counterpart of the journal posting engine. CO is a projection
of the universal journal (D-021), so an allocation is just ONE more balanced journal entry that
moves cost between cost centres — no separate CO ledger is stored. Algorithm:

1. Compute the SOURCE cost centre's net functional balance for the period via
   ``queries.cost_center_balance`` (posted functional debit minus credit on the source's lines).
   That is the amount to allocate.
2. Distribute it across the targets by their weights using ``core.money.allocate`` (largest
   remainder), so the parts sum EXACTLY to the source amount — odd splits like 1000 / 3 give
   333.34 / 333.33 / 333.33 with no lost cent.
3. Post ONE balanced journal entry (document_type CO_ALLOCATION) on a single dedicated
   ``cost_allocation`` posting-default account: ONE line on the SOURCE side moving the cost out, and
   N lines on the TARGET side, each tagged with its target cost_center_id. The account nets to zero;
   the cost moves between cost centres purely via the line cost_center_id dimension, so cost-centre
   reports (journal projections) reflect the reallocation.
4. Claim the gapless allocation number (D-012), link run→journal in docflow, track the run in
   fin_allocation_runs, and publish AllocationPosted.

IDEMPOTENT: a (rule, period) that already has a POSTED run returns that run unchanged — a retried
request never double-allocates. REVERSIBLE: the run's journal entry is reversible like any entry
(``service.reverse_entry``), which a re-run after correction relies on.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.core.events import publish
from app.core.exceptions import NotFoundError, ValidationFailedError
from app.core.money import allocate, currency_decimals
from app.core.numbering import claim_number, ensure_sequence
from app.modules.finance import queries
from app.modules.finance.constants import (
    ALLOCATION_NUMBER_PADDING,
    ALLOCATION_NUMBER_PREFIX,
    ALLOCATION_SEQUENCE_NAME,
    CO_ALLOCATION_CLEARING,
    CO_ALLOCATION_DOC_TYPE,
    CO_ALLOCATION_POSTS_LINK,
    AllocationRunStatus,
    DocumentType,
)
from app.modules.finance.events import AllocationPosted
from app.modules.finance.models import AllocationRule, AllocationRun, FiscalPeriod
from app.modules.finance.schemas import JournalEntryCreate, JournalLineCreate
from app.modules.finance.service import allocation_rules
from app.modules.finance.service.fx import functional_currency_or_none
from app.modules.finance.service.journal import create_draft_entry, post_entry
from app.modules.finance.service.posting_defaults import get_posting_default


async def _existing_run(
    session: AsyncSession, tenant_id: uuid.UUID, rule_id: uuid.UUID, period_id: uuid.UUID
) -> AllocationRun | None:
    """An already-POSTED run for this (rule, period), or None — the idempotency probe."""
    stmt = select(AllocationRun).where(
        AllocationRun.tenant_id == tenant_id,
        AllocationRun.allocation_rule_id == rule_id,
        AllocationRun.fiscal_period_id == period_id,
        AllocationRun.status == AllocationRunStatus.POSTED.value,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_allocation_run(
    session: AsyncSession, tenant_id: uuid.UUID, run_id: uuid.UUID
) -> AllocationRun:
    run = await session.get(AllocationRun, run_id)
    if run is None or run.tenant_id != tenant_id:
        raise NotFoundError(
            message="Allocation run not found", code="finance.allocation_run_not_found"
        )
    return run


async def list_allocation_runs(
    session: AsyncSession, tenant_id: uuid.UUID, rule_id: uuid.UUID | None = None
) -> list[AllocationRun]:
    stmt = select(AllocationRun).where(AllocationRun.tenant_id == tenant_id)
    if rule_id is not None:
        stmt = stmt.where(AllocationRun.allocation_rule_id == rule_id)
    stmt = stmt.order_by(AllocationRun.run_date.desc(), AllocationRun.created_at.desc())
    return list((await session.execute(stmt)).scalars().all())


def _build_lines(
    clearing_account_id: uuid.UUID,
    source_cost_center_id: uuid.UUID,
    source_amount: Decimal,
    target_ids: list[uuid.UUID],
    parts: list[Decimal],
) -> list[JournalLineCreate]:
    """Build the allocation entry's lines on the single clearing account (PLAN 4.7).

    ``source_amount`` is the source cost centre's NET balance: positive = net DEBIT (cost
    collected), moved OUT by CREDITING the source line; negative = net CREDIT, moved out by DEBIT.
    Each target takes its ``part`` on the OPPOSITE side, tagged with its cost_center_id. Zero-amount
    target parts (a tiny total split across many targets can floor one to 0) are DROPPED, since a
    line must be strictly one-sided with a positive amount (D-017); ``parts`` sum exactly to the
    source amount, so dropping zero parts keeps the entry balanced."""
    source_credit = source_amount > 0
    magnitude = abs(source_amount)
    lines: list[JournalLineCreate] = [
        JournalLineCreate(
            account_id=clearing_account_id,
            description="Cost allocation: source",
            transaction_debit_amount=Decimal(0) if source_credit else magnitude,
            transaction_credit_amount=magnitude if source_credit else Decimal(0),
            cost_center_id=source_cost_center_id,
        )
    ]
    for target_id, part in zip(target_ids, parts, strict=True):
        if part == 0:
            continue
        lines.append(
            JournalLineCreate(
                account_id=clearing_account_id,
                description="Cost allocation: target",
                # Targets take the opposite side of the source.
                transaction_debit_amount=part if source_credit else Decimal(0),
                transaction_credit_amount=Decimal(0) if source_credit else part,
                cost_center_id=target_id,
            )
        )
    return lines


async def run_allocation(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    rule_id: uuid.UUID,
    period_id: uuid.UUID,
    run_date: date,
) -> AllocationRun:
    """Run an allocation rule for a period, posting the redistribution entry (PLAN 4.7).

    Idempotent: returns an existing POSTED run for this (rule, period) untouched. Otherwise computes
    the source cost centre's net period balance, splits it across the active rule's targets by their
    weights (largest-remainder, exact), posts the CO_ALLOCATION journal entry on the cost-allocation
    clearing account with cost_center_id per line, tracks the run, links docflow, and publishes
    AllocationPosted. Raises 422 when the rule is inactive, the source balance is zero (nothing to
    allocate), or the clearing account is not configured. The caller commits via uow (D-011)."""
    existing = await _existing_run(session, tenant_id, rule_id, period_id)
    if existing is not None:
        return existing

    rule = await allocation_rules.get_allocation_rule(session, tenant_id, rule_id)
    if not rule.is_active:
        raise ValidationFailedError(
            message="An inactive allocation rule cannot be run",
            code="finance.allocation_rule_inactive",
            details={"rule_id": str(rule_id)},
        )
    period = await _require_period(session, tenant_id, period_id)
    targets = await allocation_rules.get_rule_targets(session, tenant_id, rule_id)
    if not targets:
        raise ValidationFailedError(
            message="The allocation rule has no targets",
            code="finance.allocation_no_targets",
        )

    source_amount = await queries.cost_center_balance(
        session, tenant_id, rule.source_cost_center_id, period_id
    )
    currency_code = await functional_currency_or_none(session, tenant_id) or "USD"
    source_amount = source_amount.quantize(Decimal(1).scaleb(-currency_decimals(currency_code)))
    if source_amount == 0:
        raise ValidationFailedError(
            message="The source cost centre has no balance to allocate for this period",
            code="finance.allocation_zero_balance",
            details={"source_cost_center_id": str(rule.source_cost_center_id)},
        )

    clearing_account_id = await get_posting_default(session, tenant_id, CO_ALLOCATION_CLEARING)
    weights = [Decimal(str(t.weight)) for t in targets]
    parts = allocate(abs(source_amount), weights, places=currency_decimals(currency_code))
    target_ids = [t.target_cost_center_id for t in targets]

    lines = _build_lines(
        clearing_account_id,
        rule.source_cost_center_id,
        source_amount,
        target_ids,
        parts,
    )
    entry = await create_draft_entry(
        session,
        tenant_id,
        JournalEntryCreate(
            posting_date=run_date,
            currency_code=currency_code,
            description=f"Cost allocation {rule.code}",
            document_type=DocumentType.JOURNAL,
            lines=lines,
        ),
    )
    await post_entry(session, tenant_id, entry.id)

    run = await _track_run(
        session, tenant_id, rule, period_id, run_date, abs(source_amount), entry.id
    )
    await docflow.link_documents(
        session,
        tenant_id,
        predecessor=run.document_id,
        successor=entry.document_id,
        link_type=CO_ALLOCATION_POSTS_LINK,
    )

    publish(
        session,
        AllocationPosted(
            tenant_id=tenant_id,
            allocation_run_id=run.id,
            allocation_rule_id=rule.id,
            journal_entry_id=entry.id,
            fiscal_period_id=period.id,
            source_cost_center_id=rule.source_cost_center_id,
            allocated_amount=abs(source_amount),
            target_cost_center_ids=tuple(target_ids),
        ),
    )
    return run


async def _require_period(session: AsyncSession, tenant_id: uuid.UUID, period_id: uuid.UUID):
    """The fiscal period for ``period_id`` in the tenant, or a 422: the run's amount and entry are
    period-scoped, so an unknown period is a clear client error."""

    period = await session.get(FiscalPeriod, period_id)
    if period is None or period.tenant_id != tenant_id:
        raise ValidationFailedError(
            message="The fiscal period does not exist in this tenant",
            code="finance.allocation_period_not_found",
            details={"fiscal_period_id": str(period_id)},
        )
    return period


async def _track_run(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    rule: AllocationRule,
    period_id: uuid.UUID,
    run_date: date,
    allocated_amount: Decimal,
    journal_entry_id: uuid.UUID,
) -> AllocationRun:
    """Register the run document, claim its gapless number, and persist the run row (PLAN 4.7)."""
    run_id = uuid.uuid4()
    document = await docflow.register_document(
        session,
        tenant_id,
        CO_ALLOCATION_DOC_TYPE,
        run_id,
        doc_number=None,
        status=AllocationRunStatus.POSTED.value,
    )
    await ensure_sequence(
        session,
        tenant_id,
        ALLOCATION_SEQUENCE_NAME,
        ALLOCATION_NUMBER_PREFIX,
        ALLOCATION_NUMBER_PADDING,
        year_reset=True,
    )
    run_number = await claim_number(
        session, tenant_id, ALLOCATION_SEQUENCE_NAME, on_date=run_date
    )
    run = AllocationRun(
        id=run_id,
        tenant_id=tenant_id,
        document_id=document.id,
        allocation_rule_id=rule.id,
        fiscal_period_id=period_id,
        run_number=run_number,
        run_date=run_date,
        allocated_amount=allocated_amount,
        journal_entry_id=journal_entry_id,
        status=AllocationRunStatus.POSTED.value,
    )
    session.add(run)
    await session.flush()
    await docflow.set_document_status(
        session,
        tenant_id,
        document.id,
        status=AllocationRunStatus.POSTED.value,
        doc_number=run_number,
    )
    return run
