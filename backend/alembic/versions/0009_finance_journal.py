"""finance universal journal: entries + lines + the four DB-guard triggers

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-12

PLAN 4.2 / D-017 + D-018 + D-021 + D-022 — the universal journal, the heart of Atlas finance.

Tables:
- fin_journal_entries: header (D-017). entry_number NULLABLE with a partial unique index
  (numbers claimed at posting per D-012); DocumentMixin document_id -> core_documents; self
  composite tenant FKs for reverses/reversed_by; composite tenant FK to the resolved period.
- fin_journal_lines: the append-only line table every statement projects from (D-021). The
  ck_fin_journal_lines_one_side CHECK enforces debit XOR credit on the STORED representation
  (NUMERIC on PG, micro-unit INTEGER on SQLite via MoneyType) so it holds on both engines.
  Denormalized is_posted/posting_date/fiscal_period_id let projections skip the header join.

Four per-dialect TRIGGERS (D-017/D-018), tokens translated by core/exceptions:
1. trg_fin_journal_entries_period_open  -> ATLAS_PERIOD_CLOSED   (D-018, BEFORE INSERT + UPDATE
   on the DRAFT->POSTED transition; re-derives the period from NEW.posting_date by date so a
   wrong fiscal_period_id cannot smuggle a posting into a closed period).
2. trg_fin_journal_entries_balanced     -> ATLAS_UNBALANCED_ENTRY (D-017, BEFORE UPDATE on
   DRAFT->POSTED; SUM(functional_debit) must equal SUM(functional_credit) over the lines and be
   > 0 — exact on both engines per D-015).
3. trg_fin_journal_entries_immutable + _no_delete -> ATLAS_POSTED_IMMUTABLE (D-017, BEFORE
   UPDATE/DELETE on a POSTED header; the ONLY permitted UPDATE is POSTED->REVERSED with
   reversed_by_entry_id set and no financial column changed).
4. trg_fin_journal_lines_immutable      -> ATLAS_POSTED_IMMUTABLE (D-017, BEFORE UPDATE/DELETE
   keyed on OLD.is_posted = TRUE, so the posting flush that flips is_posted FALSE->TRUE is
   allowed while a post-commit mutation of a posted line is rejected).

D-022: per-dialect string pairs side by side; upgrade DROPs IF EXISTS then CREATEs; downgrade
drops triggers + functions + tables. No batch-alter of a trigger-bearing table happens here, so
there is no trigger-recreation-after-batch concern in THIS revision.
"""

import sqlalchemy as sa
from alembic import op

from app.core.db_guards import (
    create_pg_function,
    create_pg_trigger,
    create_sqlite_trigger,
    drop_function,
    drop_trigger,
)
from app.core.money import MoneyType

# revision identifiers, used by Alembic.
revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | None = None
depends_on: str | None = None

_ENTRIES = "fin_journal_entries"
_LINES = "fin_journal_lines"

# --- trigger names + tokens ---------------------------------------------------
_TRG_PERIOD_INSERT = "trg_fin_journal_entries_period_open_ins"
_TRG_PERIOD_UPDATE = "trg_fin_journal_entries_period_open_upd"
_TRG_BALANCED = "trg_fin_journal_entries_balanced"
_TRG_HEADER_IMMUTABLE = "trg_fin_journal_entries_immutable"
_TRG_HEADER_NO_DELETE = "trg_fin_journal_entries_no_delete"
_TRG_LINE_IMMUTABLE = "trg_fin_journal_lines_immutable"
_TRG_LINE_NO_DELETE = "trg_fin_journal_lines_no_delete"

_FN_PERIOD = "fin_journal_entries_period_open"
_FN_BALANCED = "fin_journal_entries_balanced"
_FN_HEADER_IMMUTABLE = "fin_journal_entries_immutable"
_FN_HEADER_NO_DELETE = "fin_journal_entries_no_delete"
_FN_LINE_IMMUTABLE = "fin_journal_lines_immutable"

_TOKEN_PERIOD = "ATLAS_PERIOD_CLOSED"
_TOKEN_UNBALANCED = "ATLAS_UNBALANCED_ENTRY"
_TOKEN_IMMUTABLE = "ATLAS_POSTED_IMMUTABLE"

# Re-derive the period from posting_date (D-018): no OPEN period covering NEW.posting_date.
_NO_OPEN_PERIOD = (
    "NOT EXISTS (SELECT 1 FROM fin_fiscal_periods p "
    "WHERE p.tenant_id = NEW.tenant_id AND p.status = 'OPEN' "
    "AND NEW.posting_date BETWEEN p.start_date AND p.end_date)"
)

