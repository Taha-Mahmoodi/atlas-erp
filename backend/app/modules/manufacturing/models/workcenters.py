"""Work-centre master (PLAN 8.1, parity PP work centers = FULL).

A work centre is a production resource (a machine, a line, a labour pool) an operation runs on. It
carries the data 8.3's ROUGH capacity check needs — available hours/day and an efficiency factor —
and an OPTIONAL opaque finance cost-centre id for the later activity-rate costing (8.2+). The cost
centre is validated via ``finance/queries`` when set (D-029): no cross-module FK; finance owns cost
centres and is below manufacturing in the dependency order.

Times/quantities use the D-015 scaled types (QuantityType: scale-6, exact on both engines). A plain
``sa.Numeric`` would round-trip through float on SQLite and lose precision (D-015), so it is never
used for a stored decimal here.
"""

import uuid
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import (
    AuditMixin,
    Base,
    TenantMixin,
    TimestampMixin,
    UuidPKMixin,
    tenant_fk,
    tenant_unique,
)
from app.core.money import QuantityType


class WorkCenter(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, Base):
    """A production resource a routing operation runs on (parity: work center).

    ``code`` is USER-SUPPLIED and unique per tenant (the master-data precedent — no auto-number).
    ``capacity_hours_per_day`` is the available hours/day 8.3's rough capacity check compares the
    operation load against; ``efficiency_percent`` scales planned vs actual throughput (100 = no
    adjustment). ``cost_center_id`` is an OPAQUE finance cost-centre id (D-029): NULLABLE (costing
    is later), validated to exist in finance when set — no cross-module FK. Audited (D-010): master
    data driving capacity + costing.
    """

    __tablename__ = "mfg_work_centers"
    __table_args__ = (
        sa.UniqueConstraint("tenant_id", "code", name="uq_mfg_work_centers_tenant_id_code"),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        sa.CheckConstraint(
            "capacity_hours_per_day >= 0",
            name="ck_mfg_work_centers_capacity_non_negative",
        ),
        sa.CheckConstraint(
            "efficiency_percent > 0", name="ck_mfg_work_centers_efficiency_positive"
        ),
        # The (tenant, code) UNIQUE already serves the code lookup; this index serves the filtered
        # active-work-centre list (PERFORMANCE §1).
        sa.Index(
            "ix_mfg_work_centers_tenant_id_is_active", "tenant_id", "is_active"
        ),
    )

    code: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(sa.String(1000), nullable=True)
    # Opaque finance cost-centre id (D-029): no cross-module FK; the service validates it via
    # finance/queries when set. For the later activity-rate costing (8.2+).
    cost_center_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    capacity_hours_per_day: Mapped[Decimal] = mapped_column(
        QuantityType(), nullable=False, default=Decimal(0), server_default="0"
    )
    efficiency_percent: Mapped[Decimal] = mapped_column(
        QuantityType(), nullable=False, default=Decimal(100), server_default="100"
    )
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=True, server_default=sa.true()
    )
