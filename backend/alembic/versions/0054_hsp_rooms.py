"""hospitality rooms masters and housekeeping

Revision ID: 0054
Revises: 0053
Create Date: 2026-08-30

Phase 20.1 — the hotel masters. Creates FOUR tables and alters NOTHING, so no trigger-bearing
table is touched (D-022) and there is no trigger-recreation concern. All DDL is portable across
SQLite and Postgres (D-003) and every identifier is <= 63 chars (the PG cap).

- hsp_room_types: WHAT the property sells a night of. A user-supplied `code` unique per tenant (the
  item_code/vendor_code shape — a master carries a code, not a gapless document number) and the
  standard capacity Task 4 validates a booking's party size against. AuditMixin: changing what
  "DBL" means retroactively changes what every rate plan and future booking refers to.
- hsp_rooms: one physical room. Composite tenant FK to its room type; `housekeeping_status` starts
  DIRTY on a new room because nobody has made it up. The status column carries NO value-set CHECK —
  the enum is the source of truth and the service validates every move against HOUSEKEEPING_FLOW
  (the OrderTicket.status precedent), so growing the set never needs a migration.
- hsp_rate_plans: a manual nightly amount for a room type over a validity window (v1 has no rate
  calendar). MoneyType + explicit currency_code (D-015, STRUCTURE §7's money pair). Two CHECKs: the
  amount is non-negative, and the window is not backwards — NULL valid_to means open-ended and a
  NULL comparison is UNKNOWN, which a CHECK treats as satisfied.
- hsp_housekeeping_tasks: the D-012 DOCUMENT. DocumentMixin (composite FK to core_documents),
  numbered HKT-2026-000001 at creation on the order-ticket branch. `assigned_user_id` is a core
  adm_users id kept as a PLAIN id with no FK — the QualityInspection.decision_by / journal
  posted_by precedent.

Every FK and filter column gets a tenant-leading index (PERFORMANCE §1). Audit is written by the
D-010 Python listeners off AuditMixin, not by DDL, so no audited table needs a trigger here.
"""

import sqlalchemy as sa
from alembic import op

from app.core.money import MoneyType

# revision identifiers, used by Alembic.
revision: str = "0054"
down_revision: str | None = "0053"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "hsp_room_types",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("base_capacity", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("base_capacity > 0", name="ck_hsp_room_types_capacity_positive"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["adm_tenants.id"], name="fk_hsp_room_types_tenant_id_adm_tenants"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_hsp_room_types"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_hsp_room_types_tenant_id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_hsp_room_types_tenant_id_code"),
    )
    op.create_index("ix_hsp_room_types_tenant_id", "hsp_room_types", ["tenant_id"])

    op.create_table(
        "hsp_rooms",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("room_number", sa.String(length=20), nullable=False),
        sa.Column("room_type_id", sa.Uuid(), nullable=False),
        sa.Column(
            "housekeeping_status",
            sa.String(length=20),
            server_default="DIRTY",
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["adm_tenants.id"], name="fk_hsp_rooms_tenant_id_adm_tenants"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "room_type_id"],
            ["hsp_room_types.tenant_id", "hsp_room_types.id"],
            name="fk_hsp_rooms_room_type_id_hsp_room_types",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_hsp_rooms"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_hsp_rooms_tenant_id"),
        sa.UniqueConstraint("tenant_id", "room_number", name="uq_hsp_rooms_tenant_id_room_number"),
    )
    op.create_index("ix_hsp_rooms_tenant_id", "hsp_rooms", ["tenant_id"])
    op.create_index(
        "ix_hsp_rooms_tenant_id_room_type_id", "hsp_rooms", ["tenant_id", "room_type_id"]
    )
    op.create_index(
        "ix_hsp_rooms_tenant_id_housekeeping_status",
        "hsp_rooms",
        ["tenant_id", "housekeeping_status"],
    )

    op.create_table(
        "hsp_rate_plans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("room_type_id", sa.Uuid(), nullable=False),
        sa.Column("nightly_amount", MoneyType(), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "nightly_amount >= 0", name="ck_hsp_rate_plans_amount_non_negative"
        ),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from",
            name="ck_hsp_rate_plans_window_ordered",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["adm_tenants.id"], name="fk_hsp_rate_plans_tenant_id_adm_tenants"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "room_type_id"],
            ["hsp_room_types.tenant_id", "hsp_room_types.id"],
            name="fk_hsp_rate_plans_room_type_id_hsp_room_types",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_hsp_rate_plans"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_hsp_rate_plans_tenant_id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_hsp_rate_plans_tenant_id_code"),
    )
    op.create_index("ix_hsp_rate_plans_tenant_id", "hsp_rate_plans", ["tenant_id"])
    op.create_index(
        "ix_hsp_rate_plans_tenant_id_room_type_id", "hsp_rate_plans", ["tenant_id", "room_type_id"]
    )

    op.create_table(
        "hsp_housekeeping_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("task_number", sa.String(length=60), nullable=False),
        sa.Column("room_id", sa.Uuid(), nullable=False),
        sa.Column("trigger", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="OPEN", nullable=False),
        sa.Column("assigned_user_id", sa.Uuid(), nullable=True),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["adm_tenants.id"],
            name="fk_hsp_housekeeping_tasks_tenant_id_adm_tenants",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["core_documents.tenant_id", "core_documents.id"],
            name="fk_hsp_housekeeping_tasks_document_id_core_documents",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "room_id"],
            ["hsp_rooms.tenant_id", "hsp_rooms.id"],
            name="fk_hsp_housekeeping_tasks_room_id_hsp_rooms",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_hsp_housekeeping_tasks"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_hsp_housekeeping_tasks_tenant_id"),
        sa.UniqueConstraint("document_id", name="uq_hsp_housekeeping_tasks_document_id"),
        sa.UniqueConstraint(
            "tenant_id", "task_number", name="uq_hsp_housekeeping_tasks_tenant_id_task_number"
        ),
    )
    op.create_index(
        "ix_hsp_housekeeping_tasks_tenant_id", "hsp_housekeeping_tasks", ["tenant_id"]
    )
    op.create_index(
        "ix_hsp_housekeeping_tasks_tenant_id_room_id",
        "hsp_housekeeping_tasks",
        ["tenant_id", "room_id"],
    )
    op.create_index(
        "ix_hsp_housekeeping_tasks_tenant_id_status",
        "hsp_housekeeping_tasks",
        ["tenant_id", "status"],
    )


def downgrade() -> None:
    op.drop_table("hsp_housekeeping_tasks")
    op.drop_table("hsp_rate_plans")
    op.drop_table("hsp_rooms")
    op.drop_table("hsp_room_types")
