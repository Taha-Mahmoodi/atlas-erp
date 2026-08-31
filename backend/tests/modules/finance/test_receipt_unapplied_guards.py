"""The row lock and the DB backstop under a deposit's draw-down (PLAN 20.4, D-084), on BOTH engines.

``unapplied_amount`` is money, and spending it is a read-then-write: two ``apply_receipt`` calls
under DIFFERENT idempotency keys (so D-013 replay protection does not apply) both read 500, both
pass the ceiling check, and the deposit is spent twice. That is the shape the shipped
``invoice.open_amount`` clearing already has, and the reason this file exists.

**Two guards, and they catch different things — neither substitutes for the other.**

- ``with_for_update`` on the receipt row is what actually serializes the two applications: the
  second waits, re-reads the DRAWN-DOWN balance under the lock and refuses. It is a real row lock
  on Postgres and a no-op on SQLite (D-020/D-036, the ``inv_stock_quants`` precedent), so the race
  itself is provable only on the runtime engine — hence a ``-m pg`` test, and hence the
  SQLite-runnable half pins the second transaction's code path (re-read, find it drained, refuse),
  which is engine-independent.
- ``CHECK (unapplied_amount >= 0)`` is the bypass-proof floor under ANY writer — a data fix-up, a
  later folio path that forgets the lock, a migration. It does NOT catch the lost update above (both
  writers store ``500 - 300 = 200``, which is non-negative), and claiming it did would be exactly
  the kind of stale claim this PR is fixing elsewhere. It catches a balance going negative.

The ``-m pg`` variants run the SAME assertions against real Postgres (D-022/D-003), because a
portable CHECK and a FOR UPDATE clause are only worth what they do on the runtime engine.
"""

import asyncio
import os
import uuid
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.core.db import build_session_factory
from app.core.events import run_in_uow
from app.core.exceptions import ValidationFailedError
from app.core.tenancy import system_context, tenant_context
from app.modules.admin.models import Tenant
from app.modules.finance import service
from app.modules.finance.models import CustomerInvoice, CustomerReceipt
from app.modules.finance.receivables_schemas import ReceiptAllocationCreate
from app.modules.finance.service.receipts_read import get_customer_receipt
from tests.modules.finance.factories import ArSetup, build_ar_setup, seed_advance_account
from tests.modules.finance.test_receivables import _create_and_post_invoice, _invoice_payload
from tests.modules.finance.test_unapplied_receipts import _post_receipt, _receipt

_URL = os.environ.get("ATLAS_DATABASE_URL", "")

# A gated party waits at most this long for the other; a hang is a bug in the test, not a pass.
_GATE_TIMEOUT = 10.0


@pytest.fixture
async def pg_engine() -> AsyncEngine:
    """A freshly-migrated Postgres engine for the -m pg variants (the fx-guards precedent).
    Skipped when the URL is not Postgres so the default SQLite run never touches it."""
    if not _URL.startswith("postgresql"):
        pytest.skip("pg-marked test requires a PostgreSQL ATLAS_DATABASE_URL")
    engine = create_async_engine(_URL)
    yield engine
    await engine.dispose()


async def _setup(session: AsyncSession) -> ArSetup:
    """Its own tenant (so a pg run can repeat without truncating), wired for AR + on-account
    money."""
    with system_context():
        tenant = Tenant(slug=f"dep-{uuid.uuid4().hex[:8]}", name="Deposit Guard")
        session.add(tenant)
        await session.commit()
    setup = await build_ar_setup(session, tenant.id)
    await seed_advance_account(session, tenant.id)
    return setup


async def _deposit(
    session: AsyncSession, setup: ArSetup, partner_id: uuid.UUID, amount: str
) -> CustomerReceipt:
    return await _post_receipt(
        session, setup.tenant_id, _receipt(setup, partner_id=partner_id, amount=amount)
    )


def _set_unapplied(receipt_id: uuid.UUID, amount: str) -> sa.Update:
    """A CORE update straight at the column, bypassing the service (the stock-guard precedent: the
    raw-SQL ban is on app/, not tests/) — the point is what the DATABASE refuses."""
    return (
        sa.update(CustomerReceipt.__table__)
        .where(CustomerReceipt.__table__.c.id == receipt_id)
        .values(unapplied_amount=Decimal(amount))
    )


async def _assert_check_rejects_a_negative_balance(session: AsyncSession) -> None:
    setup = await _setup(session)
    deposit = await _deposit(session, setup, uuid.uuid4(), "500.00")
    with tenant_context(setup.tenant_id):
        # Spending the deposit down to exactly nothing is the normal end state.
        await session.execute(_set_unapplied(deposit.id, "0.00"))
        await session.flush()
        # One cent past it is a liability the property owes itself, and the CHECK says no.
        with pytest.raises(IntegrityError):
            await session.execute(_set_unapplied(deposit.id, "-0.01"))
            await session.flush()


async def _assert_the_locked_read_runs(session: AsyncSession) -> None:
    setup = await _setup(session)
    deposit = await _deposit(session, setup, uuid.uuid4(), "500.00")
    # The read apply_receipt takes before it spends anything: Postgres locks the row, SQLite omits
    # FOR UPDATE as a no-op (D-020). Either way the balance comes back and the statement is valid
    # DDL-wise on both dialects — the half of the lock that a portable test can assert.
    with tenant_context(setup.tenant_id):
        locked = await get_customer_receipt(session, setup.tenant_id, deposit.id, for_update=True)
    assert Decimal(str(locked.unapplied_amount)) == Decimal("500.00")


