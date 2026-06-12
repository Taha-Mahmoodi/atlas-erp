"""D-010 audit capture: split-phase session-event diffs + request context.

Two disjoint layers:

* **Context** — `RequestContext` plus the ContextVars this module OWNS (request_id,
  actor_user_id, request_ip). app.main's middleware sets request_id/request_ip and
  resets all three in a finally block; core.deps.get_current_user fills actor_user_id
  once the principal is known. tenant_id is NOT a ContextVar here — it comes off the
  changed row (every audited model is TenantMixin), which is always settled by the time
  audit reads it.

* **Data** — three Session events, because attribute history is only reliable PRE-flush
  while generated PKs only exist POST-flush:
    1. before_flush  -> UPDATE/DELETE diffs from attribute history, buffered in session.info
    2. after_flush   -> INSERT rows from current column values (PKs now exist), buffered
    3. after_flush_postexec -> ONE Core insert of the drained buffer, SAME transaction

The post-exec write uses a Core `insert()` (never the ORM) so it cannot re-enter the ORM
flush listeners — no recursion, and AuditLog never audits itself.

**Listener order (load-bearing):** install_audit_guards() is called from core.db AFTER
install_tenancy_guards(), so audit's before_flush fires AFTER tenancy stamps tenant_id on
new rows. In practice audit only reads tenant_id for UPDATE/DELETE (existing rows already
carry it) and for INSERT in after_flush (tenancy has already stamped), so correctness does
not actually depend on the order — but the documented ordering keeps it obviously safe.
"""

import uuid
from collections.abc import Iterable
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import event, inspect
from sqlalchemy import insert as sa_insert
from sqlalchemy.orm import ORMExecuteState, Session

from app.core.exceptions import AtlasError
from app.core.models import AuditLog, AuditMixin

# --- Context layer ------------------------------------------------------------
# These three ContextVars live here (the audit concern's single home). app.main imports
# request_id_ctx/request_ip_ctx and sets them in its ASGI middleware; core.deps sets
# actor_user_id_ctx after loading the principal. All are reset by the middleware finally.
request_id_ctx: ContextVar[str | None] = ContextVar("audit_request_id", default=None)
actor_user_id_ctx: ContextVar[uuid.UUID | None] = ContextVar("audit_actor_user_id", default=None)
request_ip_ctx: ContextVar[str | None] = ContextVar("audit_request_ip", default=None)

# Diff JSON of huge text columns would bloat the table (D-010 risk): cap per-value length.
_MAX_VALUE_CHARS = 4000
_TRUNCATION_MARKER = "…[truncated]"

# Buffer key in session.info; drained per flush so multi-flush transactions batch cleanly.
_BUFFER_KEY = "audit_pending_rows"


@dataclass(frozen=True)
class RequestContext:
    """Transport facts the flush listeners stamp onto every audit row. Absent fields mean
    a system/unauthenticated write (actor_user_id None, request_ip/request_id None)."""

    actor_user_id: uuid.UUID | None
    request_id: str | None
    request_ip: str | None


def current_request_context() -> RequestContext:
    """Snapshot the audit ContextVars. Outside a request (system writes, seed, tests with
    no context set) every field is None — the row is still written, just unattributed."""
    return RequestContext(
        actor_user_id=actor_user_id_ctx.get(),
        request_id=request_id_ctx.get(),
        request_ip=request_ip_ctx.get(),
    )


def json_safe(value: Any) -> Any:
    """Coerce a column value to a JSON-serializable form: uuid/Decimal -> str,
    datetime/date -> ISO 8601, leave JSON primitives untouched, str-cap the rest. Long
    strings are truncated with a marker so the diff column cannot bloat (D-010)."""
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, uuid.UUID | Decimal):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    text = value if isinstance(value, str) else str(value)
    if len(text) > _MAX_VALUE_CHARS:
        return text[:_MAX_VALUE_CHARS] + _TRUNCATION_MARKER
    return text


def _audited_columns(obj: AuditMixin) -> Iterable[str]:
    """Column attribute names to capture for an audited instance: every mapped column key
    minus the model's __audit_exclude__ set (password_hash on User, etc.)."""
    excluded = getattr(obj, "__audit_exclude__", frozenset())
    mapper = inspect(type(obj))
    for column_attr in mapper.column_attrs:
        if column_attr.key not in excluded:
            yield column_attr.key


def _diff_for_update(obj: AuditMixin) -> dict[str, dict[str, Any]]:
    """Per-field {old, new} for columns whose attribute history shows a change. History is
    only meaningful pre-flush, so this runs in before_flush."""
    state = inspect(obj)
    diff: dict[str, dict[str, Any]] = {}
    for key in _audited_columns(obj):
        history = state.attrs[key].history
        if not history.has_changes():
            continue
        old = history.deleted[0] if history.deleted else None
        new = history.added[0] if history.added else None
        diff[key] = {"old": json_safe(old), "new": json_safe(new)}
    return diff


def _full_row(obj: AuditMixin) -> dict[str, Any]:
    """All captured column values for an instance (used for INSERT 'new' and DELETE 'old')."""
    return {key: json_safe(getattr(obj, key)) for key in _audited_columns(obj)}


