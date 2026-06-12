"""Raw-SQL DB-level guard tests for the universal journal (D-017/D-018/D-022).

These DELIBERATELY bypass the service layer (sanctioned in tests/ — the grep gate is app/-only)
to prove the four triggers + the one-side CHECK fire at the DATABASE, the bypass-proof backstop
behind every service check. Each test attempts a raw UPDATE/DELETE/INSERT and asserts the
ATLAS_* token is raised.

Run on BOTH engines: the default (`not pg`) variant uses the per-test migrated SQLite copy; the
`-m pg` variant runs the SAME assertions against a real Postgres, so the per-dialect trigger DDL
is proven on the production database too (D-022). Setup data (tenant, period, accounts, a draft
entry + balanced lines) is inserted via Core ``insert()`` so MoneyType applies the correct stored
representation (micro-unit ints on SQLite, NUMERIC on PG) — only the trigger-tripping statements
use raw ``text()``.
"""

import os
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.core.docflow import Document
from app.modules.admin.models import Tenant
from app.modules.finance.models import Account, FiscalPeriod, FiscalYear, JournalEntry, JournalLine

_URL = os.environ.get("ATLAS_DATABASE_URL", "")
_PD = date(2026, 3, 15)
_CLOSED_PD = date(2026, 2, 15)


@pytest.fixture
async def pg_engine() -> AsyncEngine:
    """A freshly-migrated Postgres engine for the -m pg variant. Skipped when the URL is not
    Postgres so the default SQLite run never touches it."""
    if not _URL.startswith("postgresql"):
        pytest.skip("pg-marked test requires a PostgreSQL ATLAS_DATABASE_URL")
    engine = create_async_engine(_URL)
    yield engine
    await engine.dispose()


async def _now() -> datetime:
    return datetime.now(UTC)


def _uuid_text(sql: str, **params: object):
    """A raw ``text()`` statement whose listed UUID params bind through ``sa.Uuid`` so a uuid.UUID
    value adapts to each engine's storage (32-char hex on SQLite, native uuid on PG) — a bare
    aiosqlite bind of a UUID object is unsupported."""
    typed = [
        sa.bindparam(key, value=value, type_=sa.Uuid)
        if isinstance(value, uuid.UUID)
        else sa.bindparam(key, value=value)
        for key, value in params.items()
    ]
    return text(sql).bindparams(*typed)


async def _seed(session: AsyncSession) -> dict[str, uuid.UUID]:
    """Insert the prerequisites via Core inserts (MoneyType-aware): a tenant, an OPEN March period
    and a CLOSED February period, two postable accounts, a registry document, and a DRAFT entry
    with two BALANCED one-sided lines. Returns the ids the tests need."""
    tenant_id = uuid.uuid4()
    open_period_id = uuid.uuid4()
    closed_period_id = uuid.uuid4()
    year_id = uuid.uuid4()
    cash_id = uuid.uuid4()
    sales_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    entry_id = uuid.uuid4()
    now = await _now()

    await session.execute(
        sa.insert(Tenant.__table__).values(
            id=tenant_id, slug=f"g-{tenant_id.hex[:8]}", name="Guard",
            created_at=now, updated_at=now,
        )
    )
    await session.execute(
        sa.insert(FiscalYear.__table__).values(
            id=year_id, tenant_id=tenant_id, code="2026", name="FY2026",
            start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), status="OPEN",
            created_at=now, updated_at=now,
        )
    )
    await session.execute(
        sa.insert(FiscalPeriod.__table__).values(
            [
                {"id": open_period_id, "tenant_id": tenant_id, "fiscal_year_id": year_id,
                 "period_number": 3, "name": "2026-03", "start_date": date(2026, 3, 1),
                 "end_date": date(2026, 3, 31), "status": "OPEN", "created_at": now,
                 "updated_at": now},
                {"id": closed_period_id, "tenant_id": tenant_id, "fiscal_year_id": year_id,
                 "period_number": 2, "name": "2026-02", "start_date": date(2026, 2, 1),
                 "end_date": date(2026, 2, 28), "status": "CLOSED", "created_at": now,
                 "updated_at": now},
            ]
        )
    )
    for aid, code, name, atype in (
        (cash_id, "1000", "Cash", "ASSET"),
        (sales_id, "4000", "Sales", "REVENUE"),
    ):
        await session.execute(
            sa.insert(Account.__table__).values(
                id=aid, tenant_id=tenant_id, code=code, name=name, account_type=atype,
                normal_balance="DEBIT" if atype == "ASSET" else "CREDIT", is_postable=True,
                is_cash_equivalent=False, is_active=True, created_at=now, updated_at=now,
            )
        )
    await session.execute(
        sa.insert(Document.__table__).values(
            id=doc_id, tenant_id=tenant_id, doc_type="finance.journal_entry", doc_id=entry_id,
            doc_number=None, status="DRAFT", created_at=now, updated_at=now,
        )
    )
    await session.execute(
        sa.insert(JournalEntry.__table__).values(
            id=entry_id, tenant_id=tenant_id, document_id=doc_id, entry_number=None,
            posting_date=_PD, document_type="JOURNAL", currency_code="USD", status="DRAFT",
            created_at=now, updated_at=now,
        )
    )
    def _line(line_number: int, account_id: uuid.UUID, debit: str, credit: str) -> dict:
        dr, cr = Decimal(debit), Decimal(credit)
        return {
            "id": uuid.uuid4(), "tenant_id": tenant_id, "journal_entry_id": entry_id,
            "line_number": line_number, "account_id": account_id, "currency_code": "USD",
            "transaction_debit_amount": dr, "transaction_credit_amount": cr,
            "functional_debit_amount": dr, "functional_credit_amount": cr,
            "is_posted": False, "created_at": now, "updated_at": now,
        }

    await session.execute(
        sa.insert(JournalLine.__table__).values(
            [_line(1, cash_id, "100", "0"), _line(2, sales_id, "0", "100")]
        )
    )
    await session.commit()
    return {
        "tenant_id": tenant_id,
        "entry_id": entry_id,
        "doc_id": doc_id,
        "cash_id": cash_id,
        "open_period_id": open_period_id,
    }


