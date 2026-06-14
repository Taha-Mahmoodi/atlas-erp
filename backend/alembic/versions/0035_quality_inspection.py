"""quality inspection lots: the OPEN→ACCEPTED/REJECTED lot from a goods-receipt inspection flag

Revision ID: 0035
Revises: 0034
Create Date: 2026-06-14

PLAN 9.1 — the deliberately small QM core (s4hana-parity §QM: inspection flag on goods receipt →
inspection lot → accept/reject with stock disposition). Creates ONE table and alters NOTHING — no
trigger-bearing table is touched (D-022), so there is no trigger-recreation concern. All DDL is
portable across SQLite and Postgres; every identifier is <= 63 chars (PG cap). The QuantityType
columns render as NUMERIC(18,6) on Postgres / INTEGER micro-units on SQLite (D-015) via the model
column type — imported from app.core.money so the revision stays dialect-clean.

- qm_inspection_lots: the inspection-lot header. DocumentMixin (composite FK to core_documents);
  UNIQUE(tenant_id, lot_number) (the gapless QL- number claimed at creation); CHECKs quantity > 0
  and
  accepted/rejected_quantity >= 0; (tenant, status) + (tenant, item_id) + (tenant,
  source_document_id) filter indexes. source_document_id is the OPAQUE core_documents id of the
  originating GR (D-029/D-050) — a docflow edge, not a cross-module FK. item_id / warehouse_id /
  bin_id / inspect_lot_id / serial_id are OPAQUE inventory ids — no FK to inv_*. decision_by is the
  deciding user's id (a plain id, no FK, the journal posted_by precedent).
"""

import sqlalchemy as sa
from alembic import op

from app.core.money import QuantityType

# revision identifiers, used by Alembic.
revision: str = "0035"
down_revision: str | None = "0034"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "qm_inspection_lots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("lot_number", sa.String(length=60), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="OPEN"),
        sa.Column(
            "source", sa.String(length=20), nullable=False, server_default="GOODS_RECEIPT"
        ),
        sa.Column("source_document_id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("warehouse_id", sa.Uuid(), nullable=False),
        sa.Column("bin_id", sa.Uuid(), nullable=False),
        sa.Column("inspect_lot_id", sa.Uuid(), nullable=True),
        sa.Column("serial_id", sa.Uuid(), nullable=True),
        sa.Column("quantity", QuantityType(), nullable=False),
        sa.Column("accepted_quantity", QuantityType(), nullable=False, server_default="0"),
        sa.Column("rejected_quantity", QuantityType(), nullable=False, server_default="0"),
        sa.Column("disposition", sa.String(length=20), nullable=True),
        sa.Column("created_date", sa.Date(), nullable=False),
        sa.Column("decided_date", sa.Date(), nullable=True),
        sa.Column("decision_by", sa.Uuid(), nullable=True),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("quantity > 0", name="ck_qm_inspection_lots_quantity_positive"),
        sa.CheckConstraint(
            "accepted_quantity >= 0", name="ck_qm_inspection_lots_accepted_non_negative"
        ),
        sa.CheckConstraint(
            "rejected_quantity >= 0", name="ck_qm_inspection_lots_rejected_non_negative"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["adm_tenants.id"],
            name="fk_qm_inspection_lots_tenant_id_adm_tenants",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["core_documents.tenant_id", "core_documents.id"],
            name="fk_qm_inspection_lots_document_id_core_documents",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_qm_inspection_lots"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_qm_inspection_lots_tenant_id"),
        sa.UniqueConstraint("document_id", name="uq_qm_inspection_lots_document_id"),
        sa.UniqueConstraint(
            "tenant_id", "lot_number", name="uq_qm_inspection_lots_tenant_id_lot_number"
        ),
    )
    op.create_index(
        "ix_qm_inspection_lots_tenant_id", "qm_inspection_lots", ["tenant_id"]
    )
    op.create_index(
        "ix_qm_inspection_lots_tenant_id_status",
        "qm_inspection_lots",
        ["tenant_id", "status"],
    )
    op.create_index(
        "ix_qm_inspection_lots_tenant_id_item_id",
        "qm_inspection_lots",
        ["tenant_id", "item_id"],
    )
    op.create_index(
        "ix_qm_inspection_lots_tenant_id_source_document_id",
        "qm_inspection_lots",
        ["tenant_id", "source_document_id"],
    )


def downgrade() -> None:
    op.drop_table("qm_inspection_lots")
