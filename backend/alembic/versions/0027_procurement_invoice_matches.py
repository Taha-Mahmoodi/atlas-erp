"""procurement invoice matches: header + lines + tolerances + PO billed_quantity

Revision ID: 0027
Revises: 0026
Create Date: 2026-06-13

PLAN 6.4 — the 3-way-match document (match → AP vendor bill clearing GR/IR + reorder requisitions).
Creates THREE tables (the match header + line pair + the per-tenant tolerance config) and ADDS one
column (``billed_quantity`` on proc_purchase_order_lines, the 6.4 over-billing counter — like 6.3's
``received_quantity``). NO trigger-bearing table is touched (procurement has no triggers; D-022), so
there is no trigger-recreation concern, and ``billed_quantity`` is a plain add_column with a
``server_default`` of '0' so existing rows back-fill. The PPV / AP-control posting purposes are DATA
(posting defaults), not schema — neither lands here. All DDL is portable across SQLite and Postgres;
every identifier is <= 63 chars (PG cap).

The header mixes in DocumentMixin: a NOT NULL document_id with a composite tenant FK to
core_documents and a UNIQUE(document_id). Money/quantity columns use MoneyType / QuantityType
(D-015). Every table carries the D-007 backstop (tenant_fk to adm_tenants + UNIQUE(tenant_id, id))
and intra-module composite tenant FKs. FK / UNIQUE / CHECK names follow the D-022 convention so
autogenerate reports zero drift on SQLite AND Postgres.

- proc_invoice_matches: the match header (composite FK to proc_purchase_orders; opaque
  vendor / GR-IR / tax-code ids). (tenant, status) + (tenant, purchase_order_id) indexes (§1).
- proc_invoice_match_lines: the match lines (composite FKs to proc_purchase_order_lines + nullable
  proc_goods_receipt_lines; opaque item id; variances + within_tolerance flag).
  UNIQUE(tenant, match_id, line_number).
- proc_match_tolerances: the single-per-tenant tolerance config (UNIQUE(tenant_id); non-negative
  percentage CHECKs).
"""

import sqlalchemy as sa
from alembic import op

from app.core.money import MoneyType, QuantityType

# revision identifiers, used by Alembic.
revision: str = "0027"
down_revision: str | None = "0026"
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


def _create_invoice_matches() -> None:
    op.create_table(
        "proc_invoice_matches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("match_number", sa.String(length=60), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="DRAFT"),
        sa.Column("purchase_order_id", sa.Uuid(), nullable=False),
        sa.Column("vendor_id", sa.Uuid(), nullable=False),
        sa.Column("vendor_invoice_ref", sa.String(length=120), nullable=True),
        sa.Column("invoice_date", sa.Date(), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("total_amount", MoneyType(), nullable=False),
        sa.Column("tax_code_id", sa.Uuid(), nullable=True),
        sa.Column("gr_ir_account_id", sa.Uuid(), nullable=False),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        _tenant_root_fk("proc_invoice_matches"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["core_documents.tenant_id", "core_documents.id"],
            name="fk_proc_invoice_matches_tenant_id_core_documents",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "purchase_order_id"],
            ["proc_purchase_orders.tenant_id", "proc_purchase_orders.id"],
            name="fk_proc_invoice_matches_tenant_id_proc_purchase_orders",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_proc_invoice_matches"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_proc_invoice_matches_tenant_id"),
        sa.UniqueConstraint("document_id", name="uq_proc_invoice_matches_document_id"),
    )
    op.create_index("ix_proc_invoice_matches_tenant_id", "proc_invoice_matches", ["tenant_id"])
    op.create_index(
        "ix_proc_invoice_matches_tenant_id_status",
        "proc_invoice_matches",
        ["tenant_id", "status"],
    )
    op.create_index(
        "ix_proc_invoice_matches_tenant_id_purchase_order_id",
        "proc_invoice_matches",
        ["tenant_id", "purchase_order_id"],
    )

    op.create_table(
        "proc_invoice_match_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("match_id", sa.Uuid(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("purchase_order_line_id", sa.Uuid(), nullable=False),
        sa.Column("goods_receipt_line_id", sa.Uuid(), nullable=True),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("matched_quantity", QuantityType(), nullable=False),
        sa.Column("unit_price", MoneyType(), nullable=False),
        sa.Column("po_unit_cost", MoneyType(), nullable=False),
        sa.Column("price_variance", MoneyType(), nullable=False, server_default="0"),
        sa.Column("quantity_variance", QuantityType(), nullable=False, server_default="0"),
        sa.Column("line_amount", MoneyType(), nullable=False),
        sa.Column("within_tolerance", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_timestamps(),
        _tenant_root_fk("proc_invoice_match_lines"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "match_id"],
            ["proc_invoice_matches.tenant_id", "proc_invoice_matches.id"],
            name="fk_proc_invoice_match_lines_tenant_id_proc_invoice_matches",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "purchase_order_line_id"],
            ["proc_purchase_order_lines.tenant_id", "proc_purchase_order_lines.id"],
            name="fk_proc_invoice_match_lines_tenant_id_proc_purchase_order_lines",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "goods_receipt_line_id"],
            ["proc_goods_receipt_lines.tenant_id", "proc_goods_receipt_lines.id"],
            name="fk_proc_invoice_match_lines_tenant_id_proc_goods_receipt_lines",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_proc_invoice_match_lines"),
        sa.UniqueConstraint(
            "tenant_id", "id", name="uq_proc_invoice_match_lines_tenant_id"
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "match_id",
            "line_number",
            name="uq_proc_invoice_match_lines_match_line",
        ),
    )
    op.create_index(
        "ix_proc_invoice_match_lines_tenant_id", "proc_invoice_match_lines", ["tenant_id"]
    )


def _create_match_tolerances() -> None:
    op.create_table(
        "proc_match_tolerances",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column(
            "price_tolerance_percent", MoneyType(), nullable=False, server_default="0"
        ),
        sa.Column(
            "quantity_tolerance_percent", MoneyType(), nullable=False, server_default="0"
        ),
        *_timestamps(),
        sa.CheckConstraint(
            "price_tolerance_percent >= 0",
            name="ck_proc_match_tolerances_price_tolerance_non_negative",
        ),
        sa.CheckConstraint(
            "quantity_tolerance_percent >= 0",
            name="ck_proc_match_tolerances_quantity_tolerance_non_negative",
        ),
        _tenant_root_fk("proc_match_tolerances"),
        sa.PrimaryKeyConstraint("id", name="pk_proc_match_tolerances"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_proc_match_tolerances_tenant_id"),
        sa.UniqueConstraint("tenant_id", name="uq_proc_match_tolerances_tenant"),
    )
    op.create_index(
        "ix_proc_match_tolerances_tenant_id", "proc_match_tolerances", ["tenant_id"]
    )


def upgrade() -> None:
    _create_invoice_matches()
    _create_match_tolerances()
    # The 6.4 over-billing counter on the PO line (proc_purchase_order_lines has no trigger, so a
    # plain add_column with a server_default back-fills existing rows — the 6.3 received_quantity
    # precedent). received − billed is the open-to-bill quantity a match line cannot exceed.
    op.add_column(
        "proc_purchase_order_lines",
        sa.Column("billed_quantity", QuantityType(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("proc_purchase_order_lines", "billed_quantity")
    op.drop_table("proc_match_tolerances")
    op.drop_table("proc_invoice_match_lines")
    op.drop_table("proc_invoice_matches")
