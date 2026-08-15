"""hospitality table reservations

Revision ID: 0049
Revises: 0048
Create Date: 2026-08-15

Phase 21 — the restaurant reservation trio. Creates THREE tables and alters NOTHING, so no
trigger-bearing table is touched (D-022) and there is no trigger-recreation concern. All DDL is
portable across SQLite and Postgres and every identifier is <= 63 chars (the PG cap).

- hsp_reservation_settings: the property's pacing configuration, AT MOST ONE ROW PER TENANT
  (UNIQUE(tenant_id), named explicitly because the D-022 convention keys on column 0 and would
  collide with the composite UNIQUE(tenant_id, id)). A tenant with no row books against the
  constants.DEFAULT_* values, so this table only ever holds overrides. Times are UTC (Atlas stores
  no per-tenant timezone). AuditMixin — capacity policy is a manager decision, written a handful of
  times in a property's life.
- hsp_service_slots: the PACING COUNTER, one row per (service_date, slot_start), materialised
  LAZILY by the first booking's upsert-on-lock. The two CHECK pairs (covers/parties within max, and
  non-negative) are the DB backstop under the service's pre-flight `hospitality.slot_full` refusal,
  the inv_stock_quants shape (D-020/D-036). NOT AuditMixin: this row is written on every booking
  and every cancellation, and the reservation next door is the audited document.
- hsp_table_reservations: the reservation DOCUMENT. DocumentMixin (composite FK to core_documents)
  — numbered RSV-2026-000001 at creation, the order-ticket branch. A nullable composite tenant FK
  to hsp_order_tickets carries the check a seated party was put onto; a NULL composite FK is simply
  not enforced (MATCH SIMPLE), which is what lets it be set only at seating. No table_code column:
  the physical table is a soft assignment recorded on the check (Phase 19's finding, unchanged).

Audit is written by the D-010 Python listeners off AuditMixin, not by DDL, so neither audited table
needs a trigger here.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0049"
down_revision: str | None = "0048"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "hsp_reservation_settings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("service_open", sa.Time(), nullable=False),
        sa.Column("service_close", sa.Time(), nullable=False),
        sa.Column("default_covers_max", sa.Integer(), nullable=False),
        sa.Column("default_parties_max", sa.Integer(), nullable=False),
        sa.Column("min_party", sa.Integer(), nullable=False),
        sa.Column("max_party", sa.Integer(), nullable=False),
        sa.Column("booking_horizon_days", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "default_covers_max >= 0 AND default_parties_max >= 0",
            name="ck_hsp_reservation_settings_defaults_non_negative",
        ),
        sa.CheckConstraint(
            "min_party > 0 AND max_party >= min_party",
            name="ck_hsp_reservation_settings_party_range_sane",
        ),
        sa.CheckConstraint(
            "booking_horizon_days > 0",
            name="ck_hsp_reservation_settings_horizon_positive",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["adm_tenants.id"],
            name="fk_hsp_reservation_settings_tenant_id_adm_tenants",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_hsp_reservation_settings"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_hsp_reservation_settings_tenant_id"),
        sa.UniqueConstraint("tenant_id", name="uq_hsp_reservation_settings_one_per_tenant"),
    )
    op.create_index(
        "ix_hsp_reservation_settings_tenant_id", "hsp_reservation_settings", ["tenant_id"]
    )

    op.create_table(
        "hsp_service_slots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("service_date", sa.Date(), nullable=False),
        sa.Column("slot_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("covers_booked", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("covers_max", sa.Integer(), nullable=False),
        sa.Column("parties_booked", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("parties_max", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "covers_booked >= 0 AND covers_booked <= covers_max",
            name="ck_hsp_service_slots_covers_within_max",
        ),
        sa.CheckConstraint(
            "parties_booked >= 0 AND parties_booked <= parties_max",
            name="ck_hsp_service_slots_parties_within_max",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["adm_tenants.id"],
            name="fk_hsp_service_slots_tenant_id_adm_tenants",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_hsp_service_slots"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_hsp_service_slots_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "service_date",
            "slot_start",
            name="uq_hsp_service_slots_tenant_id_service_date_slot_start",
        ),
    )
    op.create_index("ix_hsp_service_slots_tenant_id", "hsp_service_slots", ["tenant_id"])

    op.create_table(
        "hsp_table_reservations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("reservation_number", sa.String(length=60), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="CONFIRMED", nullable=False),
        sa.Column("service_date", sa.Date(), nullable=False),
        sa.Column("slot_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("party_size", sa.Integer(), nullable=False),
        sa.Column("guest_name", sa.String(length=200), nullable=False),
        sa.Column("guest_contact", sa.String(length=200), nullable=True),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        sa.Column("ticket_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "party_size > 0", name="ck_hsp_table_reservations_party_size_positive"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["adm_tenants.id"],
            name="fk_hsp_table_reservations_tenant_id_adm_tenants",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["core_documents.tenant_id", "core_documents.id"],
            name="fk_hsp_table_reservations_document_id_core_documents",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "ticket_id"],
            ["hsp_order_tickets.tenant_id", "hsp_order_tickets.id"],
            name="fk_hsp_table_reservations_ticket_id_hsp_order_tickets",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_hsp_table_reservations"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_hsp_table_reservations_tenant_id"),
        sa.UniqueConstraint("document_id", name="uq_hsp_table_reservations_document_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "reservation_number",
            name="uq_hsp_table_reservations_tenant_id_reservation_number",
        ),
    )
    op.create_index(
        "ix_hsp_table_reservations_tenant_id", "hsp_table_reservations", ["tenant_id"]
    )
    op.create_index(
        "ix_hsp_table_reservations_tenant_id_service_date_slot_start",
        "hsp_table_reservations",
        ["tenant_id", "service_date", "slot_start"],
    )
    op.create_index(
        "ix_hsp_table_reservations_tenant_id_ticket_id",
        "hsp_table_reservations",
        ["tenant_id", "ticket_id"],
    )


def downgrade() -> None:
    op.drop_table("hsp_table_reservations")
    op.drop_table("hsp_service_slots")
    op.drop_table("hsp_reservation_settings")
