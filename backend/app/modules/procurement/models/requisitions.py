"""Purchase requisitions (PLAN 6.2): the ``PurchaseRequisition`` header +
``PurchaseRequisitionLine``.

A requisition is the internal "we need to buy this" request — the first document in the P2P chain
(requisition → RFQ → PO). The header mixes in ``DocumentMixin`` (registered in core_documents) and
carries a gapless ``requisition_number`` claimed AT CREATION (D-040 — referenceable immediately).
Lines carry an OPAQUE inventory ``item_id`` (D-029 — a plain ``sa.Uuid``, validated via
``inventory/queries.item_exists``, never a cross-module FK) and an estimated unit cost (the
requester
names a budgetary estimate, refined by an RFQ quote or the PO's negotiated price). Money/quantity
columns use ``MoneyType`` / ``QuantityType`` (D-015, exact on both engines).

Enum-valued columns are plain ``sa.String`` storing the StrEnum's UPPER_SNAKE value; the service
maps
to/from the constants classes. Every table follows the D-007 composite-tenant-FK backstop
(``tenant_unique()`` + ``tenant_fk()`` composites + ``document_fk()`` on the header).
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
from app.modules.procurement.constants import RequisitionStatus


class PurchaseRequisition(
    UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, DocumentMixin, Base
):
    """A purchase requisition header (PLAN 6.2). ``requisition_number`` is the gapless system number
    claimed at creation (D-040; NOT NULL because a requisition is permanent at create — unlike a
    finance bill whose number is NULL until posting). ``status`` runs the RequisitionStatus
    lifecycle; the SUBMIT step evaluates the REQUISITION approval threshold on the estimated total
    (≥ threshold ⇒ stays SUBMITTED awaiting approval, below ⇒ auto APPROVED). ``requested_by`` is
    the requesting user id (opaque, nullable — a requisition may be raised by a system flow).
    Audited (D-010): a document that authorizes spend downstream."""

    __tablename__ = "proc_requisitions"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("adm_tenants"),
        document_fk(),
        # The requisition list filters on (tenant, status) and (tenant, requested_by) and sorts by
        # creation (PERFORMANCE §1): composite so the filtered + paginated list is index-served.
        sa.Index("ix_proc_requisitions_tenant_id_status", "tenant_id", "status"),
    )

    requisition_number: Mapped[str] = mapped_column(sa.String(60), nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        default=RequisitionStatus.DRAFT.value,
        server_default="DRAFT",
    )
    # The requesting user id (opaque core_users id; nullable — a system flow may raise one).
    requested_by: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    needed_by_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(sa.String(1000), nullable=True)


class PurchaseRequisitionLine(UuidPKMixin, TenantMixin, TimestampMixin, Base):
    """One requested item on a requisition (PLAN 6.2). ``item_id`` and ``uom_id`` are OPAQUE
    inventory ids (D-029 — plain ``sa.Uuid``, validated via inventory/queries, never FKs).
    ``estimated_unit_cost`` (nullable) is the requester's budgetary estimate; ``currency_code`` is
    the line's currency. UNIQUE(tenant_id, requisition_id, line_number) so line numbers are dense
    per requisition. NOT AuditMixin: lines are written with their header and the header's audit row
    records the document-level change (the journal/bill-line exclusion)."""

    __tablename__ = "proc_requisition_lines"
    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id",
            "requisition_id",
            "line_number",
            name="uq_proc_requisition_lines_requisition_line",
        ),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("proc_requisitions", "requisition_id"),
    )

    requisition_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    line_number: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    item_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    description: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)
    quantity: Mapped[object] = mapped_column(QuantityType(), nullable=False)
    uom_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    estimated_unit_cost: Mapped[object | None] = mapped_column(MoneyType(), nullable=True)
    currency_code: Mapped[str] = mapped_column(sa.String(3), nullable=False)
