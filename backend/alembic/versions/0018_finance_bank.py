"""finance bank reconciliation: statements and statement lines

Revision ID: 0018
Revises: 0017
Create Date: 2026-06-12

PLAN 4.9 — bank reconciliation:

- fin_bank_statements: one imported bank-statement header. DocumentMixin (NOT NULL
  ``document_id`` -> core_documents, doc_number stays NULL — external documents are not
  Atlas-numbered) so the docflow statement->clearing-entry link works. Composite tenant FK to
  fin_accounts (``bank_account_id``; the is_cash_equivalent rule is service-level — no flag-
  scoped FK exists). ``import_job_id`` is a plain nullable Uuid (no FK, the core_jobs
  attribution precedent). Money columns are MoneyType (D-015).
- fin_bank_statement_lines: the signed statement lines (positive = money in). Composite
  tenant FKs to the statement and (nullable) the clearing journal entry;
  ``matched_journal_line_id`` is an OPAQUE Uuid (no FK — a read-only reference into the
  immutable journal). UNIQUE(tenant, statement_id, line_number). Indexes: the standalone
  tenant_id pair (D-007), (tenant_id, statement_id, status) for the reconciliation work-list
  and (tenant_id, value_date) for the candidate date-window scan (PERFORMANCE §1).

Creates TWO tables and alters NOTHING — no trigger-bearing table is touched, so there is no
trigger-recreation concern (D-022). All DDL is portable across SQLite and Postgres; every
identifier is <= 63 chars (PG cap); FK names follow the D-022 column-0 convention so they
match what the models generate.
"""

import sqlalchemy as sa
from alembic import op

from app.core.money import MoneyType

# revision identifiers, used by Alembic.
revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | None = None
depends_on: str | None = None


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def upgrade() -> None:
    op.create_table(
        "fin_bank_statements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("bank_account_id", sa.Uuid(), nullable=False),
        sa.Column("statement_date", sa.Date(), nullable=False),
        sa.Column("opening_balance", MoneyType(), server_default="0", nullable=False),
        sa.Column("closing_balance", MoneyType(), server_default="0", nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=25), server_default="IMPORTED", nullable=False),
        sa.Column("line_count", sa.Integer(), nullable=False),
        sa.Column("import_job_id", sa.Uuid(), nullable=True),
        sa.Column("source_filename", sa.String(length=255), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["adm_tenants.id"],
            name="fk_fin_bank_statements_tenant_id_adm_tenants",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["core_documents.tenant_id", "core_documents.id"],
            name="fk_fin_bank_statements_tenant_id_core_documents",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "bank_account_id"],
            ["fin_accounts.tenant_id", "fin_accounts.id"],
            name="fk_fin_bank_statements_tenant_id_fin_accounts",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_fin_bank_statements"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_fin_bank_statements_tenant_id"),
        sa.UniqueConstraint("document_id", name="uq_fin_bank_statements_document_id"),
    )
    op.create_index("ix_fin_bank_statements_tenant_id", "fin_bank_statements", ["tenant_id"])
    op.create_index(
        "ix_fin_bank_statements_tenant_id_statement_date",
        "fin_bank_statements",
        ["tenant_id", "statement_date"],
    )

    op.create_table(
        "fin_bank_statement_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("statement_id", sa.Uuid(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("value_date", sa.Date(), nullable=False),
        sa.Column("amount", MoneyType(), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("counterparty_ref", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=12), server_default="UNMATCHED", nullable=False),
        # Opaque reference into the immutable journal (no FK, mirroring dimension ids).
        sa.Column("matched_journal_line_id", sa.Uuid(), nullable=True),
        sa.Column("cleared_journal_entry_id", sa.Uuid(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["adm_tenants.id"],
            name="fk_fin_bank_statement_lines_tenant_id_adm_tenants",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "statement_id"],
            ["fin_bank_statements.tenant_id", "fin_bank_statements.id"],
            name="fk_fin_bank_statement_lines_tenant_id_fin_bank_statements",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "cleared_journal_entry_id"],
            ["fin_journal_entries.tenant_id", "fin_journal_entries.id"],
            name="fk_fin_bank_statement_lines_tenant_id_fin_journal_entries",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_fin_bank_statement_lines"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_fin_bank_statement_lines_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "statement_id",
            "line_number",
            name="uq_fin_bank_statement_lines_statement_line",
        ),
    )
    op.create_index(
        "ix_fin_bank_statement_lines_tenant_id", "fin_bank_statement_lines", ["tenant_id"]
    )
    op.create_index(
        "ix_fin_bank_statement_lines_statement_status",
        "fin_bank_statement_lines",
        ["tenant_id", "statement_id", "status"],
    )
    op.create_index(
        "ix_fin_bank_statement_lines_tenant_id_value_date",
        "fin_bank_statement_lines",
        ["tenant_id", "value_date"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_fin_bank_statement_lines_tenant_id_value_date",
        table_name="fin_bank_statement_lines",
    )
    op.drop_index(
        "ix_fin_bank_statement_lines_statement_status",
        table_name="fin_bank_statement_lines",
    )
    op.drop_index(
        "ix_fin_bank_statement_lines_tenant_id", table_name="fin_bank_statement_lines"
    )
    op.drop_table("fin_bank_statement_lines")
    op.drop_index(
        "ix_fin_bank_statements_tenant_id_statement_date", table_name="fin_bank_statements"
    )
    op.drop_index("ix_fin_bank_statements_tenant_id", table_name="fin_bank_statements")
    op.drop_table("fin_bank_statements")
