"""Realized FX at AP clearing (PLAN 4.5, D-019), SQLite + a Postgres variant.

A foreign-currency bill posted at rate R1 and paid at rate R2 books the functional difference over
the cleared amount to the realized FX gain/loss account INSIDE the payment entry, which must still
balance in functional. The pg variant proves the balance trigger accepts that foreign payment entry
on the real engine (the trigger IS involved).

Uses the fx_setup fixture (functional USD, foreign EUR; SPOT 2026-01-01=1.10, 2026-03-01=1.20;
realized-FX accounts wired; EUR bank=1100; AP control=2000; expense=5000).
"""

import os
import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.core.db import build_session_factory
from app.core.events import run_in_uow
from app.core.tenancy import system_context, tenant_context
from app.modules.admin.models import Tenant
from app.modules.finance import service
from app.modules.finance.constants import (
    FX_REALIZED_GAIN,
    FX_REALIZED_LOSS,
    BillStatus,
    RateKind,
)
from app.modules.finance.models import JournalLine, VendorBill
from app.modules.finance.payables_schemas import (
    PaymentAllocationCreate,
    VendorBillCreate,
    VendorBillLineCreate,
    VendorPaymentCreate,
)
from app.modules.finance.schemas import AccountCreate, FiscalYearCreate
from tests.modules.finance.conftest import FxSetup

_R1_DATE = date(2026, 1, 1)  # SPOT 1.10
_R2_DATE = date(2026, 3, 1)  # SPOT 1.20
_URL = os.environ.get("ATLAS_DATABASE_URL", "")


async def _post_eur_bill(
    session: AsyncSession, fx_setup: FxSetup, net: str = "100.00"
) -> VendorBill:
    partner = uuid.uuid4()
    with tenant_context(fx_setup.tenant_id):
        bill = await service.create_vendor_bill(
            session,
            fx_setup.tenant_id,
            VendorBillCreate(
                partner_id=partner,
                partner_name="Euro Vendor",
                bill_date=_R1_DATE,
                due_date=date(2026, 3, 31),
                currency_code="EUR",
                ap_account_id=fx_setup.accounts["2000"],
                lines=[
                    VendorBillLineCreate(
                        account_id=fx_setup.accounts["5000"], net_amount=Decimal(net)
                    )
                ],
            ),
        )
        await session.commit()

        async def work() -> None:
            await service.post_vendor_bill(
                session, fx_setup.tenant_id, bill.id, posting_date=_R1_DATE
            )

        await run_in_uow(session, work)
        await session.refresh(bill)
    return bill


async def test_foreign_bill_books_functional_at_bill_rate(
    db_session: AsyncSession, fx_setup: FxSetup
) -> None:
    bill = await _post_eur_bill(db_session, fx_setup)
    with tenant_context(fx_setup.tenant_id):
        lines = (
            await db_session.execute(
                select(JournalLine).where(JournalLine.journal_entry_id == bill.journal_entry_id)
            )
        ).scalars().all()
    ap_line = next(line for line in lines if line.account_id == fx_setup.accounts["2000"])
    # Transaction EUR 100, functional USD 110 (× 1.10 at the bill date).
    assert Decimal(str(ap_line.transaction_credit_amount)) == Decimal("100.00")
    assert Decimal(str(ap_line.functional_credit_amount)) == Decimal("110.00")
    assert Decimal(str(bill.open_amount)) == Decimal("100.00")  # open is transaction-currency


