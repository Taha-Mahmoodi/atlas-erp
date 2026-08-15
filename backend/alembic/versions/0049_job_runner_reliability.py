"""job runner reliability

Revision ID: 0049
Revises: 0048
Create Date: 2026-08-15

P0 (docs/research/p0-job-runner-reliability-plan.md) — the schema the stale-job sweeper needs.

- ``fin_bank_statements``: a PARTIAL UNIQUE index on (tenant_id, import_job_id) — the DB backstop
  under the service-level import guard, so a re-dispatched statement import can never leave a
  duplicate even if two runners race. Partial because inline imports carry no job id and a tenant
  may have many of those; both dialect ``where`` kwargs are required (the D-012 doc_number
  precedent).

All DDL is portable across SQLite and Postgres and every identifier is <= 63 chars (PG cap). No
trigger-bearing table is altered (D-022), so there is no trigger-recreation concern.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0049"
down_revision: str | None = "0048"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_index(
        "uq_fin_bank_statements_tenant_id_import_job_id",
        "fin_bank_statements",
        ["tenant_id", "import_job_id"],
        unique=True,
        postgresql_where=sa.text("import_job_id IS NOT NULL"),
        sqlite_where=sa.text("import_job_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_fin_bank_statements_tenant_id_import_job_id", table_name="fin_bank_statements"
    )
