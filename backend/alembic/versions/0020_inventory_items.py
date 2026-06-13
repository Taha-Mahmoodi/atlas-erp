"""inventory item masters: categories, uoms, items, uom conversions, lots, serials

Revision ID: 0020
Revises: 0019
Create Date: 2026-06-13

PLAN 5.1 — inventory item masters. Creates SIX tables and alters NOTHING — no trigger-bearing
table is touched, so there is no trigger-recreation concern (D-022). All DDL is portable across
SQLite and Postgres; every identifier is <= 63 chars (PG cap).

- inv_item_categories: default costing method + the THREE opaque finance GL-account ids COGS
  posting needs (inventory/cogs/price-difference), stored as plain Uuid (D-029: validated in the
  service via finance/queries, NOT a cross-module FK). UNIQUE(tenant, code).
- inv_uoms: unit-of-measure definitions (EA, KG, BOX...). UNIQUE(tenant, code).
- inv_items: the item master. UNIQUE(tenant, item_code); composite tenant FKs to categories and
  uoms (base_uom); QuantityType reorder columns. The list filters on
  (tenant, item_type, category_id, is_active) — the composite index serves that, plus a
  (tenant, category_id) FK index (PERFORMANCE §1).
- inv_uom_conversions: per-item alternate UoM + factor_to_base (the chosen convention). CHECK
  factor_to_base > 0; UNIQUE(tenant, item_id, alt_uom_id); (tenant, item_id) FK index.
- inv_lots / inv_serials: master tables for lot/serial instances — defined now, populated by
  receipts (5.2+). UNIQUE(tenant, item, code); (tenant, item_id) FK index each.
"""

import sqlalchemy as sa
from alembic import op

from app.core.money import QuantityType

# revision identifiers, used by Alembic.
revision: str = "0020"
down_revision: str | None = "0019"
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
        "inv_item_categories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "default_costing_method",
            sa.String(length=20),
            server_default="MOVING_AVERAGE",
            nullable=False,
        ),
        sa.Column("inventory_account_id", sa.Uuid(), nullable=True),
        sa.Column("cogs_account_id", sa.Uuid(), nullable=True),
        sa.Column("price_difference_account_id", sa.Uuid(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["adm_tenants.id"],
            name="fk_inv_item_categories_tenant_id_adm_tenants",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_inv_item_categories"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_inv_item_categories_tenant_id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_inv_item_categories_tenant_id_code"),
    )
    op.create_index(
        "ix_inv_item_categories_tenant_id", "inv_item_categories", ["tenant_id"]
    )

    op.create_table(
        "inv_uoms",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["adm_tenants.id"], name="fk_inv_uoms_tenant_id_adm_tenants"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_inv_uoms"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_inv_uoms_tenant_id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_inv_uoms_tenant_id_code"),
    )
    op.create_index("ix_inv_uoms_tenant_id", "inv_uoms", ["tenant_id"])

    op.create_table(
        "inv_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("item_code", sa.String(length=60), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=True),
        sa.Column("item_type", sa.String(length=20), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=False),
        sa.Column("base_uom_id", sa.Uuid(), nullable=False),
        sa.Column("costing_method", sa.String(length=20), nullable=False),
        sa.Column("tracking_mode", sa.String(length=10), server_default="NONE", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("reorder_point", QuantityType(), nullable=True),
        sa.Column("reorder_quantity", QuantityType(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["adm_tenants.id"], name="fk_inv_items_tenant_id_adm_tenants"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "category_id"],
            ["inv_item_categories.tenant_id", "inv_item_categories.id"],
            name="fk_inv_items_tenant_id_inv_item_categories",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "base_uom_id"],
            ["inv_uoms.tenant_id", "inv_uoms.id"],
            name="fk_inv_items_tenant_id_inv_uoms",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_inv_items"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_inv_items_tenant_id"),
        sa.UniqueConstraint("tenant_id", "item_code", name="uq_inv_items_tenant_id_item_code"),
    )
    op.create_index("ix_inv_items_tenant_id", "inv_items", ["tenant_id"])
    op.create_index(
        "ix_inv_items_tenant_id_category_id", "inv_items", ["tenant_id", "category_id"]
    )
    op.create_index(
        "ix_inv_items_tenant_id_item_type_category_id_is_active",
        "inv_items",
        ["tenant_id", "item_type", "category_id", "is_active"],
    )

    op.create_table(
        "inv_uom_conversions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("alt_uom_id", sa.Uuid(), nullable=False),
        sa.Column("factor_to_base", QuantityType(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "factor_to_base > 0", name="ck_inv_uom_conversions_factor_positive"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["adm_tenants.id"],
            name="fk_inv_uom_conversions_tenant_id_adm_tenants",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "item_id"],
            ["inv_items.tenant_id", "inv_items.id"],
            name="fk_inv_uom_conversions_tenant_id_inv_items",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "alt_uom_id"],
            ["inv_uoms.tenant_id", "inv_uoms.id"],
            name="fk_inv_uom_conversions_tenant_id_inv_uoms",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_inv_uom_conversions"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_inv_uom_conversions_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "item_id",
            "alt_uom_id",
            name="uq_inv_uom_conversions_tenant_id_item_id_alt_uom_id",
        ),
    )
    op.create_index(
        "ix_inv_uom_conversions_tenant_id", "inv_uom_conversions", ["tenant_id"]
    )
    op.create_index(
        "ix_inv_uom_conversions_tenant_id_item_id",
        "inv_uom_conversions",
        ["tenant_id", "item_id"],
    )

    op.create_table(
        "inv_lots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("lot_code", sa.String(length=60), nullable=False),
        sa.Column("status", sa.String(length=12), server_default="AVAILABLE", nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["adm_tenants.id"], name="fk_inv_lots_tenant_id_adm_tenants"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "item_id"],
            ["inv_items.tenant_id", "inv_items.id"],
            name="fk_inv_lots_tenant_id_inv_items",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_inv_lots"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_inv_lots_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id", "item_id", "lot_code", name="uq_inv_lots_tenant_id_item_id_lot_code"
        ),
    )
    op.create_index("ix_inv_lots_tenant_id", "inv_lots", ["tenant_id"])
    op.create_index("ix_inv_lots_tenant_id_item_id", "inv_lots", ["tenant_id", "item_id"])

    op.create_table(
        "inv_serials",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("serial_code", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=12), server_default="IN_STOCK", nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["adm_tenants.id"], name="fk_inv_serials_tenant_id_adm_tenants"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "item_id"],
            ["inv_items.tenant_id", "inv_items.id"],
            name="fk_inv_serials_tenant_id_inv_items",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_inv_serials"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_inv_serials_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "item_id",
            "serial_code",
            name="uq_inv_serials_tenant_id_item_id_serial_code",
        ),
    )
    op.create_index("ix_inv_serials_tenant_id", "inv_serials", ["tenant_id"])
    op.create_index(
        "ix_inv_serials_tenant_id_item_id", "inv_serials", ["tenant_id", "item_id"]
    )


def downgrade() -> None:
    op.drop_table("inv_serials")
    op.drop_table("inv_lots")
    op.drop_table("inv_uom_conversions")
    op.drop_table("inv_items")
    op.drop_table("inv_uoms")
    op.drop_table("inv_item_categories")
