"""Admin API schemas (PLAN 14.3): the wire shapes for user/role management, the audit
viewer, and the number-sequence viewer. All read schemas load from ORM attributes
(ApiModel from_attributes); password_hash is deliberately absent from UserRead."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import Field

from app.core.schemas import ApiModel


class UserRead(ApiModel):
    """A tenant user as the admin API exposes it — credentials excluded (no password_hash)."""

    id: uuid.UUID
    email: str
    full_name: str | None
    is_active: bool
    created_at: datetime


class UserCreate(ApiModel):
    """Create a user in the caller's tenant. email/password validated at the trust boundary;
    the service hashes the plaintext with argon2id (D-008 single hashing path)."""

    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=200)
    full_name: str | None = Field(default=None, max_length=200)


class RoleRead(ApiModel):
    """A role summary (list rows) — no permissions attached; the detail endpoint carries them."""

    id: uuid.UUID
    name: str
    description: str | None
    is_system: bool
    created_at: datetime


class RoleWithPermissions(RoleRead):
    """A role plus its granted permission keys (the detail endpoint), attached N+1-free."""

    permissions: list[str]


class RoleCreate(ApiModel):
    """Create a role and grant it the named permission keys. Keys are validated against the
    global catalog by the service — an unknown key is a 422 rbac.unknown_permission."""

    name: str = Field(min_length=1, max_length=100)
    permissions: list[str] = Field(default_factory=list)


class RoleAssign(ApiModel):
    """Assign a role to a user (both must belong to the caller's tenant)."""

    user_id: uuid.UUID
    role_id: uuid.UUID


class PermissionRead(ApiModel):
    """One row of the global permission catalog — the grantable universe a role editor picks."""

    key: str
    description: str | None


class AuditLogRead(ApiModel):
    """One audit-log row as the viewer exposes it (D-010). ``diff`` is the field-level
    {old,new} (or full-row) JSON the capture wrote; no extra masking beyond what capture
    already excluded (e.g. password_hash is never in a diff)."""

    id: uuid.UUID
    actor_user_id: uuid.UUID | None
    entity_table: str
    entity_id: str
    action: str
    diff: dict[str, Any] | None
    request_id: str | None
    request_ip: str | None
    created_at: datetime


class ApiKeyCreate(ApiModel):
    """Issue a machine credential bound to one of the tenant's users (spec Q1). ``scopes``
    absent/null means "inherit that user's permissions unnarrowed"; a list may only ever
    narrow them, and every key in it is validated against the RBAC catalog (D-009)."""

    name: str = Field(min_length=1, max_length=200)
    user_id: uuid.UUID
    scopes: list[str] | None = None
    expires_at: datetime | None = None


class ApiKeyRead(ApiModel):
    """A machine credential as the admin API exposes it: the secret and its digest are
    deliberately absent, so ``prefix`` (scheme + tenant ref) is the only displayable half."""

    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    prefix: str
    scopes: list[str] | None
    expires_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class ApiKeyCreated(ApiKeyRead):
    """The 201 body — the ONE time the full key is returned. Only its sha256 is stored, so
    a lost key is re-issued, never recovered."""

    key: str


class NumberSequenceCounterRead(ApiModel):
    """One year's running counter (D-012). ``next_value`` is the next number a claim in that year
    would hand out; ``year`` is null for a sequence that does not year-reset."""

    year: int | None
    next_value: int


class NumberSequenceRead(ApiModel):
    """One per-tenant number sequence as the read-only viewer exposes it (D-012).

    ``counters`` is one row per year the tenant has actually claimed in, newest first — a
    sequence claimed in no year yet has none. Showing the whole set rather than a single
    "current" position is what makes a mis-dated document visible: a stray 2022 counter next to
    the live one is the tell that somebody backdated a check (issue #209)."""

    id: uuid.UUID
    name: str
    prefix: str
    padding: int
    year_reset: bool
    counters: list[NumberSequenceCounterRead] = []
