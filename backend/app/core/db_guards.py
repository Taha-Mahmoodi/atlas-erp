"""Per-dialect DB-guard trigger DDL, shared by Alembic migrations.

The financial engine (period close, posted-entry immutability) and the audit log
all enforce invariants with BEFORE-row triggers that abort the write carrying an
``ATLAS_*`` token (the token map in core/exceptions translates it to an error
envelope, D-014). The CREATE/DROP syntax differs between PostgreSQL and SQLite, so
every migration that emits such a trigger must branch on the dialect — getting that
branch wrong is invisible to the SQLite-only test suite (issue #12). Centralising it
here means one tested implementation instead of one hand-rolled copy per migration.

Migrations import these helpers (``app`` is importable from the Alembic env), call
them inside ``upgrade``/``downgrade``, and pass ``op``. Nothing here runs at request
time; it is build-time schema DDL kept in ``core/`` because the guard tokens are part
of the platform's error contract.
"""

from __future__ import annotations

from typing import Any, Literal

TriggerEvent = Literal["UPDATE", "DELETE", "INSERT"]


def _dialect(op: Any) -> str:
    return op.get_bind().dialect.name


def drop_trigger(op: Any, name: str, table: str) -> None:
    """Idempotently drop a trigger on both engines.

    PostgreSQL requires ``DROP TRIGGER <name> ON <table>``; SQLite forbids the ``ON``
    clause and takes ``DROP TRIGGER <name>``. The unconditional table-less form is the
    SQLite-only syntax that broke migration 0005 on Postgres (#12).
    """
    if _dialect(op) == "postgresql":
        op.execute(f"DROP TRIGGER IF EXISTS {name} ON {table}")
    else:
        op.execute(f"DROP TRIGGER IF EXISTS {name}")


def drop_function(op: Any, name: str) -> None:
    """Drop a plpgsql guard function (no-op on SQLite, which has no functions)."""
    if _dialect(op) == "postgresql":
        op.execute(f"DROP FUNCTION IF EXISTS {name}()")


def create_abort_trigger(
    op: Any,
    *,
    name: str,
    table: str,
    event: TriggerEvent,
    token: str,
    function_name: str,
    when: str | None = None,
) -> None:
    """Create a BEFORE-``event`` row trigger that aborts the write raising ``token``.

    PostgreSQL needs a plpgsql function the trigger executes; SQLite inlines a
    ``RAISE(ABORT, token)`` body. ``when`` is an optional SQL boolean (a ``WHEN``
    condition) so a trigger can fire only on, e.g., a status transition — it is
    rendered into both dialects' trigger definitions. The function is created
    ``OR REPLACE`` so repeated triggers can share one function per token/condition.

    The caller is responsible for dropping the trigger first (use ``drop_trigger``)
    and for dropping the function on downgrade (use ``drop_function``).
    """
    if _dialect(op) == "postgresql":
        op.execute(
            f"CREATE OR REPLACE FUNCTION {function_name}() RETURNS trigger AS $$ "
            f"BEGIN RAISE EXCEPTION '{token}'; END; $$ LANGUAGE plpgsql;"
        )
        when_clause = f"WHEN ({when}) " if when else ""
        op.execute(
            f"CREATE TRIGGER {name} BEFORE {event} ON {table} "
            f"FOR EACH ROW {when_clause}EXECUTE FUNCTION {function_name}();"
        )
    else:
        when_clause = f"WHEN {when} " if when else ""
        op.execute(
            f"CREATE TRIGGER {name} BEFORE {event} ON {table} "
            f"FOR EACH ROW {when_clause}"
            f"BEGIN SELECT RAISE(ABORT, '{token}'); END;"
        )
