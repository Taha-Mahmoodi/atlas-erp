"""Core-level auth endpoints (D-008): login, refresh, logout, me.

JUSTIFIED ADDITION to core: auth endpoints are cross-cutting platform, not a business
module — STRUCTURE's module list has no `auth`, and they don't belong to any single
module. Routers normally live in modules/, so this is a deliberate, recorded exception
(prefix /api/v1/auth). Logic stays thin: it composes core/auth primitives, the
admin provisioning service, and the RefreshSession model.
"""

import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Request, Response
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import auth
from app.core.config import get_settings
from app.core.deps import CurrentUserDep, SessionDep
from app.core.exceptions import AuthError
from app.core.models import RefreshSession, User
from app.core.schemas import LoginRequest, MeResponse, TokenResponse
from app.core.tenancy import current_tenant_id, system_context
from app.modules.admin.service import find_tenant_by_slug, find_user_by_email

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# Cookie scoped to the refresh endpoints only (D-008): the access token is never a
# cookie, so the SPA holds it in memory; the refresh cookie is invisible to JS.
_COOKIE_NAME = "atlas_refresh"
_COOKIE_PATH = "/api/v1/auth"
# Grace window for benign multi-tab refresh races (D-008): a refresh presenting the
# immediately-previous jti within this window rotates instead of revoking the family.
_GRACE_SECONDS = 10


def _set_refresh_cookie(response: Response, refresh_token: str, max_age: int) -> None:
    response.set_cookie(
        key=_COOKIE_NAME,
        value=refresh_token,
        max_age=max_age,
        path=_COOKIE_PATH,
        httponly=True,
        secure=True,
        samesite="strict",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(key=_COOKIE_NAME, path=_COOKIE_PATH, httponly=True, secure=True)


def _refresh_ttl_seconds() -> int:
    return get_settings().jwt_refresh_ttl_seconds


def _issue_tokens(
    response: Response,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    sid: uuid.UUID,
    token_version: int,
    now: datetime,
) -> tuple[TokenResponse, str]:
    """Mint a fresh access+refresh pair and set the refresh cookie. Returns the body
    and the new refresh jti (caller stores its hash as the session's current jti)."""
    access_token = auth.encode_access(user_id, tenant_id, sid, token_version, now=now)
    refresh_token = auth.encode_refresh(user_id, tenant_id, sid, now=now)
    _set_refresh_cookie(response, refresh_token, _refresh_ttl_seconds())
    new_jti = auth.decode_token(refresh_token, expected_typ="refresh")["jti"]
    return TokenResponse(access_token=access_token), new_jti


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: SessionDep,
) -> TokenResponse:
    # Tenant + user resolution runs under system_context (D-007 site 1) — no trusted
    # tenant context exists yet. Generic 401 for every failure so we never reveal
    # whether the tenant, the email, or the password was wrong.
    tenant = await find_tenant_by_slug(session, payload.tenant_slug)
    if tenant is None or not tenant.is_active:
        raise AuthError()
    user = await find_user_by_email(session, tenant.id, payload.email)
    if user is None or not user.is_active:
        raise AuthError()
    if not await auth.verify_password_async(user.password_hash, payload.password):
        raise AuthError()

    # Upgrade the stored hash if the argon2 parameters strengthened since it was made.
    # Mutate the LOADED object, not an ORM bulk update(): the D-010 audit bulk-write guard
    # forbids ORM update()/delete() on AuditMixin models (User is audited). password_hash is
    # in User.__audit_exclude__, so this flush writes no audit row — credentials never leak
    # into the trail (D-010 v1 policy: mutate auditable entities via loaded objects).
    if auth.needs_rehash(user.password_hash):
        user.password_hash = await auth.hash_password_async(payload.password)

    now = auth.now_utc()
    sid = uuid.uuid4()
    body, new_jti = _issue_tokens(response, user.id, tenant.id, sid, user.token_version, now)

    with system_context():
        session.add(
            RefreshSession(
                id=sid,
                tenant_id=tenant.id,
                user_id=user.id,
                current_jti_hash=auth.sha256_hex(new_jti),
                issued_at=now,
                last_used_at=now,
                expires_at=now + timedelta(seconds=_refresh_ttl_seconds()),
                ip=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
            )
        )
        await session.commit()
    return body


async def _load_session(session: AsyncSession, sid: uuid.UUID) -> RefreshSession | None:
    result = await session.execute(select(RefreshSession).where(RefreshSession.id == sid))
    return result.scalar_one_or_none()


