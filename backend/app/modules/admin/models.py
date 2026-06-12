"""Admin models: the tenancy root and per-tenant settings."""

from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import (
    JSON_VARIANT,
    AuditMixin,
    Base,
    TenantMixin,
    TimestampMixin,
    UuidPKMixin,
    tenant_fk,
)


class Tenant(UuidPKMixin, AuditMixin, TimestampMixin, Base):
    """Tenancy root — deliberately NOT TenantMixin: tenants have no parent tenant,
    and the D-007 filter must never apply to resolving them. Audited (D-010): tenant
    provisioning/activation are high-value admin actions. NOTE: Tenant has no tenant_id,
    so its audit rows are stamped with the tenant's OWN id (it is its own tenant scope) —
    see core/audit._make_row, which falls back to the PK for non-TenantMixin audited rows."""

    __tablename__ = "adm_tenants"

    slug: Mapped[str] = mapped_column(sa.String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=True, server_default=sa.true()
    )


class TenantSetting(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, Base):
    """Per-tenant configuration/onboarding flags (consumed by PLAN 14.2 provisioning);
    also the first real tenant-scoped table the D-007 guard tests run against. Audited
    (D-010): settings changes are admin actions."""

    __tablename__ = "adm_tenant_settings"
    # Explicit uq name: the D-022 convention keys on column 0 only and would
    # collide with any future UNIQUE starting with tenant_id on this table.
    __table_args__ = (
        sa.UniqueConstraint("tenant_id", "key", name="uq_adm_tenant_settings_tenant_id_key"),
        tenant_fk("adm_tenants"),
    )

    key: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    value: Mapped[Any] = mapped_column(JSON_VARIANT, nullable=False)
