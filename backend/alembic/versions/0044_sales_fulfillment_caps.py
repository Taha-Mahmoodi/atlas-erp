"""sales order line fulfillment-cap CHECK constraints

Revision ID: 0044
Revises: 0043
Create Date: 2026-07-02

Fixes #75 (DB half) — the over-fulfillment guards lived only in the create path, so two DRAFT
documents created before either posted could both pass validation and over-deliver / over-bill /
over-return on post. The service post paths now re-check the caps; this migration adds the
bypass-proof DB backstop on ``sales_order_lines`` (financial/stock invariants live in code AND
DB constraints):

- ``delivered_quantity <= ordered_quantity``
- ``invoiced_quantity  <= delivered_quantity``
- ``returned_quantity  <= invoiced_quantity``

TRIGGER SAFETY (D-022): ``sales_order_lines`` is NOT trigger-bearing (0029 touched no
trigger-bearing table), so the SQLite batch copy-rebuild drops no triggers. The ALTER goes through
``batch_alter_table`` (pass-through ALTER ... ADD CONSTRAINT on Postgres, copy-rebuild on SQLite).
All DDL is portable across both engines; every identifier is <= 63 chars (PG cap). Existing rows
satisfy the constraints wherever the service caps were respected; pre-alpha data that already
violates them should be corrected, not grandfathered.
"""

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0044"
down_revision: str | None = "0043"
branch_labels: str | None = None
depends_on: str | None = None

_CAPS: tuple[tuple[str, str], ...] = (
    ("ck_sales_order_lines_delivered_le_ordered", "delivered_quantity <= ordered_quantity"),
    ("ck_sales_order_lines_invoiced_le_delivered", "invoiced_quantity <= delivered_quantity"),
    ("ck_sales_order_lines_returned_le_invoiced", "returned_quantity <= invoiced_quantity"),
)


def upgrade() -> None:
    with op.batch_alter_table("sales_order_lines") as batch:
        for name, sqltext in _CAPS:
            batch.create_check_constraint(name, sqltext)


def downgrade() -> None:
    with op.batch_alter_table("sales_order_lines") as batch:
        for name, _ in _CAPS:
            batch.drop_constraint(name, type_="check")
