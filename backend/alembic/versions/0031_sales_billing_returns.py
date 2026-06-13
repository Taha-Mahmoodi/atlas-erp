"""sales billing + return (RMA) documents

Revision ID: 0031
Revises: 0030
Create Date: 2026-06-13

PLAN 7.4 — the sales billing (invoice-from-delivery) + RMA return documents, completing the
order-to-cash loop. Creates FOUR tables and adds ONE column to sales_order_lines (returned_quantity,
the over-return cap) via batch_alter. ``invoiced_quantity`` already exists from 0029 (declared in
7.2). No trigger-bearing table is touched (sales_order_lines is plain), so there is no
trigger-recreation concern. All DDL is portable across SQLite and Postgres; every identifier is <=
63
chars (PG cap). Money/QuantityType render as NUMERIC(18,6) on Postgres / scaled integers on SQLite
(D-015) via the model's column types — imported from app.core.money so the revision stays
dialect-clean.

- sales_billings: the billing header. UNIQUE(tenant, id); composite FK to sales_orders; (tenant,
  status) + (tenant, sales_order_id) indexes. customer_id is a snapshot; payment_terms_days is a
  snapshot. status DRAFT/POSTED/CANCELLED; posted_at nullable.
- sales_billing_lines: one billed line. item_id is an OPAQUE inventory id (D-029, NO FK); the
  billing↔customer-invoice link is docflow, NOT an FK (D-046). composite FKs to sales_order_lines
  (billed) + sales_delivery_lines (the source shipment, nullable). tax_code_id opaque (NO FK).
  UNIQUE(tenant, billing_id, line_number).
- sales_returns: the RMA header. UNIQUE(tenant, id); composite FK to sales_orders; (tenant, status)
+
  (tenant, sales_order_id) indexes. warehouse_id is an OPAQUE inventory id (D-029, NO FK).
- sales_return_lines: one returned line. item_id / bin_id are OPAQUE inventory ids (D-029, NO FK);
  the return↔move + return↔credit-note links are docflow (D-046). composite FK to sales_order_lines.
  lot_code/serial_code nullable; UNIQUE(tenant, return_id, line_number).
"""

import sqlalchemy as sa
from alembic import op

from app.core.money import MoneyType, QuantityType

# revision identifiers, used by Alembic.
revision: str = "0031"
down_revision: str | None = "0030"
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


def _create_billings() -> None:
    op.create_table(
        "sales_billings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("billing_number", sa.String(length=60), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="DRAFT"),
        sa.Column("sales_order_id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("billing_date", sa.Date(), nullable=False),
        sa.Column("payment_terms_days", sa.Integer(), nullable=False),
        sa.Column("total_amount", MoneyType(), nullable=False, server_default="0"),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        _tenant_root_fk("sales_billings"),
        _document_fk("sales_billings"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "sales_order_id"],
            ["sales_orders.tenant_id", "sales_orders.id"],
            name="fk_sales_billings_sales_order_id_sales_orders",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_sales_billings"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_sales_billings_tenant_id"),
        sa.UniqueConstraint("document_id", name="uq_sales_billings_document_id"),
    )
    op.create_index("ix_sales_billings_tenant_id", "sales_billings", ["tenant_id"])
    op.create_index(
        "ix_sales_billings_tenant_id_status", "sales_billings", ["tenant_id", "status"]
    )
    op.create_index(
        "ix_sales_billings_tenant_id_sales_order_id",
        "sales_billings",
        ["tenant_id", "sales_order_id"],
    )

    op.create_table(
        "sales_billing_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("billing_id", sa.Uuid(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("sales_order_line_id", sa.Uuid(), nullable=False),
        sa.Column("delivery_line_id", sa.Uuid(), nullable=True),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", QuantityType(), nullable=False),
        sa.Column("unit_price", MoneyType(), nullable=False),
        sa.Column("discount_type", sa.String(length=10), nullable=True),
        sa.Column("discount_value", MoneyType(), nullable=True),
        sa.Column("line_amount", MoneyType(), nullable=False),
        sa.Column("tax_code_id", sa.Uuid(), nullable=True),
        *_timestamps(),
        _tenant_root_fk("sales_billing_lines"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "billing_id"],
            ["sales_billings.tenant_id", "sales_billings.id"],
            name="fk_sales_billing_lines_tenant_id_sales_billings",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "sales_order_line_id"],
            ["sales_order_lines.tenant_id", "sales_order_lines.id"],
            name="fk_sales_billing_lines_sales_order_line_id_sales_order_lines",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "delivery_line_id"],
            ["sales_delivery_lines.tenant_id", "sales_delivery_lines.id"],
            name="fk_sales_billing_lines_delivery_line_id_sales_delivery_lines",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_sales_billing_lines"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_sales_billing_lines_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "billing_id",
            "line_number",
            name="uq_sales_billing_lines_billing_line",
        ),
    )
    op.create_index("ix_sales_billing_lines_tenant_id", "sales_billing_lines", ["tenant_id"])


