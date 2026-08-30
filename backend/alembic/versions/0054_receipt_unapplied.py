"""customer receipts carry an unapplied (on-account) balance

Revision ID: 0054
Revises: 0053
Create Date: 2026-08-30

PLAN 20.4 / D-084 — a hospitality advance deposit is cash received before any invoice exists, so it
has nothing to allocate. ``unapplied_amount`` is the part of a receipt that cleared no invoice: it
is credited to the ``customer_advances`` control at posting and drawn down by ``apply_receipt``.

NOT NULL with server_default 0 and no backfill needed: every receipt that exists today was refused
unless ``amount == sum(allocations)`` (the rule this phase relaxes to ``>=``), so 0 is not a
convenient default — it is the true unapplied balance of every historical row.

``fin_customer_receipts`` is audited (D-010) and carries the audit trigger; this migration only ADDS
a column, and both engines' ALTER TABLE ADD COLUMN preserve triggers (D-022 requires recreation only
when a table is rebuilt).
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
    op.add_column(
        "fin_customer_receipts",
        sa.Column("unapplied_amount", MoneyType(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("fin_customer_receipts", "unapplied_amount")
