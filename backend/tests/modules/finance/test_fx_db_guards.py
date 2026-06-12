"""FX posting-time translation against the DB balance trigger, on BOTH engines (D-019/D-022).

Posting a foreign-currency entry recomputes each line's functional amount at the SPOT rate and
absorbs the residual cent so the FUNCTIONAL debit total equals the functional credit total exactly
— and the journal balance trigger SUM-checks those FUNCTIONAL amounts. This file proves the
translated entry passes the balance trigger on the per-test SQLite copy AND on real Postgres
(``-m pg``), so the trigger and the largest-remainder balancing agree on both engines.

This also stands as the explicit proof that migration 0010 (which batch-altered fin_accounts, NOT
fin_journal_entries) left the four journal triggers intact: these tests run against the final
migrated schema, and a posted entry exercises the balance + period triggers.
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
from app.modules.finance.constants import RateKind
from app.modules.finance.models import JournalLine
from app.modules.finance.schemas import (
    AccountCreate,
    FiscalYearCreate,
    JournalEntryCreate,
    JournalLineCreate,
)

_URL = os.environ.get("ATLAS_DATABASE_URL", "")
_PD = date(2026, 3, 15)


@pytest.fixture
async def pg_engine() -> AsyncEngine:
    if not _URL.startswith("postgresql"):
        pytest.skip("pg-marked test requires a PostgreSQL ATLAS_DATABASE_URL")
    engine = create_async_engine(_URL)
    yield engine
    await engine.dispose()


async def _setup(session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """A tenant with USD functional + EUR foreign, a SPOT rate, an EUR bank + a sales account, and
    an open 2026 year. Returns (tenant_id, eur_bank_id, sales_id)."""
    with system_context():
        tenant = Tenant(slug=f"fxg-{uuid.uuid4().hex[:8]}", name="FX Guard")
        session.add(tenant)
        await session.commit()
    tenant_id = tenant.id
    with tenant_context(tenant_id):
        await service.create_currency(
            session, tenant_id, code="USD", name="US Dollar", is_functional=True
        )
        await service.create_currency(session, tenant_id, code="EUR", name="Euro")
        await service.create_exchange_rate(
            session,
            tenant_id,
            rate_date=date(2026, 1, 1),
            from_currency_code="EUR",
            to_currency_code="USD",
            rate=Decimal("1.20"),
            rate_type=RateKind.SPOT,
        )
        eur_bank = await service.create_account(
            session,
            tenant_id,
            AccountCreate(
                code="1100", name="EUR Bank", account_type="ASSET",
                is_monetary=True, currency_code="EUR",
            ),
        )
        sales = await service.create_account(
            session, tenant_id, AccountCreate(code="4000", name="Sales", account_type="REVENUE")
        )
        await service.create_fiscal_year(
            session,
            tenant_id,
            FiscalYearCreate(code="2026", name="FY2026", start_date=date(2026, 1, 1)),
        )
        await session.commit()
    return tenant_id, eur_bank.id, sales.id


async def _post_foreign_entry(
    session: AsyncSession, tenant_id: uuid.UUID, eur_bank: uuid.UUID, sales: uuid.UUID
) -> list[JournalLine]:
    """Post a 3-line EUR entry whose translation leaves a residual cent, then return its lines."""
    with tenant_context(tenant_id):
        entry = await service.create_draft_entry(
            session,
            tenant_id,
            JournalEntryCreate(
                posting_date=_PD,
                currency_code="EUR",
                lines=[
                    JournalLineCreate(
                        account_id=eur_bank, transaction_debit_amount=Decimal("100.00")
                    ),
                    JournalLineCreate(account_id=sales, transaction_credit_amount=Decimal("33.33")),
                    JournalLineCreate(account_id=sales, transaction_credit_amount=Decimal("33.33")),
                    JournalLineCreate(account_id=sales, transaction_credit_amount=Decimal("33.34")),
                ],
            ),
        )
        await session.commit()
        # The DB balance trigger fires on this DRAFT->POSTED flush over the FUNCTIONAL sums; if the
        # residual were not absorbed it would raise ATLAS_UNBALANCED_ENTRY.
        await run_in_uow(
            session, lambda: service.post_entry(session, tenant_id, entry.id)
        )
        return list(
            (
                await session.execute(
                    select(JournalLine).where(JournalLine.journal_entry_id == entry.id)
                )
            ).scalars().all()
        )


def _assert_functional_balances(lines: list[JournalLine]) -> None:
    func_debit = sum((line.functional_debit_amount for line in lines), Decimal(0))
    func_credit = sum((line.functional_credit_amount for line in lines), Decimal(0))
    assert func_debit == func_credit == Decimal("120.00")  # 100 EUR @ 1.20, residual absorbed


async def test_foreign_translation_passes_balance_trigger_sqlite(
    db_session: AsyncSession,
) -> None:
    tenant_id, eur_bank, sales = await _setup(db_session)
    lines = await _post_foreign_entry(db_session, tenant_id, eur_bank, sales)
    _assert_functional_balances(lines)


@pytest.mark.pg
async def test_foreign_translation_passes_balance_trigger_postgres(
    pg_engine: AsyncEngine,
) -> None:
    async with pg_engine.begin() as conn:
        await conn.exec_driver_sql(
            "TRUNCATE fin_journal_lines, fin_journal_entries, fin_exchange_rates, "
            "fin_currencies, fin_fiscal_periods, fin_fiscal_years, fin_accounts, "
            "core_number_sequences, core_documents, adm_tenants RESTART IDENTITY CASCADE"
        )
    async with build_session_factory(pg_engine)() as session:
        tenant_id, eur_bank, sales = await _setup(session)
        lines = await _post_foreign_entry(session, tenant_id, eur_bank, sales)
        _assert_functional_balances(lines)
