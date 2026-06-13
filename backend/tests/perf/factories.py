"""Perf dataset builders (PLAN 4P.7, PERFORMANCE §5): one mid-volume tenant, bulk-seeded.

The volume rows are written with Core executemany bulk inserts (PERFORMANCE §2) — posting
~2,500 entries through ``post_entry`` would take minutes. Writing already-POSTED rows
directly is trigger-safe against migration 0009's guards:

* the period trigger fires on INSERT when ``NEW.status = 'POSTED'`` and only requires an
  OPEN period covering ``posting_date`` — all 12 generated periods stay OPEN and every
  posting date falls inside the year, so each insert passes;
* the balance trigger fires only on the DRAFT->POSTED UPDATE, never on a raw INSERT of a
  POSTED header — debits == credits per entry is kept by construction instead (asserted by
  the trial-balance sanity test in test_budgets.py);
* the line-immutability triggers fire on UPDATE/DELETE only, so inserting ``is_posted``
  lines (with the D-021 posting_date/fiscal_period_id denormalization set) is permitted.

Small master data (the 30-account COA, the fiscal year, the principal) goes through the
real services (D-025); only the volume tables are bulk. The thin pytest fixtures wrapping
:func:`seed_dataset` live in tests/perf/conftest.py (the tests/modules/finance split,
STRUCTURE §8.4).
"""

import random
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import build_engine, build_session_factory
from app.core.docflow import Document
from app.core.tenancy import tenant_context
from app.modules.finance import service
from app.modules.finance.constants import (
    AR_INVOICE_DOC_TYPE,
    JOURNAL_ENTRY_DOC_TYPE,
    AccountType,
    DocumentType,
    EntryStatus,
    InvoiceStatus,
)
from app.modules.finance.models import CustomerInvoice, FiscalPeriod, JournalEntry, JournalLine
from app.modules.finance.schemas import AccountCreate, FiscalYearCreate
from tests.modules.finance.factories import create_finance_principal

# Volume targets. PERFORMANCE §5 sizes the FULL volume seed (Phase 16 seed.py --volume) at
# >=100k lines; this per-session smoke tenant stays mid-sized so the suite itself runs in
# seconds while still being ~40x the unit-test fixtures.
ENTRY_COUNT = 2_500
LINES_PER_ENTRY = 8  # 4 balanced debit/credit pairs per entry -> 20,000 lines
INVOICE_COUNT = 1_500
CUSTOMER_COUNT = 50
COST_CENTER_COUNT = 12
YEAR_START = date(2026, 1, 1)

# ~30-account chart: (code, name, type, is_cash_equivalent). Includes the AR control
# (1200), revenue (40xx), output tax payable (2200) and a cash-equivalent bank (1010).
_PERF_COA: tuple[tuple[str, str, AccountType, bool], ...] = (
    ("1000", "Cash", AccountType.ASSET, False),
    ("1010", "Main Bank", AccountType.ASSET, True),
    ("1200", "Accounts Receivable", AccountType.ASSET, False),
    ("1300", "Inventory", AccountType.ASSET, False),
    ("1400", "Prepaid Expenses", AccountType.ASSET, False),
    ("1500", "Fixed Assets", AccountType.ASSET, False),
    ("1600", "Accumulated Depreciation", AccountType.ASSET, False),
    ("1700", "Deposits", AccountType.ASSET, False),
    ("6000", "Input VAT Receivable", AccountType.ASSET, False),
    ("2000", "Accounts Payable", AccountType.LIABILITY, False),
    ("2200", "Output VAT Payable", AccountType.LIABILITY, False),
    ("2300", "Accrued Liabilities", AccountType.LIABILITY, False),
    ("2400", "Loans Payable", AccountType.LIABILITY, False),
    ("2500", "Taxes Payable", AccountType.LIABILITY, False),
    ("3000", "Share Capital", AccountType.EQUITY, False),
    ("3100", "Capital Reserve", AccountType.EQUITY, False),
    ("4000", "Product Revenue", AccountType.REVENUE, False),
    ("4100", "Service Revenue", AccountType.REVENUE, False),
    ("4200", "Other Revenue", AccountType.REVENUE, False),
    ("4300", "Interest Income", AccountType.REVENUE, False),
    ("5000", "Cost of Goods Sold", AccountType.EXPENSE, False),
    ("5100", "Salaries", AccountType.EXPENSE, False),
    ("5200", "Rent", AccountType.EXPENSE, False),
    ("5300", "Utilities", AccountType.EXPENSE, False),
    ("5400", "Marketing", AccountType.EXPENSE, False),
    ("5500", "Travel", AccountType.EXPENSE, False),
    ("5600", "Office Supplies", AccountType.EXPENSE, False),
    ("5700", "Insurance", AccountType.EXPENSE, False),
    ("5800", "Depreciation Expense", AccountType.EXPENSE, False),
    ("5900", "Miscellaneous Expense", AccountType.EXPENSE, False),
)

