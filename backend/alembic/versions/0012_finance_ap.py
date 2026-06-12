"""finance accounts payable: vendor bills, payments and payment allocations

Revision ID: 0012
Revises: 0011
Create Date: 2026-06-12

PLAN 4.5 / D-029 — Accounts Payable:

- fin_vendor_bills: the vendor-bill (supplier-invoice) header. ``partner_id`` is an OPAQUE vendor id
  (D-029) — NO FK to any partner master (the vendor master lives in procurement, above finance).
  DocumentMixin (NOT NULL ``document_id`` -> core_documents) so a bill cannot exist without a
  registry entry; ``bill_number`` (the system number) is NULL until posting. Composite tenant FKs to
  fin_accounts (``ap_account_id``) and fin_journal_entries (``journal_entry_id``, set at posting).
  Money columns are MoneyType (D-015); ``open_amount`` is the still-owed balance aging reads.
- fin_vendor_bill_lines: the expense/asset lines; composite tenant FKs to the bill, the line
  account, and (nullable) the tax code. UNIQUE(tenant, bill_id, line_number).
- fin_vendor_payments: the payment header; DocumentMixin; composite tenant FKs to the bank account
  and the clearing journal entry. ``payment_number`` NULL until posting.
- fin_vendor_payment_allocations: which bills a payment clears + by how much.
  UNIQUE(tenant, payment_id, vendor_bill_id) so a payment clears each bill at most once.

This migration creates FOUR new tables and alters NOTHING. The four journal guard triggers
(migration 0009) live on fin_journal_entries / fin_journal_lines — AP tables are independent, so no
trigger-bearing table is touched and there is no trigger-recreation concern (D-022). All DDL is
portable across SQLite and Postgres. Composite-tenant FK names follow the D-022 column-0 convention
(``fk_<table>_tenant_id_<target>``) so they MATCH what the models generate; every identifier is
<= 63 chars (the Postgres limit), including the abbreviated allocations UNIQUE name.
"""

import sqlalchemy as sa
from alembic import op

from app.core.money import MoneyType

# revision identifiers, used by Alembic.
revision: str = "0012"
down_revision: str | None = "0011"
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


def _create_vendor_bills() -> None:
    op.create_table(
        "fin_vendor_bills",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        # Opaque vendor id (D-029): no FK to any partner master.
        sa.Column("partner_id", sa.Uuid(), nullable=False),
        sa.Column("partner_name", sa.String(length=200), nullable=False),
        sa.Column("bill_external_ref", sa.String(length=60), nullable=True),
        sa.Column("bill_number", sa.String(length=60), nullable=True),
        sa.Column("bill_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="DRAFT", nullable=False),
        sa.Column("ap_account_id", sa.Uuid(), nullable=False),
        sa.Column("journal_entry_id", sa.Uuid(), nullable=True),
        sa.Column("gross_amount", MoneyType(), server_default="0", nullable=False),
        sa.Column("tax_amount", MoneyType(), server_default="0", nullable=False),
        sa.Column("net_amount", MoneyType(), server_default="0", nullable=False),
        sa.Column("open_amount", MoneyType(), server_default="0", nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["adm_tenants.id"],
            name="fk_fin_vendor_bills_tenant_id_adm_tenants",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["core_documents.tenant_id", "core_documents.id"],
            name="fk_fin_vendor_bills_tenant_id_core_documents",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "ap_account_id"],
            ["fin_accounts.tenant_id", "fin_accounts.id"],
            name="fk_fin_vendor_bills_tenant_id_fin_accounts",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "journal_entry_id"],
            ["fin_journal_entries.tenant_id", "fin_journal_entries.id"],
            name="fk_fin_vendor_bills_tenant_id_fin_journal_entries",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_fin_vendor_bills"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_fin_vendor_bills_tenant_id"),
        sa.UniqueConstraint("document_id", name="uq_fin_vendor_bills_document_id"),
    )
    op.create_index("ix_fin_vendor_bills_tenant_id", "fin_vendor_bills", ["tenant_id"])


