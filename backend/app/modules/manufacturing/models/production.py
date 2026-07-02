"""Production-order models (PLAN 8.2, parity PP production orders = FULL): the header, the exploded
component reservations, and the routing-snapshot operations.

A production order turns COMPONENTS into a FINISHED parent item: a header (``ProductionOrder``) plus
its ``ProductionOrderComponent`` rows (the BOM exploded at create time — required vs issued
quantity) and its ``ProductionOrderOperation`` rows (the routing snapshotted for 8.3's capacity
load). The header mixes in ``DocumentMixin`` (it registers in core_documents + claims an MO- number
at creation — a posted document, unlike the 8.1 masters).

All item/UoM/warehouse/bin ids are OPAQUE inventory ids (D-029): no cross-module FK to inventory
tables; the service validates each via ``inventory/queries`` before writing. The ``bom_id``/
``routing_id`` are INTRA-module composite tenant FKs to ``mfg_boms``/``mfg_routings`` (the exploded
version snapshots). Quantities use the D-015 QuantityType (scale-6, exact on both engines);
``accumulated_wip_cost`` uses MoneyType (the value side, quantized to currency).

``accumulated_wip_cost`` is the running WIP debit for this order: raised by each component issue (by
the posted issue cost) and consumed at finish to compute the finished unit cost — the SSOT for the
WIP-nets-to-zero invariant (D-048), maintained on the header rather than recomputed from the journal
so the finish flow has the figure in hand.
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
from app.core.money import MoneyType, QuantityType
from app.modules.manufacturing.constants import ProductionOrderStatus


class ProductionOrder(UuidPKMixin, TenantMixin, AuditMixin, DocumentMixin, TimestampMixin, Base):
    """A PRODUCTION ORDER HEADER (D-048): the order to produce ``quantity`` of ``item_id``.

    ``item_id`` is the OPAQUE inventory parent item produced; ``bom_id`` is the INTRA-module BOM
    version EXPLODED into the component rows; ``routing_id`` (nullable) is the routing version
    snapshotted into the operation rows. ``warehouse_id`` is where components are issued FROM and
    the finished goods land. ``status`` runs the ``ProductionOrderStatus`` lifecycle.
    ``finished_quantity`` is raised at finish (0 until then); ``accumulated_wip_cost`` is the
    running WIP debit (raised by each issue, consumed at finish) — the WIP-nets-to-zero SSOT
    (D-048).
    Registers a document + claims the gapless MO- number at creation (D-012). Audited (D-010): a
    production order drives stock + GL effects.
    """

    __tablename__ = "mfg_production_orders"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("mfg_boms", "bom_id"),
        tenant_fk("mfg_routings", "routing_id"),
        document_fk(),
        sa.UniqueConstraint(
            "tenant_id",
            "order_number",
            name="uq_mfg_production_orders_tenant_id_order_number",
        ),
        sa.CheckConstraint(
            "quantity > 0", name="ck_mfg_production_orders_quantity_positive"
        ),
        sa.CheckConstraint(
            "finished_quantity >= 0",
            name="ck_mfg_production_orders_finished_non_negative",
        ),
        # The list filters on (tenant, status) and an item's orders by status (PERFORMANCE §1); the
        # composite serves the filtered + paginated list and the open-orders scan.
        sa.Index(
            "ix_mfg_production_orders_tenant_id_status", "tenant_id", "status"
        ),
        sa.Index(
            "ix_mfg_production_orders_tenant_id_item_id", "tenant_id", "item_id"
        ),
    )

    order_number: Mapped[str] = mapped_column(sa.String(60), nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        default=ProductionOrderStatus.DRAFT.value,
        server_default="DRAFT",
    )
    # OPAQUE inventory item id (D-029): the parent item produced. No FK to inv_items.
    item_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(QuantityType(), nullable=False)
    # INTRA-module composite tenant FK to mfg_boms — the exploded version snapshot.
    bom_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    # INTRA-module composite tenant FK to mfg_routings — the routing snapshot (nullable: a
    # routingless order is allowed; it just snapshots no operations).
    routing_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    # OPAQUE inventory warehouse id (D-029): components issue from it; finished goods land in it.
    warehouse_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    planned_start_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    planned_end_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    finished_quantity: Mapped[Decimal] = mapped_column(
        QuantityType(), nullable=False, default=Decimal(0), server_default="0"
    )
    # The running WIP debit (D-048): raised by each component issue's posted cost, consumed at
    # finish to derive the finished unit cost. MoneyType (the value side, quantized to currency).
    accumulated_wip_cost: Mapped[Decimal] = mapped_column(
        MoneyType(), nullable=False, default=Decimal(0), server_default="0"
    )
    notes: Mapped[str | None] = mapped_column(sa.String(1000), nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )


class ProductionOrderComponent(UuidPKMixin, TenantMixin, TimestampMixin, Base):
    """One EXPLODED, reserved component requirement of a production order (D-048).

    Snapshotted from the order's BOM at create time: ``component_item_id`` is the OPAQUE inventory
    material; ``required_quantity`` = quantity_per × order quantity × (1 + scrap_percent/100),
    quantized; ``issued_quantity`` is raised as materials are issued (0 until then — issued must
    not exceed required, v1 over-issue policy). ``bin_id`` is the OPAQUE bin the component is issued
    from (defaulted/settable). ``uom_id`` is the component's opaque UoM.

    NOT AuditMixin: components ride the order header's audit story (no independent lifecycle) — the
    BomComponent/sales-order-line precedent.
    """

    __tablename__ = "mfg_production_order_components"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("mfg_production_orders", "production_order_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "production_order_id",
            "line_number",
            name="uq_mfg_po_components_tenant_id_production_order_id_line_number",
        ),
        sa.CheckConstraint(
            "required_quantity > 0",
            name="ck_mfg_po_components_required_positive",
        ),
        sa.CheckConstraint(
            "issued_quantity >= 0",
            name="ck_mfg_po_components_issued_non_negative",
        ),
        sa.Index(
            "ix_mfg_po_components_tenant_id_production_order_id",
            "tenant_id",
            "production_order_id",
        ),
    )

    production_order_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    line_number: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    # OPAQUE inventory item id (D-029): the component material. No FK to inv_items.
    component_item_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    required_quantity: Mapped[Decimal] = mapped_column(QuantityType(), nullable=False)
    issued_quantity: Mapped[Decimal] = mapped_column(
        QuantityType(), nullable=False, default=Decimal(0), server_default="0"
    )
    # OPAQUE inventory UoM id (D-029).
    uom_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    # OPAQUE inventory bin id (D-029): where this component is issued FROM.
    bin_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)


class ProductionOrderOperation(UuidPKMixin, TenantMixin, TimestampMixin, Base):
    """One routing-snapshot operation of a production order (D-048): the per-order operation load
    8.3's rough capacity check sums against a work centre.

    Snapshotted from the order's routing at create time: ``operation_number`` is the sequence,
    ``work_center_id`` the INTRA-module work centre, ``setup_time_minutes`` the fixed setup and
    ``run_time_minutes_per_unit`` the per-unit run. ``planned_minutes`` = setup + run × order
    quantity (precomputed at snapshot so 8.3 reads the per-order load directly). All times in
    MINUTES (QuantityType, scale-6, D-015).

    NOT AuditMixin: operations ride the order header's audit story (the RoutingOperation precedent).
    """

    __tablename__ = "mfg_production_order_operations"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("mfg_production_orders", "production_order_id"),
        tenant_fk("mfg_work_centers", "work_center_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "production_order_id",
            "operation_number",
            name="uq_mfg_po_operations_tenant_order_operation_number",
        ),
        sa.CheckConstraint(
            "planned_minutes >= 0", name="ck_mfg_po_operations_planned_non_negative"
        ),
        sa.Index(
            "ix_mfg_po_operations_tenant_id_production_order_id",
            "tenant_id",
            "production_order_id",
        ),
        # The "operations at this work centre" read path (8.3 work-centre load aggregation).
        sa.Index(
            "ix_mfg_po_operations_tenant_id_work_center_id",
            "tenant_id",
            "work_center_id",
        ),
    )

    production_order_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    operation_number: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    work_center_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    description: Mapped[str | None] = mapped_column(sa.String(1000), nullable=True)
    setup_time_minutes: Mapped[Decimal] = mapped_column(
        QuantityType(), nullable=False, default=Decimal(0), server_default="0"
    )
    run_time_minutes_per_unit: Mapped[Decimal] = mapped_column(
        QuantityType(), nullable=False, default=Decimal(0), server_default="0"
    )
    planned_minutes: Mapped[Decimal] = mapped_column(
        QuantityType(), nullable=False, default=Decimal(0), server_default="0"
    )
