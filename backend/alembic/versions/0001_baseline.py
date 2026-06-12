"""baseline

Revision ID: 0001
Revises:
Create Date: 2026-06-12

Empty baseline so `alembic upgrade head` works from day one; the first real
schema lands in the next revision.
"""

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
