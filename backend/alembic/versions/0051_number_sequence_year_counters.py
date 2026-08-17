"""per-year number sequence counters

Revision ID: 0051
Revises: 0050
Create Date: 2026-08-17

Issue #209 — a document dated in a past year reset its sequence's single counter and stamped it
with the old year, after which every document in the real current year re-claimed an existing
number and died on its table's unique index. The counter now belongs to a (sequence, year) pair,
so each year keeps an independent gapless series and a backdated document cannot touch another
year's numbers.

Data migration: every existing counter moves into the new table under the year it was serving
(``current_year``, or 0 for a sequence that does not year-reset), so no tenant's next number
changes across this upgrade — the very next claim after the migration hands out exactly what it
would have handed out before.

``year`` is NOT NULL with 0 for non-year-resetting sequences: a NULL year would compare distinct
in the UNIQUE constraint on both dialects and let duplicate counters exist for one sequence.

The composite FK (tenant_id, sequence_id) -> core_number_sequences (tenant_id, id) is the D-007
item 4 backstop: a counter can only ever reference a sequence inside its own tenant. Both DDL
paths are portable across SQLite and Postgres and every identifier is <= 63 chars (PG cap).
``core_number_sequences`` carries no audit trigger (D-022), so dropping columns from it needs no
trigger recreation.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0051"
down_revision: str | None = "0050"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "core_number_sequence_counters",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("sequence_id", sa.Uuid(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("next_value", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "sequence_id",
            "year",
            name="uq_core_number_sequence_counters_tenant_sequence_year",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["adm_tenants.id"], name="fk_core_number_sequence_counters_tenant"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "sequence_id"],
            ["core_number_sequences.tenant_id", "core_number_sequences.id"],
            name="fk_core_number_sequence_counters_sequence",
        ),
    )
    op.create_index(
        "ix_core_number_sequence_counters_tenant_id",
        "core_number_sequence_counters",
        ["tenant_id"],
    )

    # Carry every live counter over unchanged. randomblob/gen_random_uuid are dialect-specific,
    # so the id is built from the source row's own id — unique by construction, one counter per
    # sequence today — via a portable expression: reuse the sequence id itself.
    op.execute(
        sa.text(
            """
            INSERT INTO core_number_sequence_counters
                (id, tenant_id, sequence_id, year, next_value, created_at, updated_at)
            SELECT id, tenant_id, id, COALESCE(current_year, 0), next_value, created_at, updated_at
            FROM core_number_sequences
            """
        )
    )

    op.drop_column("core_number_sequences", "next_value")
    op.drop_column("core_number_sequences", "current_year")


def downgrade() -> None:
    op.add_column(
        "core_number_sequences",
        sa.Column("next_value", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )
    op.add_column("core_number_sequences", sa.Column("current_year", sa.Integer(), nullable=True))
    # Collapse back to one counter per sequence: the latest year wins, which is the only shape
    # the old code could hold. Older years' counters are dropped with the table — a downgrade
    # cannot preserve what the old schema had no room for.
    op.execute(
        sa.text(
            """
            UPDATE core_number_sequences SET
                next_value = COALESCE((
                    SELECT c.next_value FROM core_number_sequence_counters c
                    WHERE c.sequence_id = core_number_sequences.id
                      AND c.tenant_id = core_number_sequences.tenant_id
                    ORDER BY c.year DESC LIMIT 1
                ), 1),
                current_year = (
                    SELECT NULLIF(c.year, 0) FROM core_number_sequence_counters c
                    WHERE c.sequence_id = core_number_sequences.id
                      AND c.tenant_id = core_number_sequences.tenant_id
                    ORDER BY c.year DESC LIMIT 1
                )
            """
        )
    )
    op.drop_index(
        "ix_core_number_sequence_counters_tenant_id", table_name="core_number_sequence_counters"
    )
    op.drop_table("core_number_sequence_counters")
