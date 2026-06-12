"""Financial statements as pure projections of the universal journal (PLAN 4.8, D-021), SQLite.

The proof the whole finance engine is correct: a realistic posted dataset (capital injection, a
taxed sale, a partial receipt, an expense bill, a payment) is driven through the REAL service layer
(D-025), then every statement is checked against hand-computed figures and its own self-check —
trial balance debit==credit, P&L net income, balance-sheet Assets==Liabilities+Equity with derived
retained earnings, the indirect cash-flow reconciliation, cost-centre grouping, and margin-by-item.
Plus: no-stored-totals (statements recompute after a new posting), tenant isolation, RBAC, and a
``-m pg`` proof that the aggregate + covering index work on Postgres AND the line-immutability
trigger survives migration 0015.

DB-trigger backstops live in test_journal_db_guards.py; this file exercises the projection layer.
"""

import os
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.core.events import run_in_uow
from app.core.tenancy import system_context, tenant_context
from app.modules.admin.service import provision_tenant
from app.modules.finance import service
from app.modules.finance.constants import (
    FINANCE_ACCOUNT_READ,
    FINANCE_JOURNAL_POST,
    FINANCE_PERIOD_READ,
    AccountType,
    CashFlowCategory,
)
from app.modules.finance.controlling_schemas import CostCenterCreate
from app.modules.finance.models import JournalLine
from app.modules.finance.schemas import (
    AccountCreate,
    AccountGroupCreate,
    FiscalYearCreate,
    JournalEntryCreate,
    JournalLineCreate,
)

# Everything posts inside the open March 2026 period so net income equals the P&L for the period.
_PD = date(2026, 3, 15)
_PERIOD_START = date(2026, 3, 1)
_PERIOD_END = date(2026, 3, 31)

# (code, name, type, group_code, cash_flow_category, is_cash_equivalent)
_ACCOUNTS: tuple[tuple[str, str, AccountType, str, CashFlowCategory | None, bool], ...] = (
    ("1000", "Cash", AccountType.ASSET, "CA", CashFlowCategory.OPERATING, True),
    ("1200", "Accounts Receivable", AccountType.ASSET, "CA", CashFlowCategory.OPERATING, False),
    ("2000", "Accounts Payable", AccountType.LIABILITY, "CL", CashFlowCategory.OPERATING, False),
    ("2200", "Output VAT", AccountType.LIABILITY, "CL", CashFlowCategory.OPERATING, False),
    ("3000", "Share Capital", AccountType.EQUITY, "EQ", CashFlowCategory.FINANCING, False),
    ("4000", "Sales Revenue", AccountType.REVENUE, "RE", None, False),
    ("5000", "Operating Expenses", AccountType.EXPENSE, "EX", None, False),
)
_GROUPS = (
    ("CA", "Current Assets"),
    ("CL", "Current Liabilities"),
    ("EQ", "Equity"),
    ("RE", "Revenue"),
    ("EX", "Expenses"),
)


@dataclass(frozen=True)
class StatementSetup:
    """A tenant with a grouped chart of accounts, an open March-2026 period, and five posted entries
    forming a realistic ledger. Plain ids so a rollback never breaks a follow-up read."""

    tenant_id: uuid.UUID
    accounts: dict[str, uuid.UUID]


def _dr(account_id: uuid.UUID, amount: str, **dims: object) -> JournalLineCreate:
    return JournalLineCreate(
        account_id=account_id, transaction_debit_amount=Decimal(amount), **dims
    )


def _cr(account_id: uuid.UUID, amount: str, **dims: object) -> JournalLineCreate:
    return JournalLineCreate(
        account_id=account_id, transaction_credit_amount=Decimal(amount), **dims
    )


