"""Routing master (PLAN 8.1, parity PP routings / operation sequences = FULL).

A routing is the operation sequence to make ONE item: a header (``Routing``) plus its ordered
``RoutingOperation`` lines, each pinned to a work centre with a setup time (fixed per order) and a
run time (per produced unit). 8.3's rough capacity check multiplies these against an order quantity
to load the work centres; 8.2 schedules the order against them.

Identity is ``(item_id, version)`` (D-047) — the SAME shape as the BOM, deliberately, so a routing
is looked up exactly like a BOM and the two read identically. ``item_id`` is an OPAQUE inventory id
(validated via inventory/queries, D-029); ``work_center_id`` on each operation is an INTRA-module
composite tenant FK to ``mfg_work_centers``.

Times use the D-015 QuantityType (scale-6 minutes — fractional minutes are expressible and the math
is exact on both engines; a plain Numeric would lose precision on SQLite, D-015). The convention is
documented on the schemas + the module guide: minutes throughout.
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
from app.modules.manufacturing.constants import RoutingStatus


class Routing(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, Base):
    """A ROUTING HEADER — one VERSION of the operation sequence for an item (D-047).

    Identity ``(item_id, version)`` (the BOM shape): ``item_id`` is the OPAQUE inventory item the
    routing makes; ``version`` is a user-supplied string. ``status`` (RoutingStatus) gates usability
    and ``is_default`` marks the version 8.2/8.3 resolve — at most ONE ACTIVE+default per item,
    enforced in the service. Audited (D-010): the routing defines the work to make the item.
    """

    __tablename__ = "mfg_routings"
    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id", "item_id", "version", name="uq_mfg_routings_tenant_id_item_id_version"
        ),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        # The default-active resolver + the filtered list key on (tenant, item_id, status)
        # (PERFORMANCE §6) — get_active_routing_for_item and the item/status filter.
        sa.Index(
            "ix_mfg_routings_tenant_id_item_id_status", "tenant_id", "item_id", "status"
        ),
    )

    # OPAQUE inventory item id (D-029): the item this routing makes. No FK to inv_items.
    item_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    version: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(20), nullable=False, default=RoutingStatus.DRAFT.value, server_default="DRAFT"
    )
    is_default: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false()
    )
    notes: Mapped[str | None] = mapped_column(sa.String(1000), nullable=True)


class RoutingOperation(UuidPKMixin, TenantMixin, TimestampMixin, Base):
    """One operation of a routing (D-047): a step at a work centre with setup + run times.

    ``operation_number`` is the sequence (10/20/30…) — unique per routing and the order operations
    run in. ``work_center_id`` is an INTRA-module composite tenant FK to ``mfg_work_centers`` (the
    resource the step uses). ``setup_time_minutes`` is the fixed setup per production order;
    ``run_time_minutes_per_unit`` is per produced unit — 8.3 loads a work centre as
    ``setup + run × order_qty``. Both in MINUTES (QuantityType, scale-6 — fractional minutes are
    allowed, exact on both engines, D-015).

    NOT AuditMixin: operations ride the routing header's audit story (no independent lifecycle) —
    the BomComponent/UomConversion precedent.
    """

    __tablename__ = "mfg_routing_operations"
    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id",
            "routing_id",
            "operation_number",
            name="uq_mfg_routing_operations_tenant_id_routing_id_operation_number",
        ),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("mfg_routings", "routing_id"),
        tenant_fk("mfg_work_centers", "work_center_id"),
        sa.CheckConstraint(
            "setup_time_minutes >= 0",
            name="ck_mfg_routing_operations_setup_non_negative",
        ),
        sa.CheckConstraint(
            "run_time_minutes_per_unit >= 0",
            name="ck_mfg_routing_operations_run_non_negative",
        ),
        # The "this routing's operations" read path (the nested list + capacity load).
        sa.Index(
            "ix_mfg_routing_operations_tenant_id_routing_id", "tenant_id", "routing_id"
        ),
        # The "operations at this work centre" read path (8.3 work-centre load aggregation).
        sa.Index(
            "ix_mfg_routing_operations_tenant_id_work_center_id",
            "tenant_id",
            "work_center_id",
        ),
    )

    routing_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    operation_number: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    work_center_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    description: Mapped[str | None] = mapped_column(sa.String(1000), nullable=True)
    setup_time_minutes: Mapped[Decimal] = mapped_column(
        QuantityType(), nullable=False, default=Decimal(0), server_default="0"
    )
    run_time_minutes_per_unit: Mapped[Decimal] = mapped_column(
        QuantityType(), nullable=False, default=Decimal(0), server_default="0"
    )
    notes: Mapped[str | None] = mapped_column(sa.String(1000), nullable=True)
