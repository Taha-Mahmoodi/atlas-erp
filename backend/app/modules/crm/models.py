"""CRM models (PLAN 12.1, parity CRM-lite = leads → opportunities kanban + activities + convert,
D-057): the ``Lead``, ``Opportunity`` (+ optional ``OpportunityLine``) and ``Activity`` tables.

FOUR tables, one concern (the pre-sales pipeline) — comfortably under the 400-line cap, so a single
models.py (the projects/maintenance precedent; split into a models/ package only at the cap).

- ``Lead`` and ``Opportunity`` are AUTO-NUMBERED (gapless LEAD-… / OPP- claimed at creation, the
  procurement-document precedent). ``Opportunity`` mixes in DocumentMixin so it carries a
  core_documents registry entry — needed so the SALES convert handler can write the convert docflow
  edges (opportunity → customer / opportunity → quote). ``Lead`` is NOT a docflow document (no
  registry entry) — it is a pipeline row whose only successor link is the intra-module
  ``converted_opportunity_id``.

- ``OpportunityLine`` (OPTIONAL — "expected products"): one row per item an opportunity expects to
  sell, with a quantity + estimated unit price. These become the QUOTE LINES on convert (each line's
  item/quantity/estimated price drives a quote line; with no lines the convert builds a single quote
  line from the opportunity's ``estimated_value``). Kept LEAN/optional per the lite scope (D-057).

- ``Activity`` is logged against EXACTLY ONE of a lead OR an opportunity. A DB CHECK
  ``ck_crm_activities_one_parent`` enforces exactly-one-parent (lead_id XOR opportunity_id), and the
  service validates it up front + that the named parent exists (D-057).

CROSS-MODULE IDS ARE OPAQUE (D-029/§5). ``owner_employee_id`` is an OPAQUE hr employee id (nullable,
validated via ``hr/queries.employee_exists`` when set). ``Opportunity.customer_id`` is an OPAQUE
sales
customer id (nullable — set when an opportunity is for an EXISTING customer; validated via
``sales/queries.customer_exists`` when set). ``OpportunityLine.item_id`` is an OPAQUE inventory item
id
(validated via ``inventory/queries.item_exists``). ``converted_customer_id`` /
``converted_quote_id``
are recorded on convert for the API, but the DURABLE convert link is the docflow edge the sales
handler writes — these columns are NOT cross-module FKs. The ``source_lead_id`` / ``lead_id`` /
``opportunity_id`` / ``opportunity_id`` (on lines) links are INTRA-module composite tenant FKs.

Money columns use the D-015 ``MoneyType`` (scale-6, exact on both engines); quantities use
``QuantityType``. A plain ``sa.Numeric`` would round-trip through float on SQLite and lose
precision,
so it is never used for a stored amount/quantity here.
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
from app.core.money import MoneyType, QuantityType
from app.modules.crm.constants import (
    ActivityStatus,
    LeadStatus,
    OpportunityStage,
)


class Lead(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, Base):
    """A LEAD — an unqualified inbound contact (D-057). Auto-numbered (gapless LEAD- at creation).

    ``status`` runs the ``LeadStatus`` lifecycle (NEW → CONTACTED → QUALIFIED → CONVERTED, or
    DISQUALIFIED). ``company_name`` / ``contact_name`` / ``email`` / ``phone`` / ``source`` describe
    the prospect. ``estimated_value`` + ``currency_code`` are the rough deal size (both nullable — a
    raw lead may carry no figure). ``owner_employee_id`` is the OPAQUE hr employee who owns the lead
    (nullable, validated when set). ``converted_opportunity_id`` is set (intra-module composite
    tenant
    FK) when ``convert_lead_to_opportunity`` turns the lead into an opportunity, alongside status
    CONVERTED — the lead → opportunity link. Audited (D-010): pipeline state.
    """

    __tablename__ = "crm_leads"
    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id", "lead_number", name="uq_crm_leads_tenant_id_lead_number"
        ),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        # The lead's successor opportunity (intra-module): a composite tenant FK so it can never
        # cross
        # tenants. Nullable — set only on convert.
        tenant_fk("crm_opportunities", "converted_opportunity_id"),
        # The filtered status list (the pipeline view) is served by (tenant, status) (PERFORMANCE
        # §1).
        sa.Index("ix_crm_leads_tenant_id_status", "tenant_id", "status"),
    )

    lead_number: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        default=LeadStatus.NEW.value,
        server_default="NEW",
    )
    company_name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    contact_name: Mapped[str | None] = mapped_column(sa.String(200), nullable=True)
    email: Mapped[str | None] = mapped_column(sa.String(320), nullable=True)
    phone: Mapped[str | None] = mapped_column(sa.String(40), nullable=True)
    # Where the lead came from (web/referral/event/…) — free text, no enum in v1.
    source: Mapped[str | None] = mapped_column(sa.String(60), nullable=True)
    estimated_value: Mapped[Decimal | None] = mapped_column(MoneyType(), nullable=True)
    currency_code: Mapped[str | None] = mapped_column(sa.String(3), nullable=True)
    # Opaque hr employee id (D-029): no cross-module FK; validated via hr/queries when set.
    owner_employee_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    notes: Mapped[str | None] = mapped_column(sa.String(1000), nullable=True)
    # Intra-module composite tenant FK (nullable): the opportunity this lead became, on convert.
    converted_opportunity_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)


class Opportunity(UuidPKMixin, TenantMixin, DocumentMixin, AuditMixin, TimestampMixin, Base):
    """An OPPORTUNITY — a qualified deal in the pipeline (D-057). Auto-numbered (gapless OPP- at
    creation) and registered in core_documents (DocumentMixin) so the SALES convert handler can
    write
    the convert docflow edges.

    ``stage`` IS THE KANBAN COLUMN (``OpportunityStage``: PROSPECTING → QUALIFICATION → PROPOSAL →
    NEGOTIATION → WON | LOST); ``move_stage`` moves the card. ``name`` is the deal label.
    ``source_lead_id`` (nullable intra-module composite tenant FK) is the lead this came from, if
    any.
    ``customer_id`` is an OPAQUE sales customer id (nullable — set when the deal is for an EXISTING
    customer, validated via sales/queries; when NULL the deal is for a PROSPECT named by
    ``company_name`` and convert creates the customer). ``company_name`` / ``contact_name`` /
    ``email``
    describe the account. ``estimated_value`` + ``currency_code`` are the deal value (the quote
    fallback when there are no lines). ``probability_percent`` is the win probability (MoneyType for
    exact 0–100, nullable). ``expected_close_date`` (Date, nullable) is the forecast close.
    ``owner_employee_id`` is the OPAQUE hr owner (nullable, validated when set).
    ``converted_customer_id`` / ``converted_quote_id`` are recorded on convert for the API (the
    durable
    link is the docflow edge, NOT an FK). Audited (D-010).
    """

    __tablename__ = "crm_opportunities"
    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id",
            "opportunity_number",
            name="uq_crm_opportunities_tenant_id_opportunity_number",
        ),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        # The source lead (intra-module composite tenant FK, nullable).
        tenant_fk("crm_leads", "source_lead_id"),
        document_fk(),
        # The kanban board / filtered stage list is served by (tenant, stage); the "my pipeline"
        # view
        # by (tenant, owner_employee_id) (PERFORMANCE §1).
        sa.Index("ix_crm_opportunities_tenant_id_stage", "tenant_id", "stage"),
        sa.Index(
            "ix_crm_opportunities_tenant_id_owner_employee_id",
            "tenant_id",
            "owner_employee_id",
        ),
    )

    opportunity_number: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    stage: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        default=OpportunityStage.PROSPECTING.value,
        server_default="PROSPECTING",
    )
    # The source lead (intra-module composite tenant FK, nullable — an opportunity may be created
    # directly without a lead).
    source_lead_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    # Opaque sales customer id (D-029): no cross-module FK; validated via sales/queries when set.
    # NULL
    # = a prospect (convert creates the customer); set = an existing customer (convert only quotes).
    customer_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    company_name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    contact_name: Mapped[str | None] = mapped_column(sa.String(200), nullable=True)
    email: Mapped[str | None] = mapped_column(sa.String(320), nullable=True)
    estimated_value: Mapped[Decimal] = mapped_column(
        MoneyType(), nullable=False, default=Decimal(0), server_default="0"
    )
    currency_code: Mapped[str] = mapped_column(sa.String(3), nullable=False)
    probability_percent: Mapped[Decimal | None] = mapped_column(MoneyType(), nullable=True)
    expected_close_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    owner_employee_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    notes: Mapped[str | None] = mapped_column(sa.String(1000), nullable=True)
    # Recorded on convert (NOT cross-module FKs — the durable link is the docflow edge, D-057).
    converted_customer_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    converted_quote_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)


class OpportunityLine(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, Base):
    """An OPPORTUNITY LINE — one expected product on an opportunity (D-057, OPTIONAL). These become
    the QUOTE LINES on convert.

    ``opportunity_id`` is the INTRA-module composite tenant FK to the owning ``crm_opportunities``
    row.
    ``line_number`` is unique within the opportunity. ``item_id`` is the OPAQUE inventory item id
    (validated via inventory/queries). ``quantity`` is the expected quantity (QuantityType, > 0).
    ``estimated_unit_price`` is the expected per-unit price (MoneyType, >= 0) — the unit price the
    convert quote line carries. ``description`` is the optional line note. Audited (D-010).
    """

    __tablename__ = "crm_opportunity_lines"
    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id",
            "opportunity_id",
            "line_number",
            name="uq_crm_opportunity_lines_tenant_opportunity_line",
        ),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("crm_opportunities", "opportunity_id"),
        sa.CheckConstraint("quantity > 0", name="quantity_positive"),
        sa.CheckConstraint("estimated_unit_price >= 0", name="estimated_unit_price_non_negative"),
        # The lines-of-an-opportunity read filters on (tenant, opportunity_id) (PERFORMANCE §1).
        sa.Index(
            "ix_crm_opportunity_lines_tenant_id_opportunity_id",
            "tenant_id",
            "opportunity_id",
        ),
    )

    opportunity_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    line_number: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    item_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    description: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(QuantityType(), nullable=False)
    estimated_unit_price: Mapped[Decimal] = mapped_column(MoneyType(), nullable=False)


class Activity(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, Base):
    """An ACTIVITY — a logged interaction against EXACTLY ONE of a lead OR an opportunity (D-057).

    ``activity_type`` (``ActivityType``: CALL/EMAIL/MEETING/TASK/NOTE) types it; ``status``
    (``ActivityStatus``: OPEN → COMPLETED/CANCELLED) runs its lifecycle. ``subject`` is the
    headline,
    ``description`` the detail (nullable). ``due_date`` (nullable) is when a planned action is due;
    ``completed_date`` (nullable) is stamped on complete. ``lead_id`` OR ``opportunity_id`` (both
    nullable intra-module composite tenant FKs) points at the parent — EXACTLY ONE is set, enforced
    by
    the ``ck_crm_activities_one_parent`` CHECK (a DB backstop) AND the service (a friendly 422 up
    front). ``owner_employee_id`` is the OPAQUE hr owner (nullable, validated when set). Audited
    (D-010).
    """

    __tablename__ = "crm_activities"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("crm_leads", "lead_id"),
        tenant_fk("crm_opportunities", "opportunity_id"),
        # EXACTLY-ONE-PARENT (D-057): lead_id XOR opportunity_id. The bare token is wrapped by the
        # D-022 ck convention -> ck_crm_activities_one_parent.
        sa.CheckConstraint(
            "(lead_id IS NOT NULL AND opportunity_id IS NULL) "
            "OR (lead_id IS NULL AND opportunity_id IS NOT NULL)",
            name="one_parent",
        ),
        # The activities-for-a-lead / -opportunity reads + the filtered status list (PERFORMANCE
        # §1).
        sa.Index("ix_crm_activities_tenant_id_lead_id", "tenant_id", "lead_id"),
        sa.Index(
            "ix_crm_activities_tenant_id_opportunity_id", "tenant_id", "opportunity_id"
        ),
        sa.Index("ix_crm_activities_tenant_id_status", "tenant_id", "status"),
    )

    activity_type: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        default=ActivityStatus.OPEN.value,
        server_default="OPEN",
    )
    subject: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(sa.String(1000), nullable=True)
    due_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    completed_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    # Intra-module composite tenant FKs (both nullable; the CHECK enforces exactly one).
    lead_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    owner_employee_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
