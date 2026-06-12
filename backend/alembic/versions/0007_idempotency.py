"""idempotency keys

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-12

D-013 idempotency reservation table:

- core_idempotency_keys: one row per (tenant_id, endpoint, key) reservation. The PRIMARY KEY
  is the NATURAL composite (tenant_id, endpoint, key) exactly as D-013 prescribes — this is
  what makes two concurrent duplicate requests collide on insert (PG's unique index arbitrates;
  SQLite's single-writer lock serializes). request_hash (sha256 of the canonical body) lets a
  replay with a DIFFERENT body be rejected; response_status/response_body store the captured
  response for verbatim replay; status is 'in_progress' | 'completed'.

The composite PK already covers tenant_id, so no separate UNIQUE(tenant_id, id) is needed — this
table is never referenced by a tenant_fk() composite child, so it carries the plain tenant FK
backstop only (D-007 item 4). Constraint/index names follow the D-022 convention so SQLite batch
mode can drop them later. DDL is portable across SQLite and Postgres; no triggers, so no
trigger-recreation-after-batch concern (D-022).
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | None = None
depends_on: str | None = None

# Portable JSON: JSONB on Postgres, plain JSON elsewhere (mirrors core/models.JSON_VARIANT).
_JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "core_idempotency_keys",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("endpoint", sa.String(length=200), nullable=False),
        sa.Column("key", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_body", _JSON, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["adm_tenants.id"],
            name=op.f("fk_core_idempotency_keys_tenant_id_adm_tenants"),
        ),
        # Natural composite PK per D-013: (tenant_id, endpoint, key). The insert in reserve()
        # collides here when two duplicates race, which is the whole reservation mechanism.
        sa.PrimaryKeyConstraint(
            "tenant_id", "endpoint", "key", name=op.f("pk_core_idempotency_keys")
        ),
    )
    # Standalone tenant_id index: uniform with every tenant-scoped table (the D-007 invariant)
    # even though the composite PK already leads with tenant_id.
    op.create_index(
        op.f("ix_core_idempotency_keys_tenant_id"), "core_idempotency_keys", ["tenant_id"]
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_core_idempotency_keys_tenant_id"), table_name="core_idempotency_keys"
    )
    op.drop_table("core_idempotency_keys")
