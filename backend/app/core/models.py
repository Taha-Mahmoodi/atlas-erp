"""Declarative Base with the D-022 naming convention and shared model mixins."""

import uuid
from datetime import datetime

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


class TimestampMixin:
    """Timezone-aware UTC stamps with server-side defaults on both engines."""

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
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
