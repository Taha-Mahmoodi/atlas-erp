"""Cost-allocation run engine (PLAN 4.7): run_allocation, SQLite + one Postgres balance test.

Proves: a source cost centre with a posted balance of 1000 allocated 50/30/20 sends 500/300/200 to
the targets on the allocation clearing account with the source credited 1000 (entry balanced); odd
splits (1000 / 3) sum EXACTLY via largest-remainder (333.34 / 333.33 / 333.33); the run is tracked,
linked in docflow, publishes AllocationPosted; re-running the same (rule, period) is idempotent; and
on Postgres a CO_ALLOCATION entry with N cost-centre dimension lines posts (exercising the balance
trigger with many lines).
"""

import os
import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.core.db import build_session_factory
from app.core.events import run_in_uow, subscribe
from app.core.tenancy import system_context, tenant_context
from app.modules.admin.models import Tenant
from app.modules.finance import service
from app.modules.finance.constants import (
    CO_ALLOCATION_CLEARING,
    AllocationBasis,
    AllocationRunStatus,
)
from app.modules.finance.controlling_schemas import (
    AllocationRuleCreate,
    AllocationTargetCreate,
    CostCenterCreate,
)
from app.modules.finance.events import AllocationPosted
from app.modules.finance.models import JournalEntry, JournalLine
from app.modules.finance.schemas import (
    AccountCreate,
    FiscalYearCreate,
    JournalEntryCreate,
    JournalLineCreate,
)
from tests.modules.finance.conftest import CoSetup

_PD = date(2026, 3, 15)
_URL = os.environ.get("ATLAS_DATABASE_URL", "")


async def _seed_source_balance(
    db_session: AsyncSession, co_setup: CoSetup, source_id: uuid.UUID, amount: str
) -> None:
    """Post a journal entry debiting 5000 (expense) with the source cost centre + crediting cash, so
    the source cost centre carries a net debit balance of ``amount`` for the period."""
    entry = await service.create_draft_entry(
        db_session,
        co_setup.tenant_id,
        JournalEntryCreate(
            posting_date=_PD,
            currency_code="USD",
            description="seed source cost",
            lines=[
                JournalLineCreate(
                    account_id=co_setup.accounts["5000"],
                    transaction_debit_amount=Decimal(amount),
                    cost_center_id=source_id,
                ),
                JournalLineCreate(
                    account_id=co_setup.accounts["1000"],
                    transaction_credit_amount=Decimal(amount),
                ),
            ],
        ),
    )
    await service.post_entry(db_session, co_setup.tenant_id, entry.id)


async def _percent_rule(
    db_session: AsyncSession,
    co_setup: CoSetup,
    weights: tuple[str, ...],
    basis: AllocationBasis = AllocationBasis.PERCENT,
) -> tuple[uuid.UUID, uuid.UUID, list[uuid.UUID]]:
    """Create a source + len(weights) target cost centres and a rule with the given weights.
    Returns (rule_id, source_id, target_ids)."""
    source = await service.create_cost_center(
        db_session, co_setup.tenant_id, CostCenterCreate(code="SRC", name="Source")
    )
    target_ids: list[uuid.UUID] = []
    targets = []
    for i in range(len(weights)):
        cc = await service.create_cost_center(
            db_session, co_setup.tenant_id, CostCenterCreate(code=f"T{i}", name=f"T{i}")
        )
        targets.append(
            AllocationTargetCreate(target_cost_center_id=cc.id, weight=Decimal(weights[i]))
        )
        target_ids.append(cc.id)
    rule = await service.create_allocation_rule(
        db_session,
        co_setup.tenant_id,
        AllocationRuleCreate(
            code="R1",
            name="Rule",
            source_cost_center_id=source.id,
            basis=basis,
            targets=targets,
        ),
    )
    return rule.id, source.id, target_ids


async def _entry_lines_by_cost_center(
    db_session: AsyncSession, tenant_id: uuid.UUID, entry_id: uuid.UUID
) -> dict[uuid.UUID, Decimal]:
    """Net debit-minus-credit per cost_center_id on the entry's lines."""
    lines = (
        await db_session.execute(
            select(JournalLine).where(JournalLine.journal_entry_id == entry_id)
        )
    ).scalars().all()
    result: dict[uuid.UUID, Decimal] = {}
    for line in lines:
        net = Decimal(str(line.transaction_debit_amount)) - Decimal(
            str(line.transaction_credit_amount)
        )
        result[line.cost_center_id] = result.get(line.cost_center_id, Decimal(0)) + net
    return result


async def _period_id(db_session: AsyncSession, co_setup: CoSetup) -> uuid.UUID:
    """The 2026 period covering _PD (resolved the same way the journal resolves it)."""
    from app.modules.finance import queries

    period = await queries.find_period_for_date(db_session, co_setup.tenant_id, _PD)
    return period.id


