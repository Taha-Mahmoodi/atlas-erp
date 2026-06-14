"""projects (PS-lite): projects + a WBS-element tree as costing objects

Revision ID: 0041
Revises: 0040
Create Date: 2026-06-14

PLAN 11.1 — the deliberately small Project-System core (s4hana-parity §PS: projects + a WBS
hierarchy as costing objects, time and purchases postable to a WBS, a project cost report;
networks/scheduling, cost planning, budgeting with availability control, settlement, results
analysis / revenue recognition, customer-project billing out of scope). Creates TWO tables and
alters NOTHING — no trigger-bearing table is touched (D-022), so there is no trigger-recreation
concern. In particular it does NOT add a journal-line project dimension:
``fin_journal_lines.project_id`` already exists (the universal-journal WBS dimension since D-017 /
migration 0009), so "purchases postable to a WBS" is already real — a posting tags that opaque
column with the WBS-element id (D-056). All DDL is portable across SQLite and Postgres; every
identifier is <= 63 chars (PG cap). The MoneyType budget columns
render as NUMERIC(18,6) on Postgres / INTEGER micro-units on SQLite (D-015) via the imported column
type so the revision stays dialect-clean.

- ps_projects: the project master. UNIQUE(tenant_id, code) (the user-supplied master code);
  (tenant, status) filter index. customer_id / cost_center_id are OPAQUE sales / finance ids (D-029)
  — no cross-module FK. budget_amount is a simple budget figure (NOT budget control, D-056).
- ps_wbs_elements: the WBS-element tree — THE costing object. UNIQUE(tenant_id, project_id, code)
  (code unique WITHIN a project, not per tenant, D-056); composite tenant FK to ps_projects; a SELF
  composite tenant FK on parent_id (the WBS tree, cycle-guarded in the service); a (tenant,
  project_id, status) tree index + (tenant, parent_id) parent-walk index. budget_amount is the
  per-WBS budget.
"""

import sqlalchemy as sa
from alembic import op

from app.core.money import MoneyType

# revision identifiers, used by Alembic.
revision: str = "0041"
down_revision: str | None = "0040"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "ps_projects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="PLANNING"),
        sa.Column("customer_id", sa.Uuid(), nullable=True),
        sa.Column("cost_center_id", sa.Uuid(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("budget_amount", MoneyType(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["adm_tenants.id"], name="fk_ps_projects_tenant_id_adm_tenants"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ps_projects"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_ps_projects_tenant_id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_ps_projects_tenant_id_code"),
    )
    op.create_index("ix_ps_projects_tenant_id", "ps_projects", ["tenant_id"])
    op.create_index("ix_ps_projects_tenant_id_status", "ps_projects", ["tenant_id", "status"])

    op.create_table(
        "ps_wbs_elements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="OPEN"),
        sa.Column("is_billable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("budget_amount", MoneyType(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["adm_tenants.id"], name="fk_ps_wbs_elements_tenant_id_adm_tenants"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "project_id"],
            ["ps_projects.tenant_id", "ps_projects.id"],
            name="fk_ps_wbs_elements_project_id_ps_projects",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "parent_id"],
            ["ps_wbs_elements.tenant_id", "ps_wbs_elements.id"],
            name="fk_ps_wbs_elements_parent_id_ps_wbs_elements",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ps_wbs_elements"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_ps_wbs_elements_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id", "project_id", "code", name="uq_ps_wbs_elements_tenant_project_code"
        ),
    )
    op.create_index("ix_ps_wbs_elements_tenant_id", "ps_wbs_elements", ["tenant_id"])
    op.create_index(
        "ix_ps_wbs_elements_tenant_id_project_id_status",
        "ps_wbs_elements",
        ["tenant_id", "project_id", "status"],
    )
    op.create_index(
        "ix_ps_wbs_elements_tenant_id_parent_id",
        "ps_wbs_elements",
        ["tenant_id", "parent_id"],
    )


def downgrade() -> None:
    op.drop_table("ps_wbs_elements")
    op.drop_table("ps_projects")
