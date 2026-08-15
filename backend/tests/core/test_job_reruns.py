"""Every registered job handler must be safe to run TWICE (P0 Task 1).

This file is the safety precondition for ``core/job_sweeper.py``, not a nice-to-have. The sweeper
re-dispatches a job whose PENDING row was orphaned; a handler that is not safe to re-run turns a
LOST COGS posting into a DUPLICATED one, which is strictly worse than the gap it closes. So the
ordering is: prove every handler here first, reclaim second.

**What these tests do and do NOT prove.** They exercise SEQUENTIAL re-execution — run, commit, run
again — which is the only shape the sweeper can produce, because it never re-dispatches a RUNNING
row and ``_run_handler``'s conditional claim means at most one runner ever executes a given job.
They prove nothing about CONCURRENT re-execution: every guard below is read-then-write with no
lock, so two handlers running at once against one payload would double-post (``run_payment_batch``
selects bills with ``open_amount > 0`` before either transaction commits). That is precisely why
the sweeper FAILS a stale RUNNING row for a human instead of re-dispatching it — see D-075(b).

**The shared detector.** :func:`ledger_fingerprint` counts the three append-only ledgers a
double-post can only ever grow — journal entries, journal lines and stock moves. Any handler that
posts twice moves that tuple, whatever module it lives in, so one helper covers all seven handlers
instead of seven bespoke assertions.

**The registry gate.** ``RERUN_VERDICTS`` must name every ``@register_job`` type in the codebase.
A new handler therefore cannot be added without classifying how it behaves on re-run, which is the
only way the sweeper's safety argument stays true as the codebase grows.

Note that ``run_in_uow`` commits ONCE, at the end, with the COMPLETED status inside the same
transaction (``core/jobs.py``) — so a runner killed mid-handler leaves no committed business
effect at all. These tests prove the STRONGER property (the first run fully committed anyway),
because that is what a human resubmitting an abandoned job re-runs against.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

import app.main  # noqa: F401  — imports every module, so the job registry is complete
from app.core.bootstrap import register_event_handlers
from app.core.events import run_in_uow
from app.core.exceptions import ConflictError
from app.core.jobs import registered_job_types
from app.core.tenancy import tenant_context
from app.modules.finance.models import JournalEntry, JournalLine
from app.modules.finance.payables_schemas import VendorBillCreate, VendorBillLineCreate
from app.modules.finance.service import bank_import, depreciation, fx_revaluation
from app.modules.finance.service import vendor_payments as ap
from app.modules.hospitality.service import depletion
from app.modules.inventory.constants import CountType
from app.modules.inventory.count_schemas import StockCountCreate
from app.modules.inventory.models import StockMove
from app.modules.inventory.service import counts as counts_service
from app.modules.inventory.service.count_jobs import count_post_job
from app.modules.manufacturing.models import PlannedOrder
from app.modules.manufacturing.service.mrp import mrp_run_job
from tests.modules.finance.factories import (
    ApSetup,
    build_ap_setup,
    build_bank_setup,
    build_fx_setup,
)
from tests.modules.finance.factories_assets import (
    build_asset_setup,
    create_active_asset,
    fiscal_periods,
)
from tests.modules.hospitality.factories import build_kitchen, build_open_ticket
from tests.modules.inventory.factories import build_count, build_stock, build_stock_setup
from tests.modules.manufacturing.mrp_factories import build_mrp_setup

# Every job type in the codebase, with WHY re-running it is safe. Adding a handler without adding a
# row here fails ``test_every_registered_job_type_is_classified`` — the gate that keeps the
# sweeper's precondition true as the codebase grows.
RERUN_VERDICTS: dict[str, str] = {
    "finance.payment_run": (
        "Naturally idempotent: the run selects bills with open_amount > 0, and the first run "
        "cleared them, so the second selects nothing."
    ),
    "finance.bank_statement_import": (
        "GUARDED (P0 Task 1): a second import under the same job_id returns the statement that "
        "job already created instead of a duplicate."
    ),
    "finance.depreciation_run": (
        "Already idempotent (PLAN 4.10): the UNIQUE(asset, period) backbone makes every asset "
        "ineligible once it has an entry for the period, so the second run finds nothing to "
        "depreciate and returns the period's existing POSTED run unchanged."
    ),
    "finance.fx_revaluation": (
        "Self-correcting by design (D-019 step 3): a re-run REVERSES the prior COMPLETED run's "
        "entries before posting fresh ones, so the net revaluation is unchanged."
    ),
    "hospitality.deplete_ticket": (
        "GUARDED (P0 Task 1): components already issued against this ticket are dropped, so a "
        "re-run issues nothing. Per-INGREDIENT, not per-ticket — a big check is chunked into "
        "several jobs whose component sets are disjoint (job_payloads)."
    ),
    "inventory.count_post": (
        "Already idempotent (D-013): post_count rejects a POSTED count with a ConflictError, so a "
        "re-run fails loudly instead of double-adjusting."
    ),
    "manufacturing.mrp_run": (
        "No natural key, and none is invented: re-planning the same date is a LEGITIMATE user "
        "action, so a second run is a second planning proposal. It posts nothing to the GL or the "
        "stock ledger, so a reclaimed run costs a discardable planning document, never a posting."
    ),
}


@pytest.fixture(autouse=True)
def _handlers() -> None:
    """The cross-module event handlers (inventory's COGS/issue bridges) the handlers publish into.
    The root conftest clears subscriptions per test, so re-register them here."""
    register_event_handlers()


async def ledger_fingerprint(session: AsyncSession, tenant_id: uuid.UUID) -> tuple[int, int, int]:
    """(journal entries, journal lines, stock moves) for a tenant — the shared double-post
    detector. All three ledgers are append-only (D-017/D-020), so a handler that posts a second
    time can only ever make this tuple grow."""
    session.expire_all()
    counts: list[int] = []
    with tenant_context(tenant_id):
        for model in (JournalEntry, JournalLine, StockMove):
            counts.append(
                (
                    await session.execute(
                        select(func.count(model.id)).where(model.tenant_id == tenant_id)
                    )
                ).scalar_one()
            )
    return counts[0], counts[1], counts[2]


async def run_handler(session: AsyncSession, tenant_id: uuid.UUID, handler, payload: dict) -> None:
    """Run one job handler exactly as ``core/jobs.py`` does: inside ``run_in_uow`` under the
    submitting tenant's context, so events, audit and the transaction boundary are production's."""
    with tenant_context(tenant_id):
        await run_in_uow(session, lambda: handler(session, tenant_id, payload))


def test_every_registered_job_type_is_classified() -> None:
    """The gate: a new @register_job handler must state how it behaves on re-run, because the
    sweeper will re-dispatch it. ``test.*`` types belong to tests/core/test_jobs.py's fixtures."""
    production = {t for t in registered_job_types() if not t.startswith("test.")}
    assert production == set(RERUN_VERDICTS)


# --- hospitality.deplete_ticket (the GL-effecting one Phase 19 backgrounded) ------


async def test_depletion_run_twice_issues_each_ingredient_once(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """The sweeper may re-dispatch a depletion whose runner died mid-flight. Depletion posts COGS,
    so running it twice must not issue the ingredients twice."""
    kitchen = await build_kitchen(
        db_session, tenant_a, {"BURGER": {"BUN": Decimal(2), "PATTY": Decimal(1)}}
    )
    ticket_id = await build_open_ticket(db_session, tenant_a, [(kitchen.dishes["BURGER"], "3")])
    with tenant_context(tenant_a):
        components = await depletion.aggregate_components(db_session, tenant_a, ticket_id)
    payload = depletion.job_payloads(ticket_id, components, move_date=date(2026, 3, 2))[0]

    await run_handler(db_session, tenant_a, depletion.deplete_ticket_job, payload)
    first = await ledger_fingerprint(db_session, tenant_a)
    assert first[2] > 0, "the first run must actually issue stock, or the test proves nothing"

    await run_handler(db_session, tenant_a, depletion.deplete_ticket_job, payload)
    assert await ledger_fingerprint(db_session, tenant_a) == first


async def test_depletion_of_a_second_chunk_still_issues_its_own_ingredients(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """The guard is per-INGREDIENT, not per-ticket. A big check is chunked into several jobs
    (``job_payloads``); a per-ticket 'already depleted?' check would silently skip every chunk
    after the first and lose most of the COGS — the exact failure the guard exists to prevent."""
    kitchen = await build_kitchen(
        db_session, tenant_a, {"BURGER": {"BUN": Decimal(1), "PATTY": Decimal(1)}}
    )
    ticket_id = await build_open_ticket(db_session, tenant_a, [(kitchen.dishes["BURGER"], "1")])
    with tenant_context(tenant_a):
        components = await depletion.aggregate_components(db_session, tenant_a, ticket_id)
    # Two single-component payloads: what job_payloads produces once the aggregate exceeds the chunk
    # ceiling, without needing a 50-ingredient recipe to reach it.
    chunks = [
        depletion.job_payloads(ticket_id, [component], move_date=date(2026, 3, 2))[0]
        for component in components
    ]
    assert len(chunks) == 2

    await run_handler(db_session, tenant_a, depletion.deplete_ticket_job, chunks[0])
    after_first = await ledger_fingerprint(db_session, tenant_a)
    await run_handler(db_session, tenant_a, depletion.deplete_ticket_job, chunks[1])

    assert (await ledger_fingerprint(db_session, tenant_a))[2] == after_first[2] + 1


# --- inventory.count_post --------------------------------------------------------


async def test_count_post_run_twice_adjusts_once(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """post_count already refuses a POSTED count (D-013). A re-run fails LOUDLY — which the runner
    records as a FAILED row on the ``failed_jobs`` card — rather than double-adjusting."""
    setup = await build_stock_setup(db_session, tenant_a)
    await build_stock(db_session, tenant_a, setup.item_id, setup.bin_a_id, Decimal(10))
    count = await build_count(
        db_session,
        tenant_a,
        StockCountCreate(count_type=CountType.PHYSICAL, warehouse_id=setup.warehouse_id),
    )
    await _count_every_line(db_session, tenant_a, count.id, Decimal(8))

    payload = {"count_id": str(count.id)}
    await run_handler(db_session, tenant_a, count_post_job, payload)
    first = await ledger_fingerprint(db_session, tenant_a)

    with pytest.raises(ConflictError):
        await run_handler(db_session, tenant_a, count_post_job, payload)
    assert await ledger_fingerprint(db_session, tenant_a) == first


async def _count_every_line(
    session: AsyncSession, tenant_id: uuid.UUID, count_id: uuid.UUID, quantity: Decimal
) -> None:
    """Record ``quantity`` on every line of a count so it is postable."""
    from app.modules.inventory.models import StockCountLine

    with tenant_context(tenant_id):
        line_ids = list(
            (
                await session.execute(
                    select(StockCountLine.id).where(StockCountLine.count_id == count_id)
                )
            )
            .scalars()
            .all()
        )

    async def work() -> None:
        with tenant_context(tenant_id):
            for line_id in line_ids:
                await counts_service.record_counted(session, tenant_id, count_id, line_id, quantity)

    with tenant_context(tenant_id):
        await run_in_uow(session, work)


# --- manufacturing.mrp_run -------------------------------------------------------


async def test_mrp_run_twice_posts_nothing_to_any_ledger(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """MRP has NO natural key and none is invented: re-planning the same date is a legitimate user
    action. Two things make a reclaimed MRP run harmless anyway — planning posts nothing to either
    ledger, and D-049's regeneration policy DELETES the prior un-firmed proposals before writing
    the new plan, so the proposal set does not grow. The only residue is a second MrpRun header,
    a discardable planning document."""
    await build_mrp_setup(db_session, tenant_a)
    payload = {"run_date": "2026-03-02", "horizon_days": 30}

    await run_handler(db_session, tenant_a, mrp_run_job, payload)
    first = await ledger_fingerprint(db_session, tenant_a)
    planned_after_first = await _count_rows(db_session, tenant_a, PlannedOrder)
    assert planned_after_first > 0

    await run_handler(db_session, tenant_a, mrp_run_job, payload)

    assert await ledger_fingerprint(db_session, tenant_a) == first
    assert await _count_rows(db_session, tenant_a, PlannedOrder) == planned_after_first


async def _count_rows(session: AsyncSession, tenant_id: uuid.UUID, model) -> int:
    session.expire_all()
    with tenant_context(tenant_id):
        return (
            await session.execute(
                select(func.count(model.id)).where(model.tenant_id == tenant_id)
            )
        ).scalar_one()


# --- finance.ap_payment_run ------------------------------------------------------


async def test_payment_run_twice_pays_each_bill_once(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """Naturally idempotent: the run selects bills with open_amount > 0, and the first run cleared
    them. No guard needed, and the test is what proves that claim stays true."""
    setup = await build_ap_setup(db_session, tenant_a)
    await _post_bill(db_session, setup)
    payload = {
        "up_to_due_date": "2026-03-31",
        "bank_account_id": str(setup.accounts["1000"]),
    }

    await run_handler(db_session, tenant_a, ap.payment_run_job, payload)
    first = await ledger_fingerprint(db_session, tenant_a)

    await run_handler(db_session, tenant_a, ap.payment_run_job, payload)
    assert await ledger_fingerprint(db_session, tenant_a) == first


async def _post_bill(session: AsyncSession, setup: ApSetup) -> None:
    """One posted vendor bill due inside the payment-run window."""
    from app.modules.finance import service as fin

    with tenant_context(setup.tenant_id):
        bill = await fin.create_vendor_bill(
            session,
            setup.tenant_id,
            VendorBillCreate(
                partner_id=uuid.uuid4(),
                partner_name="Acme Supplies",
                bill_date=date(2026, 3, 1),
                due_date=date(2026, 3, 15),
                currency_code="USD",
                ap_account_id=setup.accounts["2000"],
                description="Office supplies",
                lines=[
                    VendorBillLineCreate(
                        account_id=setup.accounts["5000"], net_amount=Decimal("100.00")
                    )
                ],
            ),
        )
        await session.commit()

    async def work() -> None:
        with tenant_context(setup.tenant_id):
            await fin.post_vendor_bill(session, setup.tenant_id, bill.id)

    with tenant_context(setup.tenant_id):
        await run_in_uow(session, work)


# --- finance.depreciation_run ----------------------------------------------------


async def test_depreciation_run_twice_charges_the_period_once(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """Without a guard the second run reads the asset's prior accumulated depreciation and advances
    the schedule ANOTHER period — a duplicated GL charge under the same period. The guard returns
    the period's existing POSTED run untouched."""
    setup = await build_asset_setup(db_session, tenant_a)
    await create_active_asset(db_session, setup, name="Lathe", cost="12000.00", life=12)
    period = (await fiscal_periods(db_session, setup))[0]
    payload = {
        "fiscal_period_id": str(period.id),
        "run_date": period.end_date.isoformat(),
    }

    await run_handler(db_session, tenant_a, depreciation.depreciation_run_job, payload)
    first = await ledger_fingerprint(db_session, tenant_a)
    assert first[0] > 0

    await run_handler(db_session, tenant_a, depreciation.depreciation_run_job, payload)
    assert await ledger_fingerprint(db_session, tenant_a) == first


# --- finance.fx_revaluation ------------------------------------------------------


async def test_fx_revaluation_run_twice_leaves_the_net_revaluation_unchanged(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """D-019 already makes this safe the append-only way: a re-run REVERSES the prior COMPLETED
    run before posting fresh entries, so the net FX adjustment is identical. New entries appear (a
    reversal is a posting), which is why the assertion is on the NET, not the row count."""
    setup = await build_fx_setup(db_session, tenant_a)
    await _post_eur_balance(db_session, setup.tenant_id, setup)
    period = await _period_containing(db_session, setup.tenant_id, date(2026, 3, 31))
    payload = {"fiscal_period_id": str(period), "rate_date": "2026-03-31"}

    await run_handler(db_session, tenant_a, fx_revaluation.fx_revaluation_job, payload)
    first = await _account_balance(db_session, tenant_a, setup.accounts["1900"])

    await run_handler(db_session, tenant_a, fx_revaluation.fx_revaluation_job, payload)
    assert await _account_balance(db_session, tenant_a, setup.accounts["1900"]) == first


async def _post_eur_balance(session: AsyncSession, tenant_id: uuid.UUID, setup) -> None:
    """A posted EUR entry giving the monetary bank account a foreign balance to revalue
    (tests/modules/finance/test_fx_revaluation.py's ``_post_eur_balance``, inlined)."""
    from app.modules.finance import service as fin
    from app.modules.finance.schemas import JournalEntryCreate, JournalLineCreate

    with tenant_context(tenant_id):
        entry = await fin.create_draft_entry(
            session,
            tenant_id,
            JournalEntryCreate(
                posting_date=date(2026, 3, 15),
                currency_code="EUR",
                lines=[
                    JournalLineCreate(
                        account_id=setup.eur_bank_id,
                        transaction_debit_amount=Decimal("100.00"),
                    ),
                    JournalLineCreate(
                        account_id=setup.accounts["4000"],
                        transaction_credit_amount=Decimal("100.00"),
                    ),
                ],
            ),
        )
        await session.commit()
        await run_in_uow(session, lambda: fin.post_entry(session, tenant_id, entry.id))


async def _period_containing(
    session: AsyncSession, tenant_id: uuid.UUID, day: date
) -> uuid.UUID:
    from app.modules.finance.models import FiscalPeriod

    with tenant_context(tenant_id):
        return (
            await session.execute(
                select(FiscalPeriod.id).where(
                    FiscalPeriod.tenant_id == tenant_id,
                    FiscalPeriod.start_date <= day,
                    FiscalPeriod.end_date >= day,
                )
            )
        ).scalar_one()


async def _account_balance(
    session: AsyncSession, tenant_id: uuid.UUID, account_id: uuid.UUID
) -> Decimal:
    session.expire_all()
    with tenant_context(tenant_id):
        rows = (
            await session.execute(
                select(
                    JournalLine.functional_debit_amount,
                    JournalLine.functional_credit_amount,
                ).where(
                    JournalLine.tenant_id == tenant_id, JournalLine.account_id == account_id
                )
            )
        ).all()
    return sum((Decimal(str(d)) - Decimal(str(c)) for d, c in rows), Decimal(0))


# --- finance.bank_statement_import -----------------------------------------------


async def test_bank_statement_import_run_twice_creates_one_statement(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """The natural key is the job id the router already stamps into the payload: a re-import under
    the same job returns the statement that job created rather than a duplicate with duplicate
    lines (which a reconciler would then have to spot by eye)."""
    from app.modules.finance.models import BankStatement

    setup = await build_bank_setup(db_session, tenant_a)
    job_id = uuid.uuid4()
    payload = {
        "bank_account_id": str(setup.bank_account_id),
        "statement_date": "2026-03-31",
        "opening_balance": "0.00",
        "closing_balance": "150.00",
        "currency_code": "USD",
        "csv_text": (
            "value_date,amount,description,counterparty_ref\n2026-03-02,150.00,Deposit,REF1\n"
        ),
        "job_id": str(job_id),
    }

    await run_handler(db_session, tenant_a, bank_import.bank_statement_import_job, payload)
    await run_handler(db_session, tenant_a, bank_import.bank_statement_import_job, payload)

    db_session.expire_all()
    with tenant_context(tenant_a):
        statements = (
            await db_session.execute(
                select(func.count(BankStatement.id)).where(BankStatement.tenant_id == tenant_a)
            )
        ).scalar_one()
    assert statements == 1
