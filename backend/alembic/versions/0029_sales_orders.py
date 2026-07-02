"""sales quote and order documents

Revision ID: 0029
Revises: 0028
Create Date: 2026-06-13

PLAN 7.2 — the sales quote → order O2C spine. Creates FOUR tables and alters NOTHING — no
trigger-bearing table is touched (D-022), so there is no trigger-recreation concern. All DDL is
portable across SQLite and Postgres; every identifier is <= 63 chars (PG cap).
MoneyType/QuantityType render as NUMERIC(18,6) on Postgres / INTEGER micro-units on SQLite (D-015)
via the model's column types — imported from app.core.money so the revision stays dialect-clean.

Each header mixes in DocumentMixin: a NOT NULL document_id with a composite tenant FK to
core_documents and a UNIQUE(document_id) (the registry-to-row 1:1). The number is claimed AT
CREATION
(D-012/D-040 claim-at-creation, not finance's number-at-post).

- sales_quotes: the pre-sales offer. UNIQUE(tenant, id); composite FK to sales_customers; (tenant,
  status) + (tenant, customer_id, status) indexes for the list. total_amount maintained.
- sales_quote_lines: one quoted item. item_id / uom_id are OPAQUE inventory ids (D-029, NO FK);
  unit_price + the optional discount drive line_amount; UNIQUE(tenant, quote_id, line_number).
- sales_orders: the committing order. UNIQUE(tenant, id); composite FK to sales_customers + a
  nullable composite FK to sales_quotes (source_quote_id); payment_terms_days snapshot;
  credit_check_status nullable; (tenant, status) + (tenant, customer_id, status) indexes (the latter
  also serves the committed-quantity + credit-exposure scans, D-044). total_amount maintained.
- sales_order_lines: one ordered item. item_id / uom_id / tax_code_id are OPAQUE ids (D-029, NO FK);
  ordered/delivered/invoiced quantities (delivered/invoiced raised by 7.3/7.4, default 0);
  UNIQUE(tenant, order_id, line_number).
"""

import sqlalchemy as sa
from alembic import op

from app.core.money import MoneyType, QuantityType

# revision identifiers, used by Alembic.
revision: str = "0029"
down_revision: str | None = "0028"
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


def _customer_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["tenant_id", "customer_id"],
        ["sales_customers.tenant_id", "sales_customers.id"],
        name=f"fk_{table}_customer_id_sales_customers",
    )


def _create_quotes() -> None:
    op.create_table(
        "sales_quotes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("quote_number", sa.String(length=60), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="DRAFT"),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("quote_date", sa.Date(), nullable=False),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("total_amount", MoneyType(), nullable=False, server_default="0"),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        *_timestamps(),
        _tenant_root_fk("sales_quotes"),
        _document_fk("sales_quotes"),
        _customer_fk("sales_quotes"),
        sa.PrimaryKeyConstraint("id", name="pk_sales_quotes"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_sales_quotes_tenant_id"),
        sa.UniqueConstraint("document_id", name="uq_sales_quotes_document_id"),
    )
    op.create_index("ix_sales_quotes_tenant_id", "sales_quotes", ["tenant_id"])
    op.create_index(
        "ix_sales_quotes_tenant_id_status", "sales_quotes", ["tenant_id", "status"]
    )
    op.create_index(
        "ix_sales_quotes_tenant_id_customer_id_status",
        "sales_quotes",
        ["tenant_id", "customer_id", "status"],
    )

    op.create_table(
        "sales_quote_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("quote_id", sa.Uuid(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("quantity", QuantityType(), nullable=False),
        sa.Column("uom_id", sa.Uuid(), nullable=False),
        sa.Column("unit_price", MoneyType(), nullable=False),
        sa.Column("discount_type", sa.String(length=10), nullable=True),
        sa.Column("discount_value", MoneyType(), nullable=True),
        sa.Column("line_amount", MoneyType(), nullable=False),
        *_timestamps(),
        _tenant_root_fk("sales_quote_lines"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "quote_id"],
            ["sales_quotes.tenant_id", "sales_quotes.id"],
            name="fk_sales_quote_lines_tenant_id_sales_quotes",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_sales_quote_lines"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_sales_quote_lines_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id", "quote_id", "line_number", name="uq_sales_quote_lines_quote_line"
        ),
    )
    op.create_index("ix_sales_quote_lines_tenant_id", "sales_quote_lines", ["tenant_id"])


def _create_orders() -> None:
    op.create_table(
        "sales_orders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("order_number", sa.String(length=60), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="DRAFT"),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("order_date", sa.Date(), nullable=False),
        sa.Column("requested_date", sa.Date(), nullable=True),
        sa.Column("payment_terms_days", sa.Integer(), nullable=False),
        sa.Column("total_amount", MoneyType(), nullable=False, server_default="0"),
        sa.Column("source_quote_id", sa.Uuid(), nullable=True),
        sa.Column("credit_check_status", sa.String(length=10), nullable=True),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        *_timestamps(),
        _tenant_root_fk("sales_orders"),
        _document_fk("sales_orders"),
        _customer_fk("sales_orders"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "source_quote_id"],
            ["sales_quotes.tenant_id", "sales_quotes.id"],
            name="fk_sales_orders_source_quote_id_sales_quotes",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_sales_orders"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_sales_orders_tenant_id"),
        sa.UniqueConstraint("document_id", name="uq_sales_orders_document_id"),
    )
    op.create_index("ix_sales_orders_tenant_id", "sales_orders", ["tenant_id"])
    op.create_index(
        "ix_sales_orders_tenant_id_status", "sales_orders", ["tenant_id", "status"]
    )
    op.create_index(
        "ix_sales_orders_tenant_id_customer_id_status",
        "sales_orders",
        ["tenant_id", "customer_id", "status"],
    )

    op.create_table(
        "sales_order_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("ordered_quantity", QuantityType(), nullable=False),
        sa.Column("uom_id", sa.Uuid(), nullable=False),
        sa.Column("unit_price", MoneyType(), nullable=False),
        sa.Column("discount_type", sa.String(length=10), nullable=True),
        sa.Column("discount_value", MoneyType(), nullable=True),
        sa.Column("line_amount", MoneyType(), nullable=False),
        sa.Column("delivered_quantity", QuantityType(), nullable=False, server_default="0"),
        sa.Column("invoiced_quantity", QuantityType(), nullable=False, server_default="0"),
        sa.Column("tax_code_id", sa.Uuid(), nullable=True),
        *_timestamps(),
        _tenant_root_fk("sales_order_lines"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "order_id"],
            ["sales_orders.tenant_id", "sales_orders.id"],
            name="fk_sales_order_lines_tenant_id_sales_orders",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_sales_order_lines"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_sales_order_lines_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id", "order_id", "line_number", name="uq_sales_order_lines_order_line"
        ),
    )
    op.create_index("ix_sales_order_lines_tenant_id", "sales_order_lines", ["tenant_id"])


def upgrade() -> None:
    _create_quotes()
    _create_orders()


def downgrade() -> None:
    op.drop_table("sales_order_lines")
    op.drop_table("sales_orders")
    op.drop_table("sales_quote_lines")
    op.drop_table("sales_quotes")
