"""procurement P2P documents: requisitions, RFQs, purchase orders, approval rules

Revision ID: 0025
Revises: 0024
Create Date: 2026-06-13

PLAN 6.2 — the requisition → RFQ → PO document chain + the data-driven approval-threshold rule.
Creates SEVEN tables (three header+line pairs plus the approval-rule config) and alters NOTHING — no
trigger-bearing table is touched (D-022), so there is no trigger-recreation concern. All DDL is
portable across SQLite and Postgres; every identifier is <= 63 chars (PG cap). The models/ package
split (Vendor/VendorApprovedItem moved to models/vendors.py) is a CODE move only — the
proc_vendors / proc_vendor_approved_items tables are unchanged from 0024.

Each header mixes in DocumentMixin: a NOT NULL document_id with a composite tenant FK to
core_documents and a UNIQUE(document_id) (the registry-to-row 1:1). Money/quantity columns use
MoneyType / QuantityType (D-015, exact on both engines). Every table carries the D-007 backstop
(tenant_fk to adm_tenants, UNIQUE(tenant_id, id)) and intra-module composite tenant FKs.

- proc_requisitions / proc_requisition_lines: the requisition header + lines. (tenant, status)
  index.
- proc_rfqs / proc_rfq_lines: the RFQ header (composite FK to proc_vendors + nullable FK to the
  source requisition) + lines. (tenant, status) and (tenant, vendor_id) indexes.
- proc_purchase_orders / proc_purchase_order_lines: the PO header (composite FK to proc_vendors +
  nullable FKs to the source requisition/RFQ) + lines (with received_quantity for 6.3, tax_code_id
  for 6.4). (tenant, status) and (tenant, vendor_id, status) indexes (PERFORMANCE §1).
- proc_approval_rules: the value-threshold rule. UNIQUE(tenant, document_type); CHECK >= 0.
"""

import sqlalchemy as sa
from alembic import op

from app.core.money import MoneyType, QuantityType

# revision identifiers, used by Alembic.
revision: str = "0025"
down_revision: str | None = "0024"
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


def _document_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["tenant_id", "document_id"],
        ["core_documents.tenant_id", "core_documents.id"],
        name=f"fk_{table}_tenant_id_core_documents",
    )


def _tenant_root_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["tenant_id"], ["adm_tenants.id"], name=f"fk_{table}_tenant_id_adm_tenants"
    )


def _create_requisitions() -> None:
    op.create_table(
        "proc_requisitions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("requisition_number", sa.String(length=60), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="DRAFT"),
        sa.Column("requested_by", sa.Uuid(), nullable=True),
        sa.Column("needed_by_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        *_timestamps(),
        _tenant_root_fk("proc_requisitions"),
        _document_fk("proc_requisitions"),
        sa.PrimaryKeyConstraint("id", name="pk_proc_requisitions"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_proc_requisitions_tenant_id"),
        sa.UniqueConstraint("document_id", name="uq_proc_requisitions_document_id"),
    )
    op.create_index("ix_proc_requisitions_tenant_id", "proc_requisitions", ["tenant_id"])
    op.create_index(
        "ix_proc_requisitions_tenant_id_status", "proc_requisitions", ["tenant_id", "status"]
    )

    op.create_table(
        "proc_requisition_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("requisition_id", sa.Uuid(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("quantity", QuantityType(), nullable=False),
        sa.Column("uom_id", sa.Uuid(), nullable=False),
        sa.Column("estimated_unit_cost", MoneyType(), nullable=True),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        *_timestamps(),
        _tenant_root_fk("proc_requisition_lines"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "requisition_id"],
            ["proc_requisitions.tenant_id", "proc_requisitions.id"],
            name="fk_proc_requisition_lines_tenant_id_proc_requisitions",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_proc_requisition_lines"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_proc_requisition_lines_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "requisition_id",
            "line_number",
            name="uq_proc_requisition_lines_requisition_line",
        ),
    )
    op.create_index(
        "ix_proc_requisition_lines_tenant_id", "proc_requisition_lines", ["tenant_id"]
    )


def _create_rfqs() -> None:
    op.create_table(
        "proc_rfqs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("rfq_number", sa.String(length=60), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="DRAFT"),
        sa.Column("vendor_id", sa.Uuid(), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("source_requisition_id", sa.Uuid(), nullable=True),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        *_timestamps(),
        _tenant_root_fk("proc_rfqs"),
        _document_fk("proc_rfqs"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "vendor_id"],
            ["proc_vendors.tenant_id", "proc_vendors.id"],
            name="fk_proc_rfqs_tenant_id_proc_vendors",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "source_requisition_id"],
            ["proc_requisitions.tenant_id", "proc_requisitions.id"],
            name="fk_proc_rfqs_tenant_id_proc_requisitions",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_proc_rfqs"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_proc_rfqs_tenant_id"),
        sa.UniqueConstraint("document_id", name="uq_proc_rfqs_document_id"),
    )
    op.create_index("ix_proc_rfqs_tenant_id", "proc_rfqs", ["tenant_id"])
    op.create_index("ix_proc_rfqs_tenant_id_status", "proc_rfqs", ["tenant_id", "status"])
    op.create_index(
        "ix_proc_rfqs_tenant_id_vendor_id", "proc_rfqs", ["tenant_id", "vendor_id"]
    )

    op.create_table(
        "proc_rfq_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("rfq_id", sa.Uuid(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("quantity", QuantityType(), nullable=False),
        sa.Column("uom_id", sa.Uuid(), nullable=False),
        sa.Column("quoted_unit_cost", MoneyType(), nullable=True),
        *_timestamps(),
        _tenant_root_fk("proc_rfq_lines"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "rfq_id"],
            ["proc_rfqs.tenant_id", "proc_rfqs.id"],
            name="fk_proc_rfq_lines_tenant_id_proc_rfqs",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_proc_rfq_lines"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_proc_rfq_lines_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id", "rfq_id", "line_number", name="uq_proc_rfq_lines_rfq_line"
        ),
    )
    op.create_index("ix_proc_rfq_lines_tenant_id", "proc_rfq_lines", ["tenant_id"])


