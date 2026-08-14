"""Declarative Base with the D-022 naming convention and shared model mixins."""

import uuid
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

# Deterministic constraint names are mandatory: SQLite batch-mode migrations
# cannot drop unnamed constraints (D-022).
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# Portable JSON: JSONB on Postgres, plain JSON elsewhere. Type variance lives in
# the models so migrations import it from here and stay dialect-clean (D-022).
JSON_VARIANT = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


class Base(DeclarativeBase):
    metadata = sa.MetaData(naming_convention=NAMING_CONVENTION)


class UuidPKMixin:
    """uuid4 primary key, client-generated so ids are portable across both engines."""

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)


class TenantMixin:
    """Row-level tenancy marker (D-007). Filtering and stamping are enforced by the
    core/tenancy.py session listeners; query authors never touch tenant_id."""

    @declared_attr
    def tenant_id(cls) -> Mapped[uuid.UUID]:
        return mapped_column(sa.Uuid, nullable=False, index=True)


class AuditMixin:
    """Marker mixin (D-010): tags a model for split-phase audit capture. It adds NO
    columns — the audit listeners in core/audit.py test ``isinstance(obj, AuditMixin)``
    to decide which INSERT/UPDATE/DELETE flushes land in core_audit_log. Per-column
    opt-outs are declared on the model via ``__audit_exclude__`` (a frozenset of
    attribute names); ``password_hash`` is excluded there on User."""

    # Attribute names never written to the diff (D-010: password_hash always). Models
    # override by setting their own frozenset; the listeners read it via getattr.
    __audit_exclude__: frozenset[str] = frozenset()


def utcnow() -> datetime:
    """Canonical timestamp source for every SQLAlchemy write (#34)."""
    return datetime.now(UTC)


class TimestampMixin:
    """Timezone-aware UTC stamps, ALWAYS Python-written (#34).

    The Python ``default``/``onupdate`` fire for ORM and Core inserts alike, so every
    stored value uses SQLAlchemy's canonical SQLite string format (six-digit
    microseconds). The DDL ``server_default`` remains only as a fallback for raw SQL
    outside SQLAlchemy and must never be relied on: SQLite's CURRENT_TIMESTAMP writes
    second-precision strings whose lexicographic comparison against bound datetimes
    breaks keyset-pagination equality — the #34 infinite-page-loop bug."""

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=sa.func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=sa.func.now(),
        onupdate=utcnow,
    )


def tenant_fk(target_table: str, local_column: str | None = None) -> sa.ForeignKeyConstraint:
    """Tenant-safe foreign key for __table_args__ (D-007 item 4).

    - tenant_fk("adm_tenants") anchors tenant_id itself to the tenants root;
      every tenant-scoped table carries this backstop.
    - tenant_fk("inv_items", "item_id") builds the composite (tenant_id, item_id)
      -> (inv_items.tenant_id, inv_items.id) FK, so a child row can never point
      at a parent row of another tenant; the parent declares tenant_unique().
    """
    if local_column is None:
        return sa.ForeignKeyConstraint(["tenant_id"], [f"{target_table}.id"])
    return sa.ForeignKeyConstraint(
        ["tenant_id", local_column],
        [f"{target_table}.tenant_id", f"{target_table}.id"],
    )


def tenant_unique() -> sa.UniqueConstraint:
    """UNIQUE (tenant_id, id) — required on every tenant-scoped table that is
    referenced through tenant_fk() composite FKs (D-007 item 4). Any OTHER unique
    constraint starting with tenant_id needs an explicit name at the call site:
    the D-022 naming convention keys on column 0 only and would collide."""
    return sa.UniqueConstraint("tenant_id", "id")


class User(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, Base):
    """Auth principal (D-008). Cross-cutting platform entity, so it lives in core
    (STRUCTURE §2 litmus: users are not a business concept). Provisioning is owned
    by modules/admin (PLAN 14); login lookup runs under system_context (D-007 site 1).
    HR compensation/PII masking is HR's concern later — these rows are credentials only.
    Audited (D-010): security-relevant; password_hash is excluded from every diff."""

    __tablename__ = "core_users"
    # D-010: never write the credential into the audit diff (insert, update, or delete).
    __audit_exclude__ = frozenset({"password_hash"})
    __table_args__ = (
        # Explicit uq name: the D-022 convention keys on column 0 (tenant_id) only and
        # would collide with tenant_unique() below.
        sa.UniqueConstraint("tenant_id", "email", name="uq_core_users_tenant_id_email"),
        tenant_unique(),
        tenant_fk("adm_tenants"),
    )

    email: Mapped[str] = mapped_column(sa.String(320), nullable=False)
    password_hash: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(sa.String(200), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=True, server_default=sa.true()
    )
    # "Revoke everything" valve: bump this and every outstanding access token whose
    # `ver` claim no longer matches is rejected on its next request (D-008).
    token_version: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default=sa.text("0")
    )


