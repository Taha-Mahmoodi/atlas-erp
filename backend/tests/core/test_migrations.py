"""The Alembic chain runs on a fresh SQLite file (D-022) and build_engine
connections enforce foreign keys via the PRAGMA listener (D-007)."""

import sqlite3
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


async def test_build_engine_connections_enforce_foreign_keys(tmp_path: Path) -> None:
    engine = build_engine(f"sqlite+aiosqlite:///{tmp_path / 'fk.sqlite'}")
    try:
        async with engine.connect() as connection:
            result = await connection.execute(text("PRAGMA foreign_keys"))
            assert result.scalar() == 1
    finally:
        await engine.dispose()