async def test_realized_fx_loss_on_later_higher_rate(
    db_session: AsyncSession, fx_setup: FxSetup
) -> None:
    """R1=1.10 at the bill, R2=1.20 at the payment: AP cleared at 110 USD, bank pays 120 USD, so a
    realized LOSS of (R1-R2)*100 = -10 USD posts inside the payment entry, which balances."""
    bill = await _post_eur_bill(db_session, fx_setup)
    holder: dict[str, uuid.UUID] = {}
    with tenant_context(fx_setup.tenant_id):
        async def work() -> None:
            payment = await service.create_and_post_payment(
                db_session,
                fx_setup.tenant_id,
                VendorPaymentCreate(
                    partner_id=bill.partner_id,
                    partner_name=bill.partner_name,
                    payment_date=_R2_DATE,
                    currency_code="EUR",
                    bank_account_id=fx_setup.accounts["1100"],
                    amount=Decimal("100.00"),
                    allocations=[
                        PaymentAllocationCreate(bill_id=bill.id, amount=Decimal("100.00"))
                    ],
                ),
            )
            holder["entry"] = payment.journal_entry_id

        await run_in_uow(db_session, work)
        await db_session.refresh(bill)
        lines = (
            await db_session.execute(
                select(JournalLine).where(JournalLine.journal_entry_id == holder["entry"])
            )
        ).scalars().all()

    assert bill.status == BillStatus.PAID.value
    # The entry balances in functional.
    debit = sum((Decimal(str(line.functional_debit_amount)) for line in lines), Decimal(0))
    credit = sum((Decimal(str(line.functional_credit_amount)) for line in lines), Decimal(0))
    assert debit == credit == Decimal("120.00")
    # AP cleared at the bill rate (110), bank paid at the payment rate (120).
    ap_line = next(line for line in lines if line.account_id == fx_setup.accounts["2000"])
    bank_line = next(line for line in lines if line.account_id == fx_setup.accounts["1100"])
    assert Decimal(str(ap_line.functional_debit_amount)) == Decimal("110.00")
    assert Decimal(str(bank_line.functional_credit_amount)) == Decimal("120.00")
    # The realized-FX LOSS line (account 7110) = (R1 - R2) * 100 = -10 -> a 10 USD debit.
    fx_line = next(line for line in lines if line.account_id == fx_setup.accounts["7110"])
    assert Decimal(str(fx_line.functional_debit_amount)) == Decimal("10.00")
    assert Decimal(str(fx_line.transaction_debit_amount)) == Decimal("10.00")


async def test_realized_fx_gain_on_later_lower_rate(
    db_session: AsyncSession, fx_setup: FxSetup
) -> None:
    """Pay the same EUR bill back AT the bill rate's date is no FX; pay at a LOWER rate to realize a
    gain. Add a 1.05 rate and pay then: AP cleared 110, bank pays 105, so a 5 USD gain (account
    7100) posts as a credit and the entry balances."""
    with tenant_context(fx_setup.tenant_id):
        from app.modules.finance.constants import RateKind

        await service.create_exchange_rate(
            db_session,
            fx_setup.tenant_id,
            rate_date=date(2026, 2, 1),
            from_currency_code="EUR",
            to_currency_code="USD",
            rate=Decimal("1.05"),
            rate_type=RateKind.SPOT,
        )
        await db_session.commit()
    bill = await _post_eur_bill(db_session, fx_setup)
    holder: dict[str, uuid.UUID] = {}
    with tenant_context(fx_setup.tenant_id):
        async def work() -> None:
            payment = await service.create_and_post_payment(
                db_session,
                fx_setup.tenant_id,
                VendorPaymentCreate(
                    partner_id=bill.partner_id,
                    partner_name=bill.partner_name,
                    payment_date=date(2026, 2, 1),
                    currency_code="EUR",
                    bank_account_id=fx_setup.accounts["1100"],
                    amount=Decimal("100.00"),
                    allocations=[
                        PaymentAllocationCreate(bill_id=bill.id, amount=Decimal("100.00"))
                    ],
                ),
            )
            holder["entry"] = payment.journal_entry_id

        await run_in_uow(db_session, work)
        lines = (
            await db_session.execute(
                select(JournalLine).where(JournalLine.journal_entry_id == holder["entry"])
            )
        ).scalars().all()
    debit = sum((Decimal(str(line.functional_debit_amount)) for line in lines), Decimal(0))
    credit = sum((Decimal(str(line.functional_credit_amount)) for line in lines), Decimal(0))
    assert debit == credit == Decimal("110.00")
    # AP cleared 110, bank paid 105, gain (7100) = 5 USD credit.
    fx_line = next(line for line in lines if line.account_id == fx_setup.accounts["7100"])
    assert Decimal(str(fx_line.functional_credit_amount)) == Decimal("5.00")


