"""hospitality room allotment counter and the room reservation

Revision ID: 0056
Revises: 0055
Create Date: 2026-08-31

PLAN 20.2 — the booking gate. Creates TWO tables and alters NOTHING, so no trigger-bearing table is
touched (D-022) and there is no trigger-recreation concern. All DDL is portable across SQLite and
PostgreSQL (D-003) — no exclusion constraint, which is the point of Q3's finding: a counter row per
(room type, night) rather than an `EXCLUDE USING gist` over a daterange, so the SQLite suite can
exercise the invariant the money path depends on.

**Every CHECK is declared with a BARE name here and on the model**, and that is not cosmetic — but
the reason is the OPPOSITE of what an earlier version of this docstring claimed. `op.create_table`
does NOT build its table on a convention-free MetaData: `alembic/operations/schemaobj.py` copies
`naming_convention` off `env.py`'s `target_metadata`, which is `Base.metadata`. So BOTH sides apply
`ck_%(table_name)s_%(constraint_name)s`, and a `ck_`-prefixed literal double-prefixes on BOTH — to
`ck_hsp_room_type_inventory_ck_hsp_room_type_inventory_sold_non_negative` (71 chars), which
PostgreSQL then takes at 60 as SQLAlchemy hash-truncates it while SQLite keeps all 71. A bare name
composes ONCE, on both sides, so the model, this migration, PostgreSQL and SQLite all agree on
`ck_hsp_room_type_inventory_sold_non_negative` (44).

Making only ONE side bare is the actual trap: it is the single way to make the two disagree, and it
shipped for one review round. `test_the_new_tables_emit_the_constraint_names_the_database_gets`
reads the names back out of `sqlite_master`/`pg_constraint` after a real migration rather than
grepping this file's source, because a bare model name is trivially a substring of a `ck_`-prefixed
literal and the source check passed while the DDL differed.

The longest identifier either side emits is
`uq_hsp_room_type_inventory_tenant_id_room_type_id_stay_date` at 59 chars, inside PostgreSQL's
63-byte cap, so nothing is silently truncated.

- hsp_room_type_inventory: the ALLOTMENT COUNTER. Unique on (tenant_id, room_type_id, stay_date),
  which doubles as the index every read of this table uses (PERFORMANCE §1: its leading columns
  serve "this type's next 30 nights" from one scan). Three CHECKs: rooms_sold >= 0, rooms_sold <=
  rooms_sellable + overbooking_limit, and both supply columns non-negative — the DB backstop under
  `allotment.adjust_allotment`'s pre-flight refusal, the inv_stock_quants shape (D-020/D-036). NOT
  audited: written on every confirmation and every cancellation, so a before/after diff per write
  would charge the guest's request for a second insert (the hsp_service_slots precedent).
- hsp_room_reservations: the D-012 DOCUMENT. DocumentMixin (composite FK to core_documents),
  numbered RMR-2026-000001 at creation on the order-ticket branch, audited (D-010) because it is a
  promise to a named guest that staff move, cancel and no-show. Composite tenant FKs to the room
  type it sells, the rate plan that prices it, and the physical room assigned at check-in (nullable
  — a NULL composite FK is not enforced, MATCH SIMPLE). CHECK departure_date > arrival_date: the
  stay is the half-open range [arrival, departure), so a zero-night stay is a booking for nobody.
  PARTIAL UNIQUE INDEX (tenant_id, room_id) WHERE status = 'CHECKED_IN': a physical room holds one
  guest at a time. Partial because a room houses a different guest every week and every past stay
  keeps its room_id, so a plain UNIQUE would refuse the second stay 101 ever had; both dialect
  predicates are declared because each engine needs its own (D-021, the core_documents precedent).

Both tables' rows are seeded by nothing: the counter materialises lazily on the first booking of a
night (a missing row means DEFAULT supply, counted live from hsp_rooms, never zero), so this
migration creates no data and its downgrade loses only what a property booked.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0056"
down_revision: str | None = "0055"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "hsp_room_type_inventory",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("room_type_id", sa.Uuid(), nullable=False),
        sa.Column("stay_date", sa.Date(), nullable=False),
        sa.Column("rooms_sellable", sa.Integer(), nullable=False),
        sa.Column("rooms_sold", sa.Integer(), server_default="0", nullable=False),
        sa.Column("overbooking_limit", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "rooms_sold >= 0", name="sold_non_negative"
        ),
        sa.CheckConstraint(
            "rooms_sold <= rooms_sellable + overbooking_limit",
            name="sold_within_supply",
        ),
        sa.CheckConstraint(
            "rooms_sellable >= 0 AND overbooking_limit >= 0",
            name="supply_non_negative",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["adm_tenants.id"],
            name="fk_hsp_room_type_inventory_tenant_id_adm_tenants",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "room_type_id"],
            ["hsp_room_types.tenant_id", "hsp_room_types.id"],
            name="fk_hsp_room_type_inventory_room_type_id_hsp_room_types",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_hsp_room_type_inventory"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_hsp_room_type_inventory_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "room_type_id",
            "stay_date",
            name="uq_hsp_room_type_inventory_tenant_id_room_type_id_stay_date",
        ),
    )
    op.create_index(
        "ix_hsp_room_type_inventory_tenant_id", "hsp_room_type_inventory", ["tenant_id"]
    )

    op.create_table(
        "hsp_room_reservations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("reservation_number", sa.String(length=60), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="TENTATIVE", nullable=False),
        sa.Column("room_type_id", sa.Uuid(), nullable=False),
        sa.Column("rate_plan_id", sa.Uuid(), nullable=False),
        sa.Column("arrival_date", sa.Date(), nullable=False),
        sa.Column("departure_date", sa.Date(), nullable=False),
        sa.Column("party_size", sa.Integer(), nullable=False),
        sa.Column("room_id", sa.Uuid(), nullable=True),
        sa.Column("guest_name", sa.String(length=200), nullable=False),
        sa.Column("guest_contact", sa.String(length=200), nullable=True),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "departure_date > arrival_date",
            name="stay_at_least_one_night",
        ),
        sa.CheckConstraint(
            "party_size > 0", name="party_size_positive"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["adm_tenants.id"],
            name="fk_hsp_room_reservations_tenant_id_adm_tenants",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["core_documents.tenant_id", "core_documents.id"],
            name="fk_hsp_room_reservations_document_id_core_documents",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "room_type_id"],
            ["hsp_room_types.tenant_id", "hsp_room_types.id"],
            name="fk_hsp_room_reservations_room_type_id_hsp_room_types",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "rate_plan_id"],
            ["hsp_rate_plans.tenant_id", "hsp_rate_plans.id"],
            name="fk_hsp_room_reservations_rate_plan_id_hsp_rate_plans",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "room_id"],
            ["hsp_rooms.tenant_id", "hsp_rooms.id"],
            name="fk_hsp_room_reservations_room_id_hsp_rooms",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_hsp_room_reservations"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_hsp_room_reservations_tenant_id"),
        sa.UniqueConstraint("document_id", name="uq_hsp_room_reservations_document_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "reservation_number",
            name="uq_hsp_room_reservations_tenant_id_reservation_number",
        ),
    )
    op.create_index("ix_hsp_room_reservations_tenant_id", "hsp_room_reservations", ["tenant_id"])
    op.create_index(
        "ix_hsp_room_reservations_tenant_id_arrival_date",
        "hsp_room_reservations",
        ["tenant_id", "arrival_date"],
    )
    op.create_index(
        "ix_hsp_room_reservations_tenant_id_room_type_id",
        "hsp_room_reservations",
        ["tenant_id", "room_type_id"],
    )
    op.create_index(
        "ix_hsp_room_reservations_tenant_id_room_id",
        "hsp_room_reservations",
        ["tenant_id", "room_id"],
    )
    op.create_index(
        "ix_hsp_room_reservations_tenant_id_rate_plan_id",
        "hsp_room_reservations",
        ["tenant_id", "rate_plan_id"],
    )
    op.create_index(
        "uq_hsp_room_reservations_tenant_id_room_id_checked_in",
        "hsp_room_reservations",
        ["tenant_id", "room_id"],
        unique=True,
        postgresql_where=sa.text("status = 'CHECKED_IN'"),
        sqlite_where=sa.text("status = 'CHECKED_IN'"),
    )


def downgrade() -> None:
    op.drop_table("hsp_room_reservations")
    op.drop_table("hsp_room_type_inventory")
