"""D-008 auth primitives: argon2 password hashing and HS256 JWT codec.

HTTP-free by design (STRUCTURE §2 litmus: no FastAPI, no ORM here) so it can be
reused by the security router, the admin provisioning service, seed, and tests.
The User/RefreshSession ORM models live in core/models.py; the router lives in
core/security_router.py.
"""

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import anyio.to_thread
import jwt
from argon2 import PasswordHasher, Type
from argon2.exceptions import VerifyMismatchError

from app.core.config import get_settings
from app.core.exceptions import AuthError

# RFC 9106 argon2id parameters fixed by D-008. Reused for verify so check_needs_rehash
# upgrades any hash produced with weaker parameters on the next successful login.
_hasher = PasswordHasher(type=Type.ID, time_cost=3, memory_cost=65536, parallelism=4)

_JWT_ALGORITHM = "HS256"
_ACCESS_TYP = "access"
_REFRESH_TYP = "refresh"


def now_utc() -> datetime:
    """Single timezone-aware UTC clock; tests inject a fixed value via the `now`
    arguments below instead of freezing the process clock (D-025 determinism)."""
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    """Coerce a stored timestamp to tz-aware UTC. aiosqlite round-trips
    DateTime(timezone=True) columns as NAIVE datetimes (a SQLite limitation), so
    session-loaded timestamps must be normalized before comparing against now_utc()."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def sha256_hex(value: str) -> str:
    """Hex sha256 — used to store jti hashes so a DB leak cannot mint sessions."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


# --- Password hashing (argon2id, thread-offloaded) ----------------------------


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Constant-time-ish verify; argon2-cffi raises on mismatch, we map to False."""
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


async def hash_password_async(password: str) -> str:
    """argon2 at 64 MiB takes tens of ms; offload off the event loop (D-008)."""
    return await anyio.to_thread.run_sync(hash_password, password)


async def verify_password_async(password_hash: str, password: str) -> bool:
    return await anyio.to_thread.run_sync(verify_password, password_hash, password)


# --- JWT codec (PyJWT, HS256) -------------------------------------------------


def _secret() -> str:
    return get_settings().jwt_secret


def encode_access(
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    sid: uuid.UUID,
    token_version: int,
    now: datetime | None = None,
) -> str:
    issued = now or now_utc()
    expires = issued + timedelta(seconds=get_settings().jwt_access_ttl_seconds)
    claims = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "sid": str(sid),
        "ver": token_version,
        "typ": _ACCESS_TYP,
        "jti": uuid.uuid4().hex,
        "iat": issued,
        "exp": expires,
    }
    return jwt.encode(claims, _secret(), algorithm=_JWT_ALGORITHM)


def encode_refresh(
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    sid: uuid.UUID,
    now: datetime | None = None,
) -> str:
    issued = now or now_utc()
    expires = issued + timedelta(seconds=get_settings().jwt_refresh_ttl_seconds)
    claims = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "sid": str(sid),
        "typ": _REFRESH_TYP,
        "jti": uuid.uuid4().hex,
        "iat": issued,
        "exp": expires,
    }
    return jwt.encode(claims, _secret(), algorithm=_JWT_ALGORITHM)


def decode_token(token: str, expected_typ: str) -> dict:
    """Validate signature, exp and typ. Any failure is an opaque 401 — we never
    leak which check failed (signature vs expiry vs wrong typ)."""
    try:
        claims = jwt.decode(token, _secret(), algorithms=[_JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise AuthError(message="Invalid token", code="auth.invalid_token") from exc
    if claims.get("typ") != expected_typ:
        raise AuthError(message="Invalid token", code="auth.invalid_token")
    return claims