# Account pools the journal generator cycles through — debit-heavy (expenses + working-
# capital assets) vs credit-heavy (revenue + liabilities + equity) — so every statement
# section carries balances and the aggregates group over many accounts.
_DEBIT_CODES = (
    "5000", "5100", "5200", "5300", "5400", "5500", "5600", "5700", "5800", "5900",
    "1000", "1010", "1200", "1300", "1500",
)
_CREDIT_CODES = ("4000", "4100", "4200", "4300", "2000", "2200", "2300", "2400", "3000")


@dataclass(frozen=True)
class PerfDataset:
    """Everything a budget test needs to hit the seeded tenant: where it lives, who may
    log in (a full-finance-permission principal for the API timing), the account map, the
    seeded year bounds, the achieved row counts, and how long the seed took."""

    database_url: str
    is_postgres: bool
    tenant_id: uuid.UUID
    tenant_slug: str
    email: str
    password: str
    accounts: dict[str, uuid.UUID]
    fiscal_year_id: uuid.UUID
    year_start: date
    year_end: date
    entry_count: int
    line_count: int
    invoice_count: int
    seed_seconds: float

    @property
    def budget_multiplier(self) -> int:
        """PERFORMANCE §5: budgets are defined against Postgres (1x); the SQLite CI smoke
        asserts at 2x so CI stays stable while still catching regressions."""
        return 1 if self.is_postgres else 2


async def _seed_coa(session: AsyncSession, tenant_id: uuid.UUID) -> dict[str, uuid.UUID]:
    """30 accounts through the real service (small master data; D-025) — the VOLUME rows
    below are the ones that must be bulk."""
    accounts: dict[str, uuid.UUID] = {}
    with tenant_context(tenant_id):
        for code, name, account_type, is_cash in _PERF_COA:
            account = await service.create_account(
                session,
                tenant_id,
                AccountCreate(
                    code=code, name=name, account_type=account_type, is_cash_equivalent=is_cash
                ),
            )
            accounts[code] = account.id
        await session.commit()
    return accounts


async def _seed_fiscal_year(
    session: AsyncSession, tenant_id: uuid.UUID
) -> tuple[uuid.UUID, date, date, list[tuple[uuid.UUID, date, date]]]:
    """One 2026 fiscal year with 12 OPEN monthly periods through the real service — the
    period INSERT trigger requires an OPEN period covering every posting date."""
    with tenant_context(tenant_id):
        year = await service.create_fiscal_year(
            session,
            tenant_id,
            FiscalYearCreate(code="2026", name="FY2026", start_date=YEAR_START),
        )
        await session.commit()
        periods = (
            await session.execute(
                select(FiscalPeriod)
                .where(FiscalPeriod.fiscal_year_id == year.id)
                .order_by(FiscalPeriod.period_number)
            )
        ).scalars().all()
    return (
        year.id,
        year.start_date,
        year.end_date,
        [(p.id, p.start_date, p.end_date) for p in periods],
    )


