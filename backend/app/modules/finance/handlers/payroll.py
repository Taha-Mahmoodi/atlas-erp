"""HR payroll-posted → consolidated payroll-journal handler (PLAN 10.4, D-055).

``create_payroll_journal`` subscribes to HR's ``hr.payroll.posted`` and posts the consolidated
payroll journal (Dr salary-expense by cost centre at total gross / Cr payroll-tax-payable at total
tax / Cr wages-payable at total net — balanced because gross = tax + net) in the SAME transaction as
the run's POSTED flip. HR PUBLISHES carrying the resolved posting-account ids + the per-cost-centre
allocation; finance posts its OWN journal (HR never imports finance/service — STRUCTURE §5), the
match → AP-bill / billing → AR-invoice precedent. A closed ``pay_date`` period trips the journal
trigger here and rolls the whole payroll post back. Built through the finance posting service (never
raw inserts) so every journal invariant fires.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.modules.finance.constants import DocumentType
from app.modules.finance.schemas import JournalEntryCreate, JournalLineCreate
from app.modules.finance.service.journal import create_draft_entry, post_entry
from app.modules.hr.constants import PAYROLL_RUN_POSTS_LINK
from app.modules.hr.events import PayrollPosted


async def create_payroll_journal(session: AsyncSession, event: PayrollPosted) -> None:
    """Post the consolidated payroll journal for a posted payroll run (PLAN 10.4, D-055), in the
    run's transaction — the §5-clean MIRROR of the match → AP-bill / billing → AR-invoice handlers.

    Builds ONE balanced journal: Dr salary-expense per cost centre (each line carrying the opaque
    cost-centre dimension so CO cost-centre reports include labour) summing to total gross, Cr
    payroll-tax-payable at total tax, Cr wages-payable at total net — balanced because the run's
    ``total_gross == total_tax + total_net`` (the balancing invariant). Posted through the finance
    posting service (``create_draft_entry`` + ``post_entry``) dated ``pay_date``, NEVER raw inserts,
    so every journal invariant fires. Links the run document → 'posts' → journal document and sets
    the run's ``journal_entry_id`` (the convenience column) in this same transaction. HR PUBLISHES;
    finance posts its OWN journal (HR must not import finance/service — STRUCTURE §5). A closed
    ``pay_date`` period trips the journal trigger here and rolls the whole payroll post back.

    Registered via ``app.main.register_event_handlers`` (the deterministic D-011 seam), so the test
    harness re-registers it after its per-test ``clear_subscriptions`` reset (D-025)."""
    lines: list[JournalLineCreate] = []
    # Dr salary-expense per cost centre (the CO dimension rides each line); a None bucket posts with
    # no cost-centre dimension (the unallocated salary expense).
    for allocation in event.salary_by_cost_center:
        if allocation.amount == 0:
            continue
        lines.append(
            JournalLineCreate(
                account_id=event.salary_expense_account_id,
                description="Salary expense",
                transaction_debit_amount=Decimal(allocation.amount),
                cost_center_id=allocation.cost_center_id,
            )
        )
    # Cr payroll-tax-payable at total tax (the withheld flat-rate tax owed to the authority).
    if event.total_tax != 0:
        lines.append(
            JournalLineCreate(
                account_id=event.payroll_tax_payable_account_id,
                description="Payroll tax withheld",
                transaction_credit_amount=Decimal(event.total_tax),
            )
        )
    # Cr wages-payable at total net (net pay owed to employees).
    lines.append(
        JournalLineCreate(
            account_id=event.wages_payable_account_id,
            description="Net wages payable",
            transaction_credit_amount=Decimal(event.total_net),
        )
    )

    entry = await create_draft_entry(
        session,
        event.tenant_id,
        JournalEntryCreate(
            posting_date=date.fromisoformat(event.pay_date),
            currency_code=event.currency_code,
            description=f"Payroll run {event.run_number}",
            document_type=DocumentType.PAYROLL,
            lines=lines,
        ),
    )
    await post_entry(session, event.tenant_id, entry.id)
    await docflow.link_documents(
        session,
        event.tenant_id,
        predecessor=event.document_id,
        successor=entry.document_id,
        link_type=PAYROLL_RUN_POSTS_LINK,
    )
    # Set the run's convenience journal link in the SAME transaction. PayrollRun is imported lazily
    # in the function body so finance's module import never depends on hr at load (finance is below
    # hr) — the durable link is the docflow 'posts' edge above; this column is the read convenience.
    from app.modules.hr.models import PayrollRun

    run = await session.get(PayrollRun, event.payroll_run_id)
    if run is not None:
        run.journal_entry_id = entry.id
        await session.flush()
