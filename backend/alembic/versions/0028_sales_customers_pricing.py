"""sales customer master + condition-style pricing

Revision ID: 0028
Revises: 0027
Create Date: 2026-06-13

PLAN 7.1 — opens the sales module with the customer master + the condition-style pricing engine.
Creates FOUR tables and alters NOTHING — no trigger-bearing table is touched (D-022), so there is no
trigger-recreation concern. All DDL is portable across SQLite and Postgres; every identifier is <=
63 chars (PG cap). MoneyType/QuantityType render as NUMERIC(18,6) on Postgres / INTEGER micro-units
on SQLite (D-015) via the model's column types — imported from app.core.money so the revision stays
dialect-clean.

- sales_customer_groups: the lean grouping master pricing keys on. UNIQUE(tenant_id, code).
- sales_customers: the customer master. UNIQUE(tenant_id, customer_code) (user-supplied code, no
  auto-number); nullable composite FK to sales_customer_groups (the optional pricing group); CHECKs
  payment_terms_days >= 0 and credit_limit >= 0; (tenant, status) index for the filtered list. The
  row id IS finance AR's opaque partner_id (D-029) — finance never FK-references this table.
- sales_price_lists: the condition header. UNIQUE(tenant_id, code); nullable composite FK to
  sales_customer_groups (NULL = a general list); CHECKs priority >= 0 and a coherent valid window;
  the (tenant, currency, group, valid_from) resolver index.
- sales_price_list_items: one base price per (list, item). Composite FK to sales_price_lists;
  item_id is an OPAQUE inventory item id (D-029 — a plain Uuid, NO FK to inv_items); CHECK
  min_quantity >= 0; UNIQUE(tenant, price_list_id, item_id); (tenant, price_list_id) + (tenant,
  item_id) indexes for the nested list + the resolver's item lookup.
"""

import sqlalchemy as sa
from alembic import op

from app.core.money import MoneyType, QuantityType

# revision identifiers, used by Alembic.
revision: str = "0028"
down_revision: str | None = "0027"
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
        "sales_customer_groups",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=60), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["adm_tenants.id"],
            name="fk_sales_customer_groups_tenant_id_adm_tenants",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_sales_customer_groups"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_sales_customer_groups_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id", "code", name="uq_sales_customer_groups_tenant_id_code"
        ),
    )
    op.create_index(
        "ix_sales_customer_groups_tenant_id", "sales_customer_groups", ["tenant_id"]
    )

    op.create_table(
        "sales_customers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("customer_code", sa.String(length=60), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ACTIVE"),
        sa.Column("customer_group_id", sa.Uuid(), nullable=True),
        sa.Column("default_currency_code", sa.String(length=3), nullable=False),
        sa.Column("payment_terms_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("credit_limit", MoneyType(), nullable=False, server_default="0"),
        sa.Column("tax_reference", sa.String(length=60), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("phone", sa.String(length=40), nullable=True),
        sa.Column("address", sa.String(length=500), nullable=True),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "payment_terms_days >= 0",
            name="ck_sales_customers_payment_terms_days_non_negative",
        ),
        sa.CheckConstraint(
            "credit_limit >= 0", name="ck_sales_customers_credit_limit_non_negative"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["adm_tenants.id"], name="fk_sales_customers_tenant_id_adm_tenants"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "customer_group_id"],
            ["sales_customer_groups.tenant_id", "sales_customer_groups.id"],
            name="fk_sales_customers_customer_group_id_sales_customer_groups",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_sales_customers"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_sales_customers_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id", "customer_code", name="uq_sales_customers_tenant_id_customer_code"
        ),
    )
    op.create_index("ix_sales_customers_tenant_id", "sales_customers", ["tenant_id"])
    op.create_index(
        "ix_sales_customers_tenant_id_status", "sales_customers", ["tenant_id", "status"]
    )

    op.create_table(
        "sales_price_lists",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=60), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("customer_group_id", sa.Uuid(), nullable=True),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ACTIVE"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        *_timestamps(),
        sa.CheckConstraint(
            "priority >= 0", name="ck_sales_price_lists_priority_non_negative"
        ),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from",
            name="ck_sales_price_lists_valid_window",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["adm_tenants.id"], name="fk_sales_price_lists_tenant_id_adm_tenants"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "customer_group_id"],
            ["sales_customer_groups.tenant_id", "sales_customer_groups.id"],
            name="fk_sales_price_lists_customer_group_id_sales_customer_groups",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_sales_price_lists"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_sales_price_lists_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id", "code", name="uq_sales_price_lists_tenant_id_code"
        ),
    )
    op.create_index("ix_sales_price_lists_tenant_id", "sales_price_lists", ["tenant_id"])
    op.create_index(
        "ix_sales_price_lists_resolver",
        "sales_price_lists",
        ["tenant_id", "currency_code", "customer_group_id", "valid_from"],
    )

    op.create_table(
        "sales_price_list_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("price_list_id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("unit_price", MoneyType(), nullable=False),
        sa.Column("min_quantity", QuantityType(), nullable=False, server_default="0"),
        *_timestamps(),
        sa.CheckConstraint(
            "min_quantity >= 0",
            name="ck_sales_price_list_items_min_quantity_non_negative",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["adm_tenants.id"],
            name="fk_sales_price_list_items_tenant_id_adm_tenants",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "price_list_id"],
            ["sales_price_lists.tenant_id", "sales_price_lists.id"],
            name="fk_sales_price_list_items_price_list_id_sales_price_lists",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_sales_price_list_items"),
        sa.UniqueConstraint(
            "tenant_id", "id", name="uq_sales_price_list_items_tenant_id"
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "price_list_id",
            "item_id",
            name="uq_sales_price_list_items_tenant_id_price_list_id_item_id",
        ),
    )
    op.create_index(
        "ix_sales_price_list_items_tenant_id",
        "sales_price_list_items",
        ["tenant_id"],
    )
    op.create_index(
        "ix_sales_price_list_items_tenant_id_price_list_id",
        "sales_price_list_items",
        ["tenant_id", "price_list_id"],
    )
    op.create_index(
        "ix_sales_price_list_items_tenant_id_item_id",
        "sales_price_list_items",
        ["tenant_id", "item_id"],
    )


def downgrade() -> None:
    op.drop_table("sales_price_list_items")
    op.drop_table("sales_price_lists")
    op.drop_table("sales_customers")
    op.drop_table("sales_customer_groups")
