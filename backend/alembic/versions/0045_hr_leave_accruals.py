"""hr leave accrual applied-periods guard table + backfill

Revision ID: 0045
Revises: 0044
Create Date: 2026-08-13

Fixes #160 (DB half) — the accrual idempotency guard was the single
``hr_leave_balances.last_accrual_period`` column, which forgot older periods: running period N,
then N+1, then N again re-granted N (QA reproduced a live double-grant). The guard is now the
``hr_leave_accruals`` table — one row per APPLIED (balance, period) — so the run can skip ANY
previously applied period, and UNIQUE(tenant, balance_id, period) backstops a concurrent
same-period double-grant at the DB (D-063).

BACKFILL: each existing balance's ``last_accrual_period`` becomes its first applied-period row
(client-generated uuid4 ids, the D-022-portable pattern: typed Core select + insert so uuid values
round-trip on both engines), so a post-upgrade re-run of that period stays idempotent on existing
data. The column itself is kept, informational only (the API read surface is unchanged).

TRIGGER SAFETY (D-022): pure CREATE TABLE + data insert — no trigger-bearing table is altered. All
DDL is portable across SQLite and Postgres; every identifier is <= 63 chars (PG cap).
"""

import uuid

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0045"
down_revision: str | None = "0044"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "hr_leave_accruals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("balance_id", sa.Uuid(), nullable=False),
        sa.Column("period", sa.String(length=7), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["adm_tenants.id"], name="fk_hr_leave_accruals_tenant_id_adm_tenants"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "balance_id"],
            ["hr_leave_balances.tenant_id", "hr_leave_balances.id"],
            name="fk_hr_leave_accruals_tenant_id_hr_leave_balances",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_hr_leave_accruals"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_hr_leave_accruals_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "balance_id",
            "period",
            name="uq_hr_leave_accruals_tenant_balance_period",
        ),
    )
    op.create_index("ix_hr_leave_accruals_tenant_id", "hr_leave_accruals", ["tenant_id"])
    op.create_index(
        "ix_hr_leave_accruals_tenant_id_period", "hr_leave_accruals", ["tenant_id", "period"]
    )

    # Backfill: promote each balance's single remembered period to a guard row.
    balances = sa.table(
        "hr_leave_balances",
        sa.column("id", sa.Uuid()),
        sa.column("tenant_id", sa.Uuid()),
        sa.column("last_accrual_period", sa.String(length=7)),
    )
    accruals = sa.table(
        "hr_leave_accruals",
        sa.column("id", sa.Uuid()),
        sa.column("tenant_id", sa.Uuid()),
        sa.column("balance_id", sa.Uuid()),
        sa.column("period", sa.String(length=7)),
    )
    bind = op.get_bind()
    rows = bind.execute(
        sa.select(balances.c.id, balances.c.tenant_id, balances.c.last_accrual_period).where(
            balances.c.last_accrual_period.is_not(None)
        )
    ).all()
    if rows:
        bind.execute(
            sa.insert(accruals),
            [
                {
                    "id": uuid.uuid4(),
                    "tenant_id": tenant_id,
                    "balance_id": balance_id,
                    "period": period,
                }
                for balance_id, tenant_id, period in rows
            ],
        )


def downgrade() -> None:
    op.drop_table("hr_leave_accruals")
