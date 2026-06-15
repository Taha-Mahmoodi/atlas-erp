"""Industry-owned model (PLAN 14.1 / D-060): the applied-template record per tenant.

``TenantIndustryConfig`` (``ind_tenant_industry_configs``) records WHICH industry template a tenant
has applied and WHEN — the onboarding record + the idempotency anchor. One row per tenant
(UNIQUE(tenant_id)): re-applying the SAME template is a safe no-op (the loader sees the matching
row and skips); applying a DIFFERENT template is rejected (a tenant's industry is chosen once at
onboarding — switching would orphan the first template's COA/fields, out of v1 scope, D-060).

This is the ONLY industry-owned table. The cross-module slices live in their owning modules'
tables (finance accounts, inventory UoMs, ...); the core/admin slices in core_custom_field_defs,
core_number_sequences and adm_tenant_settings. Audited (D-010): applying a template is a high-value
tenant-configuration action.
"""

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import (
    AuditMixin,
    Base,
    TenantMixin,
    TimestampMixin,
    UuidPKMixin,
    tenant_fk,
)


class TenantIndustryConfig(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, Base):
    """The industry template a tenant has applied (D-060). ``template_name`` is one of the shipped
    names; ``applied_at`` is the first-application timestamp. UNIQUE(tenant_id) — one industry per
    tenant, the idempotency + onboarding record."""

    __tablename__ = "ind_tenant_industry_configs"
    __table_args__ = (
        # One industry config per tenant. Explicit name: the D-022 convention keys on column 0
        # (tenant_id) only — here that IS the whole key, but the explicit name keeps it greppable
        # and consistent with the rest of the codebase.
        sa.UniqueConstraint("tenant_id", name="uq_ind_tenant_industry_configs_tenant_id"),
        tenant_fk("adm_tenants"),
    )

    template_name: Mapped[str] = mapped_column(sa.String(60), nullable=False)
    applied_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
