"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

D-022 rules for this revision:
- Every ALTER goes through `with op.batch_alter_table(...)` unconditionally.
- Trigger/raw DDL is written per-dialect, branched on op.get_bind().dialect.name.
- Any batch_alter_table on a trigger-bearing table MUST re-execute that table's
  trigger DDL afterwards — SQLite's copy-rebuild silently drops triggers.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision: str = ${repr(up_revision)}
down_revision: str | None = ${repr(down_revision)}
branch_labels: str | Sequence[str] | None = ${repr(branch_labels)}
depends_on: str | Sequence[str] | None = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
