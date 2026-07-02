"""RBAC engine (D-009): code-defined permission catalog, permission resolution with a
short TTL cache, the require_permission dependency factory, and field-level read masking.

The catalog is the source of truth: modules declare their permission keys in their
``constants.py`` and register them here at import time via ``register_permissions``;
``sync_permission_catalog`` upserts the registry into ``core_permissions`` so tenants
can only ever be granted keys that some code path actually checks. Roles and grants are
tenant data (core/models.py); resolution joins user_roles -> role_permissions ->
permissions in one query, memoized 60s keyed on (tenant_id, user_id, token_version).
"""

import functools
import time
import uuid
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from typing import Annotated, Any

from fastapi import Depends
from pydantic import WrapSerializer
from pydantic_core.core_schema import SerializerFunctionWrapHandler
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import PermissionDeniedError
from app.core.models import Permission, RolePermission, UserRole

# --- Permission catalog (code-defined source of truth) ------------------------

# Module-level registry. Modules call register_permissions at import; the values are
# the human-readable descriptions seeded alongside the key. Insertion-ordered so the
# catalog sync and tests see a stable order.
_CATALOG: dict[str, str | None] = {}


def register_permissions(*keys: str, descriptions: dict[str, str] | None = None) -> None:
    """Declare permission keys that exist in code (D-009). Idempotent: re-registering a
    key keeps the first description unless a new one is supplied. Modules call this at
    import from their ``constants.py`` (e.g. ``register_permissions(FIN_JOURNAL_POST)``)."""
    descriptions = descriptions or {}
    for key in keys:
        new_description = descriptions.get(key)
        if key not in _CATALOG or new_description is not None:
            _CATALOG[key] = new_description if new_description is not None else _CATALOG.get(key)


def catalog_keys() -> frozenset[str]:
    """The full set of code-declared permission keys (the grantable universe)."""
    return frozenset(_CATALOG)


# Core permission keys, registered at import (module __init__ files register theirs).
# Format is ``module.entity.action`` per STRUCTURE §7.
ADMIN_USER_MANAGE = "admin.user.manage"
ADMIN_ROLE_MANAGE = "admin.role.manage"
ADMIN_AUDIT_READ = "admin.audit.read"
ADMIN_TENANT_MANAGE = "admin.tenant.manage"
# The admin viewer over per-tenant number sequences (PLAN 14.3) is read-only, so it gets its
# own read key rather than reusing a .manage key that would imply a write it does not offer.
ADMIN_NUMBERING_READ = "admin.numbering.read"
CORE_DOCUMENT_READ = "core.document.read"
CORE_SETTING_MANAGE = "core.setting.manage"

register_permissions(
    ADMIN_USER_MANAGE,
    ADMIN_ROLE_MANAGE,
    ADMIN_AUDIT_READ,
    ADMIN_TENANT_MANAGE,
    ADMIN_NUMBERING_READ,
    CORE_DOCUMENT_READ,
    CORE_SETTING_MANAGE,
    descriptions={
        ADMIN_USER_MANAGE: "Create, edit and deactivate users",
        ADMIN_ROLE_MANAGE: "Create roles and assign permissions",
        ADMIN_AUDIT_READ: "Read the audit log",
        ADMIN_TENANT_MANAGE: "Manage tenant settings and provisioning",
        ADMIN_NUMBERING_READ: "View the tenant's number sequences",
        CORE_DOCUMENT_READ: "View documents and their flow",
        CORE_SETTING_MANAGE: "Manage tenant-level configuration",
    },
)


async def sync_permission_catalog(session: AsyncSession) -> int:
    """Upsert every code-declared key into core_permissions (D-009). Idempotent: existing
    keys are left as-is, only missing ones are inserted, so re-running creates no dupes.
    Permissions are GLOBAL data — callers run this under system_context (seed/provisioning).
    Returns the number of rows inserted this call."""
    existing = set(
        (await session.execute(select(Permission.key))).scalars().all()
    )
    inserted = 0
    for key, description in _CATALOG.items():
        if key in existing:
            continue
        session.add(Permission(key=key, description=description))
        inserted += 1
    await session.flush()
    return inserted


# --- Permission resolution + TTL cache (D-009) --------------------------------

_CACHE_TTL_SECONDS = 60.0
# key -> (expires_at_monotonic, permissions). Process-local; multi-worker deploys lag
# per worker by at most the TTL, or instantly on token_version bump (the key changes).
_CACHE: dict[tuple[uuid.UUID, uuid.UUID, int], tuple[float, frozenset[str]]] = {}


