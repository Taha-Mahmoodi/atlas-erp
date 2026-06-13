"""The bank-statement CSV contract: header, row validation, parsing (PLAN 4.9).

The only v1 import format (MT940/CAMT parsers are a parity-doc later feeding the same
pipeline): a header row exactly ``value_date,amount,description,counterparty_ref`` then one
data row per statement line — ISO-8601 dates, decimal-point amounts SIGNED from the bank
account's perspective (positive = money in, negative = money out), required description,
optional counterparty reference. Malformed rows are collected into a per-row error report and
the WHOLE file is rejected 422 (no partial statements). Split out of ``bank_import.py``
(STRUCTURE §3/§8.5: one concept per file, both under the cap).
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from app.core.exceptions import ValidationFailedError
from app.core.money import currency_decimals, quantize_money

CSV_HEADER = ("value_date", "amount", "description", "counterparty_ref")
# A 422 error report stays bounded no matter how broken the file is.
_MAX_ROW_ERRORS = 50


@dataclass(frozen=True)
class ParsedLine:
    """One validated CSV data row; ``line_number`` is the 1-based data-row position."""

    line_number: int
    value_date: date
    amount: Decimal
    description: str
    counterparty_ref: str | None


def count_csv_data_rows(csv_text: str) -> int:
    """Cheap routing heuristic for the sync-vs-job decision (PERFORMANCE §3): non-blank lines
    after the header. The authoritative ``line_count`` comes from the real parse."""
    return sum(1 for raw in csv_text.splitlines()[1:] if raw.strip())


def _row_problem(row: list[str]) -> str | None:
    """The first validation problem of a 4-column row, or None if it is clean."""
    if len(row) != 4:
        return f"expected 4 columns, got {len(row)}"
    raw_date, raw_amount, description, ref = (cell.strip() for cell in row)
    try:
        date.fromisoformat(raw_date)
    except ValueError:
        return f"value_date {raw_date!r} is not an ISO date"
    try:
        amount = Decimal(raw_amount)
    except InvalidOperation:
        return f"amount {raw_amount!r} is not a decimal number"
    if amount == 0:
        return "amount must be non-zero"
    if not description:
        return "description is required"
    if len(description) > 500:
        return "description exceeds 500 characters"
    if len(ref) > 100:
        return "counterparty_ref exceeds 100 characters"
    return None


def parse_statement_csv(csv_text: str, currency_code: str) -> list[ParsedLine]:
    """Parse + validate the CSV contract (module docstring): rejects a wrong header, malformed
    rows (collected into ``details.row_errors`` with 1-based data-row numbers) and an empty
    file — all 422 ``finance.statement_csv_invalid``. Amounts quantize HALF_UP to the statement
    currency's minor unit (D-015)."""
    reader = csv.reader(io.StringIO(csv_text))
    header = next(reader, None)
    if header is None or [cell.strip() for cell in header] != list(CSV_HEADER):
        raise ValidationFailedError(
            message="The CSV header must be exactly: " + ",".join(CSV_HEADER),
            code="finance.statement_csv_invalid",
            details={"header": ",".join(header) if header else None},
        )
    decimals = currency_decimals(currency_code)
    parsed: list[ParsedLine] = []
    errors: list[dict[str, Any]] = []
    row_number = 0
    for row in reader:
        if not row or all(not cell.strip() for cell in row):
            continue  # ignore blank lines (e.g. a trailing newline)
        row_number += 1
        problem = _row_problem(row)
        if problem is not None:
            if len(errors) < _MAX_ROW_ERRORS:
                errors.append({"row": row_number, "error": problem})
            continue
        raw_date, raw_amount, description, ref = (cell.strip() for cell in row)
        parsed.append(
            ParsedLine(
                line_number=row_number,
                value_date=date.fromisoformat(raw_date),
                amount=quantize_money(Decimal(raw_amount), decimals),
                description=description,
                counterparty_ref=ref or None,
            )
        )
    if errors:
        raise ValidationFailedError(
            message="The statement CSV contains malformed rows",
            code="finance.statement_csv_invalid",
            details={"row_errors": errors},
        )
    if not parsed:
        raise ValidationFailedError(
            message="The statement CSV contains no data rows",
            code="finance.statement_csv_invalid",
            details={"row_errors": []},
        )
    return parsed
