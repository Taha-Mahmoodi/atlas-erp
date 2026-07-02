"""procurement vendor master

Revision ID: 0024
Revises: 0023
Create Date: 2026-06-13

PLAN 6.1 — opens the procurement module with the vendor master. Creates TWO tables and alters
NOTHING — no trigger-bearing table is touched (D-022), so there is no trigger-recreation concern.
All DDL is portable across SQLite and Postgres; every identifier is <= 63 chars (PG cap).

- proc_vendors: the vendor master. UNIQUE(tenant_id, vendor_code) (user-supplied code, no
  auto-number); CHECK payment_terms_days >= 0; (tenant, status) index for the filtered vendor list.
  The row id IS finance AP's opaque partner_id (D-029) — finance never FK-references this table.
- proc_vendor_approved_items: the v1 info-record-lite (vendor↔item link). Composite tenant FK to
  proc_vendors; item_id is an OPAQUE inventory item id (D-029 — a plain Uuid column, NO cross-module
  FK to inv_items); UNIQUE(tenant, vendor, item); (tenant, vendor) index for the nested list.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0024"
down_revision: str | None = "0023"
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
        "proc_vendors",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("vendor_code", sa.String(length=60), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ACTIVE"),
        sa.Column("default_currency_code", sa.String(length=3), nullable=False),
        sa.Column("payment_terms_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("tax_reference", sa.String(length=60), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("phone", sa.String(length=40), nullable=True),
        sa.Column("address", sa.String(length=500), nullable=True),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "payment_terms_days >= 0",
            name="ck_proc_vendors_payment_terms_days_non_negative",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["adm_tenants.id"], name="fk_proc_vendors_tenant_id_adm_tenants"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_proc_vendors"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_proc_vendors_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id", "vendor_code", name="uq_proc_vendors_tenant_id_vendor_code"
        ),
    )
    op.create_index("ix_proc_vendors_tenant_id", "proc_vendors", ["tenant_id"])
    op.create_index(
        "ix_proc_vendors_tenant_id_status", "proc_vendors", ["tenant_id", "status"]
    )

    op.create_table(
        "proc_vendor_approved_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("vendor_id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("vendor_item_code", sa.String(length=60), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["adm_tenants.id"],
            name="fk_proc_vendor_approved_items_tenant_id_adm_tenants",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "vendor_id"],
            ["proc_vendors.tenant_id", "proc_vendors.id"],
            name="fk_proc_vendor_approved_items_tenant_id_proc_vendors",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_proc_vendor_approved_items"),
        sa.UniqueConstraint(
            "tenant_id", "id", name="uq_proc_vendor_approved_items_tenant_id"
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "vendor_id",
            "item_id",
            name="uq_proc_vendor_approved_items_tenant_id_vendor_id_item_id",
        ),
    )
    op.create_index(
        "ix_proc_vendor_approved_items_tenant_id",
        "proc_vendor_approved_items",
        ["tenant_id"],
    )
    op.create_index(
        "ix_proc_vendor_approved_items_tenant_id_vendor_id",
        "proc_vendor_approved_items",
        ["tenant_id", "vendor_id"],
    )


def downgrade() -> None:
    op.drop_table("proc_vendor_approved_items")
    op.drop_table("proc_vendors")