def _create_returns() -> None:
    op.create_table(
        "sales_returns",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("return_number", sa.String(length=60), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="DRAFT"),
        sa.Column("sales_order_id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("warehouse_id", sa.Uuid(), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("return_date", sa.Date(), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column("total_amount", MoneyType(), nullable=False, server_default="0"),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        _tenant_root_fk("sales_returns"),
        _document_fk("sales_returns"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "sales_order_id"],
            ["sales_orders.tenant_id", "sales_orders.id"],
            name="fk_sales_returns_sales_order_id_sales_orders",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_sales_returns"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_sales_returns_tenant_id"),
        sa.UniqueConstraint("document_id", name="uq_sales_returns_document_id"),
    )
    op.create_index("ix_sales_returns_tenant_id", "sales_returns", ["tenant_id"])
    op.create_index("ix_sales_returns_tenant_id_status", "sales_returns", ["tenant_id", "status"])
    op.create_index(
        "ix_sales_returns_tenant_id_sales_order_id",
        "sales_returns",
        ["tenant_id", "sales_order_id"],
    )

    op.create_table(
        "sales_return_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("return_id", sa.Uuid(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("sales_order_line_id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("bin_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", QuantityType(), nullable=False),
        sa.Column("unit_price", MoneyType(), nullable=False),
        sa.Column("line_amount", MoneyType(), nullable=False),
        sa.Column("tax_code_id", sa.Uuid(), nullable=True),
        sa.Column("lot_code", sa.String(length=100), nullable=True),
        sa.Column("serial_code", sa.String(length=100), nullable=True),
        *_timestamps(),
        _tenant_root_fk("sales_return_lines"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "return_id"],
            ["sales_returns.tenant_id", "sales_returns.id"],
            name="fk_sales_return_lines_tenant_id_sales_returns",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "sales_order_line_id"],
            ["sales_order_lines.tenant_id", "sales_order_lines.id"],
            name="fk_sales_return_lines_sales_order_line_id_sales_order_lines",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_sales_return_lines"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_sales_return_lines_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "return_id",
            "line_number",
            name="uq_sales_return_lines_return_line",
        ),
    )
    op.create_index("ix_sales_return_lines_tenant_id", "sales_return_lines", ["tenant_id"])


def upgrade() -> None:
    _create_billings()
    _create_returns()
    # The over-return cap column (invoiced − returned). batch_alter for SQLite portability; the
    # table
    # is plain (no trigger), so the batch copy is safe and reversible. server_default 0 backfills.
    with op.batch_alter_table("sales_order_lines") as batch:
        batch.add_column(
            sa.Column("returned_quantity", QuantityType(), nullable=False, server_default="0")
        )


def downgrade() -> None:
    with op.batch_alter_table("sales_order_lines") as batch:
        batch.drop_column("returned_quantity")
    op.drop_table("sales_return_lines")
    op.drop_table("sales_returns")
    op.drop_table("sales_billing_lines")
    op.drop_table("sales_billings")
