"""Payroll-run posting tests (PLAN 10.4, D-055): the KEY proof — posting a run publishes
``PayrollPosted`` and finance posts ONE balanced consolidated journal (Dr salary-expense by cost
centre / Cr payroll-tax-payable / Cr wages-payable, gross = tax + net) via the event bus, links
run → 'posts' → journal, claims the PAY- number, sets journal_entry_id; plus closed-period rollback
and idempotent re-post rejection.

The cross-module §5 mechanism: HR PUBLISHES, finance/handlers.create_payroll_journal posts (HR never
imports finance/service). HEEDS issue #53: post-failure assertions read FRESH scalars (no lazy-load
of an expired ORM object).
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import run_in_uow
from app.core.exceptions import ConflictError, ValidationFailedError
from app.core.tenancy import tenant_context
from app.modules.finance import queries as finance_queries
from app.modules.finance import service as finance_service
from app.modules.finance.constants import (
    PAYROLL_TAX_PAYABLE,
    SALARY_EXPENSE,
    WAGES_PAYABLE,
    DocumentType,
)
from app.modules.finance.models import JournalEntry, JournalLine
from app.modules.hr import queries as hr_queries
from app.modules.hr import service
from app.modules.hr.constants import PAYROLL_RUN_POSTS_LINK, PayrollRunStatus
from app.modules.hr.payroll_schemas import PayrollRunCreate
from tests.modules.hr.payroll_factories import PayrollSetup, build_payroll_setup


def _payload(**overrides) -> PayrollRunCreate:
    base = dict(
        period_start=date(2026, 6, 1),
        period_end=date(2026, 6, 30),
        pay_date=date(2026, 6, 30),
        tax_rate_percent=Decimal("20"),
    )
    base.update(overrides)
    return PayrollRunCreate(**base)


async def _create_run(
    session: AsyncSession, setup: PayrollSetup, payload: PayrollRunCreate
) -> uuid.UUID:
    holder: dict[str, uuid.UUID] = {}

    async def work() -> None:
        with tenant_context(setup.tenant_id):
            run = await service.create_payroll_run(session, setup.tenant_id, payload)
            holder["id"] = run.id

    with tenant_context(setup.tenant_id):
        await run_in_uow(session, work)
    return holder["id"]


async def _post_run(
    session: AsyncSession, setup: PayrollSetup, run_id: uuid.UUID
) -> None:
    async def work() -> None:
        with tenant_context(setup.tenant_id):
            await service.post_payroll_run(session, setup.tenant_id, run_id)

    with tenant_context(setup.tenant_id):
        await run_in_uow(session, work)


async def _journal_for_run(
    session: AsyncSession, tenant_id: uuid.UUID, run_id: uuid.UUID
) -> tuple[JournalEntry, list[JournalLine]]:
    """The posted payroll journal + its lines, resolved from the run's journal_entry_id."""
    with tenant_context(tenant_id):
        run = await hr_queries.get_payroll_run(session, tenant_id, run_id)
        entry = await session.get(JournalEntry, run.journal_entry_id)
        lines = list(
            (
                await session.execute(
                    select(JournalLine).where(JournalLine.journal_entry_id == entry.id)
                )
            )
            .scalars()
            .all()
        )
    return entry, lines


