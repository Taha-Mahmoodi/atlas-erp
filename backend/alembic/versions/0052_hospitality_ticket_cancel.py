"""hospitality order ticket cancellation

Revision ID: 0052
Revises: 0051
Create Date: 2026-08-17

Issue #206 — a check opened on the wrong table, or for a party that walked before ordering, had no
way to be closed and sat OPEN on the floor's list forever. CANCELLED is a terminal state reachable
only from OPEN (D-080), so the two columns are the stamp and the reason a human gave for it.

Both nullable with no backfill: every existing ticket is by definition not cancelled, and NULL is
the honest reading of "this never happened" — the fired_at/settled_at precedent on the same table.

``hsp_order_tickets`` IS audited (D-010) and carries the audit trigger, so this migration adds
columns only and recreates nothing: SQLite's ALTER TABLE ADD COLUMN and Postgres's both preserve
existing triggers (D-022 only requires recreation when a table is rebuilt).
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0052"
down_revision: str | None = "0051"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "hsp_order_tickets",
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "hsp_order_tickets",
        sa.Column("cancel_reason", sa.String(length=200), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("hsp_order_tickets", "cancel_reason")
    op.drop_column("hsp_order_tickets", "cancelled_at")