def _create_purchase_orders() -> None:
    op.create_table(
        "proc_purchase_orders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("po_number", sa.String(length=60), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="DRAFT"),
        sa.Column("vendor_id", sa.Uuid(), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("order_date", sa.Date(), nullable=False),
        sa.Column("expected_date", sa.Date(), nullable=True),
        sa.Column("payment_terms_days", sa.Integer(), nullable=False),
        sa.Column("total_amount", MoneyType(), nullable=False, server_default="0"),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        sa.Column("approved_by", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_requisition_id", sa.Uuid(), nullable=True),
        sa.Column("source_rfq_id", sa.Uuid(), nullable=True),
        *_timestamps(),
        _tenant_root_fk("proc_purchase_orders"),
        _document_fk("proc_purchase_orders"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "vendor_id"],
            ["proc_vendors.tenant_id", "proc_vendors.id"],
            name="fk_proc_purchase_orders_tenant_id_proc_vendors",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "source_requisition_id"],
            ["proc_requisitions.tenant_id", "proc_requisitions.id"],
            name="fk_proc_purchase_orders_tenant_id_proc_requisitions",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "source_rfq_id"],
            ["proc_rfqs.tenant_id", "proc_rfqs.id"],
            name="fk_proc_purchase_orders_tenant_id_proc_rfqs",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_proc_purchase_orders"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_proc_purchase_orders_tenant_id"),
        sa.UniqueConstraint("document_id", name="uq_proc_purchase_orders_document_id"),
    )
    op.create_index(
        "ix_proc_purchase_orders_tenant_id", "proc_purchase_orders", ["tenant_id"]
    )
    op.create_index(
        "ix_proc_purchase_orders_tenant_id_status",
        "proc_purchase_orders",
        ["tenant_id", "status"],
    )
    op.create_index(
        "ix_proc_purchase_orders_tenant_id_vendor_id_status",
        "proc_purchase_orders",
        ["tenant_id", "vendor_id", "status"],
    )

    op.create_table(
        "proc_purchase_order_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("po_id", sa.Uuid(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("quantity", QuantityType(), nullable=False),
        sa.Column("uom_id", sa.Uuid(), nullable=False),
        sa.Column("unit_cost", MoneyType(), nullable=False),
        sa.Column("line_amount", MoneyType(), nullable=False),
        sa.Column("received_quantity", QuantityType(), nullable=False, server_default="0"),
        sa.Column("tax_code_id", sa.Uuid(), nullable=True),
        *_timestamps(),
        _tenant_root_fk("proc_purchase_order_lines"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "po_id"],
            ["proc_purchase_orders.tenant_id", "proc_purchase_orders.id"],
            name="fk_proc_purchase_order_lines_tenant_id_proc_purchase_orders",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_proc_purchase_order_lines"),
        sa.UniqueConstraint(
            "tenant_id", "id", name="uq_proc_purchase_order_lines_tenant_id"
        ),
        sa.UniqueConstraint(
            "tenant_id", "po_id", "line_number", name="uq_proc_purchase_order_lines_po_line"
        ),
    )
    op.create_index(
        "ix_proc_purchase_order_lines_tenant_id", "proc_purchase_order_lines", ["tenant_id"]
    )


def _create_approval_rules() -> None:
    op.create_table(
        "proc_approval_rules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("document_type", sa.String(length=20), nullable=False),
        sa.Column("threshold_amount", MoneyType(), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("description", sa.String(length=500), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "threshold_amount >= 0", name="ck_proc_approval_rules_threshold_non_negative"
        ),
        _tenant_root_fk("proc_approval_rules"),
        sa.PrimaryKeyConstraint("id", name="pk_proc_approval_rules"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_proc_approval_rules_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id", "document_type", name="uq_proc_approval_rules_tenant_id_document_type"
        ),
    )
    op.create_index(
        "ix_proc_approval_rules_tenant_id", "proc_approval_rules", ["tenant_id"]
    )


def upgrade() -> None:
    _create_requisitions()
    _create_rfqs()
    _create_purchase_orders()
    _create_approval_rules()


def downgrade() -> None:
    op.drop_table("proc_approval_rules")
    op.drop_table("proc_purchase_order_lines")
    op.drop_table("proc_purchase_orders")
    op.drop_table("proc_rfq_lines")
    op.drop_table("proc_rfqs")
    op.drop_table("proc_requisition_lines")
    op.drop_table("proc_requisitions")
