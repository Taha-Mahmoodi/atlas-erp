"""sales outbound delivery documents

Revision ID: 0030
Revises: 0029
Create Date: 2026-06-13

PLAN 7.3 — the sales delivery fulfilment document (the outbound twin of the procurement goods
receipt). Creates TWO tables and alters NOTHING — no trigger-bearing table is touched (D-022), so
there is no trigger-recreation concern. All DDL is portable across SQLite and Postgres; every
identifier is <= 63 chars (PG cap). QuantityType renders as NUMERIC(18,6) on Postgres / INTEGER
micro-units on SQLite (D-015) via the model's column types — imported from app.core.money so the
revision stays dialect-clean.

The header mixes in DocumentMixin: a NOT NULL document_id with a composite tenant FK to
core_documents and a UNIQUE(document_id) (the registry-to-row 1:1). The DN number is claimed AT
CREATION (D-012/D-040 claim-at-creation, the goods-receipt precedent).

- sales_deliveries: the shipment header. UNIQUE(tenant, id); composite FK to sales_orders; (tenant,
  status) + (tenant, sales_order_id) indexes for the list. customer_id is a snapshot; warehouse_id
  is an OPAQUE inventory id (D-029, NO FK). status DRAFT/POSTED/CANCELLED; posted_at nullable.
- sales_delivery_lines: one shipped line. item_id / bin_id are OPAQUE inventory ids (D-029, NO FK);
  the delivery↔stock-move link is docflow, NOT a stock_move_id column (D-041). composite FK to
  sales_order_lines (the line delivered against); quantity is the shipped qty; lot_code/serial_code
  nullable for tracked items; UNIQUE(tenant, delivery_id, line_number).
"""

import sqlalchemy as sa
from alembic import op

from app.core.money import QuantityType

# revision identifiers, used by Alembic.
revision: str = "0030"
down_revision: str | None = "0029"
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


def _create_deliveries() -> None:
    op.create_table(
        "sales_deliveries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("delivery_number", sa.String(length=60), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="DRAFT"),
        sa.Column("sales_order_id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("warehouse_id", sa.Uuid(), nullable=False),
        sa.Column("delivery_date", sa.Date(), nullable=False),
        sa.Column("shipping_address", sa.String(length=1000), nullable=True),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        _tenant_root_fk("sales_deliveries"),
        _document_fk("sales_deliveries"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "sales_order_id"],
            ["sales_orders.tenant_id", "sales_orders.id"],
            name="fk_sales_deliveries_sales_order_id_sales_orders",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_sales_deliveries"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_sales_deliveries_tenant_id"),
        sa.UniqueConstraint("document_id", name="uq_sales_deliveries_document_id"),
    )
    op.create_index("ix_sales_deliveries_tenant_id", "sales_deliveries", ["tenant_id"])
    op.create_index(
        "ix_sales_deliveries_tenant_id_status", "sales_deliveries", ["tenant_id", "status"]
    )
    op.create_index(
        "ix_sales_deliveries_tenant_id_sales_order_id",
        "sales_deliveries",
        ["tenant_id", "sales_order_id"],
    )

    op.create_table(
        "sales_delivery_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("delivery_id", sa.Uuid(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("sales_order_line_id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("bin_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", QuantityType(), nullable=False),
        sa.Column("lot_code", sa.String(length=100), nullable=True),
        sa.Column("serial_code", sa.String(length=100), nullable=True),
        *_timestamps(),
        _tenant_root_fk("sales_delivery_lines"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "delivery_id"],
            ["sales_deliveries.tenant_id", "sales_deliveries.id"],
            name="fk_sales_delivery_lines_tenant_id_sales_deliveries",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "sales_order_line_id"],
            ["sales_order_lines.tenant_id", "sales_order_lines.id"],
            name="fk_sales_delivery_lines_sales_order_line_id_sales_order_lines",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_sales_delivery_lines"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_sales_delivery_lines_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "delivery_id",
            "line_number",
            name="uq_sales_delivery_lines_delivery_line",
        ),
    )
    op.create_index("ix_sales_delivery_lines_tenant_id", "sales_delivery_lines", ["tenant_id"])


def upgrade() -> None:
    _create_deliveries()


def downgrade() -> None:
    op.drop_table("sales_delivery_lines")
    op.drop_table("sales_deliveries")
