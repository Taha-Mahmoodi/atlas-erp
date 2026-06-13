"""Bill-of-materials master (PLAN 8.1, parity PP BOMs multi-level + versioned = FULL).

A BOM is the recipe for ONE parent item: a header (``Bom``) plus its direct ``BomComponent`` lines.
Identity is ``(item_id, version)`` (D-047) — the item it PRODUCES plus a user-supplied version
string — so a material can have several BOM versions, exactly one of which is the ACTIVE default
8.2/8.3 resolve. "Multi-level" is via REFERENCES: a component item can itself be the parent of its
own BOM, and the tree is walked by explosion at MRP time (8.3); the schema is single-level-per-BOM.

The item/UoM ids on the header and the component item/UoM ids on the lines are OPAQUE inventory ids
(D-029): no cross-module FK to inv_items/inv_uoms; the service validates each via
``inventory/queries`` before writing. Quantities use the D-015 QuantityType (scale-6, exact on both
engines); scrap_percent is a QuantityType ratio (never a plain Numeric, which loses precision on
SQLite, D-015).
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
from app.modules.manufacturing.constants import BomStatus


class Bom(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, Base):
    """A BOM HEADER — one VERSION of the recipe for a parent item (D-047).

    Identity ``(item_id, version)``: ``item_id`` is the OPAQUE inventory item the BOM PRODUCES (the
    finished/parent item, validated via inventory/queries); ``version`` is a user-supplied string
    (e.g. "1", "1.0", "REV-A"). ``base_quantity`` is how many parent units this BOM yields (e.g. 1);
    component ``quantity_per`` is per ``base_quantity``. ``status`` (BomStatus) gates usability;
    ``is_default`` marks the version 8.2/8.3 resolve — at most ONE ACTIVE+default per item, enforced
    in the service. Audited (D-010): the BOM defines what a production order consumes.
    """

    __tablename__ = "mfg_boms"
    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id", "item_id", "version", name="uq_mfg_boms_tenant_id_item_id_version"
        ),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        sa.CheckConstraint("base_quantity > 0", name="ck_mfg_boms_base_quantity_positive"),
        # The default-active resolver + the filtered list both key on (tenant, item_id, status)
        # (PERFORMANCE §6); this composite serves get_active_bom_for_item + the item/status filter.
        sa.Index(
            "ix_mfg_boms_tenant_id_item_id_status", "tenant_id", "item_id", "status"
        ),
    )

    # OPAQUE inventory item id (D-029): the parent item the BOM produces. No FK to inv_items.
    item_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    version: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(20), nullable=False, default=BomStatus.DRAFT.value, server_default="DRAFT"
    )
    base_quantity: Mapped[Decimal] = mapped_column(
        QuantityType(), nullable=False, default=Decimal(1), server_default="1"
    )
    # OPAQUE inventory UoM id (D-029): the parent's unit, the base_quantity is expressed in.
    uom_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    is_default: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false()
    )
    notes: Mapped[str | None] = mapped_column(sa.String(1000), nullable=True)


class BomComponent(UuidPKMixin, TenantMixin, TimestampMixin, Base):
    """One DIRECT component line of a BOM (D-047): a raw material or sub-assembly consumed to make
    the parent.

    ``component_item_id`` is an OPAQUE inventory item (validated via inventory/queries) that MUST
    differ from the BOM's parent item — a direct self-component is rejected (the service enforces
    it; deeper cycles are an 8.3 explosion-time concern). ``quantity_per`` is the quantity consumed
    per the header's ``base_quantity`` of parent; ``scrap_percent`` adds waste allowance (0 = none).
    A component item that itself has a BOM is the "multi-level via references" mechanism — resolved
    by explosion in 8.3.

    NOT AuditMixin: components are low-churn config that ride the BOM header's audit story (no
    independent lifecycle) — the inventory UomConversion precedent, keeping the audit log lean.
    """

    __tablename__ = "mfg_bom_components"
    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id",
            "bom_id",
            "line_number",
            name="uq_mfg_bom_components_tenant_id_bom_id_line_number",
        ),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("mfg_boms", "bom_id"),
        sa.CheckConstraint(
            "quantity_per > 0", name="ck_mfg_bom_components_quantity_per_positive"
        ),
        sa.CheckConstraint(
            "scrap_percent >= 0", name="ck_mfg_bom_components_scrap_non_negative"
        ),
        # The "this BOM's components" read path (the nested list + explosion).
        sa.Index("ix_mfg_bom_components_tenant_id_bom_id", "tenant_id", "bom_id"),
    )

    bom_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    line_number: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    # OPAQUE inventory item id (D-029): the component material/sub-assembly. No FK to inv_items.
    component_item_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    quantity_per: Mapped[Decimal] = mapped_column(QuantityType(), nullable=False)
    # OPAQUE inventory UoM id (D-029): the unit quantity_per is expressed in.
    uom_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    scrap_percent: Mapped[Decimal] = mapped_column(
        QuantityType(), nullable=False, default=Decimal(0), server_default="0"
    )
    notes: Mapped[str | None] = mapped_column(sa.String(1000), nullable=True)