def _create_vendor_bill_lines() -> None:
    op.create_table(
        "fin_vendor_bill_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("bill_id", sa.Uuid(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("net_amount", MoneyType(), nullable=False),
        sa.Column("tax_code_id", sa.Uuid(), nullable=True),
        sa.Column("tax_amount", MoneyType(), server_default="0", nullable=False),
        sa.Column("cost_center_id", sa.Uuid(), nullable=True),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["adm_tenants.id"],
            name="fk_fin_vendor_bill_lines_tenant_id_adm_tenants",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "bill_id"],
            ["fin_vendor_bills.tenant_id", "fin_vendor_bills.id"],
            name="fk_fin_vendor_bill_lines_tenant_id_fin_vendor_bills",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "account_id"],
            ["fin_accounts.tenant_id", "fin_accounts.id"],
            name="fk_fin_vendor_bill_lines_tenant_id_fin_accounts",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "tax_code_id"],
            ["fin_tax_codes.tenant_id", "fin_tax_codes.id"],
            name="fk_fin_vendor_bill_lines_tenant_id_fin_tax_codes",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_fin_vendor_bill_lines"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_fin_vendor_bill_lines_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id", "bill_id", "line_number",
            name="uq_fin_vendor_bill_lines_tenant_id_bill_id_line_number",
        ),
    )
    op.create_index(
        "ix_fin_vendor_bill_lines_tenant_id", "fin_vendor_bill_lines", ["tenant_id"]
    )


def _create_vendor_payments() -> None:
    op.create_table(
        "fin_vendor_payments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("partner_id", sa.Uuid(), nullable=False),
        sa.Column("partner_name", sa.String(length=200), nullable=False),
        sa.Column("payment_number", sa.String(length=60), nullable=True),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("bank_account_id", sa.Uuid(), nullable=False),
        sa.Column("amount", MoneyType(), nullable=False),
        sa.Column("journal_entry_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="POSTED", nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["adm_tenants.id"],
            name="fk_fin_vendor_payments_tenant_id_adm_tenants",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["core_documents.tenant_id", "core_documents.id"],
            name="fk_fin_vendor_payments_tenant_id_core_documents",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "bank_account_id"],
            ["fin_accounts.tenant_id", "fin_accounts.id"],
            name="fk_fin_vendor_payments_tenant_id_fin_accounts",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "journal_entry_id"],
            ["fin_journal_entries.tenant_id", "fin_journal_entries.id"],
            name="fk_fin_vendor_payments_tenant_id_fin_journal_entries",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_fin_vendor_payments"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_fin_vendor_payments_tenant_id"),
        sa.UniqueConstraint("document_id", name="uq_fin_vendor_payments_document_id"),
    )
    op.create_index("ix_fin_vendor_payments_tenant_id", "fin_vendor_payments", ["tenant_id"])


def _create_vendor_payment_allocations() -> None:
    op.create_table(
        "fin_vendor_payment_allocations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("payment_id", sa.Uuid(), nullable=False),
        sa.Column("vendor_bill_id", sa.Uuid(), nullable=False),
        sa.Column("allocated_amount", MoneyType(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["adm_tenants.id"],
            name="fk_fin_vendor_payment_allocations_tenant_id_adm_tenants",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "payment_id"],
            ["fin_vendor_payments.tenant_id", "fin_vendor_payments.id"],
            name="fk_fin_vendor_payment_allocations_tenant_id_fin_vendor_payments",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "vendor_bill_id"],
            ["fin_vendor_bills.tenant_id", "fin_vendor_bills.id"],
            name="fk_fin_vendor_payment_allocations_tenant_id_fin_vendor_bills",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_fin_vendor_payment_allocations"),
        sa.UniqueConstraint(
            "tenant_id", "id", name="uq_fin_vendor_payment_allocations_tenant_id"
        ),
        # Abbreviated explicit name: PG caps identifiers at 63 chars (a fully-qualified
        # tenant_id_payment_id_vendor_bill_id name would overflow).
        sa.UniqueConstraint(
            "tenant_id", "payment_id", "vendor_bill_id",
            name="uq_fin_vendor_payment_allocations_payment_bill",
        ),
    )
    op.create_index(
        "ix_fin_vendor_payment_allocations_tenant_id",
        "fin_vendor_payment_allocations",
        ["tenant_id"],
    )


def upgrade() -> None:
    _create_vendor_bills()
    _create_vendor_bill_lines()
    _create_vendor_payments()
    _create_vendor_payment_allocations()


def downgrade() -> None:
    op.drop_index(
        "ix_fin_vendor_payment_allocations_tenant_id",
        table_name="fin_vendor_payment_allocations",
    )
    op.drop_table("fin_vendor_payment_allocations")
    op.drop_index("ix_fin_vendor_payments_tenant_id", table_name="fin_vendor_payments")
    op.drop_table("fin_vendor_payments")
    op.drop_index("ix_fin_vendor_bill_lines_tenant_id", table_name="fin_vendor_bill_lines")
    op.drop_table("fin_vendor_bill_lines")
    op.drop_index("ix_fin_vendor_bills_tenant_id", table_name="fin_vendor_bills")
    op.drop_table("fin_vendor_bills")
