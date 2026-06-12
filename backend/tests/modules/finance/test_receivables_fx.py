"""Realized FX at AR clearing (PLAN 4.6, D-019), SQLite + a Postgres variant.

A foreign-currency invoice posted at rate R1 and received at rate R2 books the functional difference
over the cleared amount to the realized FX gain/loss account INSIDE the receipt entry, which must
still balance in functional. The pg variant proves the balance trigger accepts that foreign receipt
entry on the real engine (the trigger IS involved). The AP FX suite (test_payables_fx.py) mirror,
sign flipped (AR control is DEBITED at the invoice, so the realized-FX direction inverts).

Uses the fx_setup fixture (functional USD, foreign EUR; SPOT 2026-01-01=1.10, 2026-03-01=1.20;
realized-FX accounts wired; EUR bank=1100; AR control=1900 (an ASSET); revenue=4000).
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
    InvoiceStatus,
    RateKind,
)
from app.modules.finance.models import CustomerInvoice, JournalLine
from app.modules.finance.receivables_schemas import (
    CustomerInvoiceCreate,
    CustomerInvoiceLineCreate,
    CustomerReceiptCreate,
    ReceiptAllocationCreate,
)
from app.modules.finance.schemas import AccountCreate, FiscalYearCreate
from tests.modules.finance.conftest import FxSetup

_R1_DATE = date(2026, 1, 1)  # SPOT 1.10
_R2_DATE = date(2026, 3, 1)  # SPOT 1.20
_URL = os.environ.get("ATLAS_DATABASE_URL", "")


async def _post_eur_invoice(
    session: AsyncSession, fx_setup: FxSetup, net: str = "100.00"
) -> CustomerInvoice:
    partner = uuid.uuid4()
    with tenant_context(fx_setup.tenant_id):
        invoice = await service.create_customer_invoice(
            session,
            fx_setup.tenant_id,
            CustomerInvoiceCreate(
                partner_id=partner,
                partner_name="Euro Customer",
                invoice_date=_R1_DATE,
                due_date=date(2026, 3, 31),
                currency_code="EUR",
                ar_account_id=fx_setup.accounts["1900"],
                lines=[
                    CustomerInvoiceLineCreate(
                        account_id=fx_setup.accounts["4000"], net_amount=Decimal(net)
                    )
                ],
            ),
        )
        await session.commit()

        async def work() -> None:
            await service.post_customer_invoice(
                session, fx_setup.tenant_id, invoice.id, posting_date=_R1_DATE
            )

        await run_in_uow(session, work)
        await session.refresh(invoice)
    return invoice


async def test_foreign_invoice_books_functional_at_invoice_rate(
    db_session: AsyncSession, fx_setup: FxSetup
) -> None:
    invoice = await _post_eur_invoice(db_session, fx_setup)
    with tenant_context(fx_setup.tenant_id):
        lines = (
            await db_session.execute(
                select(JournalLine).where(JournalLine.journal_entry_id == invoice.journal_entry_id)
            )
        ).scalars().all()
    ar_line = next(line for line in lines if line.account_id == fx_setup.accounts["1900"])
    # Transaction EUR 100, functional USD 110 (× 1.10 at the invoice date) on the DEBIT side.
    assert Decimal(str(ar_line.transaction_debit_amount)) == Decimal("100.00")
    assert Decimal(str(ar_line.functional_debit_amount)) == Decimal("110.00")
    assert Decimal(str(invoice.open_amount)) == Decimal("100.00")  # open is transaction-currency


async def test_realized_fx_gain_on_later_higher_rate(
    db_session: AsyncSession, fx_setup: FxSetup
) -> None:
    """R1=1.10 at the invoice, R2=1.20 at the receipt: AR cleared at 110 USD, bank receives 120 USD,
    so a realized GAIN of (R2-R1)*100 = +10 USD posts inside the receipt entry, which balances."""
    invoice = await _post_eur_invoice(db_session, fx_setup)
    holder: dict[str, uuid.UUID] = {}
    with tenant_context(fx_setup.tenant_id):
        async def work() -> None:
            receipt = await service.create_and_post_receipt(
                db_session,
                fx_setup.tenant_id,
                CustomerReceiptCreate(
                    partner_id=invoice.partner_id,
                    partner_name=invoice.partner_name,
                    receipt_date=_R2_DATE,
                    currency_code="EUR",
                    bank_account_id=fx_setup.accounts["1100"],
                    amount=Decimal("100.00"),
                    allocations=[
                        ReceiptAllocationCreate(invoice_id=invoice.id, amount=Decimal("100.00"))
                    ],
                ),
            )
            holder["entry"] = receipt.journal_entry_id

        await run_in_uow(db_session, work)
        await db_session.refresh(invoice)
        lines = (
            await db_session.execute(
                select(JournalLine).where(JournalLine.journal_entry_id == holder["entry"])
            )
        ).scalars().all()

    assert invoice.status == InvoiceStatus.PAID.value
    # The entry balances in functional.
    debit = sum((Decimal(str(line.functional_debit_amount)) for line in lines), Decimal(0))
    credit = sum((Decimal(str(line.functional_credit_amount)) for line in lines), Decimal(0))
    assert debit == credit == Decimal("120.00")
    # AR cleared at the invoice rate (110), bank received at the receipt rate (120).
    ar_line = next(line for line in lines if line.account_id == fx_setup.accounts["1900"])
    bank_line = next(line for line in lines if line.account_id == fx_setup.accounts["1100"])
    assert Decimal(str(ar_line.functional_credit_amount)) == Decimal("110.00")
    assert Decimal(str(bank_line.functional_debit_amount)) == Decimal("120.00")
    # The realized-FX GAIN line (account 7100) = (R2 - R1) * 100 = +10 -> a 10 USD credit.
    fx_line = next(line for line in lines if line.account_id == fx_setup.accounts["7100"])
    assert Decimal(str(fx_line.functional_credit_amount)) == Decimal("10.00")
    assert Decimal(str(fx_line.transaction_credit_amount)) == Decimal("10.00")


async def test_realized_fx_loss_on_later_lower_rate(
    db_session: AsyncSession, fx_setup: FxSetup
) -> None:
    """Receive at a LOWER rate to realize a LOSS. Add a 1.05 rate and receive then: AR cleared 110,
    bank receives 105, so a 5 USD loss (account 7110) posts as a debit and the entry balances."""
    with tenant_context(fx_setup.tenant_id):
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
    invoice = await _post_eur_invoice(db_session, fx_setup)
    holder: dict[str, uuid.UUID] = {}
    with tenant_context(fx_setup.tenant_id):
        async def work() -> None:
            receipt = await service.create_and_post_receipt(
                db_session,
                fx_setup.tenant_id,
                CustomerReceiptCreate(
                    partner_id=invoice.partner_id,
                    partner_name=invoice.partner_name,
                    receipt_date=date(2026, 2, 1),
                    currency_code="EUR",
                    bank_account_id=fx_setup.accounts["1100"],
                    amount=Decimal("100.00"),
                    allocations=[
                        ReceiptAllocationCreate(invoice_id=invoice.id, amount=Decimal("100.00"))
                    ],
                ),
            )
            holder["entry"] = receipt.journal_entry_id

        await run_in_uow(db_session, work)
        lines = (
            await db_session.execute(
                select(JournalLine).where(JournalLine.journal_entry_id == holder["entry"])
            )
        ).scalars().all()
    debit = sum((Decimal(str(line.functional_debit_amount)) for line in lines), Decimal(0))
    credit = sum((Decimal(str(line.functional_credit_amount)) for line in lines), Decimal(0))
    assert debit == credit == Decimal("110.00")
    # AR cleared 110, bank received 105, loss (7110) = 5 USD debit.
    fx_line = next(line for line in lines if line.account_id == fx_setup.accounts["7110"])
    assert Decimal(str(fx_line.functional_debit_amount)) == Decimal("5.00")


# --- Postgres variant: the realized-FX receipt satisfies the balance trigger -------------------


@pytest.fixture
async def pg_engine() -> AsyncEngine:
    """A real Postgres engine for the -m pg variant; skipped on the SQLite run."""
    if not _URL.startswith("postgresql"):
        pytest.skip("pg-marked test requires a PostgreSQL ATLAS_DATABASE_URL")
    engine = create_async_engine(_URL)
    yield engine
    await engine.dispose()


async def _setup_fx_ar(session: AsyncSession) -> dict[str, uuid.UUID]:
    """Functional USD + foreign EUR, SPOT rates (1.10 @ Jan 1, 1.20 @ Mar 1), realized-FX accounts
    wired, an EUR bank + AR control + revenue account, and an open 2026 year. Returns the ids."""
    with system_context():
        tenant = Tenant(slug=f"arfx-{uuid.uuid4().hex[:8]}", name="AR FX")
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
            ("1200", "Accounts Receivable", "ASSET", False),
            ("4000", "Revenue", "REVENUE", False),
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


async def _post_invoice_and_receive(
    session: AsyncSession, ids: dict[str, uuid.UUID]
) -> list[JournalLine]:
    """Post a 100 EUR invoice at 1.10 and receive it at 1.20; return the receipt entry's lines."""
    tenant_id = ids["tenant_id"]
    partner = uuid.uuid4()
    with tenant_context(tenant_id):
        invoice = await service.create_customer_invoice(
            session,
            tenant_id,
            CustomerInvoiceCreate(
                partner_id=partner,
                partner_name="Euro Customer",
                invoice_date=_R1_DATE,
                due_date=date(2026, 3, 31),
                currency_code="EUR",
                ar_account_id=ids["1200"],
                lines=[
                    CustomerInvoiceLineCreate(account_id=ids["4000"], net_amount=Decimal("100.00"))
                ],
            ),
        )
        await session.commit()
        await run_in_uow(
            session,
            lambda: service.post_customer_invoice(
                session, tenant_id, invoice.id, posting_date=_R1_DATE
            ),
        )
        holder: dict[str, uuid.UUID] = {}

        async def work() -> None:
            receipt = await service.create_and_post_receipt(
                session,
                tenant_id,
                CustomerReceiptCreate(
                    partner_id=partner,
                    partner_name="Euro Customer",
                    receipt_date=_R2_DATE,
                    currency_code="EUR",
                    bank_account_id=ids["1100"],
                    amount=Decimal("100.00"),
                    allocations=[
                        ReceiptAllocationCreate(invoice_id=invoice.id, amount=Decimal("100.00"))
                    ],
                ),
            )
            holder["entry"] = receipt.journal_entry_id

        await run_in_uow(session, work)
        return list(
            (
                await session.execute(
                    select(JournalLine).where(JournalLine.journal_entry_id == holder["entry"])
                )
            ).scalars().all()
        )