async def test_allocation_50_30_20(db_session: AsyncSession, co_setup: CoSetup) -> None:
    with tenant_context(co_setup.tenant_id):
        rule_id, source_id, target_ids = await _percent_rule(
            db_session, co_setup, ("50", "30", "20")
        )
        await _seed_source_balance(db_session, co_setup, source_id, "1000.00")
        await db_session.commit()
        period_id = await _period_id(db_session, co_setup)
        run = await service.run_allocation(
            db_session, co_setup.tenant_id, rule_id, period_id, _PD
        )
        await db_session.commit()
        nets = await _entry_lines_by_cost_center(
            db_session, co_setup.tenant_id, run.journal_entry_id
        )
    # Source credited 1000 (net -1000); targets debited 500/300/200.
    assert nets[source_id] == Decimal("-1000.00")
    assert nets[target_ids[0]] == Decimal("500.00")
    assert nets[target_ids[1]] == Decimal("300.00")
    assert nets[target_ids[2]] == Decimal("200.00")
    # Entry balanced: the sum over every line is zero.
    assert sum(nets.values()) == Decimal("0.00")
    assert run.allocated_amount == Decimal("1000.00")
    assert run.run_number is not None


async def test_allocation_odd_split_sums_exactly(
    db_session: AsyncSession, co_setup: CoSetup
) -> None:
    with tenant_context(co_setup.tenant_id):
        rule_id, source_id, target_ids = await _percent_rule(
            db_session,
            co_setup,
            ("3333333333", "3333333333", "3333333334"),
            basis=AllocationBasis.FIXED_WEIGHT,
        )
        await _seed_source_balance(db_session, co_setup, source_id, "1000.00")
        await db_session.commit()
        period_id = await _period_id(db_session, co_setup)
        run = await service.run_allocation(
            db_session, co_setup.tenant_id, rule_id, period_id, _PD
        )
        await db_session.commit()
        nets = await _entry_lines_by_cost_center(
            db_session, co_setup.tenant_id, run.journal_entry_id
        )
    parts = sorted((nets[t] for t in target_ids), reverse=True)
    # 1000 / 3 via largest-remainder: 333.34 / 333.33 / 333.33, summing to exactly 1000.00.
    assert parts == [Decimal("333.34"), Decimal("333.33"), Decimal("333.33")]
    assert sum(parts) == Decimal("1000.00")
    assert nets[source_id] == Decimal("-1000.00")


async def test_allocation_tracked_docflow_and_event(
    db_session: AsyncSession, co_setup: CoSetup
) -> None:
    from app.core import docflow

    received: list[AllocationPosted] = []

    async def _capture(session: AsyncSession, event: AllocationPosted) -> None:
        received.append(event)

    subscribe(AllocationPosted.key, _capture)

    with tenant_context(co_setup.tenant_id):
        rule_id, source_id, _targets = await _percent_rule(
            db_session, co_setup, ("60", "40")
        )
        await _seed_source_balance(db_session, co_setup, source_id, "500.00")
        await db_session.commit()
        period_id = await _period_id(db_session, co_setup)

        async def work() -> None:
            await service.run_allocation(
                db_session, co_setup.tenant_id, rule_id, period_id, _PD
            )

        await run_in_uow(db_session, work)
        await db_session.commit()
        runs = await service.list_allocation_runs(db_session, co_setup.tenant_id, rule_id)
        chain = await docflow.get_document_chain(
            db_session, co_setup.tenant_id, runs[0].document_id
        )
    assert len(received) == 1
    assert received[0].allocated_amount == Decimal("500.00")
    assert runs[0].status == AllocationRunStatus.POSTED.value
    # The run's document links to the posted journal entry (the 'posts' edge).
    assert len(chain.nodes) >= 2


async def test_allocation_idempotent(db_session: AsyncSession, co_setup: CoSetup) -> None:
    with tenant_context(co_setup.tenant_id):
        rule_id, source_id, _targets = await _percent_rule(db_session, co_setup, ("100",))
        await _seed_source_balance(db_session, co_setup, source_id, "400.00")
        await db_session.commit()
        period_id = await _period_id(db_session, co_setup)
        first = await service.run_allocation(
            db_session, co_setup.tenant_id, rule_id, period_id, _PD
        )
        await db_session.commit()
        second = await service.run_allocation(
            db_session, co_setup.tenant_id, rule_id, period_id, _PD
        )
        await db_session.commit()
        runs = await service.list_allocation_runs(db_session, co_setup.tenant_id, rule_id)
    # Same run returned; no second run created.
    assert first.id == second.id
    assert len(runs) == 1


async def test_zero_balance_rejected(db_session: AsyncSession, co_setup: CoSetup) -> None:
    from app.core.exceptions import ValidationFailedError

    with tenant_context(co_setup.tenant_id):
        rule_id, _source_id, _targets = await _percent_rule(db_session, co_setup, ("100",))
        await db_session.commit()
        period_id = await _period_id(db_session, co_setup)
        with pytest.raises(ValidationFailedError) as exc:
            await service.run_allocation(
                db_session, co_setup.tenant_id, rule_id, period_id, _PD
            )
    assert exc.value.code == "finance.allocation_zero_balance"