def _buffer(session: Session) -> list[dict[str, Any]]:
    return session.info.setdefault(_BUFFER_KEY, [])


def _make_row(obj: AuditMixin, action: str, diff: dict[str, Any]) -> dict[str, Any] | None:
    """Assemble one core_audit_log row from a changed instance + the request context.
    Returns None when the PK is still unset (defensive)."""
    # primary_key_from_instance reads PK column attributes directly — it is populated in
    # after_flush, whereas inspect(obj).identity is still None there (the identity key is
    # assigned only once the object enters the identity map, after the flush completes).
    pk = inspect(type(obj)).primary_key_from_instance(obj)
    if pk is None or pk[0] is None:
        return None
    entity_id = str(pk[0]) if len(pk) == 1 else str(pk)
    # tenant_id of the changed row. The tenancy root (Tenant) is audited but is NOT
    # TenantMixin — it has no tenant_id, so scope its audit rows to its own id (it IS the
    # tenant). Every other audited model is TenantMixin with tenant_id always settled here.
    tenant_id = getattr(obj, "tenant_id", None) or pk[0]
    context = current_request_context()
    return {
        "id": uuid.uuid4(),
        "tenant_id": tenant_id,
        "actor_user_id": context.actor_user_id,
        "entity_table": type(obj).__tablename__,
        "entity_id": entity_id,
        "action": action,
        "diff": diff,
        "request_id": context.request_id,
        "request_ip": context.request_ip,
    }


# --- Data layer: the three flush events ---------------------------------------


def _capture_updates_and_deletes(
    session: Session, flush_context: object, instances: object
) -> None:
    """before_flush: buffer UPDATE diffs and DELETE old-row snapshots from attribute
    history (reliable only here). INSERTs are captured in after_flush where PKs exist."""
    buffer = _buffer(session)
    for obj in session.dirty:
        if not isinstance(obj, AuditMixin) or not session.is_modified(obj):
            continue
        diff = _diff_for_update(obj)
        if not diff:
            # Dirty but no audited column changed (e.g. only password_hash, or a no-op).
            continue
        row = _make_row(obj, "UPDATE", diff)
        if row is not None:
            buffer.append(row)
    for obj in session.deleted:
        if not isinstance(obj, AuditMixin):
            continue
        row = _make_row(obj, "DELETE", {"old": _full_row(obj)})
        if row is not None:
            buffer.append(row)


def _capture_inserts(session: Session, flush_context: object) -> None:
    """after_flush: buffer INSERT rows now that generated PKs exist."""
    buffer = _buffer(session)
    for obj in session.new:
        if not isinstance(obj, AuditMixin):
            continue
        row = _make_row(obj, "INSERT", {"new": _full_row(obj)})
        if row is not None:
            buffer.append(row)


def _write_buffer(session: Session, flush_context: object) -> None:
    """after_flush_postexec: drain the buffer and write it with ONE Core insert on the
    same connection/transaction. Core insert => the ORM flush listeners do not re-fire, so
    AuditLog never audits itself and there is no recursion."""
    rows = session.info.pop(_BUFFER_KEY, None)
    if not rows:
        return
    session.execute(sa_insert(AuditLog), rows)


# --- Bulk-write guard ---------------------------------------------------------


def _is_audited_orm_write(execute_state: ORMExecuteState) -> bool:
    if not execute_state.is_orm_statement:
        return False
    if not (execute_state.is_update or execute_state.is_delete):
        return False
    return any(issubclass(m.class_, AuditMixin) for m in execute_state.all_mappers)


def _guard_bulk_audited_writes(execute_state: ORMExecuteState) -> None:
    """do_orm_execute sibling to the tenancy filter: an ORM-enabled update()/delete()
    against an AuditMixin mapper bypasses before_flush/object events, so it would silently
    skip audit. Convert that gap into a hard error (D-010). Ordinary selects and writes to
    non-audited models pass straight through."""
    if _is_audited_orm_write(execute_state):
        mapper = execute_state.bind_mapper
        entity = mapper.class_.__name__ if mapper is not None else "an audited model"
        raise AtlasError(
            code="audit.bulk_write_forbidden",
            message=(
                f"ORM bulk update()/delete() on {entity} bypasses audit capture; "
                "mutate loaded objects instead (D-010)."
            ),
            status_code=409,
        )


def install_audit_guards() -> None:
    """Attach the three flush listeners + the bulk-write guard to the sync Session class
    (AsyncSession proxies it). Idempotent. Called from core.db AFTER install_tenancy_guards
    so audit's before_flush fires after tenancy stamps tenant_id (see module docstring)."""
    if not event.contains(Session, "before_flush", _capture_updates_and_deletes):
        event.listen(Session, "before_flush", _capture_updates_and_deletes)
    if not event.contains(Session, "after_flush", _capture_inserts):
        event.listen(Session, "after_flush", _capture_inserts)
    if not event.contains(Session, "after_flush_postexec", _write_buffer):
        event.listen(Session, "after_flush_postexec", _write_buffer)
    if not event.contains(Session, "do_orm_execute", _guard_bulk_audited_writes):
        event.listen(Session, "do_orm_execute", _guard_bulk_audited_writes)
