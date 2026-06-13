"""Perf smoke budgets (PLAN 4P.7, PERFORMANCE §5) against the session-seeded tenant.

Budgets are DEFINED against Postgres (PERFORMANCE §5: list endpoints p95 < 300 ms,
statements/aging < 1.5 s). Each test asserts the median of 5 timed runs (see the ``timed``
fixture) at 1x those numbers when ATLAS_PERF_DATABASE_URL points at Postgres, and at 2x on
the SQLite CI smoke (600 ms / 3 s) so the non-blocking job stays stable while still
catching regressions. The journal list is timed through the API (auth + RBAC +
serialization — the user-perceived path); the statement/aging reports time the SERVICE
functions directly, where per-request auth overhead would otherwise dominate the
aggregate being measured.

A failing budget before a promotion is ``severity:major`` (PERFORMANCE §5): file the
issue, fix or consciously re-budget with rationale in DECISIONS.md — never delete a test.
The sanity test pins the dataset volume + the debits==credits identity so a
silently-small or unbalanced seed can never fake a pass.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import tenant_context
from app.modules.finance import service
from app.modules.finance.models import CustomerInvoice, JournalEntry, JournalLine
from tests.perf.conftest import TimedFn
from tests.perf.factories import ENTRY_COUNT, INVOICE_COUNT, LINES_PER_ENTRY, PerfDataset

pytestmark = pytest.mark.perf

# PERFORMANCE §5 base budgets in seconds (Postgres = 1x; SQLite smoke = 2x via
# PerfDataset.budget_multiplier).
_LIST_BUDGET = 0.300
_STATEMENT_BUDGET = 1.5


async def test_journal_entries_list_api_meets_budget(
    perf_dataset: PerfDataset, perf_client: AsyncClient, timed: TimedFn
) -> None:
    """GET /finance/journal-entries filtered + paginated at 50 — the §5 list budget."""
    url = "/api/v1/finance/journal-entries?status=POSTED&limit=50"

    async def call() -> None:
        response = await perf_client.get(url)
        assert response.status_code == 200, response.text
        assert len(response.json()["items"]) == 50

    median = await timed("journal-entries list API (status filter, page of 50)", call)
    assert median <= _LIST_BUDGET * perf_dataset.budget_multiplier


async def test_trial_balance_full_year_meets_budget(
    perf_dataset: PerfDataset, perf_session: AsyncSession, timed: TimedFn
) -> None:
    """Trial balance over the full seeded year — the §5 statements budget."""

    async def call() -> None:
        with tenant_context(perf_dataset.tenant_id):
            report = await service.trial_balance(
                perf_session, perf_dataset.tenant_id, perf_dataset.year_end
            )
        assert report.rows

    median = await timed("trial balance (full year)", call)
    assert median <= _STATEMENT_BUDGET * perf_dataset.budget_multiplier


async def test_profit_and_loss_full_year_meets_budget(
    perf_dataset: PerfDataset, perf_session: AsyncSession, timed: TimedFn
) -> None:
    """P&L over the full seeded year — the §5 statements budget."""

    async def call() -> None:
        with tenant_context(perf_dataset.tenant_id):
            report = await service.profit_and_loss(
                perf_session,
                perf_dataset.tenant_id,
                perf_dataset.year_start,
                perf_dataset.year_end,
            )
        assert report.revenue_groups and report.expense_groups

    median = await timed("profit & loss (full year)", call)
    assert median <= _STATEMENT_BUDGET * perf_dataset.budget_multiplier


async def test_balance_sheet_year_end_meets_budget(
    perf_dataset: PerfDataset, perf_session: AsyncSession, timed: TimedFn
) -> None:
    """Balance sheet as of the seeded year-end — the §5 statements budget."""

    async def call() -> None:
        with tenant_context(perf_dataset.tenant_id):
            report = await service.balance_sheet(
                perf_session, perf_dataset.tenant_id, perf_dataset.year_end
            )
        assert report.asset_groups

    median = await timed("balance sheet (as of year-end)", call)
    assert median <= _STATEMENT_BUDGET * perf_dataset.budget_multiplier


async def test_ar_aging_meets_budget(
    perf_dataset: PerfDataset, perf_session: AsyncSession, timed: TimedFn
) -> None:
    """AR aging as of the seeded year-end — the §5 aging budget."""

    async def call() -> None:
        with tenant_context(perf_dataset.tenant_id):
            report = await service.customer_aging(
                perf_session, perf_dataset.tenant_id, perf_dataset.year_end
            )
        assert report["partners"]

    median = await timed("AR aging (as of year-end)", call)
    assert median <= _STATEMENT_BUDGET * perf_dataset.budget_multiplier


async def test_dataset_meets_volume_targets_and_balances(
    perf_dataset: PerfDataset, perf_session: AsyncSession
) -> None:
    """Precondition pin: the budgets above are only meaningful against the seeded volume,
    so a silently-small dataset (a seeding regression) fails HERE rather than producing a
    vacuous timing pass. Also proves the bulk-inserted ledger satisfies the universal-
    journal identity (debits == credits) — the same data a real posting path would yield."""
    tenant_id = perf_dataset.tenant_id
    with tenant_context(tenant_id):
        entries = (
            await perf_session.execute(
                select(func.count())
                .select_from(JournalEntry)
                .where(JournalEntry.tenant_id == tenant_id)
            )
        ).scalar_one()
        lines = (
            await perf_session.execute(
                select(func.count())
                .select_from(JournalLine)
                .where(JournalLine.tenant_id == tenant_id, JournalLine.is_posted.is_(True))
            )
        ).scalar_one()
        invoices = (
            await perf_session.execute(
                select(func.count())
                .select_from(CustomerInvoice)
                .where(CustomerInvoice.tenant_id == tenant_id)
            )
        ).scalar_one()
        trial = await service.trial_balance(perf_session, tenant_id, perf_dataset.year_end)
        aging = await service.customer_aging(perf_session, tenant_id, perf_dataset.year_end)

    assert entries >= ENTRY_COUNT
    assert lines >= ENTRY_COUNT * LINES_PER_ENTRY
    assert invoices >= INVOICE_COUNT
    assert trial.is_balanced and trial.total_debit > 0
    assert aging["total"] > 0 and len(aging["partners"]) > 1
    print(
        f"\n[perf] sanity: {entries} entries / {lines} posted lines / {invoices} invoices; "
        f"TB balanced at {trial.total_debit}; AR aging total {aging['total']}"
    )
