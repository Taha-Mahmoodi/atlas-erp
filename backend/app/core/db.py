"""Async engine and session plumbing.

Every engine the app touches (runtime, tests, migrations) is built via build_engine
or has enable_sqlite_foreign_keys attached, so the SQLite FK pragma backstop of
D-007 can never be silently absent.
"""

from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import Engine, event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.audit import install_audit_guards
from app.core.config import get_settings
from app.core.tenancy import install_tenancy_guards

# Import side effect ON PURPOSE: every engine/session factory in app, tests and
# seed is built via this module, so importing it guarantees the D-007 + D-010 listeners
# exist before any session can be constructed. tenancy.py itself cannot self-install
# from models.py (import cycle), and main.py would leave direct-session users
# (tests, seed, alembic) unguarded.
#
# Order is load-bearing (D-010): tenancy first so its before_flush STAMPS tenant_id, then
# audit so its before_flush fires AFTER and reads a settled tenant_id. before_flush
# listeners fire in registration order, so this call order is the guarantee.
install_tenancy_guards()
install_audit_guards()


def _set_sqlite_fk_pragma(dbapi_connection: Any, connection_record: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def enable_sqlite_foreign_keys(engine: Engine) -> None:
    """SQLite enforces FK constraints only with this per-connection pragma (D-007)."""
    if engine.dialect.name == "sqlite":
        event.listen(engine, "connect", _set_sqlite_fk_pragma)


def build_engine(url: str, **kwargs: Any) -> AsyncEngine:
    """The single sanctioned way to create an engine; attaches the FK pragma listener."""
    engine = create_async_engine(url, **kwargs)
    enable_sqlite_foreign_keys(engine.sync_engine)
    return engine


def build_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


engine = build_engine(get_settings().database_url)
session_factory = build_session_factory(engine)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency. Commits belong to the unit-of-work helper (later task);
    here: yield, roll back on exception, always close via the context manager."""
    async with session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """FastAPI dependency returning the runtime sessionmaker. D-013's idempotency reserve()
    needs a SEPARATE short-lived session that COMMITs immediately (so concurrent duplicates
    collide on the reservation PK independently of the request's business transaction). It
    opens that session from this factory. Exposed as a dependency — not imported directly —
    so the test harness overrides it to the per-test engine's factory the same way it
    overrides get_session, keeping the reservation in the same database as the business work."""
    return session_factory


# Register the D-013 idempotency model on Base.metadata HERE rather than via core/models'
# trailing import: core/idempotency imports THIS module for its session dependencies, and this
# module imports core/audit -> core/models, so the registration must happen AFTER db/audit/tenancy
# finish loading (the bottom of this file) to avoid the import cycle. Side-effect import only —
# the name binds the model class so alembic env.py and the engine bootstrap see the table.
from app.core import idempotency as _idempotency  # noqa: E402,F401
