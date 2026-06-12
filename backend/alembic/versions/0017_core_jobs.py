"""core background jobs

Revision ID: 0017
Revises: 0016
Create Date: 2026-06-12

PLAN 4P.5 / PERFORMANCE §3 (closes #26) — core_jobs: one row per background-job execution
(job_type from the code-defined registry, status PENDING|RUNNING|COMPLETED|FAILED, JSON
payload/result, error text, submitted_by attribution, started/finished timing). The runner and
polling endpoints live in app/core/jobs.py + jobs_router.py.

- ``submitted_by_user_id`` is attribution metadata like core_audit_log.actor_user_id: a plain
  nullable Uuid, deliberately NO FK (so no FK-index obligation under PERFORMANCE §1).
- Indexes: the uniform standalone tenant_id index (D-007 invariant), plus the two composites
  the polling endpoints filter on — (tenant_id, status) and (tenant_id, job_type, created_at).
  Both lead with tenant_id and carry explicit names (the D-022 convention keys on column 0
  and would collide).
- NOT audited: high-churn request-control infrastructure (documented exclusion in
  core/jobs.py, same class as core_refresh_sessions / core_idempotency_keys).

Creates ONE table and alters nothing — no trigger-bearing table is touched, so there is no
trigger-recreation concern (D-022). All DDL is portable across SQLite and Postgres.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | None = None
depends_on: str | None = None

# Portable JSON: JSONB on Postgres, plain JSON elsewhere (mirrors core/models.JSON_VARIANT).
_JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "core_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("job_type", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("payload", _JSON, nullable=False),
        sa.Column("result", _JSON, nullable=True),
        sa.Column("error", sa.String(length=2000), nullable=True),
        sa.Column("submitted_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["adm_tenants.id"],
            name=op.f("fk_core_jobs_tenant_id_adm_tenants"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_core_jobs")),
    )
    op.create_index(op.f("ix_core_jobs_tenant_id"), "core_jobs", ["tenant_id"])
    op.create_index("ix_core_jobs_tenant_id_status", "core_jobs", ["tenant_id", "status"])
    op.create_index(
        "ix_core_jobs_tenant_id_job_type_created_at",
        "core_jobs",
        ["tenant_id", "job_type", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_core_jobs_tenant_id_job_type_created_at", table_name="core_jobs")
    op.drop_index("ix_core_jobs_tenant_id_status", table_name="core_jobs")
    op.drop_index(op.f("ix_core_jobs_tenant_id"), table_name="core_jobs")
    op.drop_table("core_jobs")
