"""MRP models (PLAN 8.3, parity PP MRP = PARTIAL): the run header, its regenerated planned orders,
and the rough-capacity-check load rows.

An MRP RUN (``MrpRun``) is the deterministic planning pass: it gathers DEMAND (open sales-order
demand + reorder-point shortfall) and SUPPLY (on-hand + open production orders + open POs) per item,
nets them, EXPLODES MAKE items' BOMs into dependent component demand level by level, and writes the
net plan as ``PlannedOrder`` rows (MAKE or BUY). The ``CapacityLoad`` rows are the rough capacity
check's per-work-centre output (planned + open load vs available hours over the horizon).

The run header mixes in ``DocumentMixin`` (it registers in core_documents + claims an MRP- number at
creation — a posted document, the depreciation-run precedent). Planned orders + capacity loads are
run-scoped OUTPUT, not documents: they carry no number and ride the run's audit story.

All item ids are OPAQUE inventory ids (D-029): no cross-module FK to inventory tables; the run reads
them through inventory/sales/procurement queries. ``mrp_run_id`` / ``work_center_id`` are
INTRA-module composite tenant FKs. Quantities use the D-015 QuantityType (scale-6, exact on both
engines);
``utilization_percent`` is a QuantityType ratio (the efficiency_percent/scrap_percent precedent — a
plain Numeric loses precision on SQLite, D-015).
"""

import uuid
from datetime import date, datetime
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
from app.core.money import QuantityType
from app.modules.manufacturing.constants import MrpRunStatus, PlannedOrderStatus


class MrpRun(UuidPKMixin, TenantMixin, AuditMixin, DocumentMixin, TimestampMixin, Base):
    """An MRP RUN HEADER (D-049): one tenant-wide deterministic planning pass.

    ``warehouse_id`` is nullable — v1 MRP is TENANT-WIDE (on-hand summed across all warehouses,
    demand netted tenant-wide); the column reserves a warehouse-scoped run for a later phase
    (parity: MRP areas / multi-plant are deferred). ``run_date`` is the planning date;
    ``horizon_days`` the netting/capacity window. ``planned_make_count`` / ``planned_buy_count``
    summarize the plan.
    Registers a document + claims the gapless MRP- number at creation (D-012). Audited (D-010): a
    run drives downstream production/procurement proposals.
    """

    __tablename__ = "mfg_mrp_runs"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("adm_tenants"),
        document_fk(),
        sa.UniqueConstraint(
            "tenant_id", "run_number", name="uq_mfg_mrp_runs_tenant_id_run_number"
        ),
        # The list filters on (tenant, status) and orders runs over time (PERFORMANCE §1).
        sa.Index("ix_mfg_mrp_runs_tenant_id_status", "tenant_id", "status"),
    )

    run_number: Mapped[str] = mapped_column(sa.String(60), nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(20), nullable=False, default=MrpRunStatus.RUNNING.value, server_default="RUNNING"
    )
    run_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    horizon_days: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="30")
    # OPAQUE inventory warehouse id (D-029): NULL = tenant-wide (the v1 default). No FK to inv_*.
    warehouse_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    demand_source: Mapped[str | None] = mapped_column(sa.String(1000), nullable=True)
    planned_make_count: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default="0"
    )
    planned_buy_count: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default="0"
    )
    notes: Mapped[str | None] = mapped_column(sa.String(1000), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )


class PlannedOrder(UuidPKMixin, TenantMixin, TimestampMixin, Base):
    """One PLANNED ORDER (D-049): a net replenishment proposal for ``quantity`` of ``item_id``.

    Produced by the run that owns it (``mrp_run_id``). ``order_type`` is MAKE (has an active BOM →
    convert to a production order) or BUY (no BOM → convert to a requisition). ``quantity`` is the
    NET requirement (max(0, demand − supply)). ``level`` is the BOM-explosion level (0 = a
    finished/demanded item, 1 = its components, …) — the run writes level-0 first, and reads/convert
    order by it. ``status`` runs the ``PlannedOrderStatus`` lifecycle; ``converted_document_id`` is
    the real document the conversion created (NULL until CONVERTED), linked via docflow.

    Regeneration (D-049): a re-run DELETES the prior PLANNED (un-firmed) rows for the tenant before
    writing fresh ones; FIRMED/CONVERTED/CANCELLED rows survive (FIRMED/CONVERTED net as supply).

    NOT AuditMixin: planning output rides the run header's audit story (the BomComponent /
    production-order-component precedent) — regenerated each run, no independent lifecycle worth a
    diff per row.
    """

    __tablename__ = "mfg_planned_orders"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("mfg_mrp_runs", "mrp_run_id"),
        sa.CheckConstraint("quantity > 0", name="ck_mfg_planned_orders_quantity_positive"),
        # The "this run's planned orders" read (the nested list, the capacity scan input).
        sa.Index("ix_mfg_planned_orders_tenant_id_mrp_run_id", "tenant_id", "mrp_run_id"),
        # The "an item's open planned orders by status" read (regeneration + the convert worklist).
        sa.Index(
            "ix_mfg_planned_orders_tenant_id_item_id_status",
            "tenant_id",
            "item_id",
            "status",
        ),
    )

    mrp_run_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    # OPAQUE inventory item id (D-029): the item to make/buy. No FK to inv_items.
    item_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    order_type: Mapped[str] = mapped_column(sa.String(10), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(QuantityType(), nullable=False)
    due_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    status: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        default=PlannedOrderStatus.PLANNED.value,
        server_default="PLANNED",
    )
    # The net-requirement explanation: "demand X − supply Y" (why this proposal exists).
    source_notes: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)
    level: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0, server_default="0")
    # The production order / requisition document created on conversion (NULL until CONVERTED).
    # OPAQUE core_documents id (D-029-style): set by the convert flow, linked via docflow.
    converted_document_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)


class CapacityLoad(UuidPKMixin, TenantMixin, TimestampMixin, Base):
    """One work centre's ROUGH CAPACITY LOAD for an MRP run (D-049): the planned + open operation
    minutes routed through ``work_center_id`` compared to its available minutes over the horizon.

    ``planned_load_minutes`` = Σ planned-order operation minutes + open-production-order operation
    minutes through this work centre. ``available_minutes`` = capacity_hours_per_day × efficiency ×
    horizon_days × 60. ``utilization_percent`` = load / available × 100 (0 when available is 0).
    ``is_overloaded`` flags load > available. Evaluation only — no leveling/finite scheduling
    (parity: capacity = PARTIAL).

    NOT AuditMixin: run-scoped output, rides the run header's audit story.
    """

    __tablename__ = "mfg_capacity_loads"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("mfg_mrp_runs", "mrp_run_id"),
        tenant_fk("mfg_work_centers", "work_center_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "mrp_run_id",
            "work_center_id",
            name="uq_mfg_capacity_loads_tenant_run_work_center",
        ),
        sa.Index("ix_mfg_capacity_loads_tenant_id_mrp_run_id", "tenant_id", "mrp_run_id"),
    )

    mrp_run_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    work_center_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    planned_load_minutes: Mapped[Decimal] = mapped_column(
        QuantityType(), nullable=False, default=Decimal(0), server_default="0"
    )
    available_minutes: Mapped[Decimal] = mapped_column(
        QuantityType(), nullable=False, default=Decimal(0), server_default="0"
    )
    utilization_percent: Mapped[Decimal] = mapped_column(
        QuantityType(), nullable=False, default=Decimal(0), server_default="0"
    )
    is_overloaded: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false()
    )