def clear_cache() -> None:
    """Drop every cached resolution. Used by tests and a future global flush."""
    _CACHE.clear()


def invalidate(tenant_id: uuid.UUID, user_id: uuid.UUID, token_version: int) -> None:
    """Evict one principal's cached permissions after a role change (D-009). Callers that
    only know (tenant, user) can pass any token_version they hold; on mismatch the stale
    entry simply expires within the TTL — but admin role mutations should pass the live
    token_version so the next request recomputes immediately."""
    _CACHE.pop((tenant_id, user_id, token_version), None)


async def _query_permissions(
    session: AsyncSession, user_id: uuid.UUID, tenant_id: uuid.UUID
) -> frozenset[str]:
    """ONE join: user_roles -> role_permissions -> permissions -> effective key set.
    Runs under the request's tenant context, so the user_roles/role_permissions rows are
    already tenant-filtered; the explicit user_id predicate narrows to this principal."""
    stmt = (
        select(Permission.key)
        .select_from(UserRole)
        .join(RolePermission, RolePermission.role_id == UserRole.role_id)
        .join(Permission, Permission.id == RolePermission.permission_id)
        .where(UserRole.user_id == user_id)
        .distinct()
    )
    keys = (await session.execute(stmt)).scalars().all()
    return frozenset(keys)


async def resolve_permissions(
    session: AsyncSession,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    token_version: int,
    now: float | None = None,
) -> frozenset[str]:
    """Effective permission set for a principal, memoized 60s (D-009). ``now`` is an
    optional monotonic timestamp for deterministic tests; production uses time.monotonic.
    Tests prefer clear_cache()/invalidate() over advancing the clock."""
    clock = now if now is not None else time.monotonic()
    cache_key = (tenant_id, user_id, token_version)
    cached = _CACHE.get(cache_key)
    if cached is not None and cached[0] > clock:
        return cached[1]
    permissions = await _query_permissions(session, user_id, tenant_id)
    _CACHE[cache_key] = (clock + _CACHE_TTL_SECONDS, permissions)
    return permissions


# --- require_permission dependency factory (D-009) ----------------------------


def require_permission(key: str) -> Callable[..., Awaitable[Any]]:
    """FastAPI dependency factory: returns a dependency that loads the current principal
    (reusing get_current_user) and raises PermissionDeniedError (403, code
    ``rbac.permission_denied``, details naming the missing key) unless ``key`` is in the
    principal's resolved permissions. Attach per route via
    ``dependencies=[Depends(require_permission(ADMIN_USER_MANAGE))]``."""

    # Imported here, not at module top, to avoid a core import cycle: deps imports rbac
    # (get_current_user resolves permissions) and rbac imports deps (this guard).
    from app.core.deps import CurrentUser, get_current_user

    async def _dependency(
        current: Annotated[CurrentUser, Depends(get_current_user)],
    ) -> CurrentUser:
        if key not in current.permissions:
            raise PermissionDeniedError(
                code="rbac.permission_denied",
                message=f"Missing permission: {key}",
                details={"permission": key},
            )
        return current

    return _dependency


# --- Field-level read masking (D-009) -----------------------------------------

# Serialization-time principal permissions. Set by get_current_user per request and by
# the test ``permissions_context`` fixture; default empty so anything serialized OUTSIDE
# a request (jobs, tests without the fixture) fails CLOSED — masked fields read as None.
current_permissions: ContextVar[frozenset[str]] = ContextVar(
    "current_permissions", default=frozenset()
)

def _mask_serializer(
    permission: str, value: Any, handler: SerializerFunctionWrapHandler
) -> Any:
    """WrapSerializer body (D-009): emit the real serialized value only when the guarding
    permission is present in current_permissions, else None. The permission is bound via
    functools.partial below — a WrapSerializer cannot read loose Annotated metadata."""
    if permission in current_permissions.get():
        return handler(value)
    return None


def Masked[T](tp: type[T], permission: str) -> Any:  # noqa: N802 - type-factory, PascalCase by design
    """Annotate a Pydantic field as read-masked behind ``permission`` (D-009).

    Usage::

        class EmployeeRead(ApiModel):
            base_salary: Masked(Decimal | None, "hr.compensation.read")

    Serializes to the real value when current_permissions contains the key, else None.
    CONVENTION: masked fields are EXCLUDED from the entity's Create/Update schemas and
    edited through a separate permission-guarded endpoint, so a partial update can never
    silently null a masked field (the HR module enforces this for compensation)."""
    return Annotated[
        tp | None,
        WrapSerializer(functools.partial(_mask_serializer, permission)),
    ]