async def _post(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    lines: list[JournalLineCreate],
    description: str,
    posting_date: date = _PD,
) -> uuid.UUID:
    """Create + post one balanced entry through the real service (D-025)."""
    payload = JournalEntryCreate(
        posting_date=posting_date,
        currency_code="USD",
        description=description,
        lines=lines,
    )
    holder: dict[str, uuid.UUID] = {}

    async def work() -> None:
        entry = await service.create_draft_entry(session, tenant_id, payload)
        await session.flush()
        await service.post_entry(session, tenant_id, entry.id)
        holder["id"] = entry.id

    with tenant_context(tenant_id):
        await run_in_uow(session, work)
    return holder["id"]


# Statement reads run a tenant-scoped ORM query, so they need the D-007 ContextVar set
# (fail-closed). These wrappers set it so each test reads its own data without a with-block.


async def _trial_balance(session: AsyncSession, tenant_id: uuid.UUID):
    with tenant_context(tenant_id):
        return await service.trial_balance(session, tenant_id, _PERIOD_END)


async def _profit_and_loss(session: AsyncSession, tenant_id: uuid.UUID):
    with tenant_context(tenant_id):
        return await service.profit_and_loss(
            session, tenant_id, _PERIOD_START, _PERIOD_END
        )


async def _balance_sheet(session: AsyncSession, tenant_id: uuid.UUID):
    with tenant_context(tenant_id):
        return await service.balance_sheet(session, tenant_id, _PERIOD_END)


async def _cash_flow(session: AsyncSession, tenant_id: uuid.UUID):
    with tenant_context(tenant_id):
        return await service.cash_flow_indirect(
            session, tenant_id, _PERIOD_START, _PERIOD_END
        )


async def _build_dataset(
    session: AsyncSession, tenant_id: uuid.UUID
) -> dict[str, uuid.UUID]:
    """The realistic ledger (all through real services): groups + accounts + period + five entries.

    Hand-computed resulting balances (debit-positive): Cash +10300, AR +600, Share Capital -10000,
    Revenue -1000, Output VAT -200, Expense +500, AP -200. Trial balance: 11400 == 11400."""
    with tenant_context(tenant_id):
        group_ids: dict[str, uuid.UUID] = {}
        for code, name in _GROUPS:
            group = await service.create_account_group(
                session, tenant_id, AccountGroupCreate(code=code, name=name)
            )
            group_ids[code] = group.id
        accounts: dict[str, uuid.UUID] = {}
        for code, name, atype, group_code, cf, is_cash in _ACCOUNTS:
            account = await service.create_account(
                session,
                tenant_id,
                AccountCreate(
                    code=code,
                    name=name,
                    account_type=atype,
                    account_group_id=group_ids[group_code],
                    cash_flow_category=cf,
                    is_cash_equivalent=is_cash,
                ),
            )
            accounts[code] = account.id
        await service.create_fiscal_year(
            session,
            tenant_id,
            FiscalYearCreate(code="2026", name="FY2026", start_date=date(2026, 1, 1)),
        )
        await session.commit()

    a = accounts
    # 1. Capital injection: Dr Cash 10000 / Cr Share Capital 10000.
    await _post(
        session, tenant_id, [_dr(a["1000"], "10000"), _cr(a["3000"], "10000")], "Capital"
    )
    # 2. Taxed sale: Dr AR 1200 / Cr Revenue 1000 / Cr Output VAT 200.
    await _post(
        session,
        tenant_id,
        [_dr(a["1200"], "1200"), _cr(a["4000"], "1000"), _cr(a["2200"], "200")],
        "Sale",
    )
    # 3. Partial receipt: Dr Cash 600 / Cr AR 600.
    await _post(
        session, tenant_id, [_dr(a["1000"], "600"), _cr(a["1200"], "600")], "Receipt"
    )
    # 4. Expense bill: Dr Expense 500 / Cr AP 500.
    await _post(
        session, tenant_id, [_dr(a["5000"], "500"), _cr(a["2000"], "500")], "Bill"
    )
    # 5. Payment: Dr AP 300 / Cr Cash 300.
    await _post(
        session, tenant_id, [_dr(a["2000"], "300"), _cr(a["1000"], "300")], "Payment"
    )
    return accounts


