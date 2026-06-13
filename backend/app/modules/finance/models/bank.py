"""Bank reconciliation: imported statements and their lines (PLAN 4.9).

A ``BankStatement`` is an EXTERNAL document imported from a bank CSV; its lines are matched
against posted journal lines on the statement's bank account (``is_cash_equivalent`` — the
service enforces that, since fin_accounts carries no flag-scoped FK). Matching never mutates
the journal: a line records the journal line it matched (``matched_journal_line_id``, an
OPAQUE Uuid — no FK, mirroring the dimension-id precedent) or the clearing entry posted for a
bank-only line like a fee (``cleared_journal_entry_id``, a real composite tenant FK because
the entry is created BY this flow).

DocumentMixin on the statement (a deviation from the task sketch, which omitted it): the
required docflow statement->entry link (D-012) needs a core_documents registry row, and
DocumentMixin is the only sanctioned way to hold one. NO gapless number is claimed — D-012
numbering covers documents Atlas issues; a bank statement is identified by its source
(bank account + date + filename), so its registry ``doc_number`` stays NULL.

Lines are NOT AuditMixin: they are written once by the bulk import (PERFORMANCE §2) and then
only advance a small status machine; the statement's audit row records the document-level
change (the same exclusion class as journal/bill/invoice lines). Sixth file in the finance
``models/`` package (STRUCTURE §3); re-exported from ``models/__init__``.
"""

import uuid
from datetime import date

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.core.docflow import DocumentMixin, document_fk
from app.core.models import (
    AuditMixin,
    Base,
    TenantMixin,
    TimestampMixin,
    UuidPKMixin,
    tenant_fk,
    tenant_unique,
)
from app.core.money import MoneyType
from app.modules.finance.constants import LineStatus, StatementStatus


class BankStatement(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, DocumentMixin, Base):
    """One imported bank statement (PLAN 4.9). ``opening_balance + Σ(line amounts) ==
    closing_balance`` is validated at import (422 otherwise) so a statement is internally
    consistent before any reconciliation starts. ``status`` is derived from line resolution
    (a line is resolved when MATCHED or CLEARED) and recomputed by the service as lines
    advance. ``import_job_id`` records the background job that imported it (>1k-line imports,
    PERFORMANCE §3) — a plain nullable Uuid like ``core_jobs.submitted_by_user_id``, no FK.
    Audited (D-010): a financial document."""

    __tablename__ = "fin_bank_statements"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("adm_tenants"),
        document_fk(),
        tenant_fk("fin_accounts", "bank_account_id"),
        # List filter/sort combination for GET /bank-statements (PERFORMANCE §1).
        sa.Index(
            "ix_fin_bank_statements_tenant_id_statement_date",
            "tenant_id",
            "statement_date",
        ),
    )

    bank_account_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    statement_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    opening_balance: Mapped[object] = mapped_column(
        MoneyType(), nullable=False, default=0, server_default="0"
    )
    closing_balance: Mapped[object] = mapped_column(
        MoneyType(), nullable=False, default=0, server_default="0"
    )
    currency_code: Mapped[str] = mapped_column(sa.String(3), nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(25),
        nullable=False,
        default=StatementStatus.IMPORTED.value,
        server_default="IMPORTED",
    )
    line_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    import_job_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    source_filename: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)


class BankStatementLine(UuidPKMixin, TenantMixin, TimestampMixin, Base):
    """One statement line (PLAN 4.9). ``amount`` is SIGNED in the statement currency:
    positive = credit to the bank account (money in), negative = debit (money out).
    Status machine: UNMATCHED -> SUGGESTED (match suggestion, sets
    ``matched_journal_line_id``) -> MATCHED (manual confirm) | back to UNMATCHED (reject);
    UNMATCHED -> CLEARED (a posted clearing entry, sets ``cleared_journal_entry_id``).
    ``matched_journal_line_id`` is an opaque Uuid (no FK — read-only reference into the
    immutable journal); ``cleared_journal_entry_id`` is a composite tenant FK because the
    clearing entry is created by this flow."""

    __tablename__ = "fin_bank_statement_lines"
    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id",
            "statement_id",
            "line_number",
            # Explicit short name: the D-022 convention keys on column 0 (tenant_id) only
            # and would collide with tenant_unique().
            name="uq_fin_bank_statement_lines_statement_line",
        ),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("fin_bank_statements", "statement_id"),
        tenant_fk("fin_journal_entries", "cleared_journal_entry_id"),
        # The reconciliation work-list filter (lines of one statement by status) and the
        # date-window candidate scan (PERFORMANCE §1).
        sa.Index(
            "ix_fin_bank_statement_lines_statement_status",
            "tenant_id",
            "statement_id",
            "status",
        ),
        sa.Index(
            "ix_fin_bank_statement_lines_tenant_id_value_date",
            "tenant_id",
            "value_date",
        ),
    )

    statement_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    line_number: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    value_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    amount: Mapped[object] = mapped_column(MoneyType(), nullable=False)
    description: Mapped[str] = mapped_column(sa.String(500), nullable=False)
    counterparty_ref: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)
    status: Mapped[str] = mapped_column(
        sa.String(12),
        nullable=False,
        default=LineStatus.UNMATCHED.value,
        server_default="UNMATCHED",
    )
    matched_journal_line_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    cleared_journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