async def _seed_journal(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    accounts: dict[str, uuid.UUID],
    periods: list[tuple[uuid.UUID, date, date]],
) -> tuple[int, int]:
    """~2,500 POSTED entries / ~20,000 posted lines in THREE executemany inserts
    (documents -> entries -> lines). Dates spread across the year, accounts cycle through
    the debit/credit pools, every other debit line carries a cost centre, and each entry's
    debits == credits by construction (4 equal-amount pairs)."""
    rng = random.Random(42)
    debit_pool = [accounts[code] for code in _DEBIT_CODES]
    credit_pool = [accounts[code] for code in _CREDIT_CODES]
    cost_centers = [uuid.uuid4() for _ in range(COST_CENTER_COUNT)]
    year_start = periods[0][1]

    document_rows: list[dict[str, object]] = []
    entry_rows: list[dict[str, object]] = []
    line_rows: list[dict[str, object]] = []
    for i in range(ENTRY_COUNT):
        posting_date = year_start + timedelta(days=(i * 364) // ENTRY_COUNT)
        period_id = next(pid for pid, start, end in periods if start <= posting_date <= end)
        entry_id = uuid.uuid4()
        document_id = uuid.uuid4()
        number = f"JE-2026-{i + 1:05d}"
        document_rows.append(
            {
                "id": document_id,
                "tenant_id": tenant_id,
                "doc_type": JOURNAL_ENTRY_DOC_TYPE,
                "doc_id": entry_id,
                "doc_number": number,
                "status": EntryStatus.POSTED.value,
            }
        )
        entry_rows.append(
            {
                "id": entry_id,
                "tenant_id": tenant_id,
                "document_id": document_id,
                "entry_number": number,
                "posting_date": posting_date,
                "fiscal_period_id": period_id,
                "document_type": DocumentType.JOURNAL.value,
                "currency_code": "USD",
                "description": f"Perf entry {i + 1}",
                "status": EntryStatus.POSTED.value,
                "reverses_entry_id": None,
                "reversed_by_entry_id": None,
                "posted_at": datetime(
                    posting_date.year, posting_date.month, posting_date.day, tzinfo=UTC
                ),
            }
        )
        for pair in range(LINES_PER_ENTRY // 2):
            amount = Decimal(rng.randint(100, 1_000_000)) / 100
            cost_center = cost_centers[(i + pair) % COST_CENTER_COUNT] if pair % 2 == 0 else None
            for line_offset, account_id, debit, credit in (
                (0, debit_pool[(i + pair) % len(debit_pool)], amount, Decimal(0)),
                (1, credit_pool[(i * 3 + pair) % len(credit_pool)], Decimal(0), amount),
            ):
                line_rows.append(
                    {
                        "id": uuid.uuid4(),
                        "tenant_id": tenant_id,
                        "journal_entry_id": entry_id,
                        "line_number": pair * 2 + line_offset + 1,
                        "account_id": account_id,
                        "description": None,
                        "transaction_debit_amount": debit,
                        "transaction_credit_amount": credit,
                        "functional_debit_amount": debit,
                        "functional_credit_amount": credit,
                        "currency_code": "USD",
                        "cost_center_id": cost_center,
                        "profit_center_id": None,
                        "project_id": None,
                        "item_id": None,
                        "partner_type": None,
                        "partner_id": None,
                        "is_posted": True,
                        "posting_date": posting_date,
                        "fiscal_period_id": period_id,
                    }
                )

    await session.execute(insert(Document), document_rows)
    await session.execute(insert(JournalEntry), entry_rows)
    await session.execute(insert(JournalLine), line_rows)
    await session.commit()
    return len(entry_rows), len(line_rows)


async def _seed_invoices(
    session: AsyncSession, tenant_id: uuid.UUID, ar_account_id: uuid.UUID
) -> int:
    """~1,500 customer invoices in TWO executemany inserts (documents -> invoices), mixed
    statuses (40% POSTED open / 30% PARTIALLY_PAID / 20% PAID / 10% DRAFT) with due dates
    spanning every aging bucket relative to the year-end as-of."""
    rng = random.Random(43)
    customers = [(uuid.uuid4(), f"Customer {n + 1:02d}") for n in range(CUSTOMER_COUNT)]
    document_rows: list[dict[str, object]] = []
    invoice_rows: list[dict[str, object]] = []
    for i in range(INVOICE_COUNT):
        cycle = i % 10
        if cycle < 4:
            status = InvoiceStatus.POSTED
        elif cycle < 7:
            status = InvoiceStatus.PARTIALLY_PAID
        elif cycle < 9:
            status = InvoiceStatus.PAID
        else:
            status = InvoiceStatus.DRAFT
        invoice_date = YEAR_START + timedelta(days=(i * 360) // INVOICE_COUNT)
        net = Decimal(rng.randint(5_000, 2_000_000)) / 100
        tax = (net * Decimal("0.20")).quantize(Decimal("0.01"))
        gross = net + tax
        if status is InvoiceStatus.POSTED:
            open_amount = gross
        elif status is InvoiceStatus.PARTIALLY_PAID:
            open_amount = (gross / 2).quantize(Decimal("0.01"))
        else:
            open_amount = Decimal(0)
        number = None if status is InvoiceStatus.DRAFT else f"INV-2026-{i + 1:05d}"
        partner_id, partner_name = customers[i % CUSTOMER_COUNT]
        invoice_id = uuid.uuid4()
        document_id = uuid.uuid4()
        document_rows.append(
            {
                "id": document_id,
                "tenant_id": tenant_id,
                "doc_type": AR_INVOICE_DOC_TYPE,
                "doc_id": invoice_id,
                "doc_number": number,
                "status": status.value,
            }
        )
        invoice_rows.append(
            {
                "id": invoice_id,
                "tenant_id": tenant_id,
                "document_id": document_id,
                "partner_id": partner_id,
                "partner_name": partner_name,
                "external_ref": None,
                "invoice_number": number,
                "invoice_date": invoice_date,
                "due_date": invoice_date + timedelta(days=30),
                "currency_code": "USD",
                "status": status.value,
                "ar_account_id": ar_account_id,
                "journal_entry_id": None,
                "gross_amount": gross,
                "tax_amount": tax,
                "net_amount": net,
                "open_amount": open_amount,
                "dunning_level": 0,
                "last_dunned_date": None,
                "description": None,
            }
        )

    await session.execute(insert(Document), document_rows)
    await session.execute(insert(CustomerInvoice), invoice_rows)
    await session.commit()
    return len(invoice_rows)


async def seed_dataset(database_url: str, is_postgres: bool) -> PerfDataset:
    """Provision one finance principal (real services, D-025) then bulk-seed the volume
    rows. The engine lives only inside this coroutine (the conftest fixture's asyncio.run
    owns the loop), so the per-test fixtures open their own loop-local engines against the
    same database."""
    started = time.perf_counter()
    engine = build_engine(database_url)
    try:
        async with build_session_factory(engine)() as session:
            slug = f"perf-{uuid.uuid4().hex[:8]}"
            principal = await create_finance_principal(session, slug=slug, email=f"cfo@{slug}.test")
            accounts = await _seed_coa(session, principal.tenant_id)
            year_id, year_start, year_end, periods = await _seed_fiscal_year(
                session, principal.tenant_id
            )
            entry_count, line_count = await _seed_journal(
                session, principal.tenant_id, accounts, periods
            )
            invoice_count = await _seed_invoices(session, principal.tenant_id, accounts["1200"])
    finally:
        await engine.dispose()
    return PerfDataset(
        database_url=database_url,
        is_postgres=is_postgres,
        tenant_id=principal.tenant_id,
        tenant_slug=principal.tenant_slug,
        email=principal.email,
        password=principal.password,
        accounts=accounts,
        fiscal_year_id=year_id,
        year_start=year_start,
        year_end=year_end,
        entry_count=entry_count,
        line_count=line_count,
        invoice_count=invoice_count,
        seed_seconds=time.perf_counter() - started,
    )