class RefreshSession(UuidPKMixin, TenantMixin, TimestampMixin, Base):
    """Refresh-token server state (D-008). The PK id is the `sid` claim. Rotation is a
    compare-and-swap on current_jti_hash; prev_jti_hash + rotated_at implement the
    10-second grace window for benign multi-tab refresh races."""

    __tablename__ = "core_refresh_sessions"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("core_users", "user_id"),
        # Hot read path: refresh loads by sid (PK already), logout/revoke and the
        # "active sessions" admin view filter by user within a tenant.
        sa.Index("ix_core_refresh_sessions_tenant_id_user_id", "tenant_id", "user_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    current_jti_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    prev_jti_hash: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    rotated_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    issued_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    last_used_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    ip: Mapped[str | None] = mapped_column(sa.String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(sa.String(400), nullable=True)


class ApiKey(UuidPKMixin, TenantMixin, TimestampMixin, Base):
    """Machine credential for a first-party API client (the property's own website).

    Structurally mirrors RefreshSession: a hashed secret with revocation and expiry. Two
    deliberate differences. The secret is sha256, not argon2 — it is 256 bits of CSPRNG
    output, not a guessable password, and argon2id at the D-008 parameters costs "tens of
    ms" (see core/auth.py), which would blow the PERFORMANCE §5 budget on every request.
    And there is no last_used_at: writing one per request would add a write to every
    authenticated call for a statistic nobody reads.

    `scopes` is NULL for "inherit the user's permissions unnarrowed"; a non-null list may
    only ever NARROW them (see core/deps.py). Keys are bound to a real core_users row so
    the D-010 audit actor resolves — a synthetic principal id would insert cleanly and
    leave an unresolvable actor across the submitted_by/approver_id sites that deliberately
    do not FK to core_users."""

    __tablename__ = "core_api_keys"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("core_users", "user_id"),
        # The auth hot path looks a key up by its hashed secret; uniqueness is also the
        # collision guard on mint.
        sa.UniqueConstraint("secret_sha256", name="uq_core_api_keys_secret_sha256"),
        # "Keys for this user" — the admin list view and revoke-all path.
        sa.Index("ix_core_api_keys_tenant_id_user_id", "tenant_id", "user_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    # The non-secret half of the key string, kept for display ("atk_acme"). Never any part
    # of the secret. Sized for the scheme plus a full-length tenant slug: onboarding caps
    # slugs at 63 chars (modules/industry/schemas.py), and VARCHAR overflow is a
    # Postgres-only error SQLite would never show (D-003).
    prefix: Mapped[str] = mapped_column(sa.String(80), nullable=False)
    secret_sha256: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    scopes: Mapped[list[str] | None] = mapped_column(JSON_VARIANT, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)


class Permission(UuidPKMixin, Base):
    """Code-defined permission catalog (D-009). Deliberately NOT TenantMixin: a
    permission describes what the code enforces and is identical for every tenant, so
    one global row per key avoids N per-tenant copies and orphan keys nothing checks.
    Rows are upserted by core/rbac.sync_permission_catalog from the code registry —
    tenants can only be granted keys that already exist here."""

    __tablename__ = "core_permissions"

    key: Mapped[str] = mapped_column(sa.String(150), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(sa.String(300), nullable=True)


class Role(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, Base):
    """Tenant-scoped role (D-009): each tenant defines its own roles. is_system marks
    roles seeded from industry templates at provisioning (PLAN 14). Audited (D-010):
    role definitions are security-relevant."""

    __tablename__ = "core_roles"
    __table_args__ = (
        sa.UniqueConstraint("tenant_id", "name", name="uq_core_roles_tenant_id_name"),
        tenant_unique(),
        tenant_fk("adm_tenants"),
    )

    name: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(sa.String(300), nullable=True)
    is_system: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false()
    )


class RolePermission(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, Base):
    """Role-to-permission grant (D-009). TenantMixin so the role side is tenant-filtered
    and stamped; permission_id points at the GLOBAL catalog (no tenant composite). The
    composite tenant_fk on role_id keeps a grant from referencing another tenant's role.
    Audited (D-010): grants change effective authority."""

    __tablename__ = "core_role_permissions"
    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id",
            "role_id",
            "permission_id",
            name="uq_core_role_permissions_tenant_id_role_id_permission_id",
        ),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("core_roles", "role_id"),
        sa.ForeignKeyConstraint(["permission_id"], ["core_permissions.id"]),
    )

    role_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    permission_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)


