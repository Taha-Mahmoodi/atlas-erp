"""Admin provisioning service. Owns user/role management (PLAN 14); auth primitives and
RBAC resolution come from core. Kept minimal and real — full onboarding (settings,
templates) lands with PLAN 14."""

import uuid
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import hash_password_async
from app.core.exceptions import ValidationFailedError
from app.core.models import Permission, Role, RolePermission, User, UserRole
from app.core.rbac import (
    ADMIN_AUDIT_READ,
    ADMIN_ROLE_MANAGE,
    ADMIN_TENANT_MANAGE,
    ADMIN_USER_MANAGE,
    invalidate,
)
from app.core.tenancy import system_context
from app.modules.admin.models import Tenant

# The four keys a tenant's first user (the admin) gets via grant_admin_role.
_ADMIN_PERMISSION_KEYS = (
    ADMIN_USER_MANAGE,
    ADMIN_ROLE_MANAGE,
    ADMIN_AUDIT_READ,
    ADMIN_TENANT_MANAGE,
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
) -> Role:
    """Convenience used by tests/provisioning to make a tenant's first user a full admin
    (D-009): create (or reuse) the admin role with the four admin keys and assign it."""
    with system_context():
        existing = (
            await session.execute(
                select(Role).where(Role.tenant_id == tenant_id, Role.name == role_name)
            )
        ).scalar_one_or_none()
    role = existing or await create_role(
        session, tenant_id, role_name, _ADMIN_PERMISSION_KEYS, is_system=True
    )
    await assign_role(session, tenant_id, user_id, role.id, token_version)
    return role
