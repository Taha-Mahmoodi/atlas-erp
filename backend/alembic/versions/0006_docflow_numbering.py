"""docflow + numbering

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-12

D-012 document registry, flow links, and gapless per-tenant numbering:

- core_number_sequences: per-tenant gapless counter (name, prefix, padding, next_value,
  year_reset, current_year), UNIQUE(tenant_id, name) + UNIQUE(tenant_id, id), tenant FK.
- core_documents: the registry (doc_type, doc_id, nullable doc_number, status) with
  UNIQUE(tenant_id, doc_type, doc_id), UNIQUE(tenant_id, id) for composite tenant FKs, and a
  PARTIAL unique index on (tenant_id, doc_number) WHERE doc_number IS NOT NULL declared with
  BOTH postgresql_where AND sqlite_where (each engine needs its own dialect kwarg — the
  D-012/D-021 dialect-kwargs pattern). The partial index is the DB backstop turning any
  numbering bug into a constraint violation while still allowing many NULL-numbered drafts.
- core_doc_links: predecessor -> successor edges (link_type), UNIQUE(tenant_id, pred, succ),
  CHECK(pred != succ), composite tenant FKs to core_documents on both endpoints.

Constraint/index names are spelled out per the D-022 naming convention so SQLite batch mode
can drop them later; DDL is portable across SQLite and Postgres. No triggers here, so no
trigger-recreation-after-batch concern (D-022).
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "core_number_sequences",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("prefix", sa.String(length=20), nullable=False),
        sa.Column("padding", sa.Integer(), nullable=False),
        sa.Column("next_value", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("year_reset", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("current_year", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["adm_tenants.id"],
            name=op.f("fk_core_number_sequences_tenant_id_adm_tenants"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_core_number_sequences")),
        sa.UniqueConstraint(
            "tenant_id", "name", name="uq_core_number_sequences_tenant_id_name"
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_core_number_sequences_tenant_id"),
    )
    op.create_index(
        op.f("ix_core_number_sequences_tenant_id"), "core_number_sequences", ["tenant_id"]
    )

    op.create_table(
        "core_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("doc_type", sa.String(length=100), nullable=False),
        sa.Column("doc_id", sa.Uuid(), nullable=False),
        sa.Column("doc_number", sa.String(length=60), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["adm_tenants.id"],
            name=op.f("fk_core_documents_tenant_id_adm_tenants"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_core_documents")),
        sa.UniqueConstraint(
            "tenant_id",
            "doc_type",
            "doc_id",
            name="uq_core_documents_tenant_id_doc_type_doc_id",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_core_documents_tenant_id"),
    )
    op.create_index(op.f("ix_core_documents_tenant_id"), "core_documents", ["tenant_id"])
    # Partial unique index: many NULL-numbered documents allowed, never two equal numbers in
    # one tenant. Both dialect kwargs supplied — each engine needs its own WHERE (D-012).
    op.create_index(
        "uq_core_documents_tenant_id_doc_number",
        "core_documents",
        ["tenant_id", "doc_number"],
        unique=True,
        postgresql_where=sa.text("doc_number IS NOT NULL"),
        sqlite_where=sa.text("doc_number IS NOT NULL"),
    )

    op.create_table(
        "core_doc_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("predecessor_document_id", sa.Uuid(), nullable=False),
        sa.Column("successor_document_id", sa.Uuid(), nullable=False),
        sa.Column("link_type", sa.String(length=40), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "predecessor_document_id != successor_document_id",
            name="ck_core_doc_links_no_self_link",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["adm_tenants.id"],
            name=op.f("fk_core_doc_links_tenant_id_adm_tenants"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "predecessor_document_id"],
            ["core_documents.tenant_id", "core_documents.id"],
            name=op.f("fk_core_doc_links_tenant_id_core_documents"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "successor_document_id"],
            ["core_documents.tenant_id", "core_documents.id"],
            name="fk_core_doc_links_successor_document_id_core_documents",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_core_doc_links")),
        sa.UniqueConstraint(
            "tenant_id",
            "predecessor_document_id",
            "successor_document_id",
            name="uq_core_doc_links_tenant_id_predecessor_document_id_successor",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_core_doc_links_tenant_id"),
    )
    op.create_index(op.f("ix_core_doc_links_tenant_id"), "core_doc_links", ["tenant_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_core_doc_links_tenant_id"), table_name="core_doc_links")
    op.drop_table("core_doc_links")
    op.drop_index("uq_core_documents_tenant_id_doc_number", table_name="core_documents")
    op.drop_index(op.f("ix_core_documents_tenant_id"), table_name="core_documents")
    op.drop_table("core_documents")
    op.drop_index(
        op.f("ix_core_number_sequences_tenant_id"), table_name="core_number_sequences"
    )
    op.drop_table("core_number_sequences")
