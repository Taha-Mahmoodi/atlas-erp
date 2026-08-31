"""customer receipts carry an unapplied (on-account) balance

Revision ID: 0055
Revises: 0054
Create Date: 2026-08-30

PLAN 20.4 / D-084 — a hospitality advance deposit is cash received before any invoice exists, so it
has nothing to allocate. ``unapplied_amount`` is the part of a receipt that cleared no invoice: it
is credited to the ``customer_advances`` control at posting and drawn down by ``apply_receipt``.

NOT NULL with server_default 0 and no backfill needed: every receipt that exists today was refused
unless ``amount == sum(allocations)`` (the rule this phase relaxes to ``>=``), so 0 is not a
convenient default — it is the true unapplied balance of every historical row.

``CHECK (unapplied_amount >= 0)`` is the floor under the draw-down, the ``inv_stock_quants``
on-hand precedent (D-020/D-036): the balance is money, so no writer at all — service, data fix-up
or a later folio path — may leave a customer owed a negative deposit. It is NOT what stops two
concurrent applications from spending the same balance (they each store a non-negative
``500 - 300``); the ``with_for_update`` row lock in ``apply_receipt`` does that, and the two guards
are deliberately not substitutes. A single-column comparison is exact and portable on both engines
(D-003/D-015: PG NUMERIC and SQLite micro-unit INTEGER), and the identifier is 46 chars, inside
PG's 63-char cap.

``fin_customer_receipts`` is audited (D-010) but carries NO database trigger — the audit rows are
written by the Python flush listeners, and the only trigger-bearing finance tables are
``fin_journal_entries``/``fin_journal_lines`` (migration 0009). So the SQLite copy-rebuild that
``batch_alter_table`` performs to add the CHECK drops no trigger and D-022 requires no recreation
here.

Renumbered from 0054 to 0055 so it lands AFTER PR #248's ``0054_hsp_rooms``: two revisions sharing
an id AND a down_revision live in different files, so git merges both without a conflict and
whichever lands second disappears from the version map — silently. This is the shipped-finance
change and waits on the owner's review, so it takes the later slot.

``down_revision`` still reads ``0053`` and MUST be relinked to ``0054`` in the rebase that follows
#248 merging into ``dev`` — a one-line change. It cannot be written that way today because 0054
does not exist on this branch: a dangling ``down_revision`` makes ``ScriptDirectory`` fail to
resolve a head, which takes the whole suite down rather than just this migration. The failure mode
of leaving it at 0053 is the opposite kind: once both land, ``dev`` has two heads and
``script_dir.get_current_head()`` raises for every test in the repo, so the relink cannot be
forgotten quietly. Loud-and-one-line was chosen over silent-and-correct-later; the collision the
review actually found — the shared revision id, which no tool would have reported — is gone either
way.
"""

import sqlalchemy as sa
from alembic import op

from app.core.money import MoneyType

# revision identifiers, used by Alembic.
revision: str = "0055"
down_revision: str | None = "0053"
branch_labels: str | None = None
depends_on: str | None = None

_CHECK = "ck_fin_customer_receipts_unapplied_non_negative"


def upgrade() -> None:
    op.add_column(
        "fin_customer_receipts",
        sa.Column("unapplied_amount", MoneyType(), nullable=False, server_default="0"),
    )
    with op.batch_alter_table("fin_customer_receipts") as batch:
        batch.create_check_constraint(_CHECK, "unapplied_amount >= 0")


def downgrade() -> None:
    with op.batch_alter_table("fin_customer_receipts") as batch:
        batch.drop_constraint(_CHECK, type_="check")
    op.drop_column("fin_customer_receipts", "unapplied_amount")
