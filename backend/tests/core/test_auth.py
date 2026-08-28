"""D-008 auth: primitives (argon2 + JWT), login/refresh/logout/me HTTP flow,
get_current_user tenant context + token_version revocation, and tenant isolation."""

import uuid
from datetime import timedelta

import jwt
import pytest
from argon2 import PasswordHasher, Type
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import auth
from app.core.config import get_settings
from app.core.exceptions import AuthError
from app.core.models import RefreshSession, User
from app.core.tenancy import system_context
from tests.conftest import ProvisionedUser

# --- Password hashing primitives ---------------------------------------------


def test_password_hash_verify_round_trip() -> None:
    hashed = auth.hash_password("s3cret-pw")
    assert auth.verify_password(hashed, "s3cret-pw") is True


def test_password_verify_rejects_wrong_password() -> None:
    hashed = auth.hash_password("s3cret-pw")
    assert auth.verify_password(hashed, "wrong-pw") is False


def test_needs_rehash_true_for_weaker_parameters() -> None:
    # A hash made with weaker params than the D-008 fixed parameters must rehash.
    weak = PasswordHasher(type=Type.ID, time_cost=1, memory_cost=8, parallelism=1)
    weak_hash = weak.hash("s3cret-pw")
    assert auth.needs_rehash(weak_hash) is True
    assert auth.needs_rehash(auth.hash_password("s3cret-pw")) is False


async def test_async_password_wrappers_round_trip() -> None:
    hashed = await auth.hash_password_async("s3cret-pw")
    assert await auth.verify_password_async(hashed, "s3cret-pw") is True
    assert await auth.verify_password_async(hashed, "nope") is False


# --- JWT codec ----------------------------------------------------------------


def test_jwt_access_encode_decode_round_trip() -> None:
    uid, tid, sid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    token = auth.encode_access(uid, tid, sid, token_version=3)
    claims = auth.decode_token(token, expected_typ="access")
    assert claims["sub"] == str(uid)
    assert claims["tenant_id"] == str(tid)
    assert claims["sid"] == str(sid)
    assert claims["ver"] == 3
    assert claims["typ"] == "access"


def test_jwt_expired_token_rejected_via_injected_now() -> None:
    past = auth.now_utc() - timedelta(seconds=get_settings().jwt_access_ttl_seconds + 60)
    token = auth.encode_access(uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), 0, now=past)
    with pytest.raises(AuthError) as excinfo:
        auth.decode_token(token, expected_typ="access")
    assert excinfo.value.code == "auth.invalid_token"


def test_jwt_wrong_typ_rejected() -> None:
    token = auth.encode_refresh(uuid.uuid4(), uuid.uuid4(), uuid.uuid4())
    with pytest.raises(AuthError) as excinfo:
        auth.decode_token(token, expected_typ="access")
    assert excinfo.value.code == "auth.invalid_token"


def test_jwt_tampered_signature_rejected() -> None:
    forged = jwt.encode({"typ": "access", "sub": "x"}, "a-different-secret", algorithm="HS256")
    with pytest.raises(AuthError) as excinfo:
        auth.decode_token(forged, expected_typ="access")
    assert excinfo.value.code == "auth.invalid_token"


def test_sha256_hex_is_stable() -> None:
    assert auth.sha256_hex("abc") == auth.sha256_hex("abc")
    assert auth.sha256_hex("abc") != auth.sha256_hex("abd")


# --- Login --------------------------------------------------------------------


async def test_login_happy_path_returns_token_and_sets_cookie(
    client: AsyncClient, provisioned_user: ProvisionedUser
) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": provisioned_user.tenant_slug,
            "email": provisioned_user.email,
            "password": provisioned_user.password,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert auth.decode_token(body["access_token"], expected_typ="access")["sub"] == str(
        provisioned_user.user_id
    )
    set_cookie = response.headers["set-cookie"].lower()
    assert "atlas_refresh=" in set_cookie
    assert "httponly" in set_cookie
    assert "secure" in set_cookie
    assert "path=/api/v1/auth" in set_cookie
    assert "samesite=strict" in set_cookie


