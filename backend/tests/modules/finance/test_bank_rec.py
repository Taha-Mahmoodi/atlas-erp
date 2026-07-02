"""Bank-statement CSV import service behavior (PLAN 4.9), SQLite.

Proves the CSV import contract (balanced statements, per-row error reports, the
cash-equivalent account rule, the PERFORMANCE §2 bulk insert bound) plus tenant isolation on
statement reads. The shared builders (_csv/_import/_post_bank_entry/_lines) live here and are
reused by test_bank_reconcile.py (matching/clearing/status) — the file split mirrors the
service split (bank_import.py vs bank_reconcile.py). HTTP/RBAC/idempotency/jobs are proven in
test_bank_rec_api.py.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationFailedError
from app.core.tenancy import tenant_context
from app.modules.finance import service
from app.modules.finance.constants import LineStatus, StatementStatus
from app.modules.finance.models import BankStatement, BankStatementLine, JournalLine
from app.modules.finance.schemas import JournalEntryCreate, JournalLineCreate
from tests.modules.finance.conftest import BankSetup

_CSV_HEADER = "value_date,amount,description,counterparty_ref"


def _csv(rows: list[str]) -> str:
    return "\n".join([_CSV_HEADER, *rows]) + "\n"


async def _import(
    session: AsyncSession,
    setup: BankSetup,
    csv_text: str,
    *,
    opening: str = "0.00",
    closing: str,
    bank_account_id: uuid.UUID | None = None,
) -> BankStatement:
    with tenant_context(setup.tenant_id):
        statement = await service.import_statement(
            session,
            setup.tenant_id,
            bank_account_id=bank_account_id or setup.bank_account_id,
            statement_date=date(2026, 3, 31),
            opening_balance=Decimal(opening),
            closing_balance=Decimal(closing),
            currency_code="USD",
            csv_text=csv_text,
            source_filename="march.csv",
        )
        await session.commit()
    return statement


async def _post_bank_entry(
    session: AsyncSession,
    setup: BankSetup,
    amount: str,
    posting_date: date,
    *,
    money_in: bool = True,
) -> uuid.UUID:
    """Post Dr bank / Cr revenue (money in) or Dr expense / Cr bank (money out); return the
    id of the BANK-side journal line — the candidate the matcher must find."""
    bank = JournalLineCreate(
        account_id=setup.bank_account_id,
        transaction_debit_amount=Decimal(amount) if money_in else Decimal(0),
        transaction_credit_amount=Decimal(0) if money_in else Decimal(amount),
    )
    other = JournalLineCreate(
        account_id=setup.accounts["4000" if money_in else "5000"],
        transaction_credit_amount=Decimal(amount) if money_in else Decimal(0),
        transaction_debit_amount=Decimal(0) if money_in else Decimal(amount),
    )
    with tenant_context(setup.tenant_id):
        entry = await service.create_draft_entry(
            session,
            setup.tenant_id,
            JournalEntryCreate(
                posting_date=posting_date,
                currency_code="USD",
                description="Bank movement",
                lines=[bank, other],
            ),
        )
        await service.post_entry(session, setup.tenant_id, entry.id)
        await session.commit()
        line_id = (
            await session.execute(
                select(JournalLine.id).where(
                    JournalLine.journal_entry_id == entry.id,
                    JournalLine.account_id == setup.bank_account_id,
                )
            )
        ).scalar_one()
    return line_id


async def _lines(
    session: AsyncSession, setup: BankSetup, statement_id: uuid.UUID
) -> list[BankStatementLine]:
    with tenant_context(setup.tenant_id):
        return list(
            (
                await session.execute(
                    select(BankStatementLine)
                    .where(BankStatementLine.statement_id == statement_id)
                    .order_by(BankStatementLine.line_number)
                )
            )
            .scalars()
            .all()
        )


# --- import -------------------------------------------------------------------


async def test_import_creates_statement_with_parsed_lines(
    db_session: AsyncSession, bank_setup: BankSetup
) -> None:
    statement = await _import(
        db_session,
        bank_setup,
        _csv(
            [
                "2026-03-02,100.00,Customer payment ACME,INV-1",
                "2026-03-05,-12.50,Bank fee,",
                "2026-03-09,40.00,Customer payment Globex,INV-2",
            ]
        ),
        opening="10.00",
        closing="137.50",
    )
    assert statement.status == StatementStatus.IMPORTED.value
    assert statement.line_count == 3
    assert statement.source_filename == "march.csv"
    lines = await _lines(db_session, bank_setup, statement.id)
    assert [line.line_number for line in lines] == [1, 2, 3]
    assert all(line.status == LineStatus.UNMATCHED.value for line in lines)
    assert Decimal(str(lines[1].amount)) == Decimal("-12.50")
    assert lines[0].counterparty_ref == "INV-1"
    assert lines[1].counterparty_ref is None  # empty CSV cell -> NULL
    assert lines[1].value_date == date(2026, 3, 5)


async def test_import_rejects_unbalanced_statement(
    db_session: AsyncSession, bank_setup: BankSetup
) -> None:
    with pytest.raises(ValidationFailedError) as exc:
        await _import(
            db_session,
            bank_setup,
            _csv(["2026-03-02,100.00,Payment,"]),
            opening="0.00",
            closing="999.00",
        )
    assert exc.value.code == "finance.statement_unbalanced"
    assert exc.value.details["lines_total"] == "100.00"


async def test_import_rejects_malformed_rows_with_row_numbers(
    db_session: AsyncSession, bank_setup: BankSetup
) -> None:
    with pytest.raises(ValidationFailedError) as exc:
        await _import(
            db_session,
            bank_setup,
            _csv(
                [
                    "2026-03-02,100.00,Fine,",
                    "not-a-date,50.00,Bad date,",
                    "2026-03-04,abc,Bad amount,",
                    "2026-03-05,5.00,,",
                ]
            ),
            closing="155.00",
        )
    assert exc.value.code == "finance.statement_csv_invalid"
    assert [e["row"] for e in exc.value.details["row_errors"]] == [2, 3, 4]


async def test_import_rejects_non_finite_amounts(
    db_session: AsyncSession, bank_setup: BankSetup
) -> None:
    """Regression for #79: Decimal() accepts Infinity/NaN/1e10000, which used to crash
    quantize_money with a 500 (Infinity) or surface as a misleading statement_unbalanced (NaN)
    instead of the documented csv-invalid 422."""
    with pytest.raises(ValidationFailedError) as exc:
        await _import(
            db_session,
            bank_setup,
            _csv(
                [
                    "2026-03-02,Infinity,Inf,",
                    "2026-03-03,-Infinity,NegInf,",
                    "2026-03-04,NaN,NaN,",
                    "2026-03-05,1e10000,Overflow,",  # finite but overflows quantize
                ]
            ),
            closing="0.00",
        )
    assert exc.value.code == "finance.statement_csv_invalid"
    assert [e["row"] for e in exc.value.details["row_errors"]] == [1, 2, 3, 4]


async def test_import_rejects_wrong_header_and_empty_file(
    db_session: AsyncSession, bank_setup: BankSetup
) -> None:
    for bad_csv in ("date,amount\n2026-03-02,1.00\n", _CSV_HEADER + "\n"):
        with pytest.raises(ValidationFailedError) as exc:
            await _import(db_session, bank_setup, bad_csv, closing="0.00")
        assert exc.value.code == "finance.statement_csv_invalid"


async def test_import_rejects_non_cash_equivalent_account(
    db_session: AsyncSession, bank_setup: BankSetup
) -> None:
    # 4000 Sales Revenue exists but is not flagged is_cash_equivalent.
    with pytest.raises(ValidationFailedError) as exc:
        await _import(
            db_session,
            bank_setup,
            _csv(["2026-03-02,100.00,Payment,"]),
            closing="100.00",
            bank_account_id=bank_setup.accounts["4000"],
        )
    assert exc.value.code == "finance.bank_account_not_cash_equivalent"


async def test_bulk_import_runs_a_bounded_number_of_statements(
    db_session: AsyncSession, bank_setup: BankSetup, query_counter
) -> None:
    """PERFORMANCE §2: ~1200 lines import through ONE executemany insert, so the whole import
    call stays O(1) statements — measured exactly 6 (account check, document insert+select,
    statement insert, audit row, lines executemany); asserted ≤10 for slack, never O(n)."""
    rows = [f"2026-03-01,1.00,Line {i}," for i in range(1, 1201)]
    with query_counter() as qc:
        statement = await _import(db_session, bank_setup, _csv(rows), closing="1200.00")
    assert statement.line_count == 1200
    assert qc.count <= 10, f"import ran {qc.count} statements:\n" + "\n".join(qc.statements[:30])
    lines = await _lines(db_session, bank_setup, statement.id)
    assert len(lines) == 1200


async def test_tenant_isolation_on_statement_reads(
    db_session: AsyncSession, bank_setup: BankSetup, tenant_b: uuid.UUID
) -> None:
    statement = await _import(
        db_session, bank_setup, _csv(["2026-03-02,1.00,Tiny,"]), closing="1.00"
    )
    with tenant_context(tenant_b), pytest.raises(NotFoundError):
        await service.get_bank_statement(db_session, tenant_b, statement.id)
