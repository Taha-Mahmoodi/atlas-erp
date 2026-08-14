"""hospitality order tickets

Revision ID: 0048
Revises: 0047
Create Date: 2026-08-14

PLAN 19 Task 4 — the order ticket (the check for one table) and its lines. Creates TWO tables and
alters NOTHING, so no trigger-bearing table is touched (D-022) and there is no trigger-recreation
concern. All DDL is portable across SQLite and Postgres; every identifier is <= 63 chars (PG cap).
MoneyType / QuantityType render as NUMERIC(18,6) on Postgres and INTEGER micro-units on SQLite
(D-015) via the model column types, imported from app.core.money so the revision stays
dialect-clean.

- hsp_order_tickets: the header. DocumentMixin (composite FK to core_documents) — a ticket is a
  D-012 document that claims its gapless TKT- number at creation. UNIQUE(tenant_id, ticket_number);
  CHECKs total_amount >= 0 and guest_count > 0; a (tenant, opened_date, status) filter index for the
  floor/KDS list. No currency_code column: a property's checks are all in the tenant's functional
  currency (D-019), the inventory-move / production-order precedent.
- hsp_order_ticket_lines: one ordered dish. Composite tenant FK to the header;
  UNIQUE(tenant_id, ticket_id, line_number); CHECKs quantity > 0, unit_price >= 0, seat_number > 0.
  item_id is an OPAQUE inventory id (D-029) — no FK into inv_items. No uom_id: quantity is always in
  the item's base UoM, which is the basis its recipe BOM explodes against.

Audit is written by the D-010 Python listeners off AuditMixin, not by DDL, so the header needs no
trigger here.
"""

import sqlalchemy as sa
from alembic import op

from app.core.money import MoneyType, QuantityType

# revision identifiers, used by Alembic.
revision: str = "0048"
down_revision: str | None = "0047"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "hsp_order_tickets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("ticket_number", sa.String(length=60), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="OPEN", nullable=False),
        sa.Column("opened_date", sa.Date(), nullable=False),
        sa.Column("table_code", sa.String(length=20), nullable=True),
        sa.Column("guest_count", sa.Integer(), nullable=True),
        sa.Column("fired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_amount", MoneyType(), server_default="0", nullable=False),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("total_amount >= 0", name="ck_hsp_order_tickets_total_non_negative"),
        sa.CheckConstraint(
            "guest_count IS NULL OR guest_count > 0",
            name="ck_hsp_order_tickets_guest_count_positive",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["adm_tenants.id"],
            name="fk_hsp_order_tickets_tenant_id_adm_tenants",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["core_documents.tenant_id", "core_documents.id"],
            name="fk_hsp_order_tickets_document_id_core_documents",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_hsp_order_tickets"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_hsp_order_tickets_tenant_id"),
        sa.UniqueConstraint("document_id", name="uq_hsp_order_tickets_document_id"),
        sa.UniqueConstraint(
            "tenant_id", "ticket_number", name="uq_hsp_order_tickets_tenant_id_ticket_number"
        ),
    )
    op.create_index("ix_hsp_order_tickets_tenant_id", "hsp_order_tickets", ["tenant_id"])
    op.create_index(
        "ix_hsp_order_tickets_tenant_id_opened_date_status",
        "hsp_order_tickets",
        ["tenant_id", "opened_date", "status"],
    )

    op.create_table(
        "hsp_order_ticket_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", QuantityType(), nullable=False),
        sa.Column("unit_price", MoneyType(), nullable=False),
        sa.Column("line_amount", MoneyType(), nullable=False),
        sa.Column("seat_number", sa.Integer(), nullable=True),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("quantity > 0", name="ck_hsp_order_ticket_lines_quantity_positive"),
        sa.CheckConstraint(
            "unit_price >= 0", name="ck_hsp_order_ticket_lines_unit_price_non_negative"
        ),
        sa.CheckConstraint(
            "seat_number IS NULL OR seat_number > 0",
            name="ck_hsp_order_ticket_lines_seat_positive",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["adm_tenants.id"],
            name="fk_hsp_order_ticket_lines_tenant_id_adm_tenants",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "ticket_id"],
            ["hsp_order_tickets.tenant_id", "hsp_order_tickets.id"],
            name="fk_hsp_order_ticket_lines_ticket_id_hsp_order_tickets",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_hsp_order_ticket_lines"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_hsp_order_ticket_lines_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "ticket_id",
            "line_number",
            name="uq_hsp_order_ticket_lines_ticket_line",
        ),
    )
    op.create_index(
        "ix_hsp_order_ticket_lines_tenant_id", "hsp_order_ticket_lines", ["tenant_id"]
    )


def downgrade() -> None:
    op.drop_table("hsp_order_ticket_lines")
    op.drop_table("hsp_order_tickets")
