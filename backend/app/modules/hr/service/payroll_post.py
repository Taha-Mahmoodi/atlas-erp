"""Payroll-run posting (PLAN 10.4, D-055): publish ``PayrollPosted`` so finance posts the
consolidated journal in the SAME transaction.

Split out of ``payroll.py`` (create + reads + cancel) so each file stays under the 400-line cap
(STRUCTURE §8.4; the production ``production_orders``/``production_post`` precedent). This is the
§5-clean cross-module write: HR PUBLISHES the event carrying the resolved posting-account ids (read
from ``finance/queries`` — HR NEVER imports finance/service) + the per-cost-centre salary-expense
allocation; finance's ``create_payroll_journal`` handler posts the journal (Dr salary-expense by
cost centre / Cr payroll-tax-payable / Cr wages-payable) and links payroll-run → 'posts' → journal.

ATOMICITY (D-011): the handler shares the session and any failure rolls the whole transaction back,
so the run's POSTED flip and its journal land together — a closed period at ``pay_date`` trips the
journal's period trigger and rolls the WHOLE post back. IDEMPOTENT: re-posting a POSTED run is a
conflict (a run posts exactly once; correct a posted run by reversing its journal in finance).

``from __future__ import annotations`` keeps the model annotations strings at import.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import publish
from app.core.exceptions import ConflictError
from app.core.numbering import claim_number, ensure_sequence
from app.modules.finance import queries as finance_queries
from app.modules.hr.constants import (
    PAYROLL_RUN_NUMBER_PADDING,
    PAYROLL_RUN_NUMBER_PREFIX,
    PAYROLL_RUN_SEQUENCE_NAME,
    PayrollRunStatus,
)
from app.modules.hr.events import PayrollCostCenterExpense, PayrollPosted
from app.modules.hr.models import PayrollRun, PayrollRunLine
from app.modules.hr.service.payroll import get_payroll_run


async def post_payroll_run(
    session: AsyncSession, tenant_id: uuid.UUID, run_id: uuid.UUID
) -> PayrollRun:
    """Post a DRAFT payroll run (D-055): claim its gapless ``PAY-`` number, flip it POSTED, and
    publish ``PayrollPosted`` so finance posts the consolidated journal in the SAME transaction.

    Resolves the three payroll posting-default accounts (salary-expense / payroll-tax-payable /
    wages-payable) from ``finance/queries`` (RAISES 422 when a tenant has not mapped one) and the
    per-cost-centre salary-expense allocation from the run's lines, then publishes them on the
    event. Finance's handler posts Dr salary-expense by cost centre (total gross) / Cr
    payroll-tax-payable (total tax) / Cr wages-payable (total net) — balanced because gross = tax +
    net — and links the run document → 'posts' → journal. A closed ``pay_date`` period trips the
    journal trigger and rolls the whole post back. Only a DRAFT can be posted (re-posting a POSTED
    run is a conflict)."""
    run = await get_payroll_run(session, tenant_id, run_id)
    if PayrollRunStatus(run.status) != PayrollRunStatus.DRAFT:
        raise ConflictError(
            message="Only a draft payroll run can be posted",
            code="hr.payroll_run_not_draft",
            details={"status": run.status},
        )

    # Resolve the posting accounts BEFORE claiming the number (a 422 here leaves nothing claimed).
    salary_expense_account_id = await finance_queries.salary_expense_account(session, tenant_id)
    payroll_tax_payable_account_id = await finance_queries.payroll_tax_payable_account(
        session, tenant_id
    )
    wages_payable_account_id = await finance_queries.wages_payable_account(session, tenant_id)

    salary_by_cost_center = await _salary_by_cost_center(session, tenant_id, run_id)

    await ensure_sequence(
        session,
        tenant_id,
        PAYROLL_RUN_SEQUENCE_NAME,
        PAYROLL_RUN_NUMBER_PREFIX,
        PAYROLL_RUN_NUMBER_PADDING,
        year_reset=True,
    )
    run_number = await claim_number(
        session, tenant_id, PAYROLL_RUN_SEQUENCE_NAME, on_date=run.pay_date
    )
    run.run_number = run_number
    run.status = PayrollRunStatus.POSTED.value
    run.posted_at = datetime.now(UTC)
    await session.flush()

    # Publish so finance posts the consolidated journal in this same transaction (D-011). Finance's
    # handler writes the durable run↔journal link as the docflow 'posts' edge AND sets
    # run.journal_entry_id (the convenience column) — it has the run reference from the event, and
    # handler writes share this transaction, so both land atomically with the POSTED flip above.
    publish(
        session,
        PayrollPosted(
            tenant_id=tenant_id,
            payroll_run_id=run.id,
            run_number=run_number,
            document_id=run.document_id,
            pay_date=run.pay_date.isoformat(),
            currency_code=run.currency_code,
            total_gross=Decimal(run.total_gross),
            total_tax=Decimal(run.total_tax),
            total_net=Decimal(run.total_net),
            salary_expense_account_id=salary_expense_account_id,
            payroll_tax_payable_account_id=payroll_tax_payable_account_id,
            wages_payable_account_id=wages_payable_account_id,
            salary_by_cost_center=salary_by_cost_center,
        ),
    )
    return run


async def _salary_by_cost_center(
    session: AsyncSession, tenant_id: uuid.UUID, run_id: uuid.UUID
) -> tuple[PayrollCostCenterExpense, ...]:
    """The per-cost-centre salary-expense allocation for a run (D-055): SUM the line gross by
    ``cost_center_id`` (``None`` is the unallocated bucket). One set-based GROUP-BY over the run's
    lines (PERFORMANCE §6); the sum of every amount equals the run's total gross, so the
    salary-expense Dr legs balance the journal. Ordered with the unallocated bucket last for a
    stable journal-line order."""
    stmt = (
        select(
            PayrollRunLine.cost_center_id,
            func.sum(PayrollRunLine.gross_amount),
        )
        .where(
            PayrollRunLine.tenant_id == tenant_id,
            PayrollRunLine.payroll_run_id == run_id,
        )
        .group_by(PayrollRunLine.cost_center_id)
    )
    rows = list((await session.execute(stmt)).all())
    allocations = [
        PayrollCostCenterExpense(cost_center_id=cc_id, amount=Decimal(str(amount)))
        for cc_id, amount in rows
    ]
    # Stable order: real cost centres by id first, the unallocated (None) bucket last.
    allocations.sort(key=lambda a: (a.cost_center_id is None, str(a.cost_center_id)))
    return tuple(allocations)