# Unbalanced/non-positive over the entry's lines (functional amounts; exact on both engines).
_UNBALANCED = (
    "(SELECT COALESCE(SUM(functional_debit_amount), 0) "
    "- COALESCE(SUM(functional_credit_amount), 0) FROM fin_journal_lines "
    "WHERE journal_entry_id = NEW.id) <> 0 "
    "OR (SELECT COALESCE(SUM(functional_debit_amount), 0) FROM fin_journal_lines "
    "WHERE journal_entry_id = NEW.id) <= 0"
)


def _create_entries_table() -> None:
    op.create_table(
        _ENTRIES,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("entry_number", sa.String(length=60), nullable=True),
        sa.Column("posting_date", sa.Date(), nullable=False),
        sa.Column("fiscal_period_id", sa.Uuid(), nullable=True),
        sa.Column(
            "document_type", sa.String(length=20), server_default="JOURNAL", nullable=False
        ),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=10), server_default="DRAFT", nullable=False),
        sa.Column("reverses_entry_id", sa.Uuid(), nullable=True),
        sa.Column("reversed_by_entry_id", sa.Uuid(), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["adm_tenants.id"],
            name=op.f("fk_fin_journal_entries_tenant_id_adm_tenants"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["core_documents.tenant_id", "core_documents.id"],
            name=op.f("fk_fin_journal_entries_document_id_core_documents"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "fiscal_period_id"],
            ["fin_fiscal_periods.tenant_id", "fin_fiscal_periods.id"],
            name=op.f("fk_fin_journal_entries_fiscal_period_id_fin_fiscal_periods"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "reverses_entry_id"],
            ["fin_journal_entries.tenant_id", "fin_journal_entries.id"],
            name="fk_fin_journal_entries_reverses_entry_id_fin_journal_entries",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "reversed_by_entry_id"],
            ["fin_journal_entries.tenant_id", "fin_journal_entries.id"],
            name="fk_fin_journal_entries_reversed_by_entry_id_fin_journal_entries",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fin_journal_entries")),
        sa.UniqueConstraint("tenant_id", "id", name="uq_fin_journal_entries_tenant_id"),
        sa.UniqueConstraint(
            "document_id", name=op.f("uq_fin_journal_entries_document_id")
        ),
    )
    op.create_index(op.f("ix_fin_journal_entries_tenant_id"), _ENTRIES, ["tenant_id"])
    op.create_index(
        "uq_fin_journal_entries_tenant_id_entry_number",
        _ENTRIES,
        ["tenant_id", "entry_number"],
        unique=True,
        postgresql_where=sa.text("entry_number IS NOT NULL"),
        sqlite_where=sa.text("entry_number IS NOT NULL"),
    )