@pytest.mark.pg
async def test_realized_fx_receipt_posts_on_postgres(pg_engine: AsyncEngine) -> None:
    """The realized-FX receipt entry must satisfy the real Postgres balance trigger (D-019/D-017):
    it balances in functional (110 Cr AR + 120 Dr bank, 10 Cr FX gain) even though its transaction
    sides differ across currencies. Proves the foreign clearing entry posts on the real engine."""
    async with pg_engine.begin() as conn:
        await conn.exec_driver_sql(
            "TRUNCATE fin_customer_receipt_allocations, fin_customer_receipts, "
            "fin_customer_invoice_lines, fin_customer_invoices, fin_journal_lines, "
            "fin_journal_entries, fin_posting_defaults, fin_exchange_rates, fin_currencies, "
            "fin_fiscal_periods, fin_fiscal_years, fin_accounts, core_number_sequences, "
            "core_documents, core_doc_links, adm_tenants RESTART IDENTITY CASCADE"
        )
    async with build_session_factory(pg_engine)() as session:
        ids = await _setup_fx_ar(session)
        lines = await _post_invoice_and_receive(session, ids)
    debit = sum((Decimal(str(line.functional_debit_amount)) for line in lines), Decimal(0))
    credit = sum((Decimal(str(line.functional_credit_amount)) for line in lines), Decimal(0))
    assert debit == credit == Decimal("120.00")
    fx_line = next(line for line in lines if line.account_id == ids["7100"])
    assert Decimal(str(fx_line.functional_credit_amount)) == Decimal("10.00")