# --- Postgres balance-trigger test (-m pg) ------------------------------------


@pytest.fixture
async def pg_engine() -> AsyncEngine:
    """A real Postgres engine for the -m pg variant; skipped on the SQLite run."""
    if not _URL.startswith("postgresql"):
        pytest.skip("pg-marked test requires a PostgreSQL ATLAS_DATABASE_URL")
    engine = create_async_engine(_URL)
    yield engine
    await engine.dispose()


async def _setup_co(session: AsyncSession) -> dict[str, uuid.UUID]:
    """A tenant with an expense + cash + clearing account (clearing wired as the cost_allocation
    posting default), an open 2026 year, and a source + four target cost centres. Returns ids."""
    with system_context():
        tenant = Tenant(slug=f"co-{uuid.uuid4().hex[:8]}", name="CO")
        session.add(tenant)
        await session.commit()
    tenant_id = tenant.id
    ids: dict[str, uuid.UUID] = {"tenant_id": tenant_id}
    with tenant_context(tenant_id):
        for code, name, atype in (
            ("1000", "Cash", "ASSET"),
            ("5000", "Expense", "EXPENSE"),
            ("9000", "Cost Allocation Clearing", "EXPENSE"),
        ):
            account = await service.create_account(
                session, tenant_id, AccountCreate(code=code, name=name, account_type=atype)
            )
            ids[code] = account.id
        await service.set_posting_default(session, tenant_id, CO_ALLOCATION_CLEARING, ids["9000"])
        await service.create_fiscal_year(
            session,
            tenant_id,
            FiscalYearCreate(code="2026", name="FY2026", start_date=date(2026, 1, 1)),
        )
        source = await service.create_cost_center(
            session, tenant_id, CostCenterCreate(code="SRC", name="Source")
        )
        ids["source"] = source.id
        targets = []
        for i in range(4):
            cc = await service.create_cost_center(
                session, tenant_id, CostCenterCreate(code=f"T{i}", name=f"T{i}")
            )
            targets.append(AllocationTargetCreate(target_cost_center_id=cc.id, weight=Decimal(25)))
            ids[f"T{i}"] = cc.id
        rule = await service.create_allocation_rule(
            session,
            tenant_id,
            AllocationRuleCreate(
                code="R1",
                name="Rule",
                source_cost_center_id=source.id,
                basis=AllocationBasis.PERCENT,
                targets=targets,
            ),
        )
        ids["rule"] = rule.id
        await session.commit()
    return ids


@pytest.mark.pg
async def test_allocation_posts_on_postgres(pg_engine: AsyncEngine) -> None:
    """A CO_ALLOCATION entry with N cost-centre dimension lines posts on Postgres, exercising the
    balance trigger (it SUMs debits == credits over many lines) on the real database."""
    async with pg_engine.begin() as conn:
        await conn.exec_driver_sql(
            "TRUNCATE fin_allocation_runs, fin_allocation_rule_targets, fin_allocation_rules, "
            "fin_cost_centers, fin_profit_centers, fin_journal_lines, fin_journal_entries, "
            "fin_posting_defaults, fin_fiscal_periods, fin_fiscal_years, fin_accounts, "
            "core_number_sequences, core_documents, core_doc_links, adm_tenants "
            "RESTART IDENTITY CASCADE"
        )
    async with build_session_factory(pg_engine)() as session:
        ids = await _setup_co(session)
        tenant_id = ids["tenant_id"]
        with tenant_context(tenant_id):
            entry = await service.create_draft_entry(
                session,
                tenant_id,
                JournalEntryCreate(
                    posting_date=_PD,
                    currency_code="USD",
                    lines=[
                        JournalLineCreate(
                            account_id=ids["5000"],
                            transaction_debit_amount=Decimal("1000.00"),
                            cost_center_id=ids["source"],
                        ),
                        JournalLineCreate(
                            account_id=ids["1000"],
                            transaction_credit_amount=Decimal("1000.00"),
                        ),
                    ],
                ),
            )
            await service.post_entry(session, tenant_id, entry.id)
            await session.commit()
            period = (
                await session.execute(
                    select(JournalEntry.fiscal_period_id).where(JournalEntry.id == entry.id)
                )
            ).scalar_one()

            async def work() -> None:
                await service.run_allocation(session, tenant_id, ids["rule"], period, _PD)

            await run_in_uow(session, work)
            await session.commit()
            runs = await service.list_allocation_runs(session, tenant_id, ids["rule"])
            posted = await session.get(JournalEntry, runs[0].journal_entry_id)
            lines = (
                await session.execute(
                    select(JournalLine).where(
                        JournalLine.journal_entry_id == runs[0].journal_entry_id
                    )
                )
            ).scalars().all()
    assert posted.entry_number is not None
    debit = sum((Decimal(str(line.functional_debit_amount)) for line in lines), Decimal(0))
    credit = sum((Decimal(str(line.functional_credit_amount)) for line in lines), Decimal(0))
    # Five lines (1 source credit + 4 target debits), balanced in functional.
    assert debit == credit == Decimal("1000.00")
