"""inventory stock topology + move ledger + on-hand quant projection

Revision ID: 0021
Revises: 0020
Create Date: 2026-06-13

PLAN 5.2 — warehouses, bins, the stock-move ledger (the quantity SSOT, D-020) and the maintained
on-hand quant projection (D-036). Creates FOUR tables and alters NOTHING — no trigger-bearing table
is touched, so there is no trigger-recreation concern (D-022). All DDL is portable across SQLite and
Postgres; every identifier is <= 63 chars (PG cap).

- inv_warehouses: stock locations. UNIQUE(tenant, code); is_active soft-delete.
- inv_bins: storage bins within a warehouse. Composite tenant FK to inv_warehouses;
  UNIQUE(tenant, warehouse, code); (tenant, warehouse) FK index; is_default/is_active flags.
- inv_stock_moves: the append-only move ledger (POSTED at creation, immutable). DocumentMixin
  document_id (composite FK to core_documents, UNIQUE); composite tenant FKs to items, uoms, two
  bins (from/to, distinct explicit names), lots, serials; quantity ALWAYS positive; four indexes
  per PERFORMANCE §1 ((tenant,item,to_bin), (tenant,item,from_bin), (tenant,move_date),
  (tenant,item)).
- inv_stock_quants: the maintained on-hand projection. UNIQUE(tenant, item, bin, lot) upsert
  target; CHECK(on_hand_qty >= 0) — negative stock forbidden outright (D-020), portable single-
  column CHECK on both engines; (tenant, item) index for the total-on-hand aggregate.
"""

import sqlalchemy as sa
from alembic import op

from app.core.money import QuantityType

# revision identifiers, used by Alembic.
revision: str = "0021"
down_revision: str | None = "0020"
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
        "inv_warehouses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["adm_tenants.id"], name="fk_inv_warehouses_tenant_id_adm_tenants"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_inv_warehouses"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_inv_warehouses_tenant_id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_inv_warehouses_tenant_id_code"),
    )
    op.create_index("ix_inv_warehouses_tenant_id", "inv_warehouses", ["tenant_id"])

    op.create_table(
        "inv_bins",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("warehouse_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["adm_tenants.id"], name="fk_inv_bins_tenant_id_adm_tenants"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "warehouse_id"],
            ["inv_warehouses.tenant_id", "inv_warehouses.id"],
            name="fk_inv_bins_tenant_id_inv_warehouses",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_inv_bins"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_inv_bins_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id", "warehouse_id", "code", name="uq_inv_bins_tenant_id_warehouse_id_code"
        ),
    )
    op.create_index("ix_inv_bins_tenant_id", "inv_bins", ["tenant_id"])
    op.create_index(
        "ix_inv_bins_tenant_id_warehouse_id", "inv_bins", ["tenant_id", "warehouse_id"]
    )

    op.create_table(
        "inv_stock_moves",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("move_number", sa.String(length=60), nullable=False),
        sa.Column("move_type", sa.String(length=12), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", QuantityType(), nullable=False),
        sa.Column("base_uom_id", sa.Uuid(), nullable=False),
        sa.Column("from_bin_id", sa.Uuid(), nullable=True),
        sa.Column("to_bin_id", sa.Uuid(), nullable=True),
        sa.Column("lot_id", sa.Uuid(), nullable=True),
        sa.Column("serial_id", sa.Uuid(), nullable=True),
        sa.Column("move_date", sa.Date(), nullable=False),
        sa.Column("reference", sa.String(length=500), nullable=True),
        sa.Column("posted", sa.Boolean(), server_default=sa.true(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["adm_tenants.id"], name="fk_inv_stock_moves_tenant_id_adm_tenants"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["core_documents.tenant_id", "core_documents.id"],
            name="fk_inv_stock_moves_tenant_id_core_documents",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "item_id"],
            ["inv_items.tenant_id", "inv_items.id"],
            name="fk_inv_stock_moves_tenant_id_inv_items",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "base_uom_id"],
            ["inv_uoms.tenant_id", "inv_uoms.id"],
            name="fk_inv_stock_moves_tenant_id_inv_uoms",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "from_bin_id"],
            ["inv_bins.tenant_id", "inv_bins.id"],
            name="fk_inv_stock_moves_from_bin_id_inv_bins",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "to_bin_id"],
            ["inv_bins.tenant_id", "inv_bins.id"],
            name="fk_inv_stock_moves_to_bin_id_inv_bins",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "lot_id"],
            ["inv_lots.tenant_id", "inv_lots.id"],
            name="fk_inv_stock_moves_tenant_id_inv_lots",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "serial_id"],
            ["inv_serials.tenant_id", "inv_serials.id"],
            name="fk_inv_stock_moves_tenant_id_inv_serials",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_inv_stock_moves"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_inv_stock_moves_tenant_id"),
        sa.UniqueConstraint("document_id", name="uq_inv_stock_moves_document_id"),
    )
    op.create_index("ix_inv_stock_moves_tenant_id", "inv_stock_moves", ["tenant_id"])
    op.create_index(
        "ix_inv_stock_moves_tenant_id_item_id", "inv_stock_moves", ["tenant_id", "item_id"]
    )
    op.create_index(
        "ix_inv_stock_moves_tenant_id_item_id_to_bin_id",
        "inv_stock_moves",
        ["tenant_id", "item_id", "to_bin_id"],
    )
    op.create_index(
        "ix_inv_stock_moves_tenant_id_item_id_from_bin_id",
        "inv_stock_moves",
        ["tenant_id", "item_id", "from_bin_id"],
    )
    op.create_index(
        "ix_inv_stock_moves_tenant_id_move_date", "inv_stock_moves", ["tenant_id", "move_date"]
    )

    op.create_table(
        "inv_stock_quants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("bin_id", sa.Uuid(), nullable=False),
        sa.Column("lot_id", sa.Uuid(), nullable=True),
        sa.Column("on_hand_qty", QuantityType(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "on_hand_qty >= 0", name="ck_inv_stock_quants_on_hand_non_negative"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["adm_tenants.id"], name="fk_inv_stock_quants_tenant_id_adm_tenants"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "item_id"],
            ["inv_items.tenant_id", "inv_items.id"],
            name="fk_inv_stock_quants_tenant_id_inv_items",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "bin_id"],
            ["inv_bins.tenant_id", "inv_bins.id"],
            name="fk_inv_stock_quants_tenant_id_inv_bins",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "lot_id"],
            ["inv_lots.tenant_id", "inv_lots.id"],
            name="fk_inv_stock_quants_tenant_id_inv_lots",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_inv_stock_quants"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_inv_stock_quants_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "item_id",
            "bin_id",
            "lot_id",
            name="uq_inv_stock_quants_tenant_id_item_id_bin_id_lot_id",
        ),
    )
    op.create_index("ix_inv_stock_quants_tenant_id", "inv_stock_quants", ["tenant_id"])
    op.create_index(
        "ix_inv_stock_quants_tenant_id_item_id", "inv_stock_quants", ["tenant_id", "item_id"]
    )


def downgrade() -> None:
    op.drop_table("inv_stock_quants")
    op.drop_table("inv_stock_moves")
    op.drop_table("inv_bins")
    op.drop_table("inv_warehouses")
