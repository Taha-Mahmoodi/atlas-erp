"""job runner reliability

Revision ID: 0049
Revises: 0048
Create Date: 2026-08-15

P0 (docs/research/p0-job-runner-reliability-plan.md) — the schema the stale-job sweeper needs.

- ``core_jobs.attempts``: how many times the sweeper has re-dispatched a job. NOT NULL DEFAULT 0,
  so existing rows backfill to "never reclaimed" without a data migration. The ceiling built on it
  is what turns "reclaim forever" into "abandon visibly".
- ``ix_core_jobs_status_updated_at_unfinished``: the sweep's covering index. The only index on
  this table that does NOT lead with tenant_id — the scan crosses tenants by definition — and
  PARTIAL on the unfinished statuses, so it stays tiny however large the job history grows.
- ``fin_bank_statements``: a PARTIAL UNIQUE index on (tenant_id, import_job_id) — the DB backstop
  under the service-level import guard, so a re-dispatched statement import can never leave a
  duplicate even if two runners race. Partial because inline imports carry no job id and a tenant
  may have many of those.
- ``ix_core_idempotency_keys_created_at``: the retention purge scans by age.

Both dialect ``where`` kwargs are given on every partial index (the D-012 doc_number precedent);
all DDL is portable across SQLite and Postgres and every identifier is <= 63 chars (PG cap). No
trigger-bearing table is altered (D-022), so there is no trigger-recreation concern —
``core_jobs`` is explicitly not audited (core/jobs.py) and carries no trigger.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0049"
down_revision: str | None = "0048"
branch_labels: str | None = None
depends_on: str | None = None

_UNFINISHED = "status IN ('PENDING', 'RUNNING')"


def upgrade() -> None:
    op.add_column(
        "core_jobs",
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_index(
        "ix_core_jobs_status_updated_at_unfinished",
        "core_jobs",
        ["status", "updated_at"],
        postgresql_where=sa.text(_UNFINISHED),
        sqlite_where=sa.text(_UNFINISHED),
    )
    op.create_index(
        "uq_fin_bank_statements_tenant_id_import_job_id",
        "fin_bank_statements",
        ["tenant_id", "import_job_id"],
        unique=True,
        postgresql_where=sa.text("import_job_id IS NOT NULL"),
        sqlite_where=sa.text("import_job_id IS NOT NULL"),
    )
    op.create_index(
        "ix_core_idempotency_keys_created_at", "core_idempotency_keys", ["created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_core_idempotency_keys_created_at", table_name="core_idempotency_keys")
    op.drop_index(
        "uq_fin_bank_statements_tenant_id_import_job_id", table_name="fin_bank_statements"
    )
    op.drop_index("ix_core_jobs_status_updated_at_unfinished", table_name="core_jobs")
    op.drop_column("core_jobs", "attempts")