async def _revoke_family(session: AsyncSession, sid: uuid.UUID, now: datetime) -> None:
    await session.execute(
        update(RefreshSession).where(RefreshSession.id == sid).values(revoked_at=now)
    )
    await session.commit()


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    response: Response,
    session: SessionDep,
) -> TokenResponse:
    token = request.cookies.get(_COOKIE_NAME)
    if not token:
        raise AuthError(message="Missing refresh token", code="auth.invalid_token")

    claims = auth.decode_token(token, expected_typ="refresh")
    try:
        sid = uuid.UUID(claims["sid"])
        tenant_id = uuid.UUID(claims["tenant_id"])
        user_id = uuid.UUID(claims["sub"])
    except (KeyError, ValueError, TypeError) as exc:
        raise AuthError(message="Invalid refresh token", code="auth.invalid_token") from exc

    # Refresh sets the tenancy ContextVar directly from the validated claim (D-007
    # item 1: refresh does NOT use system_context), so the session loads run scoped.
    current_tenant_id.set(tenant_id)

    sess = await _load_session(session, sid)
    now = auth.now_utc()
    if sess is None or sess.revoked_at is not None or auth.as_utc(sess.expires_at) <= now:
        raise AuthError(message="Invalid refresh token", code="auth.invalid_token")

    presented_hash = auth.sha256_hex(claims["jti"])

    if presented_hash == sess.current_jti_hash:
        return await _rotate(session, sess, user_id, tenant_id, response, now)

    within_grace = (
        sess.prev_jti_hash is not None
        and presented_hash == sess.prev_jti_hash
        and sess.rotated_at is not None
        and (now - auth.as_utc(sess.rotated_at)) < timedelta(seconds=_GRACE_SECONDS)
    )
    if within_grace:
        # Benign concurrent refresh (a second tab raced or a response was lost):
        # rotate again from the CURRENT chain rather than revoking the family.
        return await _rotate(session, sess, user_id, tenant_id, response, now)

    # Any other mismatch is a replay of a stale token: kill the whole session family.
    await _revoke_family(session, sid, now)
    raise AuthError(message="Refresh token reuse detected", code="auth.invalid_token")


async def _rotate(
    session: AsyncSession,
    sess: RefreshSession,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    response: Response,
    now: datetime,
) -> TokenResponse:
    """Issue a new token pair and compare-and-swap the session's jti chain. The CAS
    WHERE clause makes a true race deterministic: the loser updates 0 rows and gets a
    401 (it will retry through the grace branch with the prev jti). token_version is
    re-read from the user row so a mid-session global revoke takes effect on refresh."""
    user = (
        await session.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if user is None or not user.is_active:
        raise AuthError(message="Invalid refresh token", code="auth.invalid_token")

    sid = sess.id
    body, new_jti = _issue_tokens(response, user_id, tenant_id, sid, user.token_version, now)
    new_hash = auth.sha256_hex(new_jti)
    old_current = sess.current_jti_hash

    result = await session.execute(
        update(RefreshSession)
        .where(RefreshSession.id == sid, RefreshSession.current_jti_hash == old_current)
        .values(
            prev_jti_hash=old_current,
            current_jti_hash=new_hash,
            rotated_at=now,
            last_used_at=now,
        )
    )
    if result.rowcount == 0:
        # Lost a true CAS race: another worker rotated first. Roll back and 401; the
        # client retries and lands in the grace branch on the next attempt.
        await session.rollback()
        raise AuthError(message="Concurrent refresh", code="auth.invalid_token")
    await session.commit()
    return body


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    response: Response,
    session: SessionDep,
) -> Response:
    # Best-effort revoke: even a malformed/expired cookie clears client state.
    token = request.cookies.get(_COOKIE_NAME)
    if token:
        try:
            claims = auth.decode_token(token, expected_typ="refresh")
            sid = uuid.UUID(claims["sid"])
            current_tenant_id.set(uuid.UUID(claims["tenant_id"]))
            await _revoke_family(session, sid, auth.now_utc())
        except (AuthError, KeyError, ValueError, TypeError):
            pass
    _clear_refresh_cookie(response)
    response.status_code = 204
    return response


@router.get("/me", response_model=MeResponse)
async def me(
    current: CurrentUserDep,
    session: SessionDep,
) -> MeResponse:
    # get_current_user already set the tenant context, so this select is scoped.
    user = (
        await session.execute(select(User).where(User.id == current.user_id))
    ).scalar_one()
    return MeResponse(
        id=user.id,
        tenant_id=user.tenant_id,
        email=user.email,
        full_name=user.full_name,
        permissions=sorted(current.permissions),
    )