async def _assert_a_second_application_finds_the_deposit_drained(session: AsyncSession) -> None:
    """The code path the LOSER of the race runs after the lock releases, pinned where SQLite can
    see it: re-read the balance, find 200 left, refuse the 300. Engine-independent — Postgres runs
    exactly this once the winner commits."""
    setup = await _setup(session)
    first = await _create_and_post_invoice(
        session, setup, _invoice_payload(setup, net="300.00")
    )
    partner_id = first.partner_id
    second = await _create_and_post_invoice(
        session, setup, _invoice_payload(setup, net="300.00", partner_id=partner_id)
    )
    deposit = await _deposit(session, setup, partner_id, "500.00")

    with tenant_context(setup.tenant_id):

        async def spend_first() -> None:
            await service.apply_receipt(
                session,
                setup.tenant_id,
                deposit.id,
                [ReceiptAllocationCreate(invoice_id=first.id, amount=Decimal("300.00"))],
            )

        await run_in_uow(session, spend_first)

        with pytest.raises(ValidationFailedError) as exc:

            async def spend_second() -> None:
                await service.apply_receipt(
                    session,
                    setup.tenant_id,
                    deposit.id,
                    [ReceiptAllocationCreate(invoice_id=second.id, amount=Decimal("300.00"))],
                )

            await run_in_uow(session, spend_second)

    assert exc.value.code == "finance.receipt_apply_exceeds_unapplied"
    await session.refresh(deposit)
    await session.refresh(second)
    assert Decimal(str(deposit.unapplied_amount)) == Decimal("200.00")
    assert Decimal(str(second.open_amount)) == Decimal("300.00")  # nothing was spent twice


async def test_the_unapplied_check_rejects_a_negative_balance_sqlite(
    db_session: AsyncSession,
) -> None:
    await _assert_check_rejects_a_negative_balance(db_session)
    await db_session.rollback()


async def test_the_locked_read_runs_sqlite(db_session: AsyncSession) -> None:
    await _assert_the_locked_read_runs(db_session)


async def test_a_second_application_finds_the_deposit_drained_sqlite(
    db_session: AsyncSession,
) -> None:
    await _assert_a_second_application_finds_the_deposit_drained(db_session)


@pytest.mark.pg
async def test_the_unapplied_check_rejects_a_negative_balance_postgres(
    pg_engine: AsyncEngine,
) -> None:
    async with build_session_factory(pg_engine)() as session:
        await _assert_check_rejects_a_negative_balance(session)
        await session.rollback()


@pytest.mark.pg
async def test_the_locked_read_runs_postgres(pg_engine: AsyncEngine) -> None:
    async with build_session_factory(pg_engine)() as session:
        await _assert_the_locked_read_runs(session)
        await session.rollback()


@pytest.mark.pg
async def test_two_concurrent_applications_cannot_spend_one_deposit_twice(
    pg_engine: AsyncEngine,
) -> None:
    """THE race, on the engine that has one. Two applications of 300 against a 500 deposit, in
    separate sessions, released together — different invoices and different idempotency keys, so
    nothing upstream deduplicates them. Without the row lock both read 500, both pass the ceiling
    and both post: 600 spent out of 500, both invoices PAID, and the receipt still reads a tidy 200
    because each writer stored ``500 - 300``. With it, one waits, re-reads 200 and refuses."""
    factory = build_session_factory(pg_engine)
    async with factory() as session:
        setup = await _setup(session)
        first = await _create_and_post_invoice(
            session, setup, _invoice_payload(setup, net="300.00")
        )
        partner_id = first.partner_id
        second = await _create_and_post_invoice(
            session, setup, _invoice_payload(setup, net="300.00", partner_id=partner_id)
        )
        deposit = await _deposit(session, setup, partner_id, "500.00")
        tenant_id, deposit_id = setup.tenant_id, deposit.id
        invoice_ids = (first.id, second.id)

    gate = asyncio.Barrier(2)

    async def spend(invoice_id: uuid.UUID) -> str | None:
        """Apply 300 to one invoice in its own session; return the refusal code, or None if it
        won. Both parties wait at the barrier so neither can finish before the other begins."""
        async with factory() as own:
            with tenant_context(tenant_id):

                async def work() -> None:
                    await service.apply_receipt(
                        own,
                        tenant_id,
                        deposit_id,
                        [ReceiptAllocationCreate(invoice_id=invoice_id, amount=Decimal("300.00"))],
                    )

                await asyncio.wait_for(gate.wait(), _GATE_TIMEOUT)
                try:
                    await run_in_uow(own, work)
                except ValidationFailedError as exc:
                    return exc.code
        return None

    outcomes = await asyncio.gather(*(spend(invoice_id) for invoice_id in invoice_ids))

    assert sorted(outcome is None for outcome in outcomes) == [False, True]
    assert {outcome for outcome in outcomes if outcome} == {
        "finance.receipt_apply_exceeds_unapplied"
    }
    async with factory() as after:
        with tenant_context(tenant_id):
            receipt = await get_customer_receipt(after, tenant_id, deposit_id)
            open_amounts = [
                Decimal(str((await after.get(CustomerInvoice, invoice_id)).open_amount))
                for invoice_id in invoice_ids
            ]
    # 300 of the 500 was spent, once. The loser's invoice is untouched.
    assert Decimal(str(receipt.unapplied_amount)) == Decimal("200.00")
    assert sorted(open_amounts) == [Decimal("0.00"), Decimal("300.00")]
