"""Inspection-lot model (PLAN 9.1, D-050): the ``InspectionLot`` header.

ONE table — the deliberately small v1 QM core (s4hana-parity §QM: inspection plans, characteristics,
results recording, notifications are all OUT). A lot is a header only (no result lines): it records
the inspected quantity from a goods-receipt line and a lot-level accept/reject outcome.

The header mixes in ``DocumentMixin`` (it registers in core_documents + claims a gapless ``QL-``
number at creation — a posted document, the orders/receipts precedent). It is created OPEN by the GR
handler when a ``requires_inspection`` GR line posts.

CROSS-MODULE IDS ARE OPAQUE (D-029/§5). ``source_document_id`` is the GR document's core_documents
id, carried as a plain column AND linked via docflow (GR → 'inspected_by' → lot) — NOT a
cross-module
FK into procurement. ``item_id``/``bin_id``/``warehouse_id``/``lot_id``/``serial_id`` are OPAQUE
inventory ids snapshot from the GR line (validated/used via inventory/queries + the disposition
event, never a FK into inv_*). ``decision_by`` is the deciding user's id (a core adm_users id, the
posted-by precedent — kept as a plain id, no FK, mirroring journal posted_by_user_id style).
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
from app.core.money import QuantityType
from app.modules.quality.constants import InspectionLotStatus, InspectionSource


class InspectionLot(UuidPKMixin, TenantMixin, AuditMixin, DocumentMixin, TimestampMixin, Base):
    """An INSPECTION LOT header (D-050): the unit of inspection for one received, flagged GR line.

    ``lot_number`` is the gapless QL- number claimed at creation. ``status`` runs the
    ``InspectionLotStatus`` lifecycle (OPEN at creation → ACCEPTED / REJECTED on the usage decision;
    OPEN → CANCELLED). ``source`` is the origin (GOODS_RECEIPT in v1); ``source_document_id`` is the
    GR document's OPAQUE core_documents id (also a docflow edge — D-050). ``item_id``/``bin_id``/
    ``warehouse_id`` are OPAQUE inventory ids snapshot from the GR line; ``inspect_lot_id``/
    ``serial_id`` carry the tracked instance the received stock landed on (nullable). ``quantity``
    is
    the inspected quantity; ``accepted_quantity``/``rejected_quantity`` record the decision split (0
    until decided). ``disposition`` is set only on a reject. ``decided_date``/``decision_by`` stamp
    the decision. Audited (D-010): a usage decision drives stock + GL effects.
    """

    __tablename__ = "qm_inspection_lots"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("adm_tenants"),
        document_fk(),
        sa.UniqueConstraint(
            "tenant_id", "lot_number", name="uq_qm_inspection_lots_tenant_id_lot_number"
        ),
        sa.CheckConstraint("quantity > 0", name="ck_qm_inspection_lots_quantity_positive"),
        sa.CheckConstraint(
            "accepted_quantity >= 0", name="ck_qm_inspection_lots_accepted_non_negative"
        ),
        sa.CheckConstraint(
            "rejected_quantity >= 0", name="ck_qm_inspection_lots_rejected_non_negative"
        ),
        # PERFORMANCE §1: the lot list filters on (tenant, status) and an item's lots; the
        # GR→lot lookup filters on (tenant, source_document_id).
        sa.Index("ix_qm_inspection_lots_tenant_id_status", "tenant_id", "status"),
        sa.Index("ix_qm_inspection_lots_tenant_id_item_id", "tenant_id", "item_id"),
        sa.Index(
            "ix_qm_inspection_lots_tenant_id_source_document_id",
            "tenant_id",
            "source_document_id",
        ),
    )

    lot_number: Mapped[str] = mapped_column(sa.String(60), nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        default=InspectionLotStatus.OPEN.value,
        server_default="OPEN",
    )
    source: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        default=InspectionSource.GOODS_RECEIPT.value,
        server_default="GOODS_RECEIPT",
    )
    # OPAQUE core_documents id of the originating GR (D-029/D-050): a plain column + a docflow edge,
    # never a cross-module FK into procurement.
    source_document_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    # OPAQUE inventory ids snapshot from the GR line (D-029). No FK to inv_*.
    item_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    warehouse_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    bin_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    # The tracked instance the received stock landed on (nullable — only for lot/serial items).
    inspect_lot_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    serial_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    quantity: Mapped[Decimal] = mapped_column(QuantityType(), nullable=False)
    accepted_quantity: Mapped[Decimal] = mapped_column(
        QuantityType(), nullable=False, default=Decimal(0), server_default="0"
    )
    rejected_quantity: Mapped[Decimal] = mapped_column(
        QuantityType(), nullable=False, default=Decimal(0), server_default="0"
    )
    disposition: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    created_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    decided_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    # The deciding user (a core adm_users id, kept as a plain id like a journal's posted_by — no
    # FK).
    decision_by: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    notes: Mapped[str | None] = mapped_column(sa.String(1000), nullable=True)
