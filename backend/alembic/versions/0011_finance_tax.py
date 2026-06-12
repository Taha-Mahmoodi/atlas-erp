"""finance tax: configurable line-level tax codes

Revision ID: 0011
Revises: 0010
Create Date: 2026-06-12

PLAN 4.4 — the tax engine:

- fin_tax_codes: the tenant's tax-code catalog. ``rate_percent`` is a MoneyType column (NUMERIC
  (18,6) on PG / scaled-integer micro-units on SQLite, D-015) holding a PERCENTAGE, not an amount.
  ``is_inclusive`` and ``is_active`` are booleans; ``tax_payable_account_id`` /
  ``tax_receivable_account_id`` are NULLABLE composite tenant FKs to fin_accounts (the OUTPUT/sales
  and INPUT/purchase tax accounts). UNIQUE(tenant_id, code) keys the code per tenant.

This migration creates ONE new table and alters NOTHING. The four journal guard triggers (migration
0009) live on fin_journal_entries / fin_journal_lines — tax codes are independent, so no
trigger-bearing table is touched and there is no trigger-recreation concern. All DDL is portable
across SQLite and Postgres; constraint/index names follow the D-022 convention.
"""

import sqlalchemy as sa
from alembic import op

from app.core.money import MoneyType

# revision identifiers, used by Alembic.
revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "fin_tax_codes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        # A PERCENTAGE (20 == 20%), exact decimal via MoneyType (D-015) — not a money amount.
        sa.Column("rate_percent", MoneyType(), nullable=False),
        sa.Column("jurisdiction", sa.String(length=20), nullable=True),
        sa.Column("is_inclusive", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("tax_payable_account_id", sa.Uuid(), nullable=True),
        sa.Column("tax_receivable_account_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["adm_tenants.id"],
            name=op.f("fk_fin_tax_codes_tenant_id_adm_tenants"),
        ),
        # Composite tenant FKs: a tax code's posting accounts must belong to the same tenant.
        sa.ForeignKeyConstraint(
            ["tenant_id", "tax_payable_account_id"],
            ["fin_accounts.tenant_id", "fin_accounts.id"],
            name=op.f("fk_fin_tax_codes_tax_payable_account_id_fin_accounts"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "tax_receivable_account_id"],
            ["fin_accounts.tenant_id", "fin_accounts.id"],
            name=op.f("fk_fin_tax_codes_tax_receivable_account_id_fin_accounts"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fin_tax_codes")),
        sa.UniqueConstraint("tenant_id", "id", name="uq_fin_tax_codes_tenant_id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_fin_tax_codes_tenant_id_code"),
    )
    op.create_index(op.f("ix_fin_tax_codes_tenant_id"), "fin_tax_codes", ["tenant_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_fin_tax_codes_tenant_id"), table_name="fin_tax_codes")
    op.drop_table("fin_tax_codes")
