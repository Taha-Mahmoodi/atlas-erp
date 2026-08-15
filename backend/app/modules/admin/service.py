"""Admin provisioning service. Owns user/role management (PLAN 14); auth primitives and
RBAC resolution come from core. Kept minimal and real — full onboarding (settings,
templates) lands with PLAN 14."""

import uuid
from collections.abc import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import API_KEY_PREFIX, hash_password_async, mint_api_key, now_utc
from app.core.exceptions import ValidationFailedError
from app.core.models import ApiKey, Permission, Role, RolePermission, User, UserRole
from app.core.rbac import (
    ADMIN_APIKEY_MANAGE,
    ADMIN_AUDIT_READ,
    ADMIN_NUMBERING_READ,
    ADMIN_ROLE_MANAGE,
    ADMIN_TENANT_MANAGE,
    ADMIN_USER_MANAGE,
    catalog_keys,
    invalidate,
)
from app.core.tenancy import system_context
from app.modules.admin.models import Tenant
from app.modules.admin.schemas import ApiKeyCreate

# The admin keys a tenant's first user (the admin) gets via grant_admin_role.
_ADMIN_PERMISSION_KEYS = (
    ADMIN_USER_MANAGE,
    ADMIN_ROLE_MANAGE,
    ADMIN_AUDIT_READ,
    ADMIN_TENANT_MANAGE,
    ADMIN_NUMBERING_READ,
    ADMIN_APIKEY_MANAGE,
)


async def provision_user(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    email: str,
    password: str,
    full_name: str | None = None,
) -> User:
    """Create a tenant's user under system_context (D-007 sanctioned site 2), hashing
    the password with argon2id. tenant_id is set explicitly because system_context
    suspends the stamping listener. Used by seed and the test tenant_factory."""
    password_hash = await hash_password_async(password)
    user = User(
        tenant_id=tenant_id,
        email=email,
        password_hash=password_hash,
        full_name=full_name,
    )
    with system_context():
        session.add(user)
        await session.flush()
    return user


async def provision_tenant(
    session: AsyncSession,
    slug: str,
    name: str,
) -> Tenant:
    """Create a tenancy-root tenant under system_context. Minimal counterpart to
    provision_user so tests/seed have one real provisioning path (PLAN 14 extends it)."""
    tenant = Tenant(slug=slug, name=name)
    with system_context():
        session.add(tenant)
        await session.flush()
    return tenant


async def find_user_by_email(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    email: str,
) -> User | None:
    """Login user-lookup (D-007 sanctioned site 1) under system_context — the tenant
    is resolved from the request body's slug, not from a trusted context yet."""
    with system_context():
        result = await session.execute(
            select(User).where(User.tenant_id == tenant_id, User.email == email)
        )
        return result.scalar_one_or_none()


async def find_tenant_by_slug(session: AsyncSession, slug: str) -> Tenant | None:
    """Tenants are not TenantMixin, so this needs no context; kept here so login
    resolves both tenant and user through the admin service surface."""
    result = await session.execute(select(Tenant).where(Tenant.slug == slug))
    return result.scalar_one_or_none()


# --- Role management (D-009) --------------------------------------------------


async def create_role(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    name: str,
    permission_keys: Iterable[str],
    *,
    is_system: bool = False,
) -> Role:
    """Create a tenant role and grant it the named permissions (D-009). Keys are
    validated against the GLOBAL catalog rows (core_permissions): a key that no code
    declares — and so was never synced — raises ValidationFailedError, enforcing 'tenants
    cannot invent keys nothing enforces'. Runs under system_context so the global
    core_permissions lookup is unfiltered while tenant_id is stamped explicitly."""
    keys = list(dict.fromkeys(permission_keys))
    role = Role(tenant_id=tenant_id, name=name, description=None, is_system=is_system)
    with system_context():
        rows = (
            await session.execute(select(Permission).where(Permission.key.in_(keys)))
        ).scalars().all()
        found = {permission.key: permission.id for permission in rows}
        missing = [key for key in keys if key not in found]
        if missing:
            raise ValidationFailedError(
                code="rbac.unknown_permission",
                message="Unknown permission key(s)",
                details={"keys": missing},
            )
        session.add(role)
        await session.flush()  # role.id needed for the grants below
        for key in keys:
            session.add(
                RolePermission(
                    tenant_id=tenant_id, role_id=role.id, permission_id=found[key]
                )
            )
        await session.flush()
    return role


async def assign_role(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    role_id: uuid.UUID,
    token_version: int,
) -> UserRole:
    """Assign a role to a user and evict the cached resolution so the new permissions
    appear on the next request (D-009). token_version is passed so the exact cache key is
    invalidated. Runs under system_context for explicit tenant stamping."""
    assignment = UserRole(tenant_id=tenant_id, user_id=user_id, role_id=role_id)
    with system_context():
        session.add(assignment)
        await session.flush()
    invalidate(tenant_id, user_id, token_version)
    return assignment


