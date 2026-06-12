"""finance accounts receivable: customer invoices, receipts and receipt allocations

Revision ID: 0013
Revises: 0012
Create Date: 2026-06-12

PLAN 4.6 / D-029 — Accounts Receivable (the AP migration 0012 mirror, sign flipped):

- fin_customer_invoices: the customer-invoice header. ``partner_id`` is an OPAQUE customer id
  (D-029) — NO FK to any partner master (the customer master lives in sales, above finance).
  DocumentMixin (NOT NULL ``document_id`` -> core_documents) so an invoice cannot exist without a
  registry entry; ``invoice_number`` (the system number) is NULL until posting. Composite tenant FKs
  to fin_accounts (``ar_account_id``) and fin_journal_entries (``journal_entry_id``). Money columns
  are MoneyType (D-015); ``open_amount`` is the still-owed balance aging reads. ``dunning_level`` +
  ``last_dunned_date`` carry the dunning state the dunning run advances (it posts no journal).
- fin_customer_invoice_lines: the revenue lines; composite tenant FKs to the invoice, the line
  account, and (nullable) the tax code. UNIQUE(tenant, invoice_id, line_number).
- fin_customer_receipts: the receipt header; DocumentMixin; composite tenant FKs to the bank account
  and the clearing journal entry. ``receipt_number`` NULL until posting.
- fin_customer_receipt_allocations: which invoices a receipt clears + by how much.
  UNIQUE(tenant, receipt_id, customer_invoice_id) so a receipt clears each invoice at most once.

This migration creates FOUR new tables and alters NOTHING. The four journal guard triggers
(migration 0009) live on fin_journal_entries / fin_journal_lines — AR tables are independent, so no
trigger-bearing table is touched and there is no trigger-recreation concern (D-022). All DDL is
portable across SQLite and Postgres. Composite-tenant FK names follow the D-022 column-0 convention
(``fk_<table>_tenant_id_<target>``) so they MATCH what the models generate; every identifier is
<= 63 chars (the Postgres limit), including the abbreviated allocations + line UNIQUE names.
"""

import sqlalchemy as sa
from alembic import op

from app.core.money import MoneyType

# revision identifiers, used by Alembic.
revision: str = "0013"
down_revision: str | None = "0012"
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


def _create_customer_invoices() -> None:
    op.create_table(
        "fin_customer_invoices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        # Opaque customer id (D-029): no FK to any partner master.
        sa.Column("partner_id", sa.Uuid(), nullable=False),
        sa.Column("partner_name", sa.String(length=200), nullable=False),
        sa.Column("external_ref", sa.String(length=60), nullable=True),
        sa.Column("invoice_number", sa.String(length=60), nullable=True),
        sa.Column("invoice_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="DRAFT", nullable=False),
        sa.Column("ar_account_id", sa.Uuid(), nullable=False),
        sa.Column("journal_entry_id", sa.Uuid(), nullable=True),
        sa.Column("gross_amount", MoneyType(), server_default="0", nullable=False),
        sa.Column("tax_amount", MoneyType(), server_default="0", nullable=False),
        sa.Column("net_amount", MoneyType(), server_default="0", nullable=False),
        sa.Column("open_amount", MoneyType(), server_default="0", nullable=False),
        sa.Column("dunning_level", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_dunned_date", sa.Date(), nullable=True),
        sa.Column("description", sa.String(length=500), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["adm_tenants.id"],
            name="fk_fin_customer_invoices_tenant_id_adm_tenants",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["core_documents.tenant_id", "core_documents.id"],
            name="fk_fin_customer_invoices_tenant_id_core_documents",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "ar_account_id"],
            ["fin_accounts.tenant_id", "fin_accounts.id"],
            name="fk_fin_customer_invoices_tenant_id_fin_accounts",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "journal_entry_id"],
            ["fin_journal_entries.tenant_id", "fin_journal_entries.id"],
            name="fk_fin_customer_invoices_tenant_id_fin_journal_entries",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_fin_customer_invoices"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_fin_customer_invoices_tenant_id"),
        sa.UniqueConstraint("document_id", name="uq_fin_customer_invoices_document_id"),
    )
    op.create_index("ix_fin_customer_invoices_tenant_id", "fin_customer_invoices", ["tenant_id"])


