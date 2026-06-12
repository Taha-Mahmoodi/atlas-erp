"""Bank reconciliation request/response schemas (PLAN 4.9, Pydantic v2, ApiModel base).

A sibling of ``schemas.py`` exactly like ``payables_schemas.py``/``receivables_schemas.py``
(STRUCTURE §8.5 one-concept-per-file; ``schemas.py`` is at the cap). Money fields are
``Decimal`` serialized as strings (D-015). The import request carries the CSV as a plain
``csv_text`` string (JSON body, no multipart) — the documented contract lives in
``service/bank_import.py``. Server-owned fields (ids, status, line_count, import_job_id,
timestamps) are never accepted on the import request.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from app.core.schemas import ApiModel


class BankStatementImportRequest(ApiModel):
    """Import one statement. ``opening_balance + Σ(csv line amounts)`` must equal
    ``closing_balance`` (422 otherwise). The router runs ≤1000-line imports inline (201) and
    submits larger ones as a background job (202 {job_id}, PERFORMANCE §3)."""

    bank_account_id: uuid.UUID
    statement_date: date
    opening_balance: Decimal
    closing_balance: Decimal
    currency_code: str
    csv_text: str
    source_filename: str | None = None


class BankStatementRead(ApiModel):
    id: uuid.UUID
    bank_account_id: uuid.UUID
    statement_date: date
    opening_balance: Decimal
    closing_balance: Decimal
    currency_code: str
    status: str
    line_count: int
    import_job_id: uuid.UUID | None = None
    source_filename: str | None = None
    created_at: datetime


class StatementProgressRead(ApiModel):
    """Line counts by status; ``resolved`` = matched + cleared."""

    total: int
    unmatched: int
    suggested: int
    matched: int
    cleared: int
    resolved: int


class BankStatementDetail(BankStatementRead):
    """Statement header + its reconciliation progress counts."""

    progress: StatementProgressRead


class BankStatementLineRead(ApiModel):
    id: uuid.UUID
    statement_id: uuid.UUID
    line_number: int
    value_date: date
    amount: Decimal
    description: str
    counterparty_ref: str | None = None
    status: str
    matched_journal_line_id: uuid.UUID | None = None
    cleared_journal_entry_id: uuid.UUID | None = None


class SuggestMatchesResult(ApiModel):
    """Outcome of a suggestion run over a statement's UNMATCHED lines."""

    suggested: int
    unmatched: int


class ClearLineRequest(ApiModel):
    """Optional explicit contra account; defaults to the ``bank_unmatched_clearing`` posting
    default when omitted."""

    contra_account_id: uuid.UUID | None = None
