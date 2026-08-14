"""hospitality menu availability

Revision ID: 0047
Revises: 0046
Create Date: 2026-08-14

hsp_menu_availability — the stored menu-availability row (PLAN 19, spec Q2). One row per sellable
inventory item, UNIQUE on (tenant_id, item_id): that constraint IS the index the batched guest read
uses, so no second index is created. `item_id` is an OPAQUE inventory id (D-029) with no FK into
inv_items; only the D-007 composite-FK backstops on tenant_id are declared. Constraint names are
spelled out per the D-022 convention so SQLite batch mode can drop them later. No audit trigger and
no AuditMixin: 86-ing is shift-scoped churn, which is precisely why it is not a flag on inv_items.
"""

import sqlalchemy as sa
from alembic import op

from app.core.money import QuantityType

# revision identifiers, used by Alembic.
revision: str = "0047"
down_revision: str | None = "0046"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "hsp_menu_availability",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(length=20), server_default="AVAILABLE", nullable=False),
        sa.Column("remaining_qty", QuantityType(), nullable=True),
        sa.Column("available_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.String(length=200), nullable=True),
        sa.Column("source", sa.String(length=10), server_default="MANUAL", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "remaining_qty IS NULL OR remaining_qty >= 0",
            name="ck_hsp_menu_availability_remaining_non_negative",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["adm_tenants.id"],
            name="fk_hsp_menu_availability_tenant_id_adm_tenants",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_hsp_menu_availability"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_hsp_menu_availability_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id", "item_id", name="uq_hsp_menu_availability_tenant_id_item_id"
        ),
    )
    op.create_index("ix_hsp_menu_availability_tenant_id", "hsp_menu_availability", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("hsp_menu_availability")
