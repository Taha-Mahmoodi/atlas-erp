"""finance asset accounting lite: assets, depreciation runs, depreciation entries

Revision ID: 0019
Revises: 0018
Create Date: 2026-06-12

PLAN 4.10 — asset accounting lite:

- fin_assets: the asset register. DocumentMixin (registered at creation, doc_number NULL);
  the gapless AST number is claimed at ACTIVATION, so ``asset_number`` is nullable with the
  partial unique index (both dialect WHEREs). Three composite tenant FKs to fin_accounts
  carry explicit names (the D-022 column-0 convention would collide three ways);
  ``cost_center_id`` stays an opaque dimension Uuid (journal-line precedent).
- fin_depreciation_runs: one run per execution (allocation-run pattern) — DocumentMixin,
  DEP number claimed at posting, link to the ONE grouped journal entry.
- fin_depreciation_entries: one asset's depreciation in one period.
  UNIQUE(tenant, asset, fiscal_period) is the idempotency backbone — an asset depreciates
  once per period, ever. Indexes: (tenant, run_id) for the run's entry list and
  (tenant, fiscal_period_id) for the register's as-of bound (PERFORMANCE §1).

Creates THREE tables and alters NOTHING — no trigger-bearing table is touched, so there is
no trigger-recreation concern (D-022). All DDL is portable across SQLite and Postgres;
every identifier is <= 63 chars (PG cap).
"""

import sqlalchemy as sa
from alembic import op

from app.core.money import MoneyType

