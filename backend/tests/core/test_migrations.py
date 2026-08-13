"""The Alembic chain runs on a fresh SQLite file (D-022) and build_engine
connections enforce foreign keys via the PRAGMA listener (D-007)."""

import sqlite3
import uuid
from collections.abc import Callable
from contextlib import closing
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text

from app.core.db import build_engine


def test_alembic_upgrade_head_succeeds_on_fresh_sqlite(
    tmp_path: Path, make_alembic_config: Callable[[str], Config]
) -> None:
    db_path = tmp_path / "fresh.sqlite"
    config = make_alembic_config(f"sqlite+aiosqlite:///{db_path}")

    command.upgrade(config, "head")

    head = ScriptDirectory.from_config(config).get_current_head()
    with closing(sqlite3.connect(db_path)) as connection:
        rows = connection.execute("SELECT version_num FROM alembic_version").fetchall()
    assert rows == [(head,)]


def test_0002_creates_tenant_tables_and_downgrade_removes_them(
    tmp_path: Path, make_alembic_config: Callable[[str], Config]
) -> None:
    db_path = tmp_path / "tenants.sqlite"
    config = make_alembic_config(f"sqlite+aiosqlite:///{db_path}")

    def table_names() -> set[str]:
        with closing(sqlite3.connect(db_path)) as connection:
            rows = connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
            return {row[0] for row in rows}

    command.upgrade(config, "head")
    assert {"adm_tenants", "adm_tenant_settings"} <= table_names()

    command.downgrade(config, "0001")
    assert not ({"adm_tenants", "adm_tenant_settings"} & table_names())


def test_0045_backfills_applied_periods_from_last_accrual_period(
    tmp_path: Path, make_alembic_config: Callable[[str], Config]
) -> None:
    """#160: 0045 promotes each pre-existing balance's single last_accrual_period into an
    hr_leave_accruals guard row, so a post-upgrade re-run of that period stays idempotent."""
    db_path = tmp_path / "backfill.sqlite"
    config = make_alembic_config(f"sqlite+aiosqlite:///{db_path}")
    command.upgrade(config, "0044")

    tenant_id = uuid.uuid4().hex
    stamped_id, unstamped_id = uuid.uuid4().hex, uuid.uuid4().hex
    with closing(sqlite3.connect(db_path)) as connection:
        # FK enforcement is off on this raw connection, so the minimal parent set suffices:
        # the migration connection enforces FKs and the backfill row references adm_tenants.
        connection.execute(
            "INSERT INTO adm_tenants (id, slug, name) VALUES (?, 'bf', 'Backfill')",
            (tenant_id,),
        )
        connection.execute(
            "INSERT INTO hr_leave_balances "
            "(id, tenant_id, employee_id, leave_type_id, last_accrual_period) "
            "VALUES (?, ?, ?, ?, ?)",
            (stamped_id, tenant_id, uuid.uuid4().hex, uuid.uuid4().hex, "2026-06"),
        )
        connection.execute(
            "INSERT INTO hr_leave_balances "
            "(id, tenant_id, employee_id, leave_type_id, last_accrual_period) "
            "VALUES (?, ?, ?, ?, NULL)",
            (unstamped_id, tenant_id, uuid.uuid4().hex, uuid.uuid4().hex),
        )
        connection.commit()

    command.upgrade(config, "head")

    with closing(sqlite3.connect(db_path)) as connection:
        rows = connection.execute(
            "SELECT tenant_id, balance_id, period FROM hr_leave_accruals"
        ).fetchall()
    # Exactly the stamped balance was backfilled; the never-accrued one produced no guard row.
    assert rows == [(tenant_id, stamped_id, "2026-06")]


async def test_build_engine_connections_enforce_foreign_keys(tmp_path: Path) -> None:
    engine = build_engine(f"sqlite+aiosqlite:///{tmp_path / 'fk.sqlite'}")
    try:
        async with engine.connect() as connection:
            result = await connection.execute(text("PRAGMA foreign_keys"))
            assert result.scalar() == 1
    finally:
        await engine.dispose()
