"""finance statement-projection covering index

Revision ID: 0015
Revises: 0014
Create Date: 2026-06-12

PLAN 4.8 / D-021 — bring the statement-projection index on fin_journal_lines up to its covering
shape. Migration 0009 created the bare partial index ``ix_fin_journal_lines_proj`` ON
(tenant_id, account_id, posting_date) WHERE is_posted. This revision promotes it to a COVERING
index by adding ``INCLUDE (functional_debit_amount, functional_credit_amount)`` on Postgres, so the
single base aggregate every statement reads (``select(account_id, sum(functional_debit -
functional_credit)) WHERE tenant, is_posted, posting_date <= date GROUP BY account_id``) runs as an
index-only scan — sub-second to ~10M lines. The ``include`` kwarg is harmlessly ignored on SQLite,
which keeps the plain partial index.

Per D-021 the index carries BOTH dialect partial predicates: ``postgresql_where=text('is_posted')``
AND ``sqlite_where=text('is_posted')`` (each engine needs its own).

TRIGGER SAFETY (D-022, load-bearing): fin_journal_lines is trigger-bearing (the line-immutability
trigger ``trg_fin_journal_lines_immutable`` / ``_no_delete``, migration 0009). This migration uses
plain ``op.create_index`` / ``op.drop_index`` — a CREATE/DROP INDEX, NOT an ALTER TABLE that
rebuilds the table — so SQLite does NOT copy-rebuild the table and the triggers are NOT dropped. No
``batch_alter_table`` is used and so no trigger recreation is required. A pg-marked guard test
asserts the line-immutability trigger still fires after this migration (test_statements.py).
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | None = None
depends_on: str | None = None

_LINES = "fin_journal_lines"
_INDEX = "ix_fin_journal_lines_proj"
_COLUMNS = ["tenant_id", "account_id", "posting_date"]
_INCLUDE = ["functional_debit_amount", "functional_credit_amount"]


def upgrade() -> None:
    # Recreate the partial index in covering form. Plain DROP/CREATE INDEX — no table rebuild, so
    # the trigger-bearing table's immutability triggers survive untouched (D-022).
    op.drop_index(_INDEX, table_name=_LINES)
    op.create_index(
        _INDEX,
        _LINES,
        _COLUMNS,
        postgresql_where=sa.text("is_posted"),
        sqlite_where=sa.text("is_posted"),
        # Index-only scans for the statement aggregate on PG; ignored on SQLite.
        postgresql_include=_INCLUDE,
    )


def downgrade() -> None:
    # Restore the bare partial index (0009's form): drop the covering index, recreate without
    # INCLUDE. Same plain DROP/CREATE INDEX — triggers unaffected.
    op.drop_index(_INDEX, table_name=_LINES)
    op.create_index(
        _INDEX,
        _LINES,
        _COLUMNS,
        postgresql_where=sa.text("is_posted"),
        sqlite_where=sa.text("is_posted"),
    )