def _create_lines_table() -> None:
    op.create_table(
        _LINES,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("journal_entry_id", sa.Uuid(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("transaction_debit_amount", MoneyType(), server_default="0", nullable=False),
        sa.Column("transaction_credit_amount", MoneyType(), server_default="0", nullable=False),
        sa.Column("functional_debit_amount", MoneyType(), server_default="0", nullable=False),
        sa.Column("functional_credit_amount", MoneyType(), server_default="0", nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("cost_center_id", sa.Uuid(), nullable=True),
        sa.Column("profit_center_id", sa.Uuid(), nullable=True),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("item_id", sa.Uuid(), nullable=True),
        sa.Column("partner_type", sa.String(length=20), nullable=True),
        sa.Column("partner_id", sa.Uuid(), nullable=True),
        sa.Column("is_posted", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("posting_date", sa.Date(), nullable=True),
        sa.Column("fiscal_period_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "(transaction_debit_amount > 0 AND transaction_credit_amount = 0) "
            "OR (transaction_credit_amount > 0 AND transaction_debit_amount = 0)",
            name="ck_fin_journal_lines_one_side",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["adm_tenants.id"],
            name=op.f("fk_fin_journal_lines_tenant_id_adm_tenants"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "journal_entry_id"],
            ["fin_journal_entries.tenant_id", "fin_journal_entries.id"],
            name=op.f("fk_fin_journal_lines_journal_entry_id_fin_journal_entries"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "account_id"],
            ["fin_accounts.tenant_id", "fin_accounts.id"],
            name=op.f("fk_fin_journal_lines_account_id_fin_accounts"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fin_journal_lines")),
        sa.UniqueConstraint("tenant_id", "id", name="uq_fin_journal_lines_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "journal_entry_id",
            "line_number",
            name="uq_fin_journal_lines_tenant_id_journal_entry_id_line_number",
        ),
    )
    op.create_index(op.f("ix_fin_journal_lines_tenant_id"), _LINES, ["tenant_id"])
    op.create_index(
        "ix_fin_journal_lines_proj",
        _LINES,
        ["tenant_id", "account_id", "posting_date"],
        postgresql_where=sa.text("is_posted"),
        sqlite_where=sa.text("is_posted"),
    )


def _create_triggers() -> None:
    # 1. Period-open (D-018). Re-derive by date; fire on direct posted INSERT and DRAFT->POSTED.
    drop_trigger(op, _TRG_PERIOD_INSERT, _ENTRIES)
    drop_trigger(op, _TRG_PERIOD_UPDATE, _ENTRIES)
    create_pg_function(
        op,
        _FN_PERIOD,
        f"IF {_NO_OPEN_PERIOD} THEN RAISE EXCEPTION '{_TOKEN_PERIOD}'; END IF; RETURN NEW;",
    )
    create_pg_trigger(
        op,
        name=_TRG_PERIOD_INSERT,
        table=_ENTRIES,
        event="INSERT",
        function_name=_FN_PERIOD,
        when="NEW.status = 'POSTED'",
    )
    create_pg_trigger(
        op,
        name=_TRG_PERIOD_UPDATE,
        table=_ENTRIES,
        event="UPDATE",
        function_name=_FN_PERIOD,
        when="NEW.status = 'POSTED' AND OLD.status <> 'POSTED'",
    )
    create_sqlite_trigger(
        op,
        name=_TRG_PERIOD_INSERT,
        table=_ENTRIES,
        event="INSERT",
        when="NEW.status = 'POSTED'",
        body=f"SELECT RAISE(ABORT, '{_TOKEN_PERIOD}') WHERE {_NO_OPEN_PERIOD};",
    )
    create_sqlite_trigger(
        op,
        name=_TRG_PERIOD_UPDATE,
        table=_ENTRIES,
        event="UPDATE",
        when="NEW.status = 'POSTED' AND OLD.status <> 'POSTED'",
        body=f"SELECT RAISE(ABORT, '{_TOKEN_PERIOD}') WHERE {_NO_OPEN_PERIOD};",
    )

    # 2. Balance (D-017). DRAFT->POSTED only.
    drop_trigger(op, _TRG_BALANCED, _ENTRIES)
    create_pg_function(
        op,
        _FN_BALANCED,
        f"IF {_UNBALANCED} THEN RAISE EXCEPTION '{_TOKEN_UNBALANCED}'; END IF; RETURN NEW;",
    )
    create_pg_trigger(
        op,
        name=_TRG_BALANCED,
        table=_ENTRIES,
        event="UPDATE",
        function_name=_FN_BALANCED,
        when="NEW.status = 'POSTED' AND OLD.status <> 'POSTED'",
    )
    create_sqlite_trigger(
        op,
        name=_TRG_BALANCED,
        table=_ENTRIES,
        event="UPDATE",
        when="NEW.status = 'POSTED' AND OLD.status <> 'POSTED'",
        body=f"SELECT RAISE(ABORT, '{_TOKEN_UNBALANCED}') WHERE {_UNBALANCED};",
    )

    # 3. Header immutability (D-017). The ONLY permitted UPDATE of a POSTED header is
    # POSTED->REVERSED with reversed_by_entry_id set and no financial/identity column changed.
    drop_trigger(op, _TRG_HEADER_IMMUTABLE, _ENTRIES)
    drop_trigger(op, _TRG_HEADER_NO_DELETE, _ENTRIES)
    # Boolean expression that is TRUE when the UPDATE is the SANCTIONED reversal transition.
    sanctioned = (
        "NEW.status = 'REVERSED' AND NEW.reversed_by_entry_id IS NOT NULL "
        "AND NEW.posting_date = OLD.posting_date AND NEW.entry_number = OLD.entry_number "
        "AND NEW.currency_code = OLD.currency_code AND NEW.document_type = OLD.document_type "
        "AND NEW.fiscal_period_id = OLD.fiscal_period_id"
    )
    create_pg_function(
        op,
        _FN_HEADER_IMMUTABLE,
        f"IF NOT ({sanctioned}) THEN RAISE EXCEPTION '{_TOKEN_IMMUTABLE}'; END IF; RETURN NEW;",
    )
    create_pg_trigger(
        op,
        name=_TRG_HEADER_IMMUTABLE,
        table=_ENTRIES,
        event="UPDATE",
        function_name=_FN_HEADER_IMMUTABLE,
        when="OLD.status = 'POSTED'",
    )
    create_pg_function(
        op,
        _FN_HEADER_NO_DELETE,
        f"RAISE EXCEPTION '{_TOKEN_IMMUTABLE}'; RETURN OLD;",
    )
    create_pg_trigger(
        op,
        name=_TRG_HEADER_NO_DELETE,
        table=_ENTRIES,
        event="DELETE",
        function_name=_FN_HEADER_NO_DELETE,
        when="OLD.status IN ('POSTED', 'REVERSED')",
    )
    create_sqlite_trigger(
        op,
        name=_TRG_HEADER_IMMUTABLE,
        table=_ENTRIES,
        event="UPDATE",
        when="OLD.status = 'POSTED'",
        body=f"SELECT RAISE(ABORT, '{_TOKEN_IMMUTABLE}') WHERE NOT ({sanctioned});",
    )
    create_sqlite_trigger(
        op,
        name=_TRG_HEADER_NO_DELETE,
        table=_ENTRIES,
        event="DELETE",
        when="OLD.status IN ('POSTED', 'REVERSED')",
        body=f"SELECT RAISE(ABORT, '{_TOKEN_IMMUTABLE}');",
    )

    # 4. Line immutability (D-017). Key on OLD.is_posted = TRUE so the posting flush that flips
    # is_posted FALSE->TRUE is allowed, while a post-commit mutation/delete of a posted line is
    # rejected. (TRUE renders as TRUE on PG and 1 on SQLite — write the WHEN per dialect.)
    drop_trigger(op, _TRG_LINE_IMMUTABLE, _LINES)
    drop_trigger(op, _TRG_LINE_NO_DELETE, _LINES)
    create_pg_function(
        op, _FN_LINE_IMMUTABLE, f"RAISE EXCEPTION '{_TOKEN_IMMUTABLE}'; RETURN OLD;"
    )
    create_pg_trigger(
        op,
        name=_TRG_LINE_IMMUTABLE,
        table=_LINES,
        event="UPDATE",
        function_name=_FN_LINE_IMMUTABLE,
        when="OLD.is_posted = TRUE",
    )
    create_pg_trigger(
        op,
        name=_TRG_LINE_NO_DELETE,
        table=_LINES,
        event="DELETE",
        function_name=_FN_LINE_IMMUTABLE,
        when="OLD.is_posted = TRUE",
    )
    create_sqlite_trigger(
        op,
        name=_TRG_LINE_IMMUTABLE,
        table=_LINES,
        event="UPDATE",
        when="OLD.is_posted = 1",
        body=f"SELECT RAISE(ABORT, '{_TOKEN_IMMUTABLE}');",
    )
    create_sqlite_trigger(
        op,
        name=_TRG_LINE_NO_DELETE,
        table=_LINES,
        event="DELETE",
        when="OLD.is_posted = 1",
        body=f"SELECT RAISE(ABORT, '{_TOKEN_IMMUTABLE}');",
    )


def upgrade() -> None:
    _create_entries_table()
    _create_lines_table()
    _create_triggers()


def downgrade() -> None:
    drop_trigger(op, _TRG_LINE_NO_DELETE, _LINES)
    drop_trigger(op, _TRG_LINE_IMMUTABLE, _LINES)
    drop_trigger(op, _TRG_HEADER_NO_DELETE, _ENTRIES)
    drop_trigger(op, _TRG_HEADER_IMMUTABLE, _ENTRIES)
    drop_trigger(op, _TRG_BALANCED, _ENTRIES)
    drop_trigger(op, _TRG_PERIOD_UPDATE, _ENTRIES)
    drop_trigger(op, _TRG_PERIOD_INSERT, _ENTRIES)
    drop_function(op, _FN_LINE_IMMUTABLE)
    drop_function(op, _FN_HEADER_NO_DELETE)
    drop_function(op, _FN_HEADER_IMMUTABLE)
    drop_function(op, _FN_BALANCED)
    drop_function(op, _FN_PERIOD)

    op.drop_index("ix_fin_journal_lines_proj", table_name=_LINES)
    op.drop_index(op.f("ix_fin_journal_lines_tenant_id"), table_name=_LINES)
    op.drop_table(_LINES)
    op.drop_index("uq_fin_journal_entries_tenant_id_entry_number", table_name=_ENTRIES)
    op.drop_index(op.f("ix_fin_journal_entries_tenant_id"), table_name=_ENTRIES)
    op.drop_table(_ENTRIES)
