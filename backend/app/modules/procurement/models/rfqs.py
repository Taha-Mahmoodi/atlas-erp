"""Requests for quotation (PLAN 6.2): the ``Rfq`` header + ``RfqLine``.

An RFQ is the sourcing document — "vendor, what would this cost?". In v1 an RFQ targets ONE vendor
(``vendor_id`` is a composite tenant FK to ``proc_vendors``); multi-bidder comparison is the
documented parity later. The header mixes in ``DocumentMixin`` and carries a gapless ``rfq_number``
claimed at creation (D-040). An RFQ may be raised FROM an approved requisition
(``source_requisition_id`` set, a nullable composite tenant FK + a docflow edge). Lines copy the
requested item/qty; ``quoted_unit_cost`` (nullable ``MoneyType``) is filled when the vendor's prices
are recorded (the SENT→QUOTED step).

Enum columns are plain ``sa.String``; every table follows the D-007 composite-tenant-FK backstop.
"""

import uuid
from datetime import date

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
from app.modules.procurement.constants import RfqStatus


class Rfq(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, DocumentMixin, Base):
    """A request-for-quotation header (PLAN 6.2). ``vendor_id`` is the vendor asked to quote (a
    composite tenant FK to proc_vendors — an intra-module parent). ``rfq_number`` is claimed at
    creation (D-040). ``status`` runs the RfqStatus lifecycle. ``source_requisition_id`` (nullable
    composite tenant FK) records the requisition this RFQ was sourced from; ``valid_until`` is the
    quote's validity date. Audited (D-010)."""

    __tablename__ = "proc_rfqs"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("adm_tenants"),
        document_fk(),
        tenant_fk("proc_vendors", "vendor_id"),
        tenant_fk("proc_requisitions", "source_requisition_id"),
        # The RFQ list filters on (tenant, status) and (tenant, vendor_id) (PERFORMANCE §1).
        sa.Index("ix_proc_rfqs_tenant_id_status", "tenant_id", "status"),
        sa.Index("ix_proc_rfqs_tenant_id_vendor_id", "tenant_id", "vendor_id"),
    )

    rfq_number: Mapped[str] = mapped_column(sa.String(60), nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(20), nullable=False, default=RfqStatus.DRAFT.value, server_default="DRAFT"
    )
    vendor_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    currency_code: Mapped[str] = mapped_column(sa.String(3), nullable=False)
    valid_until: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    source_requisition_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    notes: Mapped[str | None] = mapped_column(sa.String(1000), nullable=True)


class RfqLine(UuidPKMixin, TenantMixin, TimestampMixin, Base):
    """One line on an RFQ (PLAN 6.2). ``item_id`` / ``uom_id`` are OPAQUE inventory ids (D-029).
    ``quoted_unit_cost`` (nullable ``MoneyType``) is filled when the vendor quotes (the record-quote
    step). UNIQUE(tenant_id, rfq_id, line_number). NOT AuditMixin (the header-line exclusion)."""

    __tablename__ = "proc_rfq_lines"
    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id", "rfq_id", "line_number", name="uq_proc_rfq_lines_rfq_line"
        ),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("proc_rfqs", "rfq_id"),
    )

    rfq_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    line_number: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    item_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    description: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)
    quantity: Mapped[object] = mapped_column(QuantityType(), nullable=False)
    uom_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    quoted_unit_cost: Mapped[object | None] = mapped_column(MoneyType(), nullable=True)