async def _post_directly(session: AsyncSession, ids: dict[str, uuid.UUID]) -> None:
    """Flip the entry to POSTED via raw SQL (lines first, then header) the way the service does,
    so subsequent immutability tests have a posted entry to attack. Runs against an OPEN period.
    is_posted is set via the typed Core UPDATE so the boolean adapts to each engine."""
    await session.execute(
        sa.update(JournalLine.__table__)
        .where(JournalLine.__table__.c.journal_entry_id == ids["entry_id"])
        .values(is_posted=True)
    )
    await session.execute(
        _uuid_text(
            "UPDATE fin_journal_entries SET status = 'POSTED', entry_number = 'JE-2026-00001', "
            "fiscal_period_id = :p, posted_at = :now WHERE id = :e",
            p=ids["open_period_id"],
            now=await _now(),
            e=ids["entry_id"],
        )
    )
    await session.commit()


def _new_session(engine: AsyncEngine) -> AsyncSession:
    from app.core.db import build_session_factory

    return build_session_factory(engine)()


async def _run_seed(engine: AsyncEngine) -> tuple[dict[str, uuid.UUID], AsyncSession]:
    session = _new_session(engine)
    ids = await _seed(session)
    return ids, session


def _line_amounts(debit: str, credit: str) -> dict:
    dr, cr = Decimal(debit), Decimal(credit)
    return {
        "transaction_debit_amount": dr, "transaction_credit_amount": cr,
        "functional_debit_amount": dr, "functional_credit_amount": cr,
    }


# --- the guard assertions, parametrized over the engine -----------------------


async def _assert_one_side_check(session: AsyncSession, ids: dict) -> None:
    with pytest.raises((IntegrityError, DBAPIError)):
        await session.execute(
            sa.insert(JournalLine.__table__).values(
                id=uuid.uuid4(), tenant_id=ids["tenant_id"], journal_entry_id=ids["entry_id"],
                line_number=99, account_id=ids["cash_id"], currency_code="USD",
                is_posted=False, created_at=await _now(), updated_at=await _now(),
                **_line_amounts("5", "5"),
            )
        )


async def _assert_period_closed(session: AsyncSession, ids: dict) -> None:
    await session.execute(
        _uuid_text(
            "UPDATE fin_journal_entries SET posting_date = :d WHERE id = :e",
            d=_CLOSED_PD, e=ids["entry_id"],
        )
    )
    await session.commit()
    with pytest.raises(DBAPIError) as exc:
        await session.execute(
            _uuid_text(
                "UPDATE fin_journal_entries SET status = 'POSTED' WHERE id = :e", e=ids["entry_id"]
            )
        )
    assert "ATLAS_PERIOD_CLOSED" in str(exc.value)


