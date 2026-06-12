"""D-007 tenancy enforcement: context, non-bypassable session filter, write stamping.

Three of the four cooperating D-007 layers live here:
1. Context — the `current_tenant_id` ContextVar (set by core/deps.py after JWT
   validation from PLAN 3.3 on; by `tenant_context()` in tests and seed).
2. Read/write filtering — the `do_orm_execute` listener.
3. Write stamping — the `before_flush` listener.
The fourth layer (composite FKs + the SQLite FK pragma) lives in core/models.py
and core/db.py.
"""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from itertools import chain

from sqlalchemy import event
from sqlalchemy.orm import ORMExecuteState, Session, with_loader_criteria

from app.core.exceptions import TenancyError
from app.core.models import TenantMixin

current_tenant_id: ContextVar[uuid.UUID | None] = ContextVar("current_tenant_id", default=None)
_system_context: ContextVar[bool] = ContextVar("system_context", default=False)


def get_current_tenant_id() -> uuid.UUID | None:
    """Active tenant id, fail-closed: raises unless a tenant context is set.
    Returns None only while system_context() is active."""
    tenant_id = current_tenant_id.get()
    if tenant_id is None and not _system_context.get():
        raise TenancyError("No tenant context is active")
    return tenant_id


@contextmanager
def tenant_context(tenant_id: uuid.UUID) -> Iterator[None]:
    """Run the block as one tenant (tests, seed transaction phase; request handling
    sets the ContextVar directly in core/deps.py with middleware reset, per D-007)."""
    token = current_tenant_id.set(tenant_id)
    try:
        yield
    finally:
        current_tenant_id.reset(token)


@contextmanager
def system_context() -> Iterator[None]:
    """Suspend tenant filtering and write stamping for the block.

    Sanctioned in exactly four greppable app call sites (D-007):
    1. login user-lookup (core/auth, PLAN 3.3);
    2. tenant provisioning in modules/admin (PLAN 14.2);
    3. Alembic/seed provisioning phase (seed.py, PLAN 16);
    4. event-bus system-event replay (core/events, PLAN 3.6).
    Test fixtures may also use it (D-025 tenant_factory). Writers under system
    context must set tenant_id explicitly; the composite-FK backstop still applies.
    """
    token = _system_context.set(True)
    try:
        yield
    finally:
        _system_context.reset(token)


def _involves_tenant_scoped_entities(execute_state: ORMExecuteState) -> bool:
    # all_mappers inspects select() column descriptions / mapper entities AND the
    # bind mapper of ORM-enabled update()/delete() — the D-007 involvement rule.
    return any(issubclass(m.class_, TenantMixin) for m in execute_state.all_mappers)


def _filter_tenant_statements(execute_state: ORMExecuteState) -> None:
    """do_orm_execute listener: inject the tenant predicate into every ORM
    select/update/delete; fail-closed when tenant-scoped entities are touched
    without a tenant context."""
    if not execute_state.is_orm_statement:
        # Core statements bypass by design: sanctioned only inside core/ with
        # explicit tenant_id, bounded by the D-007 grep gate.
        return
    if execute_state.is_column_load or execute_state.is_relationship_load:
        # Refresh and lazy loads inherit the criteria propagated from their
        # originating statement; re-injecting here would break attribute refresh.
        return
    if not (execute_state.is_select or execute_state.is_update or execute_state.is_delete):
        return
    if _system_context.get():
        return
    tenant_id = current_tenant_id.get()
    if tenant_id is None:
        if _involves_tenant_scoped_entities(execute_state):
            raise TenancyError("Tenant-scoped statement executed without a tenant context")
        # Statements touching only non-tenant tables (Alembic bookkeeping, the
        # tenants root) legitimately run with no tenant context.
        return
    execute_state.statement = execute_state.statement.options(
        with_loader_criteria(
            TenantMixin,
            # The ContextVar is read above, in this per-execution listener — the
            # lambda-SQL system forbids invoking .get() inside the lambda itself.
            # track_closure_variables=False keeps the closure value out of the
            # statement cache key, so each execution binds the fresh tenant id
            # instead of baking in the first value seen (pinned by a test).
            lambda cls: cls.tenant_id == tenant_id,
            include_aliases=True,
            track_closure_variables=False,
        )
    )


def _stamp_tenant_on_flush(session: Session, flush_context: object, instances: object) -> None:
    """before_flush listener: stamp tenant_id on new tenant-scoped instances and
    reject any new/dirty instance whose tenant_id differs from the context."""
    if _system_context.get():
        # Provisioning/seed/system writes set tenant_id explicitly; the composite
        # FK backstop still rejects ids that do not exist in adm_tenants.
        return
    active = current_tenant_id.get()
    for obj in chain(session.new, session.dirty):
        if not isinstance(obj, TenantMixin):
            continue
        if active is None:
            raise TenancyError("Tenant-scoped instance flushed without a tenant context")
        if obj.tenant_id is None:
            obj.tenant_id = active
        elif obj.tenant_id != active:
            raise TenancyError(
                "Instance tenant_id differs from the active tenant context",
                code="tenancy.tenant_mismatch",
            )


def install_tenancy_guards() -> None:
    """Attach both listeners to the sync Session class — AsyncSession proxies it,
    so every execute call and relationship load is covered. Idempotent so repeated
    calls cannot double-register. Invoked at import time of app.core.db: every
    engine/session factory in app, tests and seed is built from that module, so no
    session can exist unguarded (models.py cannot host the call — this module
    imports TenantMixin from it, which would be an import cycle)."""
    if not event.contains(Session, "do_orm_execute", _filter_tenant_statements):
        event.listen(Session, "do_orm_execute", _filter_tenant_statements)
    if not event.contains(Session, "before_flush", _stamp_tenant_on_flush):
        event.listen(Session, "before_flush", _stamp_tenant_on_flush)
