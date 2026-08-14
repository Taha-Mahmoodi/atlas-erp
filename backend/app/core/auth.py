"""D-008 auth primitives: argon2 password hashing and HS256 JWT codec.

HTTP-free by design (STRUCTURE §2 litmus: no FastAPI, no ORM here) so it can be
reused by the security router, the admin provisioning service, seed, and tests.
The User/RefreshSession ORM models live in core/models.py; the router lives in
core/security_router.py.
"""

import hashlib
import secrets
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


# --- Machine credential key strings (spec Q1) ---------------------------------

API_KEY_PREFIX = "atk"


def mint_api_key(tenant_id: uuid.UUID) -> tuple[str, str]:
    """Mint a key for a tenant. Returns (full_key, secret_sha256).

    The full key is shown to the operator exactly once and never stored; only the digest
    is persisted, so a database leak cannot mint or replay a credential — the same
    argument as the refresh-jti hashing above. sha256 and not argon2: the argument that
    forces argon2 for passwords does not apply to 256 bits of CSPRNG output, and argon2
    at D-008 parameters costs tens of ms per request (see hash_password_async below).

    The tenant ref rides in the key so the D-007 ContextVar can be set BEFORE any lookup,
    which is what keeps the sanctioned system_context() bypass list at exactly four
    (tenancy.py). A forged ref simply finds no row.

    The ref is the tenant UUID, not its slug: the slug would have to be RESOLVED to an id
    on every request, and that query pushes an API-key list request to 4 statements —
    over PERFORMANCE §2's ≤3 on every endpoint that also computes a collection ETag
    (core/conditional.py), which is most reference lists in the codebase. The UUID is
    already the id, so the ContextVar is set with zero queries and the key path costs the
    same one statement the JWT path costs.
    """
    secret = secrets.token_urlsafe(32)
    return f"{API_KEY_PREFIX}_{tenant_id.hex}_{secret}", sha256_hex(secret)


def parse_api_key(raw: str) -> tuple[uuid.UUID, str] | None:
    """Split a presented key into (tenant_id, secret_sha256), or None if malformed.

    maxsplit=2 so the urlsafe secret's own underscores stay in the secret half; the ref is
    a UUID hex, which carries no underscore. Never raises — deps.py turns None into a 401
    and an exception here would surface as a 500.
    """
    parts = raw.split("_", 2)
    if len(parts) != 3:
        return None
    scheme, tenant_ref, secret = parts
    if scheme != API_KEY_PREFIX or not secret:
        return None
    try:
        tenant_id = uuid.UUID(hex=tenant_ref)
    except ValueError:
        return None
    return tenant_id, sha256_hex(secret)


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
