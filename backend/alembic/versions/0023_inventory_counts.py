"""inventory physical & cycle counts

Revision ID: 0023
Revises: 0022
Create Date: 2026-06-13

PLAN 5.4 — physical/cycle counts with variance posting (D-038). A count captures counted quantities
per (item, bin, lot), compares to live on-hand and posts the differences as stock ADJUSTMENT moves
(which flow through the 5.3 costing engine → the price-difference journal). Creates TWO tables and
alters NOTHING — no trigger-bearing table is touched (D-022), so there is no trigger-recreation
concern. All DDL is portable across SQLite and Postgres; every identifier is <= 63 chars (PG cap).

- inv_stock_counts: the count document. DocumentMixin document_id (composite FK to core_documents,
  UNIQUE); composite tenant FK to inv_warehouses; (tenant, warehouse) + (tenant, status) indexes for
  the filtered list; count_number claimed at creation; status DRAFT→COUNTING→POSTED|CANCELLED.
- inv_stock_count_lines: one line per (item, bin, lot) in scope. Composite tenant FKs to the count,
  item, bin, lot (nullable) and the generated adjustment move (nullable); UNIQUE(tenant, count,
  item, bin, lot); (tenant, count) index for the lines-of-a-count read. system_qty is the snapshot;
  counted_qty/variance_qty/adjustment_move_id/unit_cost are filled at post.
"""

import sqlalchemy as sa
from alembic import op

from app.core.money import MoneyType, QuantityType

# revision identifiers, used by Alembic.
revision: str = "0023"
down_revision: str | None = "0022"
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
        "inv_stock_counts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("count_number", sa.String(length=60), nullable=False),
        sa.Column("count_type", sa.String(length=12), nullable=False),
        sa.Column("warehouse_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("count_date", sa.Date(), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["adm_tenants.id"], name="fk_inv_stock_counts_tenant_id_adm_tenants"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["core_documents.tenant_id", "core_documents.id"],
            name="fk_inv_stock_counts_tenant_id_core_documents",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "warehouse_id"],
            ["inv_warehouses.tenant_id", "inv_warehouses.id"],
            name="fk_inv_stock_counts_tenant_id_inv_warehouses",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_inv_stock_counts"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_inv_stock_counts_tenant_id"),
        sa.UniqueConstraint("document_id", name="uq_inv_stock_counts_document_id"),
    )
    op.create_index("ix_inv_stock_counts_tenant_id", "inv_stock_counts", ["tenant_id"])
    op.create_index(
        "ix_inv_stock_counts_tenant_id_warehouse_id",
        "inv_stock_counts",
        ["tenant_id", "warehouse_id"],
    )
    op.create_index(
        "ix_inv_stock_counts_tenant_id_status", "inv_stock_counts", ["tenant_id", "status"]
    )

    op.create_table(
        "inv_stock_count_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("count_id", sa.Uuid(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("bin_id", sa.Uuid(), nullable=False),
        sa.Column("lot_id", sa.Uuid(), nullable=True),
        sa.Column("system_qty", QuantityType(), nullable=False),
        sa.Column("counted_qty", QuantityType(), nullable=True),
        sa.Column("variance_qty", QuantityType(), nullable=True),
        sa.Column("adjustment_move_id", sa.Uuid(), nullable=True),
        sa.Column("unit_cost", MoneyType(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["adm_tenants.id"],
            name="fk_inv_stock_count_lines_tenant_id_adm_tenants",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "count_id"],
            ["inv_stock_counts.tenant_id", "inv_stock_counts.id"],
            name="fk_inv_stock_count_lines_tenant_id_inv_stock_counts",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "item_id"],
            ["inv_items.tenant_id", "inv_items.id"],
            name="fk_inv_stock_count_lines_tenant_id_inv_items",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "bin_id"],
            ["inv_bins.tenant_id", "inv_bins.id"],
            name="fk_inv_stock_count_lines_tenant_id_inv_bins",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "lot_id"],
            ["inv_lots.tenant_id", "inv_lots.id"],
            name="fk_inv_stock_count_lines_tenant_id_inv_lots",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "adjustment_move_id"],
            ["inv_stock_moves.tenant_id", "inv_stock_moves.id"],
            name="fk_inv_stock_count_lines_tenant_id_inv_stock_moves",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_inv_stock_count_lines"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_inv_stock_count_lines_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "count_id",
            "item_id",
            "bin_id",
            "lot_id",
            name="uq_inv_stock_count_lines_tenant_id_count_id_item_id_bin_id_lot",
        ),
    )
    op.create_index(
        "ix_inv_stock_count_lines_tenant_id", "inv_stock_count_lines", ["tenant_id"]
    )
    op.create_index(
        "ix_inv_stock_count_lines_tenant_id_count_id",
        "inv_stock_count_lines",
        ["tenant_id", "count_id"],
    )


def downgrade() -> None:
    op.drop_table("inv_stock_count_lines")
    op.drop_table("inv_stock_counts")
