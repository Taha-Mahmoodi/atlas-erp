"""Admin provisioning service. Owns user creation (PLAN 14); auth primitives come
from core. Kept minimal and real — full onboarding (roles, settings, templates)
lands with PLAN 14."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import hash_password_async
from app.core.models import User
from app.core.tenancy import system_context
from app.modules.admin.models import Tenant


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
