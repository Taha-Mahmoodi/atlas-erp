"""ap + ar list-filter indexes

Revision ID: 0016
Revises: 0015
Create Date: 2026-06-12

PERFORMANCE §1 retrofit (#25): GET /vendor-bills and GET /customer-invoices filter on
partner_id + status and sort by the document date, but migrations 0012/0013 shipped only
the bare tenant_id index — a full per-tenant scan filtered in memory. Adds the
tenant-led composite for the dominant filter combination on each table. Aging, payment
runs, and dunning use the same access paths.

Plain CREATE INDEX on both engines — neither table is trigger-bearing, no batch rebuild,
so no trigger re-creation is needed (D-022).
"""

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | None = None
depends_on: str | None = None

_BILLS_INDEX = "ix_fin_vendor_bills_list_filters"
_INVOICES_INDEX = "ix_fin_customer_invoices_list_filters"


def upgrade() -> None:
    op.create_index(
        _BILLS_INDEX,
        "fin_vendor_bills",
        ["tenant_id", "partner_id", "status", "bill_date"],
    )
    op.create_index(
        _INVOICES_INDEX,
        "fin_customer_invoices",
        ["tenant_id", "partner_id", "status", "invoice_date"],
    )


def downgrade() -> None:
    op.drop_index(_INVOICES_INDEX, table_name="fin_customer_invoices")
    op.drop_index(_BILLS_INDEX, table_name="fin_vendor_bills")
