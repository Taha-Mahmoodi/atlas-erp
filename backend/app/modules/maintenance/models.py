"""Maintenance models (PLAN 9.2, parity PM = equipment register + corrective/preventive orders):
the ``Equipment`` register, the ``MaintenanceOrder`` document, and the interval-based
``MaintenancePlan``.

THREE tables, one concern (PM v1) — well under the 400-line cap, so a single models.py (the quality
precedent; split into a models/ package only at the cap).

- ``Equipment`` and ``MaintenancePlan`` are MASTERS keyed by a USER-SUPPLIED ``code`` unique per
  tenant (no gapless number — the work-centre precedent). The plan ALSO mixes in DocumentMixin so it
  can be the docflow PREDECESSOR of the orders its run generates (the only master here that is a
  docflow source).
- ``MaintenanceOrder`` is a posted DOCUMENT (DocumentMixin + a gapless MNT- number at creation — the
  production-order precedent).

CROSS-MODULE IDS ARE OPAQUE (D-029/§5). ``cost_center_id`` is an OPAQUE finance cost-centre id
(nullable, validated via finance/queries when set — never a cross-module FK). ``assigned_to`` is a
core users id kept as a plain id (the journal posted_by precedent — no FK). The ``equipment_id`` /
``maintenance_plan_id`` links are INTRA-module composite tenant FKs.

Money columns use the D-015 MoneyType (scale-6, exact on both engines); a plain ``sa.Numeric`` would
round-trip through float on SQLite and lose precision (D-015), so it is never used for a stored
amount here.
"""

import uuid
from datetime import date
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.core.docflow import DocumentMixin, document_fk
from app.core.models import (
    AuditMixin,
    Base,
    TenantMixin,
    TimestampMixin,
    UuidPKMixin,
    tenant_fk,
    tenant_unique,
)
from app.core.money import MoneyType
from app.modules.maintenance.constants import (
    EquipmentStatus,
    MaintenanceOrderStatus,
    MaintenanceOrderType,
    MaintenancePlanStatus,
)


class Equipment(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, Base):
    """A piece of EQUIPMENT in the flat register (D-051): a machine, vehicle or asset maintenance is
    performed on.

    ``code`` is USER-SUPPLIED and unique per tenant (the master-data precedent — no auto-number).
    ``status`` runs the ``EquipmentStatus`` lifecycle. ``location`` is a FREE-TEXT label (e.g.
    "Plant A / Line 3") — NOT a functional-location hierarchy (that is out of v1, D-051).
    ``manufacturer`` / ``model`` / ``serial_number`` carry the nameplate data; ``commissioned_date``
    is when it entered service. ``cost_center_id`` is an OPAQUE finance cost-centre id (nullable,
    validated via finance/queries when set — for cost attribution). Audited (D-010): master data
    driving maintenance.
    """

    __tablename__ = "pm_equipment"
    __table_args__ = (
        sa.UniqueConstraint("tenant_id", "code", name="uq_pm_equipment_tenant_id_code"),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        # The (tenant, code) UNIQUE already serves the code lookup; this index serves the filtered
        # status list (PERFORMANCE §1).
        sa.Index("ix_pm_equipment_tenant_id_status", "tenant_id", "status"),
    )

    code: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(sa.String(1000), nullable=True)
    status: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        default=EquipmentStatus.ACTIVE.value,
        server_default="ACTIVE",
    )
    # Free-text location label (D-051): NOT a functional-location hierarchy (out of v1 scope).
    location: Mapped[str | None] = mapped_column(sa.String(200), nullable=True)
    manufacturer: Mapped[str | None] = mapped_column(sa.String(200), nullable=True)
    model: Mapped[str | None] = mapped_column(sa.String(200), nullable=True)
    serial_number: Mapped[str | None] = mapped_column(sa.String(200), nullable=True)
    commissioned_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    # Opaque finance cost-centre id (D-029): no cross-module FK; the service validates it via
    # finance/queries when set. For cost attribution of the equipment's maintenance.
    cost_center_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    notes: Mapped[str | None] = mapped_column(sa.String(1000), nullable=True)


