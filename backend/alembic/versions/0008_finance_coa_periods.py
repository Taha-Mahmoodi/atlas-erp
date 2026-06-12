"""finance chart of accounts + fiscal years/periods

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-12

PLAN 4.1 / D-021 + D-018 — the finance schema foundation:

- fin_account_groups: the COA presentation hierarchy (D-021). Self-referential composite
  tenant FK on parent_id so a group's parent is always same-tenant; UNIQUE(tenant_id, code)
  + UNIQUE(tenant_id, id) for composite tenant FKs.
- fin_accounts: GL accounts (D-021). account_type drives every statement projection;
  normal_balance is stored (derivable from type) for query simplicity; only is_postable
  (leaf) accounts accept journal lines (4.2). Composite tenant FK to fin_account_groups;
  UNIQUE(tenant_id, code) + UNIQUE(tenant_id, id).
- fin_fiscal_years: a year with a CLOSED-after-all-periods status (D-018). CHECK
  start_date <= end_date; UNIQUE(tenant_id, code) + UNIQUE(tenant_id, id).
- fin_fiscal_periods: posting periods (D-018). Composite tenant FK to fin_fiscal_years;
  UNIQUE(tenant_id, fiscal_year_id, period_number); CHECK start_date <= end_date; plus the
  (tenant_id, start_date, end_date) index for the date->period lookup the journal uses on
  every posting (4.2).

NO TRIGGERS here: the D-018 period-posting-rejection trigger fires on fin_journal_entries,
which does not exist until 4.2 — so there is no trigger-recreation-after-batch concern in
this revision (D-022). Constraint/index names follow the D-022 naming convention so SQLite
batch mode can drop them later; DDL is portable across SQLite and Postgres.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "fin_account_groups",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["adm_tenants.id"],
            name=op.f("fk_fin_account_groups_tenant_id_adm_tenants"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "parent_id"],
            ["fin_account_groups.tenant_id", "fin_account_groups.id"],
            name=op.f("fk_fin_account_groups_parent_id_fin_account_groups"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fin_account_groups")),
        sa.UniqueConstraint("tenant_id", "code", name="uq_fin_account_groups_tenant_id_code"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_fin_account_groups_tenant_id"),
    )
    op.create_index(
        op.f("ix_fin_account_groups_tenant_id"), "fin_account_groups", ["tenant_id"]
    )

    op.create_table(
        "fin_accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("account_type", sa.String(length=20), nullable=False),
        sa.Column("normal_balance", sa.String(length=10), nullable=False),
        sa.Column("is_postable", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("cash_flow_category", sa.String(length=20), nullable=True),
        sa.Column(
            "is_cash_equivalent", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Column("account_group_id", sa.Uuid(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["adm_tenants.id"],
            name=op.f("fk_fin_accounts_tenant_id_adm_tenants"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "account_group_id"],
            ["fin_account_groups.tenant_id", "fin_account_groups.id"],
            name=op.f("fk_fin_accounts_account_group_id_fin_account_groups"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fin_accounts")),
        sa.UniqueConstraint("tenant_id", "code", name="uq_fin_accounts_tenant_id_code"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_fin_accounts_tenant_id"),
    )
    op.create_index(op.f("ix_fin_accounts_tenant_id"), "fin_accounts", ["tenant_id"])

    op.create_table(
        "fin_fiscal_years",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=10), server_default="OPEN", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("start_date <= end_date", name="ck_fin_fiscal_years_date_order"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["adm_tenants.id"],
            name=op.f("fk_fin_fiscal_years_tenant_id_adm_tenants"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fin_fiscal_years")),
        sa.UniqueConstraint("tenant_id", "code", name="uq_fin_fiscal_years_tenant_id_code"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_fin_fiscal_years_tenant_id"),
    )
    op.create_index(
        op.f("ix_fin_fiscal_years_tenant_id"), "fin_fiscal_years", ["tenant_id"]
    )

    op.create_table(
        "fin_fiscal_periods",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("fiscal_year_id", sa.Uuid(), nullable=False),
        sa.Column("period_number", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=40), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=10), server_default="OPEN", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "start_date <= end_date", name="ck_fin_fiscal_periods_date_order"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["adm_tenants.id"],
            name=op.f("fk_fin_fiscal_periods_tenant_id_adm_tenants"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "fiscal_year_id"],
            ["fin_fiscal_years.tenant_id", "fin_fiscal_years.id"],
            name=op.f("fk_fin_fiscal_periods_fiscal_year_id_fin_fiscal_years"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fin_fiscal_periods")),
        sa.UniqueConstraint(
            "tenant_id",
            "fiscal_year_id",
            "period_number",
            name="uq_fin_fiscal_periods_tenant_id_fiscal_year_id_period_number",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_fin_fiscal_periods_tenant_id"),
    )
    op.create_index(
        op.f("ix_fin_fiscal_periods_tenant_id"), "fin_fiscal_periods", ["tenant_id"]
    )
    # Date -> period lookup the journal uses on every posting (4.2): "the period covering
    # posting_date" filters on (tenant_id, start_date, end_date).
    op.create_index(
        "ix_fin_fiscal_periods_tenant_id_start_date_end_date",
        "fin_fiscal_periods",
        ["tenant_id", "start_date", "end_date"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_fin_fiscal_periods_tenant_id_start_date_end_date",
        table_name="fin_fiscal_periods",
    )
    op.drop_index(
        op.f("ix_fin_fiscal_periods_tenant_id"), table_name="fin_fiscal_periods"
    )
    op.drop_table("fin_fiscal_periods")
    op.drop_index(op.f("ix_fin_fiscal_years_tenant_id"), table_name="fin_fiscal_years")
    op.drop_table("fin_fiscal_years")
    op.drop_index(op.f("ix_fin_accounts_tenant_id"), table_name="fin_accounts")
    op.drop_table("fin_accounts")
    op.drop_index(
        op.f("ix_fin_account_groups_tenant_id"), table_name="fin_account_groups"
    )
    op.drop_table("fin_account_groups")