@pytest.fixture
async def statements_setup(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> StatementSetup:
    accounts = await _build_dataset(db_session, tenant_a)
    return StatementSetup(tenant_id=tenant_a, accounts=accounts)


# --- Trial balance ------------------------------------------------------------


async def test_trial_balance_is_balanced_and_matches_hand_computation(
    db_session: AsyncSession, statements_setup: StatementSetup
) -> None:
    tb = await _trial_balance(db_session, statements_setup.tenant_id)
    assert tb.is_balanced is True
    assert tb.total_debit == tb.total_credit == Decimal("11400.00")
    # A known account's balance: Cash nets +10300 on the debit side.
    cash = next(r for r in tb.rows if r.account_code == "1000")
    assert cash.debit == Decimal("10300.00")
    assert cash.credit == Decimal("0.00")
    # Output VAT is a credit-side balance.
    vat = next(r for r in tb.rows if r.account_code == "2200")
    assert vat.credit == Decimal("200.00")
    assert vat.debit == Decimal("0.00")


# --- P&L ----------------------------------------------------------------------


async def test_profit_and_loss_net_income(
    db_session: AsyncSession, statements_setup: StatementSetup
) -> None:
    pl = await _profit_and_loss(db_session, statements_setup.tenant_id)
    assert pl.revenue_total == Decimal("1000.00")
    assert pl.expense_total == Decimal("500.00")
    # Net income == revenue - expense (hand-computed).
    assert pl.net_income == Decimal("500.00")
    # Revenue appears under its account group as a positive (natural) magnitude.
    revenue_line = pl.revenue_groups[0].lines[0]
    assert revenue_line.account_code == "4000"
    assert revenue_line.amount == Decimal("1000.00")


# --- Balance sheet ------------------------------------------------------------


async def test_balance_sheet_balances_with_derived_retained_earnings(
    db_session: AsyncSession, statements_setup: StatementSetup
) -> None:
    bs = await _balance_sheet(db_session, statements_setup.tenant_id)
    assert bs.is_balanced is True
    assert bs.asset_total == Decimal("10900.00")
    assert bs.liability_total == Decimal("400.00")
    assert bs.equity_total == Decimal("10500.00")
    # Assets == Liabilities + Equity.
    assert bs.asset_total == bs.liability_total + bs.equity_total
    # Retained earnings is derived = net income to date, and (all activity in one period) equals the
    # P&L net income.
    assert bs.retained_earnings == Decimal("500.00")
    pl = await _profit_and_loss(db_session, statements_setup.tenant_id)
    assert bs.retained_earnings == pl.net_income
    # The synthetic earnings line is present in equity (no real account backs it).
    earnings = [
        line
        for group in bs.equity_groups
        for line in group.lines
        if line.amount == Decimal("500.00") and line.account_code == "EARNINGS"
    ]
    assert len(earnings) == 1


# --- Cash flow (indirect) -----------------------------------------------------


async def test_cash_flow_indirect_reconciles(
    db_session: AsyncSession, statements_setup: StatementSetup
) -> None:
    cf = await _cash_flow(db_session, statements_setup.tenant_id)
    # The built-in self-check: net change from activities == actual cash-equivalent movement.
    assert cf.is_reconciled is True
    assert cf.net_income == Decimal("500.00")
    # Cash (the only cash equivalent) moved +10300 over the period.
    assert cf.cash_account_movement == Decimal("10300.00")
    assert cf.net_change_from_activities == Decimal("10300.00")
    # Net income + working-capital deltas tie out to the cash movement both ways.
    assert cf.net_change_from_activities == cf.cash_account_movement


# --- Cost-centre report -------------------------------------------------------


async def test_cost_center_report_sums_to_account_totals(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    # A dedicated dataset: two cost centres each carrying part of the expense + an untagged part.
    with tenant_context(tenant_a):
        cash = await service.create_account(
            db_session,
            tenant_a,
            AccountCreate(code="1000", name="Cash", account_type=AccountType.ASSET),
        )
        expense = await service.create_account(
            db_session,
            tenant_a,
            AccountCreate(code="5000", name="Expenses", account_type=AccountType.EXPENSE),
        )
        cc_a = await service.create_cost_center(
            db_session, tenant_a, CostCenterCreate(code="CC-A", name="Centre A")
        )
        cc_b = await service.create_cost_center(
            db_session, tenant_a, CostCenterCreate(code="CC-B", name="Centre B")
        )
        await service.create_fiscal_year(
            db_session,
            tenant_a,
            FiscalYearCreate(code="2026", name="FY2026", start_date=date(2026, 1, 1)),
        )
        await db_session.commit()

    # Dr Expense (CC-A 100 + CC-B 70 + untagged 30) / Cr Cash 200. The cash credit carries no cost
    # centre, so it lands in the untagged bucket alongside the untagged expense.
    await _post(
        db_session,
        tenant_a,
        [
            _dr(expense.id, "100", cost_center_id=cc_a.id),
            _dr(expense.id, "70", cost_center_id=cc_b.id),
            _dr(expense.id, "30"),
            _cr(cash.id, "200"),
        ],
        "Tagged expense",
    )

    with tenant_context(tenant_a):
        report = await service.cost_center_report(
            db_session, tenant_a, _PERIOD_START, _PERIOD_END
        )

    def _expense_amount(section) -> Decimal:
        """The Expense (5000) account's contribution within a cost-centre section, or 0."""
        return next(
            (line.amount for line in section.lines if line.account_code == "5000"),
            Decimal(0),
        )

    by_centre = {s.cost_center_code: s for s in report.sections}
    # Each cost centre carries exactly its tagged share of the expense.
    assert _expense_amount(by_centre["CC-A"]) == Decimal("100.00")
    assert _expense_amount(by_centre["CC-B"]) == Decimal("70.00")
    # The untagged bucket carries the untagged expense 30 plus the untagged cash credit -200.
    untagged = by_centre[None]
    assert _expense_amount(untagged) == Decimal("30.00")
    # The expense account's per-cost-centre balances sum to its full account total (200) — the
    # cost-centre report is a faithful re-grouping of the SAME journal lines (D-021).
    expense_total = sum((_expense_amount(s) for s in report.sections), Decimal(0))
    assert expense_total == Decimal("200.00")

    # Filtering to one cost centre returns only that section.
    with tenant_context(tenant_a):
        filtered = await service.cost_center_report(
            db_session, tenant_a, _PERIOD_START, _PERIOD_END, cost_center_id=cc_a.id
        )
    assert [s.cost_center_code for s in filtered.sections] == ["CC-A"]
    assert _expense_amount(filtered.sections[0]) == Decimal("100.00")


# --- Margin by product --------------------------------------------------------


async def test_margin_by_product_per_item(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    item_x = uuid.uuid4()
    item_y = uuid.uuid4()
    with tenant_context(tenant_a):
        cash = await service.create_account(
            db_session,
            tenant_a,
            AccountCreate(code="1000", name="Cash", account_type=AccountType.ASSET),
        )
        revenue = await service.create_account(
            db_session,
            tenant_a,
            AccountCreate(code="4000", name="Revenue", account_type=AccountType.REVENUE),
        )
        cogs = await service.create_account(
            db_session,
            tenant_a,
            AccountCreate(code="5000", name="COGS", account_type=AccountType.EXPENSE),
        )
        await service.create_fiscal_year(
            db_session,
            tenant_a,
            FiscalYearCreate(code="2026", name="FY2026", start_date=date(2026, 1, 1)),
        )
        await db_session.commit()

    # Item X: revenue 1000, COGS 600 -> margin 400 (40%). Item Y: revenue 500, COGS 500 -> margin 0.
    await _post(
        db_session,
        tenant_a,
        [_dr(cash.id, "1000"), _cr(revenue.id, "1000", item_id=item_x)],
        "Sale X",
    )
    await _post(
        db_session,
        tenant_a,
        [_dr(cogs.id, "600", item_id=item_x), _cr(cash.id, "600")],
        "COGS X",
    )
    await _post(
        db_session,
        tenant_a,
        [_dr(cash.id, "500"), _cr(revenue.id, "500", item_id=item_y)],
        "Sale Y",
    )
    await _post(
        db_session,
        tenant_a,
        [_dr(cogs.id, "500", item_id=item_y), _cr(cash.id, "500")],
        "COGS Y",
    )

    with tenant_context(tenant_a):
        margin = await service.margin_by_product(
            db_session, tenant_a, _PERIOD_START, _PERIOD_END
        )
    by_item = {row.item_id: row for row in margin.items}
    assert by_item[item_x].revenue == Decimal("1000.00")
    assert by_item[item_x].cogs == Decimal("600.00")
    assert by_item[item_x].margin == Decimal("400.00")
    assert by_item[item_x].margin_percent == Decimal("40.00")
    assert by_item[item_y].margin == Decimal("0.00")
    assert by_item[item_y].margin_percent == Decimal("0.00")


# --- No stored totals: statements recompute after a new posting ---------------


async def test_statements_recompute_after_new_posting(
    db_session: AsyncSession, statements_setup: StatementSetup
) -> None:
    setup = statements_setup
    before = await _trial_balance(db_session, setup.tenant_id)
    assert before.total_debit == Decimal("11400.00")
    # Post another sale; with no stored totals the trial balance reflects it on the next read.
    await _post(
        db_session,
        setup.tenant_id,
        [_dr(setup.accounts["1000"], "250"), _cr(setup.accounts["4000"], "250")],
        "Extra cash sale",
    )
    after = await _trial_balance(db_session, setup.tenant_id)
    assert after.is_balanced is True
    assert after.total_debit == Decimal("11650.00")  # 11400 + 250
    pl = await _profit_and_loss(db_session, setup.tenant_id)
    assert pl.revenue_total == Decimal("1250.00")  # 1000 + 250


# --- Tenant isolation ---------------------------------------------------------


async def test_statements_exclude_other_tenant(
    db_session: AsyncSession,
    statements_setup: StatementSetup,
    tenant_b: uuid.UUID,
) -> None:
    # Tenant B gets its own ledger; tenant A's statements must not see B's postings.
    await _build_dataset(db_session, tenant_b)
    a_tb = await _trial_balance(db_session, statements_setup.tenant_id)
    b_tb = await _trial_balance(db_session, tenant_b)
    # Each tenant sees exactly its own 11400; neither doubles up.
    assert a_tb.total_debit == Decimal("11400.00")
    assert b_tb.total_debit == Decimal("11400.00")
    a_account_ids = {r.account_id for r in a_tb.rows}
    b_account_ids = {r.account_id for r in b_tb.rows}
    assert a_account_ids.isdisjoint(b_account_ids)


# --- RBAC ---------------------------------------------------------------------


async def test_statements_require_statements_read_permission(
    client: AsyncClient, finance_user_factory
) -> None:
    from tests.modules.finance.conftest import _login

    # A principal WITHOUT finance.statements.read (only generic read keys).
    principal = await finance_user_factory(
        slug="fin-norpt",
        email="norpt@fin-norpt.test",
        keys=(FINANCE_ACCOUNT_READ, FINANCE_PERIOD_READ, FINANCE_JOURNAL_POST),
    )
    token = await _login(client, principal)
    client.headers["Authorization"] = f"Bearer {token}"
    resp = await client.get(
        "/api/v1/finance/statements/trial-balance", params={"as_of": "2026-03-31"}
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "rbac.permission_denied"


async def test_statements_endpoint_returns_balanced(
    finance_client: AsyncClient, db_session: AsyncSession
) -> None:
    # Build a dataset for the finance_client's tenant, then hit the endpoints.
    me = await finance_client.get("/api/v1/auth/me")
    tenant_id = uuid.UUID(me.json()["tenant_id"])
    await _build_dataset(db_session, tenant_id)

    tb = await finance_client.get(
        "/api/v1/finance/statements/trial-balance", params={"as_of": "2026-03-31"}
    )
    assert tb.status_code == 200, tb.text
    assert tb.json()["is_balanced"] is True
    # Money serializes as a Decimal string at the MoneyType scale; compare via Decimal (D-015).
    assert Decimal(tb.json()["total_debit"]) == Decimal("11400.00")

    bs = await finance_client.get(
        "/api/v1/finance/statements/balance-sheet", params={"as_of": "2026-03-31"}
    )
    assert bs.status_code == 200, bs.text
    assert bs.json()["is_balanced"] is True
    assert Decimal(bs.json()["retained_earnings"]) == Decimal("500.00")

    cf = await finance_client.get(
        "/api/v1/finance/statements/cash-flow",
        params={"date_from": "2026-03-01", "date_to": "2026-03-31"},
    )
    assert cf.status_code == 200, cf.text
    assert cf.json()["is_reconciled"] is True


# --- Postgres: aggregate + covering index + trigger-survival proof (-m pg) ----


@pytest.fixture
async def pg_engine() -> AsyncEngine:
    """A freshly-migrated Postgres engine for the -m pg variant (mirrors the db-guard fixture)."""
    url = os.environ.get("ATLAS_DATABASE_URL", "")
    if not url.startswith("postgresql"):
        pytest.skip("pg-marked test requires a PostgreSQL ATLAS_DATABASE_URL")
    engine = create_async_engine(url)
    yield engine
    await engine.dispose()


async def _reset_pg(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE fin_journal_lines, fin_journal_entries, fin_fiscal_periods, "
                "fin_fiscal_years, fin_account_groups, fin_accounts, core_documents, "
                "core_number_sequences, adm_tenants RESTART IDENTITY CASCADE"
            )
        )


@pytest.mark.pg
async def test_statements_on_postgres_balanced_and_trigger_survives(
    pg_engine: AsyncEngine,
) -> None:
    """On real Postgres (D-022): the base aggregate + covering index produce a balanced trial
    balance and balance sheet, AND the line-immutability trigger still fires after migration 0015 —
    proving the index migration did not drop the trigger (CREATE INDEX is not a table rebuild)."""
    from app.core.db import build_session_factory

    await _reset_pg(pg_engine)
    session = build_session_factory(pg_engine)()
    async with session:
        with system_context():
            tenant = await provision_tenant(session, slug="st-pg", name="Stmt")
            await session.commit()
        tenant_id = tenant.id
        accounts = await _build_dataset(session, tenant_id)

        with tenant_context(tenant_id):
            tb = await service.trial_balance(session, tenant_id, _PERIOD_END)
            assert tb.is_balanced is True
            assert tb.total_debit == tb.total_credit == Decimal("11400.00")
            bs = await service.balance_sheet(session, tenant_id, _PERIOD_END)
            assert bs.is_balanced is True
            assert bs.retained_earnings == Decimal("500.00")

            # The line-immutability trigger must still fire after 0015's index migration: a raw
            # UPDATE on a POSTED line raises ATLAS_POSTED_IMMUTABLE (CREATE INDEX is not a rebuild).
            posted_line_id = (
                await session.execute(
                    sa.select(JournalLine.id)
                    .where(
                        JournalLine.account_id == accounts["1000"],
                        JournalLine.is_posted.is_(True),
                    )
                    .limit(1)
                )
            ).scalar_one()
        with pytest.raises((DBAPIError, IntegrityError)) as exc:
            await session.execute(
                text("UPDATE fin_journal_lines SET line_number = 99 WHERE id = :i").bindparams(
                    sa.bindparam("i", value=posted_line_id, type_=sa.Uuid)
                )
            )
        assert "ATLAS_POSTED_IMMUTABLE" in str(exc.value)
    await session.close()
