"""FastAPI dependencies (D-008 get_current_user, D-007 production ContextVar setter).

This is the ONE place that sets `current_tenant_id` for the request lifecycle from a
validated access token; the pure-ASGI middleware in app.main resets it in a finally
block so request A's tenant never leaks to request B on the same worker.
"""

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.audit import actor_user_id_ctx
from app.core.auth import as_utc, decode_token, now_utc, parse_api_key
from app.core.config import get_settings
from app.core.db import get_session, get_session_factory
from app.core.exceptions import AuthError
from app.core.models import ApiKey, User
from app.core.rbac import current_permissions, resolve_permissions
from app.core.tenancy import current_tenant_id
from app.modules.admin.service import find_tenant_by_slug

# get_session / get_settings are re-exported so routers depend on a single core.deps
# surface rather than reaching into core.db / core.config directly.
__all__ = [
    "CurrentUser",
    "CurrentUserDep",
    "SessionDep",
    "SessionFactoryDep",
    "get_current_user",
    "get_session",
    "get_session_factory",
    "get_settings",
]

# auto_error=False: a missing/blank header must surface as the D-014 auth envelope
# (AuthError -> 401), not Starlette's bare 403 HTTPException.
_bearer_scheme = HTTPBearer(auto_error=False)

# Annotated dependency aliases: the modern FastAPI idiom that keeps Depends() out of
# parameter defaults (ruff B008) and lets routers share one typed handle.
SessionDep = Annotated[AsyncSession, Depends(get_session)]
# The sessionmaker dependency (test-overridable like get_session). Job-submitting routers pass
# it to schedule_job post-commit so the runner opens its sessions against the SAME database —
# the app factory in production, the per-test engine's factory under the conftest override.
SessionFactoryDep = Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)]
_CredentialsDep = Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)]


@dataclass(frozen=True)
class CurrentUser:
    """Resolved request principal (D-008/D-009). `permissions` is the effective key set
    resolved by RBAC (one join query, cached 60s)."""

    user_id: uuid.UUID
    tenant_id: uuid.UUID
    permissions: frozenset[str]
    token_version: int


async def get_current_user(
    credentials: _CredentialsDep,
    session: SessionDep,
) -> CurrentUser:
    if credentials is None:
        raise AuthError(message="Missing bearer token", code="auth.invalid_token")

    # Two credential shapes reach this function: a user access JWT and a machine API key
    # (spec Q1). They converge on the SAME CurrentUser, which is why no router, no
    # require_permission call and no idempotency path needed changing. parse_api_key
    # never raises — a malformed key is simply not key-shaped and falls through to the
    # JWT decode, which rejects it.
    parsed = parse_api_key(credentials.credentials)
    if parsed is not None:
        return await _authenticate_api_key(session, *parsed)

    claims = decode_token(credentials.credentials, expected_typ="access")
    try:
        user_id = uuid.UUID(claims["sub"])
        tenant_id = uuid.UUID(claims["tenant_id"])
        claim_version = int(claims["ver"])
    except (KeyError, ValueError, TypeError) as exc:
        raise AuthError(message="Invalid token", code="auth.invalid_token") from exc

    # Set the tenancy ContextVar FROM the validated token (D-007 production setter):
    # the user lookup below then runs under the token's tenant, so a tampered
    # tenant_id can only ever resolve a user that actually belongs to that tenant —
    # cross-tenant access is impossible. The middleware resets this in a finally block.
    current_tenant_id.set(tenant_id)

    user = (
        await session.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if user is None or not user.is_active:
        raise AuthError(message="Invalid token", code="auth.invalid_token")
    if user.token_version != claim_version:
        # Stale token after a "revoke everything" bump (D-008).
        raise AuthError(message="Invalid token", code="auth.invalid_token")

    # RBAC resolution (D-009): one join query, memoized 60s on
    # (tenant_id, user_id, token_version). Runs under the tenant context set above, so
    # the user_roles/role_permissions rows are already tenant-filtered.
    permissions = await resolve_permissions(
        session, user.id, user.tenant_id, user.token_version
    )
    # Serialization-time masking (D-009) reads this ContextVar; the middleware resets it
    # in a finally block alongside current_tenant_id so it never leaks across requests.
    current_permissions.set(permissions)
    # D-010 audit context: now that the principal is known, stamp the actor onto every
    # audit row this request writes. The middleware seeded it None (system) and resets it.
    actor_user_id_ctx.set(user.id)

    return CurrentUser(
        user_id=user.id,
        tenant_id=user.tenant_id,
        permissions=permissions,
        token_version=user.token_version,
    )


async def _authenticate_api_key(
    session: AsyncSession, tenant_ref: str, secret_sha256: str
) -> CurrentUser:
    """Resolve a machine API key to the same principal a JWT would produce (spec Q1).

    The tenancy ContextVar is set from the key's OWN tenant ref before the key is looked
    up, exactly as the JWT path above does from the token claim — so the key row is read
    under the ordinary D-007 filter and a key presented with someone else's tenant ref
    can only ever find nothing. This is why the machine credential needs no fifth
    sanctioned system_context() bypass (core/tenancy.py).
    """
    # Tenants are not TenantMixin, so resolving the ref needs no tenant context — the
    # same reason login can call this before any principal exists. Reused rather than
    # reimplemented so there is one slug resolver, not two.
    tenant = await find_tenant_by_slug(session, tenant_ref)
    if tenant is None or not tenant.is_active:
        raise AuthError(message="Invalid API key", code="auth.invalid_token")
    current_tenant_id.set(tenant.id)

    # ONE joined statement, not a key SELECT followed by a user SELECT: PERFORMANCE §2
    # budgets ≤3 statements per list request and tests/conftest.py warns that its one
    # query of slack is a regression margin, not headroom.
    row = (
        await session.execute(
            select(User, ApiKey)
            .join(ApiKey, ApiKey.user_id == User.id)
            .where(ApiKey.secret_sha256 == secret_sha256)
        )
    ).one_or_none()
    if row is None:
        raise AuthError(message="Invalid API key", code="auth.invalid_token")

    user, key = row
    # as_utc because aiosqlite round-trips DateTime(timezone=True) as naive (core/auth).
    if (
        not user.is_active
        or key.revoked_at is not None
        or (key.expires_at is not None and as_utc(key.expires_at) <= now_utc())
    ):
        raise AuthError(message="Invalid API key", code="auth.invalid_token")

    permissions = await resolve_permissions(
        session, user.id, user.tenant_id, user.token_version
    )
    if key.scopes is not None:
        # Intersection, never union (D-009): a key may narrow its user's permissions and
        # can never grant one the user does not hold. NULL scopes inherit unnarrowed.
        permissions &= frozenset(key.scopes)

    # Same three ContextVars the JWT path sets: masking (D-009) and the audit actor
    # (D-010), which resolves because the key is bound to a real core_users row.
    current_permissions.set(permissions)
    actor_user_id_ctx.set(user.id)
    return CurrentUser(
        user_id=user.id,
        tenant_id=user.tenant_id,
        permissions=permissions,
        # The key's own revocation lives in revoked_at; carrying the user's token_version
        # keeps the "revoke everything" bump a kill-switch for both credential shapes.
        token_version=user.token_version,
    )


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
