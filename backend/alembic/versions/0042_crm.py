"""crm (CRM-lite): leads → opportunities kanban + activities + convert-to-customer+quote

Revision ID: 0042
Revises: 0041
Create Date: 2026-06-14

PLAN 12.1 — the deliberately small CRM core (s4hana-parity §CRM/Sales-pipeline scope: leads →
opportunities kanban, activities against leads/opportunities, convert a won opportunity to a
customer +
quote; campaigns / marketing automation / contact-account hierarchies / forecasting analytics /
service
tickets / opportunity teams out of scope). Creates FOUR tables and alters NOTHING pre-existing — no
trigger-bearing table is touched (D-022), so there is no trigger-recreation concern. All DDL is
portable across SQLite and Postgres; every identifier is <= 63 chars (PG cap). The MoneyType /
QuantityType columns render as NUMERIC(18,6) on Postgres / INTEGER micro-units on SQLite (D-015) via
the
imported column types so the revision stays dialect-clean.

- crm_leads: the lead master. UNIQUE(tenant_id, lead_number) (the auto LEAD- number); (tenant,
status)
  filter index. owner_employee_id is an OPAQUE hr id (D-029) — no cross-module FK.
  converted_opportunity_id
  is the intra-module link to the opportunity a lead became (a composite tenant FK added AFTER
  crm_opportunities exists — the two tables reference each other, so the cross-FK is added last in a
  batch_alter_table to avoid an ordering deadlock; SQLite needs batch mode to add an FK).
- crm_opportunities: the pipeline deal. DocumentMixin (document_id UNIQUE → core_documents, so the
  convert handler can write the opportunity → quote docflow edge). UNIQUE(tenant_id,
  opportunity_number)
  (the auto OPP- number); composite tenant FK source_lead_id → crm_leads; (tenant, stage) kanban
  index +
  (tenant, owner_employee_id) "my pipeline" index. customer_id / converted_customer_id /
  converted_quote_id
  are OPAQUE ids (D-029) — no cross-module FK.
- crm_opportunity_lines: the expected products (optional). UNIQUE(tenant_id, opportunity_id,
line_number);
  composite tenant FK opportunity_id → crm_opportunities; CHECK quantity > 0 + estimated_unit_price
  >= 0;
  (tenant, opportunity_id) index. item_id is an OPAQUE inventory id (D-029).
- crm_activities: the logged interactions. composite tenant FKs lead_id → crm_leads + opportunity_id
→
  crm_opportunities (both nullable); the ck_crm_activities_one_parent CHECK enforces
  EXACTLY-ONE-PARENT
  (lead_id XOR opportunity_id); (tenant, lead_id)/(tenant, opportunity_id)/(tenant, status) indexes.
  owner_employee_id is an OPAQUE hr id (D-029).
"""

import sqlalchemy as sa
from alembic import op

from app.core.money import MoneyType, QuantityType