class UserRole(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, Base):
    """User-to-role assignment (D-009). Both sides are tenant-scoped, so both carry the
    composite tenant_fk backstop: a user can never be assigned a role from another
    tenant. Audited (D-010): assignments change effective authority."""

    __tablename__ = "core_user_roles"
    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id", "user_id", "role_id", name="uq_core_user_roles_tenant_id_user_id_role_id"
        ),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("core_users", "user_id"),
        tenant_fk("core_roles", "role_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    role_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)


class AuditLog(UuidPKMixin, TenantMixin, TimestampMixin, Base):
    """Append-only audit trail (D-010). Deliberately NOT AuditMixin — auditing the audit
    log would recurse on every flush. tenant_id is the CHANGED row's tenant (every audited
    model is TenantMixin, so it always exists); created_at is when the row was written.

    Deviation from D-010's literal schema (bigint id, NULLABLE tenant_id, `source`
    column): this build follows the binding PLAN 3.5 spec — UuidPKMixin + TenantMixin so
    reads are tenant-isolated through the ordinary D-007 filter, action stored UPPER_SNAKE.
    Reads run through the ORM, so the D-007 filter gives tenant isolation for free; the
    Core writer in core/audit.py sets tenant_id explicitly (it bypasses ORM stamping).

    Append-only is enforced at the DB by per-dialect triggers (migration 0005): any UPDATE
    or DELETE raises 'ATLAS_AUDIT_APPEND_ONLY', translated to an envelope by core/exceptions.
    Excluded from capture: AuditLog itself (recursion) and RefreshSession (high-churn,
    low-value token state — documented exclusion, never tagged AuditMixin)."""

    __tablename__ = "core_audit_log"
    __table_args__ = (
        # Both composite indexes lead with tenant_id, so the D-022 convention (keyed on
        # column 0) would collide — name them explicitly. Read paths: "history for one
        # entity" and "tenant activity over time".
        sa.Index(
            "ix_core_audit_log_tenant_id_entity_table_entity_id",
            "tenant_id",
            "entity_table",
            "entity_id",
        ),
        sa.Index("ix_core_audit_log_tenant_id_created_at", "tenant_id", "created_at"),
    )

    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    entity_table: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    # Stringified PK (UUIDs today, composite/int keys later) — kept text for portability.
    entity_id: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    action: Mapped[str] = mapped_column(sa.String(10), nullable=False)
    diff: Mapped[Any] = mapped_column(JSON_VARIANT, nullable=False)
    request_id: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    request_ip: Mapped[str | None] = mapped_column(sa.String(45), nullable=True)


# The D-012 numbering/docflow ORM models live in their concern files (core/numbering.py,
# core/docflow.py) to keep this file under the ~350-line soft cap, but they must register on
# Base.metadata so every import path that loads core models (alembic env.py, the engine
# bootstrap via core/db.py, the tenancy mapper-enumeration suite) sees them. Importing at the
# END — after Base and the mixins are defined — breaks the cycle (those modules import from
# here), the same trailing-import pattern core/schemas.py uses for Masked.
from app.core import custom_fields as _custom_fields  # noqa: E402,F401
from app.core import docflow as _docflow  # noqa: E402,F401
from app.core import numbering as _numbering  # noqa: E402,F401

# NOTE: the D-013 core_idempotency_keys model (core/idempotency.py) and the 4P.5 core_jobs model
# (core/jobs.py) are NOT registered here. Both import modules that import core/models mid-cycle
# (idempotency imports core/db; jobs imports core/audit for the actor ContextVar), so a trailing
# import here would dead-lock the import cycle. They are registered from the bottom of
# core/db.py instead, after db/audit/tenancy have finished loading.