def _create_customer_invoice_lines() -> None:
    op.create_table(
        "fin_customer_invoice_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("invoice_id", sa.Uuid(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("net_amount", MoneyType(), nullable=False),
        sa.Column("tax_code_id", sa.Uuid(), nullable=True),
        sa.Column("tax_amount", MoneyType(), server_default="0", nullable=False),
        sa.Column("cost_center_id", sa.Uuid(), nullable=True),
        sa.Column("profit_center_id", sa.Uuid(), nullable=True),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["adm_tenants.id"],
            name="fk_fin_customer_invoice_lines_tenant_id_adm_tenants",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "invoice_id"],
            ["fin_customer_invoices.tenant_id", "fin_customer_invoices.id"],
            name="fk_fin_customer_invoice_lines_tenant_id_fin_customer_invoices",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "account_id"],
            ["fin_accounts.tenant_id", "fin_accounts.id"],
            name="fk_fin_customer_invoice_lines_tenant_id_fin_accounts",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "tax_code_id"],
            ["fin_tax_codes.tenant_id", "fin_tax_codes.id"],
            name="fk_fin_customer_invoice_lines_tenant_id_fin_tax_codes",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_fin_customer_invoice_lines"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_fin_customer_invoice_lines_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id", "invoice_id", "line_number",
            name="uq_fin_customer_invoice_lines_invoice_line",
        ),
    )
    op.create_index(
        "ix_fin_customer_invoice_lines_tenant_id", "fin_customer_invoice_lines", ["tenant_id"]
    )


def _create_customer_receipts() -> None:
    op.create_table(
        "fin_customer_receipts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("partner_id", sa.Uuid(), nullable=False),
        sa.Column("partner_name", sa.String(length=200), nullable=False),
        sa.Column("receipt_number", sa.String(length=60), nullable=True),
        sa.Column("receipt_date", sa.Date(), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("bank_account_id", sa.Uuid(), nullable=False),
        sa.Column("amount", MoneyType(), nullable=False),
        sa.Column("journal_entry_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="POSTED", nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["adm_tenants.id"],
            name="fk_fin_customer_receipts_tenant_id_adm_tenants",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["core_documents.tenant_id", "core_documents.id"],
            name="fk_fin_customer_receipts_tenant_id_core_documents",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "bank_account_id"],
            ["fin_accounts.tenant_id", "fin_accounts.id"],
            name="fk_fin_customer_receipts_tenant_id_fin_accounts",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "journal_entry_id"],
            ["fin_journal_entries.tenant_id", "fin_journal_entries.id"],
            name="fk_fin_customer_receipts_tenant_id_fin_journal_entries",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_fin_customer_receipts"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_fin_customer_receipts_tenant_id"),
        sa.UniqueConstraint("document_id", name="uq_fin_customer_receipts_document_id"),
    )
    op.create_index("ix_fin_customer_receipts_tenant_id", "fin_customer_receipts", ["tenant_id"])


def _create_customer_receipt_allocations() -> None:
    op.create_table(
        "fin_customer_receipt_allocations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("receipt_id", sa.Uuid(), nullable=False),
        sa.Column("customer_invoice_id", sa.Uuid(), nullable=False),
        sa.Column("allocated_amount", MoneyType(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["adm_tenants.id"],
            name="fk_fin_customer_receipt_allocations_tenant_id_adm_tenants",
        ),
        # Abbreviated explicit names: the D-022 auto name for these two composite FKs would be 67
        # chars — over PG's 63-char identifier cap — so the model + this migration share the short
        # name (matching the model keeps autogenerate drift-free).
        sa.ForeignKeyConstraint(
            ["tenant_id", "receipt_id"],
            ["fin_customer_receipts.tenant_id", "fin_customer_receipts.id"],
            name="fk_fin_cust_receipt_allocs_tenant_id_receipts",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "customer_invoice_id"],
            ["fin_customer_invoices.tenant_id", "fin_customer_invoices.id"],
            name="fk_fin_cust_receipt_allocs_tenant_id_invoices",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_fin_customer_receipt_allocations"),
        sa.UniqueConstraint(
            "tenant_id", "id", name="uq_fin_customer_receipt_allocations_tenant_id"
        ),
        # Abbreviated explicit name: PG caps identifiers at 63 chars (a fully-qualified
        # tenant_id_receipt_id_customer_invoice_id name would overflow).
        sa.UniqueConstraint(
            "tenant_id", "receipt_id", "customer_invoice_id",
            name="uq_fin_customer_receipt_allocations_receipt_invoice",
        ),
    )
    op.create_index(
        "ix_fin_customer_receipt_allocations_tenant_id",
        "fin_customer_receipt_allocations",
        ["tenant_id"],
    )


def upgrade() -> None:
    _create_customer_invoices()
    _create_customer_invoice_lines()
    _create_customer_receipts()
    _create_customer_receipt_allocations()


def downgrade() -> None:
    op.drop_index(
        "ix_fin_customer_receipt_allocations_tenant_id",
        table_name="fin_customer_receipt_allocations",
    )
    op.drop_table("fin_customer_receipt_allocations")
    op.drop_index("ix_fin_customer_receipts_tenant_id", table_name="fin_customer_receipts")
    op.drop_table("fin_customer_receipts")
    op.drop_index(
        "ix_fin_customer_invoice_lines_tenant_id", table_name="fin_customer_invoice_lines"
    )
    op.drop_table("fin_customer_invoice_lines")
    op.drop_index("ix_fin_customer_invoices_tenant_id", table_name="fin_customer_invoices")
    op.drop_table("fin_customer_invoices")