# revision identifiers, used by Alembic.
revision: str = "0042"
down_revision: str | None = "0041"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # crm_leads FIRST, WITHOUT the converted_opportunity_id composite FK (crm_opportunities does not
    # exist yet — the two tables reference each other; the cross-FK is added in a batch_alter_table
    # at
    # the end).
    op.create_table(
        "crm_leads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("lead_number", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="NEW"),
        sa.Column("company_name", sa.String(length=200), nullable=False),
        sa.Column("contact_name", sa.String(length=200), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("phone", sa.String(length=40), nullable=True),
        sa.Column("source", sa.String(length=60), nullable=True),
        sa.Column("estimated_value", MoneyType(), nullable=True),
        sa.Column("currency_code", sa.String(length=3), nullable=True),
        sa.Column("owner_employee_id", sa.Uuid(), nullable=True),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        sa.Column("converted_opportunity_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["adm_tenants.id"], name="fk_crm_leads_tenant_id_adm_tenants"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_crm_leads"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_crm_leads_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id", "lead_number", name="uq_crm_leads_tenant_id_lead_number"
        ),
    )
    op.create_index("ix_crm_leads_tenant_id", "crm_leads", ["tenant_id"])
    op.create_index("ix_crm_leads_tenant_id_status", "crm_leads", ["tenant_id", "status"])

    op.create_table(
        "crm_opportunities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_number", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("stage", sa.String(length=20), nullable=False, server_default="PROSPECTING"),
        sa.Column("source_lead_id", sa.Uuid(), nullable=True),
        sa.Column("customer_id", sa.Uuid(), nullable=True),
        sa.Column("company_name", sa.String(length=200), nullable=False),
        sa.Column("contact_name", sa.String(length=200), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("estimated_value", MoneyType(), nullable=False, server_default="0"),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("probability_percent", MoneyType(), nullable=True),
        sa.Column("expected_close_date", sa.Date(), nullable=True),
        sa.Column("owner_employee_id", sa.Uuid(), nullable=True),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        sa.Column("converted_customer_id", sa.Uuid(), nullable=True),
        sa.Column("converted_quote_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["adm_tenants.id"], name="fk_crm_opportunities_tenant_id_adm_tenants"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["core_documents.tenant_id", "core_documents.id"],
            name="fk_crm_opportunities_tenant_id_core_documents",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "source_lead_id"],
            ["crm_leads.tenant_id", "crm_leads.id"],
            name="fk_crm_opportunities_tenant_id_crm_leads",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_crm_opportunities"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_crm_opportunities_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "opportunity_number",
            name="uq_crm_opportunities_tenant_id_opportunity_number",
        ),
        sa.UniqueConstraint("document_id", name="uq_crm_opportunities_document_id"),
    )
    op.create_index("ix_crm_opportunities_tenant_id", "crm_opportunities", ["tenant_id"])
    op.create_index(
        "ix_crm_opportunities_tenant_id_stage", "crm_opportunities", ["tenant_id", "stage"]
    )
    op.create_index(
        "ix_crm_opportunities_tenant_id_owner_employee_id",
        "crm_opportunities",
        ["tenant_id", "owner_employee_id"],
    )

    op.create_table(
        "crm_opportunity_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("quantity", QuantityType(), nullable=False),
        sa.Column("estimated_unit_price", MoneyType(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "quantity > 0", name="ck_crm_opportunity_lines_quantity_positive"
        ),
        sa.CheckConstraint(
            "estimated_unit_price >= 0",
            name="ck_crm_opportunity_lines_estimated_unit_price_non_negative",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["adm_tenants.id"],
            name="fk_crm_opportunity_lines_tenant_id_adm_tenants",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "opportunity_id"],
            ["crm_opportunities.tenant_id", "crm_opportunities.id"],
            name="fk_crm_opportunity_lines_tenant_id_crm_opportunities",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_crm_opportunity_lines"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_crm_opportunity_lines_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "opportunity_id",
            "line_number",
            name="uq_crm_opportunity_lines_tenant_opportunity_line",
        ),
    )
    op.create_index(
        "ix_crm_opportunity_lines_tenant_id", "crm_opportunity_lines", ["tenant_id"]
    )
    op.create_index(
        "ix_crm_opportunity_lines_tenant_id_opportunity_id",
        "crm_opportunity_lines",
        ["tenant_id", "opportunity_id"],
    )

    op.create_table(
        "crm_activities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("activity_type", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="OPEN"),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("completed_date", sa.Date(), nullable=True),
        sa.Column("lead_id", sa.Uuid(), nullable=True),
        sa.Column("opportunity_id", sa.Uuid(), nullable=True),
        sa.Column("owner_employee_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "(lead_id IS NOT NULL AND opportunity_id IS NULL) "
            "OR (lead_id IS NULL AND opportunity_id IS NOT NULL)",
            name="ck_crm_activities_one_parent",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["adm_tenants.id"], name="fk_crm_activities_tenant_id_adm_tenants"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "lead_id"],
            ["crm_leads.tenant_id", "crm_leads.id"],
            name="fk_crm_activities_tenant_id_crm_leads",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "opportunity_id"],
            ["crm_opportunities.tenant_id", "crm_opportunities.id"],
            name="fk_crm_activities_tenant_id_crm_opportunities",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_crm_activities"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_crm_activities_tenant_id"),
    )
    op.create_index("ix_crm_activities_tenant_id", "crm_activities", ["tenant_id"])
    op.create_index(
        "ix_crm_activities_tenant_id_lead_id", "crm_activities", ["tenant_id", "lead_id"]
    )
    op.create_index(
        "ix_crm_activities_tenant_id_opportunity_id",
        "crm_activities",
        ["tenant_id", "opportunity_id"],
    )
    op.create_index(
        "ix_crm_activities_tenant_id_status", "crm_activities", ["tenant_id", "status"]
    )

    # The lead → opportunity cross-FK, added last (crm_opportunities now exists). batch_alter_table
    # is
    # a pass-through on Postgres and a copy-rebuild on SQLite (which cannot ADD an FK in place); the
    # constraint name matches the convention (column_0 = tenant_id, referred table =
    # crm_opportunities).
    with op.batch_alter_table("crm_leads", schema=None) as batch_op:
        batch_op.create_foreign_key(
            "fk_crm_leads_tenant_id_crm_opportunities",
            "crm_opportunities",
            ["tenant_id", "converted_opportunity_id"],
            ["tenant_id", "id"],
        )


def downgrade() -> None:
    # Drop the cross-FK first (in batch — SQLite rebuilds the table), then the tables in
    # reverse-dependency order.
    with op.batch_alter_table("crm_leads", schema=None) as batch_op:
        batch_op.drop_constraint(
            "fk_crm_leads_tenant_id_crm_opportunities", type_="foreignkey"
        )
    op.drop_table("crm_activities")
    op.drop_table("crm_opportunity_lines")
    op.drop_table("crm_opportunities")
    op.drop_table("crm_leads")
