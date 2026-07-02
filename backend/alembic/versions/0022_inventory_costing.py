"""inventory costing: valuation + FIFO layers + layer consumptions + stock-move unit_cost

Revision ID: 0022
Revises: 0021
Create Date: 2026-06-13

PLAN 5.3 — moving-average AND FIFO valuation per (item, warehouse) with same-transaction COGS
(D-020/D-037). Creates THREE tables and adds ONE nullable column to inv_stock_moves via
batch_alter_table (D-022). inv_stock_moves is NOT trigger-bearing, so the SQLite copy-rebuild has no
triggers to re-create (the D-022 rule only bites on trigger-bearing tables). All DDL is portable
across SQLite and Postgres; every identifier is <= 63 chars (PG cap).

- inv_item_valuations: the moving-average state per (item, warehouse). UNIQUE(tenant, item,
  warehouse) upsert/lock target; CHECK(on_hand_qty >= 0) (value side of no-negative-stock, D-020);
  (tenant, item) index.
- inv_cost_layers: FIFO layers, one per receipt. Composite tenant FKs to items, warehouses and the
  receipt move; CHECK(0 <= remaining_qty <= original_qty); (tenant, item, warehouse, received_at)
  FIFO-scan index + (tenant, receipt_move_id) FK index.
- inv_layer_consumptions: one row per layer an issue touched (audit trail + exact reversal record).
  Composite tenant FKs to the issue move and the layer; (tenant, issue_move_id) and (tenant,
  layer_id) FK indexes.
- inv_stock_moves.unit_cost: MoneyType nullable — the RECEIPT entry cost / the computed ISSUE cost.
"""

import sqlalchemy as sa
from alembic import op

from app.core.money import MoneyType, QuantityType

# revision identifiers, used by Alembic.
revision: str = "0022"
down_revision: str | None = "0021"
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
        "inv_item_valuations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("warehouse_id", sa.Uuid(), nullable=False),
        sa.Column("on_hand_qty", QuantityType(), nullable=False),
        sa.Column("avg_unit_cost", MoneyType(), nullable=False),
        sa.Column("total_value", MoneyType(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "on_hand_qty >= 0", name="ck_inv_item_valuations_on_hand_non_negative"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["adm_tenants.id"], name="fk_inv_item_valuations_tenant_id_adm_tenants"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "item_id"],
            ["inv_items.tenant_id", "inv_items.id"],
            name="fk_inv_item_valuations_tenant_id_inv_items",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "warehouse_id"],
            ["inv_warehouses.tenant_id", "inv_warehouses.id"],
            name="fk_inv_item_valuations_tenant_id_inv_warehouses",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_inv_item_valuations"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_inv_item_valuations_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "item_id",
            "warehouse_id",
            name="uq_inv_item_valuations_tenant_id_item_id_warehouse_id",
        ),
    )
    op.create_index(
        "ix_inv_item_valuations_tenant_id", "inv_item_valuations", ["tenant_id"]
    )
    op.create_index(
        "ix_inv_item_valuations_tenant_id_item_id",
        "inv_item_valuations",
        ["tenant_id", "item_id"],
    )

    op.create_table(
        "inv_cost_layers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("warehouse_id", sa.Uuid(), nullable=False),
        sa.Column("receipt_move_id", sa.Uuid(), nullable=False),
        sa.Column("received_at", sa.Date(), nullable=False),
        sa.Column("original_qty", QuantityType(), nullable=False),
        sa.Column("remaining_qty", QuantityType(), nullable=False),
        sa.Column("unit_cost", MoneyType(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "remaining_qty >= 0 AND remaining_qty <= original_qty",
            name="ck_inv_cost_layers_remaining_within_original",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["adm_tenants.id"], name="fk_inv_cost_layers_tenant_id_adm_tenants"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "item_id"],
            ["inv_items.tenant_id", "inv_items.id"],
            name="fk_inv_cost_layers_tenant_id_inv_items",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "warehouse_id"],
            ["inv_warehouses.tenant_id", "inv_warehouses.id"],
            name="fk_inv_cost_layers_tenant_id_inv_warehouses",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "receipt_move_id"],
            ["inv_stock_moves.tenant_id", "inv_stock_moves.id"],
            name="fk_inv_cost_layers_tenant_id_inv_stock_moves",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_inv_cost_layers"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_inv_cost_layers_tenant_id"),
    )
    op.create_index("ix_inv_cost_layers_tenant_id", "inv_cost_layers", ["tenant_id"])
    op.create_index(
        "ix_inv_cost_layers_tenant_id_item_id_warehouse_id_received_at",
        "inv_cost_layers",
        ["tenant_id", "item_id", "warehouse_id", "received_at"],
    )
    op.create_index(
        "ix_inv_cost_layers_tenant_id_receipt_move_id",
        "inv_cost_layers",
        ["tenant_id", "receipt_move_id"],
    )

    op.create_table(
        "inv_layer_consumptions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("issue_move_id", sa.Uuid(), nullable=False),
        sa.Column("layer_id", sa.Uuid(), nullable=False),
        sa.Column("qty", QuantityType(), nullable=False),
        sa.Column("cost", MoneyType(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["adm_tenants.id"],
            name="fk_inv_layer_consumptions_tenant_id_adm_tenants",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "issue_move_id"],
            ["inv_stock_moves.tenant_id", "inv_stock_moves.id"],
            name="fk_inv_layer_consumptions_tenant_id_inv_stock_moves",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "layer_id"],
            ["inv_cost_layers.tenant_id", "inv_cost_layers.id"],
            name="fk_inv_layer_consumptions_tenant_id_inv_cost_layers",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_inv_layer_consumptions"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_inv_layer_consumptions_tenant_id"),
    )
    op.create_index(
        "ix_inv_layer_consumptions_tenant_id", "inv_layer_consumptions", ["tenant_id"]
    )
    op.create_index(
        "ix_inv_layer_consumptions_tenant_id_issue_move_id",
        "inv_layer_consumptions",
        ["tenant_id", "issue_move_id"],
    )
    op.create_index(
        "ix_inv_layer_consumptions_tenant_id_layer_id",
        "inv_layer_consumptions",
        ["tenant_id", "layer_id"],
    )

    # The costing unit_cost on the move ledger (D-020). inv_stock_moves is NOT trigger-bearing, so
    # the SQLite batch copy-rebuild has no triggers to re-create (D-022). Nullable: pre-5.3 rows
    # carried none and the engine fills it.
    with op.batch_alter_table("inv_stock_moves") as batch_op:
        batch_op.add_column(sa.Column("unit_cost", MoneyType(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("inv_stock_moves") as batch_op:
        batch_op.drop_column("unit_cost")
    op.drop_table("inv_layer_consumptions")
    op.drop_table("inv_cost_layers")
    op.drop_table("inv_item_valuations")