# revision identifiers, used by Alembic.
revision: str = "0019"
down_revision: str | None = "0018"
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
        "fin_assets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("asset_number", sa.String(length=60), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("acquisition_date", sa.Date(), nullable=False),
        sa.Column("acquisition_cost", MoneyType(), nullable=False),
        sa.Column("salvage_value", MoneyType(), server_default="0", nullable=False),
        sa.Column("useful_life_months", sa.Integer(), nullable=False),
        sa.Column("depreciation_method", sa.String(length=20), nullable=False),
        sa.Column("declining_rate_percent", MoneyType(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="DRAFT", nullable=False),
        sa.Column("asset_account_id", sa.Uuid(), nullable=False),
        sa.Column("accumulated_depreciation_account_id", sa.Uuid(), nullable=False),
        sa.Column("depreciation_expense_account_id", sa.Uuid(), nullable=False),
        sa.Column("cost_center_id", sa.Uuid(), nullable=True),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("capitalized_journal_entry_id", sa.Uuid(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["adm_tenants.id"],
            name="fk_fin_assets_tenant_id_adm_tenants",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["core_documents.tenant_id", "core_documents.id"],
            name="fk_fin_assets_tenant_id_core_documents",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "asset_account_id"],
            ["fin_accounts.tenant_id", "fin_accounts.id"],
            name="fk_fin_assets_tenant_id_asset_account",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "accumulated_depreciation_account_id"],
            ["fin_accounts.tenant_id", "fin_accounts.id"],
            name="fk_fin_assets_tenant_id_accum_depr_account",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "depreciation_expense_account_id"],
            ["fin_accounts.tenant_id", "fin_accounts.id"],
            name="fk_fin_assets_tenant_id_depr_expense_account",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "capitalized_journal_entry_id"],
            ["fin_journal_entries.tenant_id", "fin_journal_entries.id"],
            name="fk_fin_assets_tenant_id_fin_journal_entries",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_fin_assets"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_fin_assets_tenant_id"),
        sa.UniqueConstraint("document_id", name="uq_fin_assets_document_id"),
    )
    op.create_index("ix_fin_assets_tenant_id", "fin_assets", ["tenant_id"])
    op.create_index("ix_fin_assets_tenant_id_status", "fin_assets", ["tenant_id", "status"])
    op.create_index(
        "uq_fin_assets_tenant_id_asset_number",
        "fin_assets",
        ["tenant_id", "asset_number"],
        unique=True,
        postgresql_where=sa.text("asset_number IS NOT NULL"),
        sqlite_where=sa.text("asset_number IS NOT NULL"),
    )

    op.create_table(
        "fin_depreciation_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("fiscal_period_id", sa.Uuid(), nullable=False),
        sa.Column("run_number", sa.String(length=60), nullable=True),
        sa.Column("run_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=12), server_default="POSTED", nullable=False),
        sa.Column("journal_entry_id", sa.Uuid(), nullable=True),
        sa.Column("total_amount", MoneyType(), server_default="0", nullable=False),
        sa.Column("asset_count", sa.Integer(), server_default="0", nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["adm_tenants.id"],
            name="fk_fin_depreciation_runs_tenant_id_adm_tenants",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["core_documents.tenant_id", "core_documents.id"],
            name="fk_fin_depreciation_runs_tenant_id_core_documents",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "fiscal_period_id"],
            ["fin_fiscal_periods.tenant_id", "fin_fiscal_periods.id"],
            name="fk_fin_depreciation_runs_tenant_id_fin_fiscal_periods",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "journal_entry_id"],
            ["fin_journal_entries.tenant_id", "fin_journal_entries.id"],
            name="fk_fin_depreciation_runs_tenant_id_fin_journal_entries",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_fin_depreciation_runs"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_fin_depreciation_runs_tenant_id"),
        sa.UniqueConstraint("document_id", name="uq_fin_depreciation_runs_document_id"),
    )
    op.create_index(
        "ix_fin_depreciation_runs_tenant_id", "fin_depreciation_runs", ["tenant_id"]
    )
    op.create_index(
        "ix_fin_depreciation_runs_tenant_id_fiscal_period_id",
        "fin_depreciation_runs",
        ["tenant_id", "fiscal_period_id"],
    )

    op.create_table(
        "fin_depreciation_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("fiscal_period_id", sa.Uuid(), nullable=False),
        sa.Column("amount", MoneyType(), nullable=False),
        sa.Column("accumulated_after", MoneyType(), nullable=False),
        sa.Column("nbv_after", MoneyType(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["adm_tenants.id"],
            name="fk_fin_depreciation_entries_tenant_id_adm_tenants",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["fin_depreciation_runs.tenant_id", "fin_depreciation_runs.id"],
            name="fk_fin_depreciation_entries_tenant_id_fin_depreciation_runs",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "asset_id"],
            ["fin_assets.tenant_id", "fin_assets.id"],
            name="fk_fin_depreciation_entries_tenant_id_fin_assets",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "fiscal_period_id"],
            ["fin_fiscal_periods.tenant_id", "fin_fiscal_periods.id"],
            name="fk_fin_depreciation_entries_tenant_id_fin_fiscal_periods",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_fin_depreciation_entries"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_fin_depreciation_entries_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "asset_id",
            "fiscal_period_id",
            name="uq_fin_depreciation_entries_asset_period",
        ),
    )
    op.create_index(
        "ix_fin_depreciation_entries_tenant_id", "fin_depreciation_entries", ["tenant_id"]
    )
    op.create_index(
        "ix_fin_depreciation_entries_tenant_id_run_id",
        "fin_depreciation_entries",
        ["tenant_id", "run_id"],
    )
    op.create_index(
        "ix_fin_depreciation_entries_tenant_id_fiscal_period_id",
        "fin_depreciation_entries",
        ["tenant_id", "fiscal_period_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_fin_depreciation_entries_tenant_id_fiscal_period_id",
        table_name="fin_depreciation_entries",
    )
    op.drop_index(
        "ix_fin_depreciation_entries_tenant_id_run_id", table_name="fin_depreciation_entries"
    )
    op.drop_index(
        "ix_fin_depreciation_entries_tenant_id", table_name="fin_depreciation_entries"
    )
    op.drop_table("fin_depreciation_entries")
    op.drop_index(
        "ix_fin_depreciation_runs_tenant_id_fiscal_period_id",
        table_name="fin_depreciation_runs",
    )
    op.drop_index("ix_fin_depreciation_runs_tenant_id", table_name="fin_depreciation_runs")
    op.drop_table("fin_depreciation_runs")
    op.drop_index("uq_fin_assets_tenant_id_asset_number", table_name="fin_assets")
    op.drop_index("ix_fin_assets_tenant_id_status", table_name="fin_assets")
    op.drop_index("ix_fin_assets_tenant_id", table_name="fin_assets")
    op.drop_table("fin_assets")
