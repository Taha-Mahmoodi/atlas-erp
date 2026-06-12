"""AtlasError hierarchy rendered as the D-014 error envelope by handlers in app.main.

This file also owns the D-014 DB-guard translation: trigger-raised `ATLAS_*` tokens are
mapped to envelope codes here so the DB backstops surface through the SAME envelope as
service-level checks. Kept in this file (not a new core/db_errors.py) because the map is a
small dict and STRUCTURE §8.1 prefers extending an existing home; promote to its own file
only if the table grows past a screenful.
"""

from typing import Any

from sqlalchemy.exc import DBAPIError


class AtlasError(Exception):
    """Base for every error the API surfaces deliberately. Codes are machine-readable
    and dot-namespaced (generic: common.*; domain rules: e.g. finance.period_closed)."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


class NotFoundError(AtlasError):
    def __init__(
        self,
        message: str = "Resource not found",
        code: str = "common.not_found",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(code=code, message=message, status_code=404, details=details)


class ValidationFailedError(AtlasError):
    def __init__(
        self,
        message: str = "Validation failed",
        code: str = "common.validation_error",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(code=code, message=message, status_code=422, details=details)


class ConflictError(AtlasError):
    def __init__(
        self,
        message: str = "Conflict with existing state",
        code: str = "common.conflict",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(code=code, message=message, status_code=409, details=details)


class AuthError(AtlasError):
    def __init__(
        self,
        message: str = "Invalid credentials",
        code: str = "auth.invalid_credentials",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(code=code, message=message, status_code=401, details=details)


class PermissionDeniedError(AtlasError):
    def __init__(
        self,
        message: str = "Permission denied",
        code: str = "common.permission_denied",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(code=code, message=message, status_code=403, details=details)


class TenancyError(AtlasError):
    def __init__(
        self,
        message: str = "Tenant context missing or mismatched",
        code: str = "tenancy.context_missing",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(code=code, message=message, status_code=403, details=details)


# --- D-014 DB-guard translation (trigger token -> envelope) --------------------
#
# Table-driven so future backstops (ATLAS_PERIOD_CLOSED, ATLAS_POSTED_IMMUTABLE,
# ATLAS_UNBALANCED_ENTRY) plug in by adding one row. SQLite RAISE(ABORT) surfaces as
# IntegrityError and asyncpg plpgsql RAISE surfaces differently, but both are subclasses
# of DBAPIError and both carry the token in str(exc) — so substring matching on the base
# class covers both engines (D-022 pins it on each).
#
# DEVIATION from D-014's literal table: D-014 maps ATLAS_AUDIT_APPEND_ONLY ->
# internal_error 500; PLAN 3.5 binds it to 409 / "audit.append_only" (an append-only
# write is a client-visible conflict, not an opaque server fault), so this map follows
# the task. Finance tokens below are pre-registered for PLAN 4 and keep D-014's codes.
DB_GUARD_TOKEN_MAP: dict[str, tuple[int, str]] = {
    "ATLAS_AUDIT_APPEND_ONLY": (409, "audit.append_only"),
    "ATLAS_PERIOD_CLOSED": (422, "finance.period_closed"),
    "ATLAS_POSTED_IMMUTABLE": (422, "finance.entry_immutable"),
    "ATLAS_UNBALANCED_ENTRY": (422, "finance.journal_unbalanced"),
}


def translate_db_guard_error(exc: DBAPIError) -> AtlasError | None:
    """Map a trigger-raised ATLAS_* token in a DBAPIError to an AtlasError, or None if the
    error carries no known token (then it is a genuine integrity/operational failure and
    the catch-all 500 handler owns it). Matching is on the full message text because the
    token is embedded in the raised exception string on both engines."""
    message = str(exc.orig) if exc.orig is not None else str(exc)
    for token, (status_code, code) in DB_GUARD_TOKEN_MAP.items():
        if token in message:
            return AtlasError(code=code, message=token, status_code=status_code)
    return None