async def _assert_unbalanced(session: AsyncSession, ids: dict) -> None:
    # Unbalance by zeroing line 2's credit and moving it to debit; the entry no longer balances.
    await session.execute(
        sa.update(JournalLine.__table__)
        .where(
            JournalLine.__table__.c.journal_entry_id == ids["entry_id"],
            JournalLine.__table__.c.line_number == 2,
        )
        .values(**_line_amounts("100", "0"))
    )
    await session.commit()
    with pytest.raises(DBAPIError) as exc:
        await session.execute(
            _uuid_text(
                "UPDATE fin_journal_entries SET status = 'POSTED', fiscal_period_id = :p "
                "WHERE id = :e",
                p=ids["open_period_id"], e=ids["entry_id"],
            )
        )
    assert "ATLAS_UNBALANCED_ENTRY" in str(exc.value)


async def _assert_header_update_blocked(session: AsyncSession, ids: dict) -> None:
    await _post_directly(session, ids)
    with pytest.raises(DBAPIError) as exc:
        await session.execute(
            _uuid_text(
                "UPDATE fin_journal_entries SET description = 'tampered' WHERE id = :e",
                e=ids["entry_id"],
            )
        )
    assert "ATLAS_POSTED_IMMUTABLE" in str(exc.value)


async def _assert_header_delete_blocked(session: AsyncSession, ids: dict) -> None:
    await _post_directly(session, ids)
    with pytest.raises(DBAPIError) as exc:
        await session.execute(
            _uuid_text("DELETE FROM fin_journal_entries WHERE id = :e", e=ids["entry_id"])
        )
    assert "ATLAS_POSTED_IMMUTABLE" in str(exc.value)


async def _assert_sanctioned_reversal_allowed(session: AsyncSession, ids: dict) -> None:
    await _post_directly(session, ids)
    # A self-reference satisfies the same-tenant FK for this isolated transition test.
    await session.execute(
        _uuid_text(
            "UPDATE fin_journal_entries SET status = 'REVERSED', reversed_by_entry_id = :e "
            "WHERE id = :e",
            e=ids["entry_id"],
        )
    )
    await session.commit()
    status = (
        await session.execute(
            _uuid_text("SELECT status FROM fin_journal_entries WHERE id = :e", e=ids["entry_id"])
        )
    ).scalar_one()
    assert status == "REVERSED"


async def _assert_line_update_blocked(session: AsyncSession, ids: dict) -> None:
    await _post_directly(session, ids)
    with pytest.raises(DBAPIError) as exc:
        await session.execute(
            sa.update(JournalLine.__table__)
            .where(JournalLine.__table__.c.journal_entry_id == ids["entry_id"])
            .values(functional_debit_amount=Decimal("999"))
        )
    assert "ATLAS_POSTED_IMMUTABLE" in str(exc.value)


async def _assert_line_delete_blocked(session: AsyncSession, ids: dict) -> None:
    await _post_directly(session, ids)
    with pytest.raises(DBAPIError) as exc:
        await session.execute(
            _uuid_text(
                "DELETE FROM fin_journal_lines WHERE journal_entry_id = :e", e=ids["entry_id"]
            )
        )
    assert "ATLAS_POSTED_IMMUTABLE" in str(exc.value)


_GUARD_CASES = (
    _assert_one_side_check,
    _assert_period_closed,
    _assert_unbalanced,
    _assert_header_update_blocked,
    _assert_header_delete_blocked,
    _assert_sanctioned_reversal_allowed,
    _assert_line_update_blocked,
    _assert_line_delete_blocked,
)


# --- SQLite (default run): the migrated per-test copy --------------------------


@pytest.mark.parametrize("guard", _GUARD_CASES, ids=lambda g: g.__name__)
async def test_journal_guard_sqlite(db_engine: AsyncEngine, guard) -> None:
    ids, session = await _run_seed(db_engine)
    async with session:
        await guard(session, ids)


# --- Postgres (-m pg): the SAME assertions on the real engine (D-022) ----------


async def _reset_pg(engine: AsyncEngine) -> None:
    """Truncate so each pg case starts clean (the pg engine is one shared database, unlike the
    per-test SQLite copy)."""
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE fin_journal_lines, fin_journal_entries, fin_fiscal_periods, "
                "fin_fiscal_years, fin_accounts, core_documents, adm_tenants "
                "RESTART IDENTITY CASCADE"
            )
        )


@pytest.mark.pg
@pytest.mark.parametrize("guard", _GUARD_CASES, ids=lambda g: g.__name__)
async def test_journal_guard_postgres(pg_engine: AsyncEngine, guard) -> None:
    await _reset_pg(pg_engine)
    ids, session = await _run_seed(pg_engine)
    async with session:
        await guard(session, ids)
