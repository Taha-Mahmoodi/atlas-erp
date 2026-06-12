"""audit

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-12

core_audit_log (D-010): append-only audit trail. UuidPKMixin + TenantMixin (tenant_id of
the CHANGED row) + TimestampMixin (created_at = when written). Carries actor_user_id,
entity_table, entity_id (stringified PK), action (INSERT|UPDATE|DELETE), diff (JSON/JSONB),
request_id, request_ip. Two composite indexes lead with tenant_id so they are named
explicitly (the D-022 convention keys on column 0 and would collide).

APPEND-ONLY is enforced at the DB by per-dialect triggers (D-022 trigger template): any
UPDATE or DELETE raises 'ATLAS_AUDIT_APPEND_ONLY', which core/exceptions translates to a
409 envelope. Trigger names are stable (trg_core_audit_log_no_update / _no_delete);
upgrade DROPs IF EXISTS then CREATEs; downgrade drops the triggers and the table.

No batch-alter of a trigger-bearing table happens here; were one to, D-022 requires
re-executing this trigger DDL afterwards because SQLite copy-rebuild silently drops it.
"""

import sqlalchemy as sa
from alembic import op

from app.core.models import JSON_VARIANT

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | None = None
depends_on: str | None = None

_TABLE = "core_audit_log"
_TRG_NO_UPDATE = "trg_core_audit_log_no_update"
_TRG_NO_DELETE = "trg_core_audit_log_no_delete"
_GUARD_FN = "core_audit_log_append_only"

# Postgres: one plpgsql function reused by both triggers; RAISE surfaces through asyncpg
# carrying the token. The function is created idempotently and dropped on downgrade.
_PG_FUNCTION = f"""
CREATE OR REPLACE FUNCTION {_GUARD_FN}() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'ATLAS_AUDIT_APPEND_ONLY';
END;
$$ LANGUAGE plpgsql;
"""
_PG_TRG_UPDATE = (
    f"CREATE TRIGGER {_TRG_NO_UPDATE} BEFORE UPDATE ON {_TABLE} "
    f"FOR EACH ROW EXECUTE FUNCTION {_GUARD_FN}();"
)
_PG_TRG_DELETE = (
    f"CREATE TRIGGER {_TRG_NO_DELETE} BEFORE DELETE ON {_TABLE} "
    f"FOR EACH ROW EXECUTE FUNCTION {_GUARD_FN}();"
)

# SQLite: BEFORE UPDATE/DELETE triggers that RAISE(ABORT); the token surfaces as an
# IntegrityError carrying the message.
_SQLITE_TRG_UPDATE = (
    f"CREATE TRIGGER {_TRG_NO_UPDATE} BEFORE UPDATE ON {_TABLE} "
    f"BEGIN SELECT RAISE(ABORT, 'ATLAS_AUDIT_APPEND_ONLY'); END;"
)
_SQLITE_TRG_DELETE = (
    f"CREATE TRIGGER {_TRG_NO_DELETE} BEFORE DELETE ON {_TABLE} "
    f"BEGIN SELECT RAISE(ABORT, 'ATLAS_AUDIT_APPEND_ONLY'); END;"
)


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("entity_table", sa.String(length=100), nullable=False),
        sa.Column("entity_id", sa.String(length=100), nullable=False),
        sa.Column("action", sa.String(length=10), nullable=False),
        sa.Column("diff", JSON_VARIANT, nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("request_ip", sa.String(length=45), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_core_audit_log")),
    )
    op.create_index(op.f("ix_core_audit_log_tenant_id"), _TABLE, ["tenant_id"])
    op.create_index(
        "ix_core_audit_log_tenant_id_entity_table_entity_id",
        _TABLE,
        ["tenant_id", "entity_table", "entity_id"],
    )
    op.create_index("ix_core_audit_log_tenant_id_created_at", _TABLE, ["tenant_id", "created_at"])

    op.execute(f"DROP TRIGGER IF EXISTS {_TRG_NO_UPDATE}")
    op.execute(f"DROP TRIGGER IF EXISTS {_TRG_NO_DELETE}")
    if op.get_bind().dialect.name == "postgresql":
        op.execute(_PG_FUNCTION)
        op.execute(_PG_TRG_UPDATE)
        op.execute(_PG_TRG_DELETE)
        # Defense in depth (D-010): the app role cannot mutate audit rows even if a
        # trigger were dropped. Scoped to the current role so it stays portable.
        op.execute(f"REVOKE UPDATE, DELETE ON {_TABLE} FROM CURRENT_USER")
    else:
        op.execute(_SQLITE_TRG_UPDATE)
        op.execute(_SQLITE_TRG_DELETE)


def downgrade() -> None:
    op.execute(f"DROP TRIGGER IF EXISTS {_TRG_NO_UPDATE}")
    op.execute(f"DROP TRIGGER IF EXISTS {_TRG_NO_DELETE}")
    if op.get_bind().dialect.name == "postgresql":
        op.execute(f"DROP FUNCTION IF EXISTS {_GUARD_FN}()")
    op.drop_index("ix_core_audit_log_tenant_id_created_at", table_name=_TABLE)
    op.drop_index("ix_core_audit_log_tenant_id_entity_table_entity_id", table_name=_TABLE)
    op.drop_index(op.f("ix_core_audit_log_tenant_id"), table_name=_TABLE)
    op.drop_table(_TABLE)