_PARTS = ("33.33", "33.33", "33.34")  # EUR 100 settled in three payments (#251, D-088)


async def _pay_part(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    bill: VendorBill,
    bank_account_id: uuid.UUID,
    amount: str,
) -> None:
    """Pay ``amount`` of ``bill`` in its own unit of work, as three separate payments would go out —
    so each clearing reads the open_amount the previous one left behind."""
    with tenant_context(tenant_id):

        async def work() -> None:
            await service.create_and_post_payment(
                session,
                tenant_id,
                VendorPaymentCreate(
                    partner_id=bill.partner_id,
                    partner_name=bill.partner_name,
                    payment_date=_R2_DATE,
                    currency_code="EUR",
                    bank_account_id=bank_account_id,
                    amount=Decimal(amount),
                    allocations=[PaymentAllocationCreate(bill_id=bill.id, amount=Decimal(amount))],
                ),
            )

        await run_in_uow(session, work)


async def _control_balance(
    session: AsyncSession, tenant_id: uuid.UUID, account_id: uuid.UUID
) -> tuple[Decimal, Decimal]:
    """The functional (debit, credit) totals every posted line put on one control account."""
    with tenant_context(tenant_id):
        lines = list(
            (
                await session.execute(
                    select(JournalLine).where(JournalLine.account_id == account_id)
                )
            )
            .scalars()
            .all()
        )
    debit = sum((Decimal(str(line.functional_debit_amount)) for line in lines), Decimal(0))
    credit = sum((Decimal(str(line.functional_credit_amount)) for line in lines), Decimal(0))
    return debit, credit


async def test_a_foreign_bill_settled_in_parts_leaves_nothing_on_the_ap_control(
    db_session: AsyncSession, fx_setup: FxSetup
) -> None:
    """#251 (D-088), the AP mirror of the AR case — identical because both legs run through the ONE
    ``clearing_fx`` builder, and the issue's claim that the mirror is identical is what this proves.

    EUR 100 at 1.10 CREDITS the control one quantized USD 110.00. Paying it as 33.33 / 33.33 /
    33.34 used to debit ``quantize(part x 1.10)`` per payment — 36.66 + 36.66 + 36.67 = USD 109.99
    — stranding USD 0.01 on the control forever, silently: the realized-FX line absorbed it, every
    entry balanced and the bill still read PAID. The telescoped draw-down makes the parts sum back
    by construction: 36.66 + 36.67 + 36.67.
    """
    bill = await _post_eur_bill(db_session, fx_setup)
    for part in _PARTS:
        await _pay_part(db_session, fx_setup.tenant_id, bill, fx_setup.accounts["1100"], part)

    await db_session.refresh(bill)
    assert bill.status == BillStatus.PAID.value
    assert Decimal(str(bill.open_amount)) == Decimal("0.00")

    debit, credit = await _control_balance(
        db_session, fx_setup.tenant_id, fx_setup.accounts["2000"]
    )
    # The bill credited USD 110.00 once; the three payments must debit exactly that back.
    assert credit == Decimal("110.00")
    assert debit == Decimal("110.00")
    assert debit - credit == Decimal(0)  # a settled payable owes the ledger nothing


# --- Postgres variant: the realized-FX payment satisfies the balance trigger -------------------


@pytest.fixture
async def pg_engine() -> AsyncEngine:
    """A real Postgres engine for the -m pg variant; skipped on the SQLite run."""
    if not _URL.startswith("postgresql"):
        pytest.skip("pg-marked test requires a PostgreSQL ATLAS_DATABASE_URL")
    engine = create_async_engine(_URL)
    yield engine
    await engine.dispose()


