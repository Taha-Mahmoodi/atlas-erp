"""finance controlling: cost centres, profit centres, allocation rules + runs

Revision ID: 0014
Revises: 0013
Create Date: 2026-06-12

PLAN 4.7 / D-021 — Controlling (CO) is a PROJECTION of the universal journal: cost/profit centres
are journal-line dimensions (``fin_journal_lines.cost_center_id`` / ``profit_center_id``, opaque
``sa.Uuid`` with NO FK — D-022 keeps the trigger-bearing journal-lines table FK-free), and an
allocation is one more balanced journal entry. This migration creates FIVE master/bookkeeping tables
and alters NOTHING — fin_journal_lines/entries are untouched, so there is no trigger-recreation
concern (D-022).

- fin_profit_centers: self-referential hierarchy (parent_id), UNIQUE(tenant, code).
- fin_cost_centers: self-referential hierarchy; ``default_profit_center_id`` composite tenant FK
  to fin_profit_centers; UNIQUE(tenant, code).
- fin_allocation_rules: ``source_cost_center_id`` composite tenant FK; ``basis``
  PERCENT|FIXED_WEIGHT; UNIQUE(tenant, code).
- fin_allocation_rule_targets: (rule, target cost centre, weight); UNIQUE(tenant, rule, target).
- fin_allocation_runs: DocumentMixin (document_id -> core_documents); composite tenant FKs to the
  rule, the fiscal period and the journal entry; ``run_number`` NULL until posting.

All DDL is portable across SQLite and Postgres. Composite-tenant FK names follow the D-022 column-0
convention (``fk_<table>_tenant_id_<target>``), with abbreviated explicit names where the auto name
would exceed PG's 63-char identifier cap (allocation_rule_targets) — matching the models keeps
autogenerate drift-free.
"""

import sqlalchemy as sa
from alembic import op

from app.core.money import MoneyType

# revision identifiers, used by Alembic.
revision: str = "0014"
down_revision: str | None = "0013"
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


def _create_profit_centers() -> None:
    op.create_table(
        "fin_profit_centers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["adm_tenants.id"],
            name="fk_fin_profit_centers_tenant_id_adm_tenants",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "parent_id"],
            ["fin_profit_centers.tenant_id", "fin_profit_centers.id"],
            name="fk_fin_profit_centers_tenant_id_fin_profit_centers",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_fin_profit_centers"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_fin_profit_centers_tenant_id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_fin_profit_centers_tenant_id_code"),
    )
    op.create_index("ix_fin_profit_centers_tenant_id", "fin_profit_centers", ["tenant_id"])


def _create_cost_centers() -> None:
    op.create_table(
        "fin_cost_centers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("manager_name", sa.String(length=200), nullable=True),
        sa.Column("default_profit_center_id", sa.Uuid(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["adm_tenants.id"],
            name="fk_fin_cost_centers_tenant_id_adm_tenants",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "parent_id"],
            ["fin_cost_centers.tenant_id", "fin_cost_centers.id"],
            name="fk_fin_cost_centers_tenant_id_fin_cost_centers",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "default_profit_center_id"],
            ["fin_profit_centers.tenant_id", "fin_profit_centers.id"],
            name="fk_fin_cost_centers_tenant_id_fin_profit_centers",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_fin_cost_centers"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_fin_cost_centers_tenant_id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_fin_cost_centers_tenant_id_code"),
    )
    op.create_index("ix_fin_cost_centers_tenant_id", "fin_cost_centers", ["tenant_id"])


def _create_allocation_rules() -> None:
    op.create_table(
        "fin_allocation_rules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("source_cost_center_id", sa.Uuid(), nullable=False),
        sa.Column("basis", sa.String(length=20), server_default="PERCENT", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["adm_tenants.id"],
            name="fk_fin_allocation_rules_tenant_id_adm_tenants",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "source_cost_center_id"],
            ["fin_cost_centers.tenant_id", "fin_cost_centers.id"],
            name="fk_fin_allocation_rules_tenant_id_fin_cost_centers",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_fin_allocation_rules"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_fin_allocation_rules_tenant_id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_fin_allocation_rules_tenant_id_code"),
    )
    op.create_index("ix_fin_allocation_rules_tenant_id", "fin_allocation_rules", ["tenant_id"])