async def test_post_creates_balanced_consolidated_journal(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """Posting a run posts ONE balanced journal: Dr salary-expense total gross / Cr
    payroll-tax-payable total tax + Cr wages-payable total net, gross = tax + net (D-055)."""
    setup = await build_payroll_setup(
        db_session, tenant_a, salaries=(Decimal("5000"), Decimal("3000"))
    )
    run_id = await _create_run(db_session, setup, _payload())
    await _post_run(db_session, setup, run_id)

    entry, lines = await _journal_for_run(db_session, tenant_a, run_id)
    assert entry.document_type == DocumentType.PAYROLL.value
    assert entry.status == "POSTED"
    assert entry.entry_number is not None

    total_debit = sum(Decimal(line.transaction_debit_amount) for line in lines)
    total_credit = sum(Decimal(line.transaction_credit_amount) for line in lines)
    assert total_debit == total_credit == Decimal("8000")  # gross = tax (1600) + net (6400)

    by_account: dict[uuid.UUID, tuple[Decimal, Decimal]] = {}
    for line in lines:
        d, c = by_account.get(line.account_id, (Decimal(0), Decimal(0)))
        by_account[line.account_id] = (
            d + Decimal(line.transaction_debit_amount),
            c + Decimal(line.transaction_credit_amount),
        )
    salary_acct = setup.accounts[SALARY_EXPENSE]
    tax_acct = setup.accounts[PAYROLL_TAX_PAYABLE]
    wages_acct = setup.accounts[WAGES_PAYABLE]
    assert by_account[salary_acct][0] == Decimal("8000")  # Dr salary expense = total gross
    assert by_account[tax_acct][1] == Decimal("1600")  # Cr payroll tax payable = total tax
    assert by_account[wages_acct][1] == Decimal("6400")  # Cr wages payable = total net


async def test_post_salary_expense_carries_cost_center_dimension(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """The salary-expense Dr legs carry the employees' cost-centre dimension so CO reports include
    labour (D-055)."""
    setup = await build_payroll_setup(db_session, tenant_a, salaries=(Decimal("5000"),))
    run_id = await _create_run(db_session, setup, _payload())
    await _post_run(db_session, setup, run_id)
    _, lines = await _journal_for_run(db_session, tenant_a, run_id)
    salary_lines = [
        line for line in lines if line.account_id == setup.accounts[SALARY_EXPENSE]
    ]
    assert salary_lines, "expected a salary-expense line"
    assert all(line.cost_center_id == setup.cost_center_id for line in salary_lines)


async def test_post_run_status_and_number_and_journal_link(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """A posted run goes POSTED, claims a PAY- number, links journal_entry_id, stamps posted_at, and
    records the docflow run → 'posts' → journal edge (D-055)."""
    setup = await build_payroll_setup(db_session, tenant_a, salaries=(Decimal("4000"),))
    run_id = await _create_run(db_session, setup, _payload())
    await _post_run(db_session, setup, run_id)

    with tenant_context(tenant_a):
        run = await hr_queries.get_payroll_run(db_session, tenant_a, run_id)
        assert run.status == PayrollRunStatus.POSTED.value
        assert run.run_number is not None and run.run_number.startswith("PAY-")
        assert run.journal_entry_id is not None
        assert run.posted_at is not None
        from app.core import docflow

        chain = await docflow.get_document_chain(db_session, tenant_a, run.document_id)
    assert any(edge.link_type == PAYROLL_RUN_POSTS_LINK for edge in chain.edges)


async def test_post_into_closed_period_rolls_back(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """A post whose journal would land in a CLOSED pay-date period fails (the period trigger fires
    in the same transaction) and the whole post rolls back — the run stays DRAFT, no journal, no
    number (issue #53: fresh scalar reads, no lazy-load of an expired object)."""
    setup = await build_payroll_setup(db_session, tenant_a, salaries=(Decimal("5000"),))
    run_id = await _create_run(db_session, setup, _payload(pay_date=date(2026, 6, 30)))
    with tenant_context(tenant_a):
        period = await finance_queries.find_period_for_date(
            db_session, tenant_a, date(2026, 6, 30)
        )
        await finance_service.close_period(db_session, tenant_a, period.id)
        await db_session.commit()
    journals_before = await _count_journals(db_session, tenant_a)

    with pytest.raises(Exception):  # noqa: B017, PT011 - period trigger / service error
        await _post_run(db_session, setup, run_id)

    assert await _count_journals(db_session, tenant_a) == journals_before
    db_session.expire_all()
    status, run_number, journal_id = await _run_post_state(db_session, tenant_a, run_id)
    assert status == PayrollRunStatus.DRAFT.value
    assert run_number is None
    assert journal_id is None


async def test_post_idempotent_repost_rejected(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """Re-posting an already-POSTED run is a conflict — a run posts exactly once (D-055)."""
    setup = await build_payroll_setup(db_session, tenant_a, salaries=(Decimal("5000"),))
    run_id = await _create_run(db_session, setup, _payload())
    await _post_run(db_session, setup, run_id)
    with pytest.raises(ConflictError) as exc:
        await _post_run(db_session, setup, run_id)
    assert exc.value.code == "hr.payroll_run_not_draft"


async def test_post_unmapped_posting_default_rejected(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """A tenant that has not mapped the payroll posting defaults gets a 422 on post (D-055)."""
    setup = await build_payroll_setup(
        db_session, tenant_a, salaries=(Decimal("5000"),), map_defaults=False
    )
    run_id = await _create_run(db_session, setup, _payload())
    with pytest.raises(ValidationFailedError) as exc:
        await _post_run(db_session, setup, run_id)
    assert exc.value.code == "finance.posting_default_unmapped"


async def _count_journals(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    with tenant_context(tenant_id):
        return (
            await session.execute(
                select(func.count())
                .select_from(JournalEntry)
                .where(JournalEntry.tenant_id == tenant_id)
            )
        ).scalar_one()


async def _run_post_state(
    session: AsyncSession, tenant_id: uuid.UUID, run_id: uuid.UUID
) -> tuple[str, str | None, uuid.UUID | None]:
    """A FRESH (status, run_number, journal_entry_id) scalar read for post-rollback assertions
    (issue #53 — never lazy-loads an expired ORM object)."""
    from app.modules.hr.models import PayrollRun

    with tenant_context(tenant_id):
        row = (
            await session.execute(
                select(
                    PayrollRun.status, PayrollRun.run_number, PayrollRun.journal_entry_id
                ).where(PayrollRun.id == run_id)
            )
        ).one()
    return row[0], row[1], row[2]