async def _setup_fx_ap(session: AsyncSession) -> dict[str, uuid.UUID]:
    """Functional USD + foreign EUR, SPOT rates (1.10 @ Jan 1, 1.20 @ Mar 1), realized-FX accounts
    wired, an EUR bank + AP control + expense account, and an open 2026 year. Returns the ids."""
    with system_context():
        tenant = Tenant(slug=f"apfx-{uuid.uuid4().hex[:8]}", name="AP FX")
        session.add(tenant)
        await session.commit()
    tenant_id = tenant.id
    ids: dict[str, uuid.UUID] = {"tenant_id": tenant_id}
    with tenant_context(tenant_id):
        await service.create_currency(
            session, tenant_id, code="USD", name="US Dollar", is_functional=True
        )
        await service.create_currency(session, tenant_id, code="EUR", name="Euro")
        for rate_date, rate in ((date(2026, 1, 1), "1.10"), (date(2026, 3, 1), "1.20")):
            await service.create_exchange_rate(
                session,
                tenant_id,
                rate_date=rate_date,
                from_currency_code="EUR",
                to_currency_code="USD",
                rate=Decimal(rate),
                rate_type=RateKind.SPOT,
            )
        for code, name, atype, monetary in (
            ("1100", "EUR Bank", "ASSET", True),
            ("2000", "Accounts Payable", "LIABILITY", False),
            ("5000", "Expense", "EXPENSE", False),
            ("7100", "FX Realized Gain", "REVENUE", False),
            ("7110", "FX Realized Loss", "EXPENSE", False),
        ):
            account = await service.create_account(
                session,
                tenant_id,
                AccountCreate(
                    code=code,
                    name=name,
                    account_type=atype,
                    is_monetary=monetary,
                    currency_code="EUR" if monetary else None,
                ),
            )
            ids[code] = account.id
        await service.set_posting_default(session, tenant_id, FX_REALIZED_GAIN, ids["7100"])
        await service.set_posting_default(session, tenant_id, FX_REALIZED_LOSS, ids["7110"])
        await service.create_fiscal_year(
            session,
            tenant_id,
            FiscalYearCreate(code="2026", name="FY2026", start_date=date(2026, 1, 1)),
        )
        await session.commit()
    return ids


async def _post_bill_and_pay(session: AsyncSession, ids: dict[str, uuid.UUID]) -> list[JournalLine]:
    """Post a 100 EUR bill at 1.10 and pay it at 1.20; return the payment entry's lines."""
    tenant_id = ids["tenant_id"]
    partner = uuid.uuid4()
    with tenant_context(tenant_id):
        bill = await service.create_vendor_bill(
            session,
            tenant_id,
            VendorBillCreate(
                partner_id=partner,
                partner_name="Euro Vendor",
                bill_date=_R1_DATE,
                due_date=date(2026, 3, 31),
                currency_code="EUR",
                ap_account_id=ids["2000"],
                lines=[VendorBillLineCreate(account_id=ids["5000"], net_amount=Decimal("100.00"))],
            ),
        )
        await session.commit()
        await run_in_uow(
            session,
            lambda: service.post_vendor_bill(session, tenant_id, bill.id, posting_date=_R1_DATE),
        )
        holder: dict[str, uuid.UUID] = {}

        async def work() -> None:
            payment = await service.create_and_post_payment(
                session,
                tenant_id,
                VendorPaymentCreate(
                    partner_id=partner,
                    partner_name="Euro Vendor",
                    payment_date=_R2_DATE,
                    currency_code="EUR",
                    bank_account_id=ids["1100"],
                    amount=Decimal("100.00"),
                    allocations=[
                        PaymentAllocationCreate(bill_id=bill.id, amount=Decimal("100.00"))
                    ],
                ),
            )
            holder["entry"] = payment.journal_entry_id

        await run_in_uow(session, work)
        return list(
            (
                await session.execute(
                    select(JournalLine).where(JournalLine.journal_entry_id == holder["entry"])
                )
            ).scalars().all()
        )