async def test_login_bad_password_returns_401_envelope(
    client: AsyncClient, provisioned_user: ProvisionedUser
) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": provisioned_user.tenant_slug,
            "email": provisioned_user.email,
            "password": "wrong-password",
        },
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "auth.invalid_credentials"


async def test_login_no_user_path_still_runs_password_verify(
    client: AsyncClient, provisioned_user: ProvisionedUser, monkeypatch
) -> None:
    """Regression for #80: the unknown-email and unknown-tenant paths must burn an argon2
    verify (against the dummy hash) so login latency doesn't enumerate valid accounts."""
    calls: list[str] = []
    real_verify = auth.verify_password_async

    async def counting_verify(password_hash: str, password: str) -> bool:
        calls.append(password_hash)
        return await real_verify(password_hash, password)

    from app.core import security_router

    monkeypatch.setattr(security_router.auth, "verify_password_async", counting_verify)
    for body in (
        {  # valid tenant, unknown email
            "tenant_slug": provisioned_user.tenant_slug,
            "email": "no-such-user@acme.test",
            "password": "whatever",
        },
        {  # unknown tenant
            "tenant_slug": "no-such-tenant",
            "email": provisioned_user.email,
            "password": "whatever",
        },
    ):
        calls.clear()
        response = await client.post("/api/v1/auth/login", json=body)
        assert response.status_code == 401
        assert calls == [security_router._DUMMY_PASSWORD_HASH]


async def test_login_unknown_tenant_slug_returns_401(
    client: AsyncClient, provisioned_user: ProvisionedUser
) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": "no-such-tenant",
            "email": provisioned_user.email,
            "password": provisioned_user.password,
        },
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "auth.invalid_credentials"


# --- get_current_user / me ----------------------------------------------------


async def test_me_returns_current_user(
    authed_client: AsyncClient, provisioned_user: ProvisionedUser
) -> None:
    response = await authed_client.get("/api/v1/auth/me")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(provisioned_user.user_id)
    assert body["tenant_id"] == str(provisioned_user.tenant_id)
    assert body["email"] == provisioned_user.email
    # The property's display name, the printed check's letterhead (#211) — the SPA has no
    # other read of it.
    assert body["tenant_name"] == provisioned_user.tenant_slug.title()
    # RBAC seam (PLAN 3.4): no permissions resolved yet, real empty list.
    assert body["permissions"] == []


async def test_me_without_token_returns_401(client: AsyncClient) -> None:
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "auth.invalid_token"


async def test_stale_token_version_is_rejected(
    client: AsyncClient,
    db_session: AsyncSession,
    provisioned_user: ProvisionedUser,
) -> None:
    access_token = (
        await client.post(
            "/api/v1/auth/login",
            json={
                "tenant_slug": provisioned_user.tenant_slug,
                "email": provisioned_user.email,
                "password": provisioned_user.password,
            },
        )
    ).json()["access_token"]
    # Global revoke: bump token_version; the already-issued access token's ver is stale.
    # Mutate the LOADED user (User is now AuditMixin-audited per D-010, so the audit
    # bulk-write guard forbids ORM update()/delete() on it — the same loaded-object path
    # the admin "revoke now" endpoint will use).
    with system_context():
        user = (
            await db_session.execute(select(User).where(User.id == provisioned_user.user_id))
        ).scalar_one()
        user.token_version += 1
        await db_session.commit()
    response = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "auth.invalid_token"


async def test_token_with_foreign_tenant_id_cannot_load_user(
    client: AsyncClient,
    provisioned_user: ProvisionedUser,
) -> None:
    # Tenant isolation: forge an access token with the right user id but a DIFFERENT
    # tenant_id. get_current_user sets the tenant context from the token, so the
    # user lookup runs under the wrong tenant and the row is filtered away -> 401.
    forged = auth.encode_access(
        provisioned_user.user_id,
        uuid.uuid4(),  # foreign tenant
        uuid.uuid4(),
        token_version=0,
    )
    response = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {forged}"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "auth.invalid_token"