class MaintenancePlan(UuidPKMixin, TenantMixin, AuditMixin, DocumentMixin, TimestampMixin, Base):
    """An interval-based PREVENTIVE maintenance PLAN (D-051): a recurring task on a piece of
    equipment.

    ``code`` is USER-SUPPLIED and unique per tenant. ``equipment_id`` is the INTRA-module composite
    tenant FK to the equipment the plan maintains. ``status`` runs the ``MaintenancePlanStatus``
    lifecycle. ``interval_value`` × ``interval_unit`` is the recurrence (e.g. every 3 MONTHS).
    ``task_description`` is the free-text work the generated orders carry. ``last_generated_date``
    is the ``scheduled_date`` of the LAST order this plan generated (NULL until the first
    generation); ``next_due_date`` is when the NEXT order is due — the generation run creates an
    order when ``next_due_date <= as_of`` and advances it (the OVERDUE-ADVANCE rule: a plan overdue
    by multiple intervals generates ONE order and advances to the next FUTURE due date, D-051).
    ``estimated_cost`` seeds the generated orders' estimate (nullable).

    Mixes in DocumentMixin so the plan is a docflow PREDECESSOR of the orders its run generates
    (plan→'generates'→order). Audited (D-010): master data driving order generation.
    """

    __tablename__ = "pm_maintenance_plans"
    __table_args__ = (
        sa.UniqueConstraint("tenant_id", "code", name="uq_pm_maintenance_plans_tenant_id_code"),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("pm_equipment", "equipment_id"),
        document_fk(),
        sa.CheckConstraint(
            "interval_value > 0", name="ck_pm_maintenance_plans_interval_positive"
        ),
        # The generation run scans ACTIVE plans due on/before a date (PERFORMANCE §1): the composite
        # serves the set-based due-plan scan.
        sa.Index(
            "ix_pm_maintenance_plans_tenant_id_status_next_due_date",
            "tenant_id",
            "status",
            "next_due_date",
        ),
        sa.Index(
            "ix_pm_maintenance_plans_tenant_id_equipment_id",
            "tenant_id",
            "equipment_id",
        ),
    )

    code: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    # INTRA-module composite tenant FK to pm_equipment.
    equipment_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        default=MaintenancePlanStatus.ACTIVE.value,
        server_default="ACTIVE",
    )
    interval_value: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    interval_unit: Mapped[str] = mapped_column(sa.String(10), nullable=False)
    task_description: Mapped[str] = mapped_column(sa.String(1000), nullable=False)
    last_generated_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    next_due_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    estimated_cost: Mapped[Decimal | None] = mapped_column(MoneyType(), nullable=True)


class MaintenanceOrder(UuidPKMixin, TenantMixin, AuditMixin, DocumentMixin, TimestampMixin, Base):
    """A MAINTENANCE ORDER header (D-051): the order to maintain a piece of equipment.

    ``order_number`` is the gapless MNT- number claimed at creation. ``order_type`` is CORRECTIVE
    (ad-hoc) or PREVENTIVE (generated by a plan). ``status`` runs the ``MaintenanceOrderStatus``
    lifecycle. ``equipment_id`` is the INTRA-module composite tenant FK to the equipment;
    ``maintenance_plan_id`` (nullable) is set when a plan's run generated this order (a CORRECTIVE
    order has none). ``description`` is the free-text work. ``scheduled_date`` is the planned date;
    ``completed_date`` is stamped at completion. ``estimated_cost`` / ``actual_cost`` are MoneyType
    (the actual recorded at completion — record-only, no GL posting, D-051). ``assigned_to`` is the
    technician's user id (a plain id, no FK — the journal posted_by precedent).

    Registers a document + claims the gapless MNT- number at creation (D-012). Audited (D-010): a
    maintenance order tracks cost.
    """

    __tablename__ = "pm_maintenance_orders"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("pm_equipment", "equipment_id"),
        # Explicit name: the D-022 convention (fk_<table>_<col0>_<referred>) would render
        # ``fk_pm_maintenance_orders_maintenance_plan_id_pm_maintenance_plans`` (65 chars > the PG
        # 63-char cap), so spell out a shortened name (matches migration 0036).
        sa.ForeignKeyConstraint(
            ["tenant_id", "maintenance_plan_id"],
            ["pm_maintenance_plans.tenant_id", "pm_maintenance_plans.id"],
            name="fk_pm_mnt_orders_maintenance_plan_id_pm_maintenance_plans",
        ),
        document_fk(),
        sa.UniqueConstraint(
            "tenant_id",
            "order_number",
            name="uq_pm_maintenance_orders_tenant_id_order_number",
        ),
        # The list filters on (tenant, equipment, status) and (tenant, status, scheduled_date)
        # (PERFORMANCE §1): the equipment's open orders + the scheduled-date worklist.
        sa.Index(
            "ix_pm_maintenance_orders_tenant_id_equipment_id_status",
            "tenant_id",
            "equipment_id",
            "status",
        ),
        sa.Index(
            "ix_pm_maintenance_orders_tenant_id_status_scheduled_date",
            "tenant_id",
            "status",
            "scheduled_date",
        ),
    )

    order_number: Mapped[str] = mapped_column(sa.String(60), nullable=False)
    order_type: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        default=MaintenanceOrderType.CORRECTIVE.value,
        server_default="CORRECTIVE",
    )
    status: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        default=MaintenanceOrderStatus.DRAFT.value,
        server_default="DRAFT",
    )
    # INTRA-module composite tenant FK to pm_equipment.
    equipment_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    # INTRA-module composite tenant FK to pm_maintenance_plans (nullable — set when generated by a
    # preventive plan's run; a corrective order has none).
    maintenance_plan_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    description: Mapped[str] = mapped_column(sa.String(1000), nullable=False)
    scheduled_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    completed_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    estimated_cost: Mapped[Decimal | None] = mapped_column(MoneyType(), nullable=True)
    # Recorded at completion (record-only — no GL posting in v1, D-051).
    actual_cost: Mapped[Decimal | None] = mapped_column(MoneyType(), nullable=True)
    # The assigned technician (a core users id, kept as a plain id like a journal's posted_by — no
    # FK).
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    notes: Mapped[str | None] = mapped_column(sa.String(1000), nullable=True)
