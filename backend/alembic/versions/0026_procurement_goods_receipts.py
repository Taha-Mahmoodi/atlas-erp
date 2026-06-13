"""procurement goods receipts: header + lines

Revision ID: 0026
Revises: 0025
Create Date: 2026-06-13

PLAN 6.3 — the goods-receipt document (receipt of PO goods → stock + GR/IR journal). Creates TWO
tables (the header + line pair) and alters NOTHING — no trigger-bearing table is touched (D-022), so
there is no trigger-recreation concern. The GR/IR clearing posting purpose is DATA (a posting
default), not schema; the inventory valuation-offset override is a service PARAMETER, not a column —
so neither lands here. All DDL is portable across SQLite and Postgres; every identifier is <= 63
chars (PG cap).

The header mixes in DocumentMixin: a NOT NULL document_id with a composite tenant FK to
core_documents and a UNIQUE(document_id) (the registry-to-row 1:1). Money/quantity columns use
MoneyType / QuantityType (D-015). Every table carries the D-007 backstop (tenant_fk to adm_tenants,
UNIQUE(tenant_id, id)) and intra-module composite tenant FKs.

- proc_goods_receipts: the GR header (composite FK to proc_purchase_orders; opaque vendor/warehouse
  ids). (tenant, status) and (tenant, purchase_order_id) indexes (PERFORMANCE §1).
- proc_goods_receipt_lines: the GR lines (composite FK to proc_purchase_order_lines; opaque item/bin
  ids; lot/serial codes; requires_inspection flag). UNIQUE(tenant, gr_id, line_number).
"""

import sqlalchemy as sa
from alembic import op

from app.core.money import MoneyType, QuantityType

# revision identifiers, used by Alembic.
revision: str = "0026"
down_revision: str | None = "0025"
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


def _tenant_root_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["tenant_id"], ["adm_tenants.id"], name=f"fk_{table}_tenant_id_adm_tenants"
    )


def _document_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["tenant_id", "document_id"],
        ["core_documents.tenant_id", "core_documents.id"],
        name=f"fk_{table}_tenant_id_core_documents",
    )


def _create_goods_receipts() -> None:
    op.create_table(
        "proc_goods_receipts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("gr_number", sa.String(length=60), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="DRAFT"),
        sa.Column("purchase_order_id", sa.Uuid(), nullable=False),
        sa.Column("vendor_id", sa.Uuid(), nullable=False),
        sa.Column("warehouse_id", sa.Uuid(), nullable=False),
        sa.Column("receipt_date", sa.Date(), nullable=False),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        _tenant_root_fk("proc_goods_receipts"),
        _document_fk("proc_goods_receipts"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "purchase_order_id"],
            ["proc_purchase_orders.tenant_id", "proc_purchase_orders.id"],
            name="fk_proc_goods_receipts_tenant_id_proc_purchase_orders",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_proc_goods_receipts"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_proc_goods_receipts_tenant_id"),
        sa.UniqueConstraint("document_id", name="uq_proc_goods_receipts_document_id"),
    )
    op.create_index("ix_proc_goods_receipts_tenant_id", "proc_goods_receipts", ["tenant_id"])
    op.create_index(
        "ix_proc_goods_receipts_tenant_id_status",
        "proc_goods_receipts",
        ["tenant_id", "status"],
    )
    op.create_index(
        "ix_proc_goods_receipts_tenant_id_purchase_order_id",
        "proc_goods_receipts",
        ["tenant_id", "purchase_order_id"],
    )

    op.create_table(
        "proc_goods_receipt_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("gr_id", sa.Uuid(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("purchase_order_line_id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("bin_id", sa.Uuid(), nullable=False),
        sa.Column("received_quantity", QuantityType(), nullable=False),
        sa.Column("unit_cost", MoneyType(), nullable=False),
        sa.Column("lot_code", sa.String(length=100), nullable=True),
        sa.Column("serial_code", sa.String(length=100), nullable=True),
        sa.Column(
            "requires_inspection", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        *_timestamps(),
        _tenant_root_fk("proc_goods_receipt_lines"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "gr_id"],
            ["proc_goods_receipts.tenant_id", "proc_goods_receipts.id"],
            name="fk_proc_goods_receipt_lines_tenant_id_proc_goods_receipts",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "purchase_order_line_id"],
            ["proc_purchase_order_lines.tenant_id", "proc_purchase_order_lines.id"],
            name="fk_proc_goods_receipt_lines_tenant_id_proc_po_lines",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_proc_goods_receipt_lines"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_proc_goods_receipt_lines_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id", "gr_id", "line_number", name="uq_proc_goods_receipt_lines_gr_line"
        ),
    )
    op.create_index(
        "ix_proc_goods_receipt_lines_tenant_id", "proc_goods_receipt_lines", ["tenant_id"]
    )


def upgrade() -> None:
    _create_goods_receipts()


def downgrade() -> None:
    op.drop_table("proc_goods_receipt_lines")
    op.drop_table("proc_goods_receipts")