# --- Refresh rotation ---------------------------------------------------------


async def _login_for_cookie(client: AsyncClient, principal: ProvisionedUser) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": principal.tenant_slug,
            "email": principal.email,
            "password": principal.password,
        },
    )
    assert response.status_code == 200
    return response.cookies["atlas_refresh"]


async def test_refresh_rotates_to_new_token(
    client: AsyncClient, provisioned_user: ProvisionedUser
) -> None:
    original = await _login_for_cookie(client, provisioned_user)
    response = await client.post("/api/v1/auth/refresh")
    assert response.status_code == 200
    rotated = response.cookies["atlas_refresh"]
    assert rotated != original
    # Distinct jti proves a genuine rotation, not a re-emit of the same token.
    old_jti = auth.decode_token(original, expected_typ="refresh")["jti"]
    new_jti = auth.decode_token(rotated, expected_typ="refresh")["jti"]
    assert old_jti != new_jti


async def test_reusing_old_refresh_after_rotation_revokes_session(
    client: AsyncClient,
    db_session: AsyncSession,
    provisioned_user: ProvisionedUser,
) -> None:
    original = await _login_for_cookie(client, provisioned_user)
    sid = uuid.UUID(auth.decode_token(original, expected_typ="refresh")["sid"])
    # Rotate once; the original token is now the prev in the chain.
    await client.post("/api/v1/auth/refresh")
    # Replay the ORIGINAL (prev) token but force it OUTSIDE the grace window by aging
    # rotated_at into the past — this is the theft signature.
    with system_context():
        await db_session.execute(
            update(RefreshSession)
            .where(RefreshSession.id == sid)
            .values(rotated_at=auth.now_utc() - timedelta(seconds=60))
        )
        await db_session.commit()
    client.cookies.set("atlas_refresh", original, path="/api/v1/auth")
    response = await client.post("/api/v1/auth/refresh")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "auth.invalid_token"
    # Whole family revoked.
    with system_context():
        sess = (
            await db_session.execute(select(RefreshSession).where(RefreshSession.id == sid))
        ).scalar_one()
    assert sess.revoked_at is not None


async def test_reusing_prev_refresh_within_grace_succeeds(
    client: AsyncClient,
    db_session: AsyncSession,
    provisioned_user: ProvisionedUser,
) -> None:
    original = await _login_for_cookie(client, provisioned_user)
    sid = uuid.UUID(auth.decode_token(original, expected_typ="refresh")["sid"])
    await client.post("/api/v1/auth/refresh")
    # Keep rotated_at recent so the prev token is still inside the 10s grace window
    # (benign multi-tab race), then replay the original.
    with system_context():
        await db_session.execute(
            update(RefreshSession)
            .where(RefreshSession.id == sid)
            .values(rotated_at=auth.now_utc())
        )
        await db_session.commit()
    client.cookies.set("atlas_refresh", original, path="/api/v1/auth")
    response = await client.post("/api/v1/auth/refresh")
    assert response.status_code == 200
    with system_context():
        sess = (
            await db_session.execute(select(RefreshSession).where(RefreshSession.id == sid))
        ).scalar_one()
    assert sess.revoked_at is None


# --- Logout -------------------------------------------------------------------


async def test_logout_revokes_session_so_refresh_fails(
    client: AsyncClient, provisioned_user: ProvisionedUser
) -> None:
    await _login_for_cookie(client, provisioned_user)
    logout_response = await client.post("/api/v1/auth/logout")
    assert logout_response.status_code == 204
    refresh_response = await client.post("/api/v1/auth/refresh")
    assert refresh_response.status_code == 401
    assert refresh_response.json()["error"]["code"] == "auth.invalid_token"
