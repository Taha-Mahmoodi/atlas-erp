"""Admin read queries (PLAN 14.3): the read side of user/role management, the audit
viewer, and the number-sequence viewer. Writes reuse admin/service.py; these are the
paginated, N+1-free reads the router needs on top of it.

Every list runs under the request's tenant context, so the D-007 filter tenant-isolates
the rows on top of the explicit ``tenant_id`` predicate — ordinary tenant-scoped reads,
never a bypass. STRUCTURE §5: this file imports core (models + pagination) and admin only,
never another module's internals.

Role→permission and user→role are the two spots that could N+1; both are answered with a
single JOIN + in-Python grouping keyed on the parent id, so a page of N roles (or one user's
roles) costs ONE extra query, not N.

``from __future__ import annotations`` keeps ``Page[User]`` and friends as STRING annotations
so Pydantic never eagerly builds a schema over the ORM row type at import (the finance-service
pattern) — these are the service-layer Page of ORM rows the router maps into wire schemas.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import (
    ApiKey,
    AuditLog,
    Permission,
    Role,
    RolePermission,
    User,
    UserRole,
)
from app.core.numbering import NumberSequence, NumberSequenceCounter
from app.core.pagination import OrderKey, SortDirection, filter_fingerprint, paginate
from app.core.schemas import Page


async def list_users(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    cursor: str | None,
    limit: int,
) -> Page[User]:
    """The tenant's users, keyset-paginated newest-first (D-014). Credentials only —
    password_hash is never serialized (the Read schema omits it)."""
    stmt = select(User).where(User.tenant_id == tenant_id)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(User.created_at, SortDirection.DESC)],
        pk=User.id,
        cursor=cursor,
        limit=limit,
    )


async def get_user_roles(
    session: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID
) -> list[Role]:
    """The roles assigned to one user, in one JOIN (no N+1). Empty list when the user has
    none; the caller checks user existence separately so an unknown user 404s, not [] ."""
    stmt = (
        select(Role)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user_id, Role.tenant_id == tenant_id)
        .order_by(Role.name)
    )
    return list((await session.execute(stmt)).scalars().all())


async def get_user(
    session: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID
) -> User | None:
    stmt = select(User).where(User.tenant_id == tenant_id, User.id == user_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_roles(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    cursor: str | None,
    limit: int,
) -> Page[Role]:
    """The tenant's roles, keyset-paginated by name (stable, human-ordered)."""
    stmt = select(Role).where(Role.tenant_id == tenant_id)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(Role.name, SortDirection.ASC)],
        pk=Role.id,
        cursor=cursor,
        limit=limit,
    )