def _create_allocation_rule_targets() -> None:
    op.create_table(
        "fin_allocation_rule_targets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("allocation_rule_id", sa.Uuid(), nullable=False),
        sa.Column("target_cost_center_id", sa.Uuid(), nullable=False),
        sa.Column("weight", MoneyType(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["adm_tenants.id"],
            name="fk_fin_allocation_rule_targets_tenant_id_adm_tenants",
        ),
        # Abbreviated explicit names: the D-022 auto name for these composite FKs / the unique would
        # exceed PG's 63-char identifier cap, so the model + this migration share the short name.
        sa.ForeignKeyConstraint(
            ["tenant_id", "allocation_rule_id"],
            ["fin_allocation_rules.tenant_id", "fin_allocation_rules.id"],
            name="fk_fin_alloc_rule_targets_tenant_id_rules",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "target_cost_center_id"],
            ["fin_cost_centers.tenant_id", "fin_cost_centers.id"],
            name="fk_fin_alloc_rule_targets_tenant_id_cost_centers",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_fin_allocation_rule_targets"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_fin_allocation_rule_targets_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id", "allocation_rule_id", "target_cost_center_id",
            name="uq_fin_alloc_rule_targets_rule_target",
        ),
    )
    op.create_index(
        "ix_fin_allocation_rule_targets_tenant_id", "fin_allocation_rule_targets", ["tenant_id"]
    )


def _create_allocation_runs() -> None:
    op.create_table(
        "fin_allocation_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("allocation_rule_id", sa.Uuid(), nullable=False),
        sa.Column("fiscal_period_id", sa.Uuid(), nullable=False),
        sa.Column("run_number", sa.String(length=60), nullable=True),
        sa.Column("run_date", sa.Date(), nullable=False),
        sa.Column("allocated_amount", MoneyType(), server_default="0", nullable=False),
        sa.Column("journal_entry_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=12), server_default="POSTED", nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["adm_tenants.id"],
            name="fk_fin_allocation_runs_tenant_id_adm_tenants",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["core_documents.tenant_id", "core_documents.id"],
            name="fk_fin_allocation_runs_tenant_id_core_documents",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "allocation_rule_id"],
            ["fin_allocation_rules.tenant_id", "fin_allocation_rules.id"],
            name="fk_fin_allocation_runs_tenant_id_fin_allocation_rules",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "fiscal_period_id"],
            ["fin_fiscal_periods.tenant_id", "fin_fiscal_periods.id"],
            name="fk_fin_allocation_runs_tenant_id_fin_fiscal_periods",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "journal_entry_id"],
            ["fin_journal_entries.tenant_id", "fin_journal_entries.id"],
            name="fk_fin_allocation_runs_tenant_id_fin_journal_entries",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_fin_allocation_runs"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_fin_allocation_runs_tenant_id"),
        sa.UniqueConstraint("document_id", name="uq_fin_allocation_runs_document_id"),
    )
    op.create_index("ix_fin_allocation_runs_tenant_id", "fin_allocation_runs", ["tenant_id"])


def upgrade() -> None:
    _create_profit_centers()
    _create_cost_centers()
    _create_allocation_rules()
    _create_allocation_rule_targets()
    _create_allocation_runs()


def downgrade() -> None:
    op.drop_index("ix_fin_allocation_runs_tenant_id", table_name="fin_allocation_runs")
    op.drop_table("fin_allocation_runs")
    op.drop_index(
        "ix_fin_allocation_rule_targets_tenant_id", table_name="fin_allocation_rule_targets"
    )
    op.drop_table("fin_allocation_rule_targets")
    op.drop_index("ix_fin_allocation_rules_tenant_id", table_name="fin_allocation_rules")
    op.drop_table("fin_allocation_rules")
    op.drop_index("ix_fin_cost_centers_tenant_id", table_name="fin_cost_centers")
    op.drop_table("fin_cost_centers")
    op.drop_index("ix_fin_profit_centers_tenant_id", table_name="fin_profit_centers")
    op.drop_table("fin_profit_centers")