async def grant_admin_role(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    token_version: int = 0,
    role_name: str = "Administrator",
    *,
    permission_keys: Sequence[str] = _ADMIN_PERMISSION_KEYS,
) -> Role:
    """Convenience used by tests/provisioning to make a tenant's first user a full admin
    (D-009): create (or reuse) the admin role with ``permission_keys`` and assign it.

    ``permission_keys`` defaults to the six admin.* keys — the narrow role every existing
    caller (seed, the test factories) already got. Onboarding overrides BOTH it and
    ``role_name`` (#165, D-075): a tenant's FIRST human has to be able to read what its own
    industry template just created, and the six admin keys cover none of the COA/tax/UoM rows
    the template writes, so the wizard grants a wide ``Owner`` role instead. Keys are still
    validated against the synced catalog by ``create_role``, so callers must sync first.

    Only used when the role is CREATED: an existing role of the same name is reused as-is
    rather than re-granted, because re-granting would silently re-widen a role a tenant
    admin had deliberately narrowed."""
    with system_context():
        existing = (
            await session.execute(
                select(Role).where(Role.tenant_id == tenant_id, Role.name == role_name)
            )
        ).scalar_one_or_none()
    role = existing or await create_role(
        session, tenant_id, role_name, permission_keys, is_system=True
    )
    await assign_role(session, tenant_id, user_id, role.id, token_version)
    return role


# --- Machine credentials (spec Q1) --------------------------------------------


async def create_api_key(
    session: AsyncSession, tenant_id: uuid.UUID, payload: ApiKeyCreate
) -> tuple[ApiKey, str]:
    """Mint a key for one of the tenant's users and store only its digest, returning
    (row, full key). The caller shows the full key ONCE — it is never stored, so a lost
    key is re-issued, never recovered.

    Scopes validate against the CODE catalog, not the tenant's granted rows (D-009): a
    tenant cannot scope a key to a permission no code path checks. No subset check against
    the bound user's own permissions is done here — authentication intersects the two on
    every request (core/deps.py), so a key can only ever narrow its user, and a later role
    change re-narrows it without orphaning the key.

    The key string carries the tenant UUID because that is the ref core/deps.py sets the
    D-007 ContextVar from; minting on any other ref produces a key that authenticates
    against nothing. Not the slug: resolving a slug costs a query on EVERY request, which
    put an API-key list request at 4 statements, over PERFORMANCE §2's ≤3.
    """
    unknown = sorted(set(payload.scopes or ()) - catalog_keys())
    if unknown:
        raise ValidationFailedError(
            code="rbac.unknown_permission",
            message="Unknown permission key(s)",
            details={"keys": unknown},
        )
    full_key, secret_sha256 = mint_api_key(tenant_id)
    key = ApiKey(
        tenant_id=tenant_id,
        user_id=payload.user_id,
        name=payload.name,
        # Scheme + tenant ref, rebuilt from its parts rather than sliced off the key:
        # secrets.token_urlsafe emits '_', so splitting the key on the LAST underscore
        # lands inside the secret about half the time and stores most of it in a column
        # the list endpoint displays. No part of the secret belongs here — operators tell
        # two keys apart by ``name``.
        prefix=f"{API_KEY_PREFIX}_{tenant_id.hex}",
        secret_sha256=secret_sha256,
        scopes=payload.scopes,
        expires_at=payload.expires_at,
    )
    session.add(key)
    await session.flush()
    return key, full_key


async def revoke_api_key(session: AsyncSession, key: ApiKey) -> ApiKey:
    """Revoke a key, keeping the first revocation timestamp so a SEQUENTIAL retry is a no-op
    rather than an error. It takes effect on the very next request: core/deps.py re-reads the
    row on every call and nothing caches it.

    Sequential, precisely: two revokes of one key racing in separate transactions both read
    ``revoked_at IS NULL`` and both write, so the later stamp can win and one caller is told a
    time that is not the stored one (tests/core/test_api_key_concurrency.py pins this). Left
    as-is deliberately — closing it needs an atomic ``UPDATE ... WHERE revoked_at IS NULL``,
    and ApiKey is AuditMixin, so neither form is available: the ORM one is a hard 409 from
    core/audit.py's ``_guard_bulk_audited_writes``, and a raw Core one skips the flush events
    D-010 capture hooks. The credential is equally revoked either way."""
    if key.revoked_at is None:
        key.revoked_at = now_utc()
        await session.flush()
    return key