async def get_role(
    session: AsyncSession, tenant_id: uuid.UUID, role_id: uuid.UUID
) -> Role | None:
    stmt = select(Role).where(Role.tenant_id == tenant_id, Role.id == role_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def permission_keys_for_roles(
    session: AsyncSession, tenant_id: uuid.UUID, role_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[str]]:
    """{role_id -> [permission keys]} for the given roles in ONE JOIN, grouped in Python —
    the N+1-free way to attach permissions to a page of roles (or one role). Returns an empty
    mapping for the empty input so callers can skip the query when a page has no roles."""
    if not role_ids:
        return {}
    stmt = (
        select(RolePermission.role_id, Permission.key)
        .join(Permission, Permission.id == RolePermission.permission_id)
        .where(
            RolePermission.tenant_id == tenant_id,
            RolePermission.role_id.in_(role_ids),
        )
        .order_by(Permission.key)
    )
    grouped: dict[uuid.UUID, list[str]] = defaultdict(list)
    for role_id, key in (await session.execute(stmt)).all():
        grouped[role_id].append(key)
    return grouped


async def list_permissions(session: AsyncSession) -> list[Permission]:
    """The GLOBAL permission catalog (core_permissions) — the grantable universe a role
    editor picks from (D-009). Not tenant-scoped: permissions are code-defined and identical
    for every tenant. Small, slow-changing set, so unpaginated is fine (YAGNI)."""
    stmt = select(Permission).order_by(Permission.key)
    return list((await session.execute(stmt)).scalars().all())


async def list_audit_logs(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    cursor: str | None,
    limit: int,
    entity_table: str | None = None,
    entity_id: str | None = None,
    actor_user_id: uuid.UUID | None = None,
    action: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> Page[AuditLog]:
    """The tenant's audit trail, keyset-paginated newest-first and optionally filtered by
    entity / actor / action / date range (D-010). Tenant-isolated by the D-007 filter, so a
    tenant can only ever read its OWN rows. The filter set is folded into the cursor
    fingerprint so a cursor from one filtered view cannot be replayed on another (D-014).

    Index note: the two filter paths (tenant_id+entity_table+entity_id and tenant_id+created_at)
    are both covered by the composite indexes on core_audit_log (see AuditLog.__table_args__),
    so the hot filters seek rather than scan.
    """
    stmt = select(AuditLog).where(AuditLog.tenant_id == tenant_id)
    if entity_table is not None:
        stmt = stmt.where(AuditLog.entity_table == entity_table)
    if entity_id is not None:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if actor_user_id is not None:
        stmt = stmt.where(AuditLog.actor_user_id == actor_user_id)
    if action is not None:
        stmt = stmt.where(AuditLog.action == action)
    if created_from is not None:
        stmt = stmt.where(AuditLog.created_at >= created_from)
    if created_to is not None:
        stmt = stmt.where(AuditLog.created_at <= created_to)
    fingerprint = filter_fingerprint(
        entity_table, entity_id, actor_user_id, action, created_from, created_to
    )
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(AuditLog.created_at, SortDirection.DESC)],
        pk=AuditLog.id,
        cursor=cursor,
        limit=limit,
        filters=fingerprint,
    )


async def list_api_keys(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    cursor: str | None,
    limit: int,
) -> Page[ApiKey]:
    """The tenant's machine credentials, keyset-paginated newest-first (D-014). Revoked and
    expired keys stay in the list: an operator auditing what was issued needs to see them.
    The stored digest is never serialized (the Read schema omits it)."""
    stmt = select(ApiKey).where(ApiKey.tenant_id == tenant_id)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(ApiKey.created_at, SortDirection.DESC)],
        pk=ApiKey.id,
        cursor=cursor,
        limit=limit,
    )


async def get_api_key(
    session: AsyncSession, tenant_id: uuid.UUID, key_id: uuid.UUID
) -> ApiKey | None:
    stmt = select(ApiKey).where(ApiKey.tenant_id == tenant_id, ApiKey.id == key_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_number_sequences(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    cursor: str | None,
    limit: int,
) -> Page[NumberSequence]:
    """The tenant's number sequences, keyset-paginated by name (D-012). Read-only viewer."""
    stmt = select(NumberSequence).where(NumberSequence.tenant_id == tenant_id)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(NumberSequence.name, SortDirection.ASC)],
        pk=NumberSequence.id,
        cursor=cursor,
        limit=limit,
    )


async def counters_for_sequences(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    sequence_ids: Sequence[uuid.UUID],
) -> dict[uuid.UUID, list[NumberSequenceCounter]]:
    """Every year's counter for the given sequences, newest year first — ONE statement for the
    whole page (PERFORMANCE §2), not one per sequence. An empty input short-circuits."""
    if not sequence_ids:
        return {}
    rows = (
        await session.execute(
            select(NumberSequenceCounter)
            .where(
                NumberSequenceCounter.tenant_id == tenant_id,
                NumberSequenceCounter.sequence_id.in_(list(sequence_ids)),
            )
            .order_by(NumberSequenceCounter.year.desc())
        )
    ).scalars()
    by_sequence: dict[uuid.UUID, list[NumberSequenceCounter]] = {}
    for row in rows:
        by_sequence.setdefault(row.sequence_id, []).append(row)
    return by_sequence