@pytest.mark.pg
async def test_realized_fx_payment_posts_on_postgres(pg_engine: AsyncEngine) -> None:
    """The realized-FX payment entry must satisfy the real Postgres balance trigger (D-019/D-017):
    it balances in functional (110 Dr AP + 10 Dr FX loss = 120 Cr bank) even though its transaction
    sides differ across currencies. Proves the foreign clearing entry posts on the real engine."""
    async with pg_engine.begin() as conn:
        await conn.exec_driver_sql(
            "TRUNCATE fin_vendor_payment_allocations, fin_vendor_payments, "
            "fin_vendor_bill_lines, fin_vendor_bills, fin_journal_lines, fin_journal_entries, "
            "fin_posting_defaults, fin_exchange_rates, fin_currencies, fin_fiscal_periods, "
            "fin_fiscal_years, fin_accounts, core_number_sequences, core_documents, "
            "core_doc_links, adm_tenants RESTART IDENTITY CASCADE"
        )
    async with build_session_factory(pg_engine)() as session:
        ids = await _setup_fx_ap(session)
        lines = await _post_bill_and_pay(session, ids)
    debit = sum((Decimal(str(line.functional_debit_amount)) for line in lines), Decimal(0))
    credit = sum((Decimal(str(line.functional_credit_amount)) for line in lines), Decimal(0))
    assert debit == credit == Decimal("120.00")
    fx_line = next(line for line in lines if line.account_id == ids["7110"])
    assert Decimal(str(fx_line.functional_debit_amount)) == Decimal("10.00")


async def _post_bill_and_pay_in_parts(
    session: AsyncSession, ids: dict[str, uuid.UUID]
) -> tuple[Decimal, Decimal]:
    """Post a 100 EUR bill at 1.10, pay it as 33.33 / 33.33 / 33.34, and return the AP control's
    functional (debit, credit) totals."""
    tenant_id = ids["tenant_id"]
    partner = uuid.uuid4()
    with tenant_context(tenant_id):
        bill = await service.create_vendor_bill(
            session,
            tenant_id,
            VendorBillCreate(
                partner_id=partner,
                partner_name="Euro Vendor",
                bill_date=_R1_DATE,
                due_date=date(2026, 3, 31),
                currency_code="EUR",
                ap_account_id=ids["2000"],
                lines=[VendorBillLineCreate(account_id=ids["5000"], net_amount=Decimal("100.00"))],
            ),
        )
        await session.commit()
        await run_in_uow(
            session,
            lambda: service.post_vendor_bill(session, tenant_id, bill.id, posting_date=_R1_DATE),
        )
    for part in _PARTS:
        await _pay_part(session, tenant_id, bill, ids["1100"], part)
    return await _control_balance(session, tenant_id, ids["2000"])


@pytest.mark.pg
async def test_a_partly_settled_ap_control_clears_on_postgres(pg_engine: AsyncEngine) -> None:
    """#251 (D-088) on the real engine. The residue is arithmetic, but the cumulative it telescopes
    against is READ BACK from the stored ``open_amount`` between payments, and MoneyType stores
    NUMERIC on Postgres and scaled integer micro-units on SQLite (D-015) — so the fix is proven on
    both, not just the one the suite runs on."""
    async with pg_engine.begin() as conn:
        await conn.exec_driver_sql(
            "TRUNCATE fin_vendor_payment_allocations, fin_vendor_payments, "
            "fin_vendor_bill_lines, fin_vendor_bills, fin_journal_lines, fin_journal_entries, "
            "fin_posting_defaults, fin_exchange_rates, fin_currencies, fin_fiscal_periods, "
            "fin_fiscal_years, fin_accounts, core_number_sequences, core_documents, "
            "core_doc_links, adm_tenants RESTART IDENTITY CASCADE"
        )
    async with build_session_factory(pg_engine)() as session:
        ids = await _setup_fx_ap(session)
        debit, credit = await _post_bill_and_pay_in_parts(session, ids)
    assert debit == credit == Decimal("110.00")
