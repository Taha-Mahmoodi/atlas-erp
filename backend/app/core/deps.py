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
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import actor_user_id_ctx
from app.core.auth import decode_token
from app.core.config import get_settings
from app.core.db import get_session, get_session_factory
from app.core.exceptions import AuthError
from app.core.models import User
from app.core.rbac import current_permissions, resolve_permissions
from app.core.tenancy import current_tenant_id

# get_session / get_settings are re-exported so routers depend on a single core.deps
# surface rather than reaching into core.db / core.config directly.
__all__ = [
    "CurrentUser",
    "CurrentUserDep",
    "SessionDep",
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


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
