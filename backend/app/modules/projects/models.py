"""Projects models (PLAN 11.1, parity PS = projects + a WBS hierarchy as costing objects, D-056):
the ``Project`` master and its ``WbsElement`` tree.

TWO tables, one concern (PS v1 cost collection) — well under the 400-line cap, so a single
models.py (the maintenance/quality precedent; split into a models/ package only at the cap).

- ``Project`` and ``WbsElement`` are both MASTERS keyed by a USER-SUPPLIED ``code`` (no gapless
  document number — the work-centre / equipment precedent). Neither mixes in DocumentMixin: a
  project/WBS is reference data a posting TAGS, not a posted docflow document (D-056). The
  ``Project`` code is UNIQUE per tenant; the ``WbsElement`` code is UNIQUE per (tenant, project) —
  it only has to be unique within its project (the account-group-within-chart precedent).

- A ``WbsElement``'s ``id`` IS THE COSTING OBJECT (D-056): it is the opaque ``project_id`` dimension
  a finance journal line / HR time entry tags when work / purchases are "posted to a WBS". The cost
  report projects journal lines + timesheet hours by that id.

CROSS-MODULE IDS ARE OPAQUE (D-029/§5). ``Project.customer_id`` is an OPAQUE sales customer id
(nullable, validated via ``sales/queries.customer_exists`` when set — never a cross-module FK).
``Project.cost_center_id`` is an OPAQUE finance cost-centre id (nullable, validated via
``finance/queries.cost_center_exists`` when set). The ``project_id`` / ``parent_id`` links are
INTRA-module composite tenant FKs (the WBS tree + its owning project).

Money columns use the D-015 ``MoneyType`` (scale-6, exact on both engines); a plain ``sa.Numeric``
would round-trip through float on SQLite and lose precision, so it is never used for a stored amount
here. ``budget_amount`` is a SIMPLE budget figure feeding the cost report's variance — NOT a
budget-control mechanism (no posting-time funds check in v1, D-056).
"""

import uuid
from datetime import date
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
from app.core.money import MoneyType
from app.modules.projects.constants import ProjectStatus, WbsStatus


class Project(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, Base):
    """A PROJECT master (D-056): the top of a work-breakdown structure and the umbrella a cost
    report aggregates.

    ``code`` is USER-SUPPLIED and unique per tenant (no auto-number — the master-data precedent).
    ``status`` runs the ``ProjectStatus`` lifecycle (informational in v1 — it does NOT gate posting,
    D-029). ``customer_id`` is an OPAQUE sales customer id (nullable, validated via sales/queries
    when set — a project may be for a customer). ``cost_center_id`` is an OPAQUE finance cost-centre
    id (nullable, validated via finance/queries when set — for cost attribution). ``start_date`` /
    ``end_date`` bracket the project (Date, nullable). ``budget_amount`` is a SIMPLE budget figure
    feeding the cost report's project-level variance (MoneyType, nullable — NOT budget control,
    D-056). ``is_active`` is the soft-enable flag (the master-data precedent). Audited (D-010):
    master data driving cost reporting.
    """

    __tablename__ = "ps_projects"
    __table_args__ = (
        sa.UniqueConstraint("tenant_id", "code", name="uq_ps_projects_tenant_id_code"),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        # The (tenant, code) UNIQUE already serves the code lookup; this index serves the filtered
        # status list (PERFORMANCE §1).
        sa.Index("ix_ps_projects_tenant_id_status", "tenant_id", "status"),
    )

    code: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(sa.String(1000), nullable=True)
    status: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        default=ProjectStatus.PLANNING.value,
        server_default="PLANNING",
    )
    # Opaque sales customer id (D-029): no cross-module FK; the service validates it via
    # sales/queries when set. A project may be FOR a customer.
    customer_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    # Opaque finance cost-centre id (D-029): no cross-module FK; validated via finance/queries when
    # set. For cost attribution of the project.
    cost_center_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    start_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    # A SIMPLE budget figure for the cost report's variance — NOT budget control (D-056).
    budget_amount: Mapped[Decimal | None] = mapped_column(MoneyType(), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=True, server_default=sa.true()
    )


class WbsElement(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, Base):
    """A WBS ELEMENT (D-056): a node in a project's work-breakdown tree and THE COSTING OBJECT.

    ``project_id`` is the INTRA-module composite tenant FK to the owning ``ps_projects`` row.
    ``code`` is USER-SUPPLIED and unique per (tenant, PROJECT) — it only has to be unique within its
    project (the account-group-within-chart precedent). ``parent_id`` (nullable self composite
    tenant FK) builds the WBS TREE; the service cycle-guards it. ``status`` runs the ``WbsStatus``
    lifecycle (OPEN/CLOSED — advisory in v1, D-056). ``is_billable`` flags billable work (default
    false). ``budget_amount`` is the per-WBS budget feeding the cost report's per-element variance
    (MoneyType, nullable — NOT budget control).

    THE ELEMENT'S ``id`` IS THE OPAQUE PROJECT DIMENSION a finance journal line
    (``fin_journal_lines.project_id``) and a HR time entry (``hr_time_entries.project_id``) tag when
    work / purchases are posted to this WBS (D-056). Audited (D-010): the costing-object master.
    """

    __tablename__ = "ps_wbs_elements"
    __table_args__ = (
        # Code unique WITHIN a project (not per tenant): the same code may recur under different
        # projects (D-056).
        sa.UniqueConstraint(
            "tenant_id", "project_id", "code", name="uq_ps_wbs_elements_tenant_project_code"
        ),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("ps_projects", "project_id"),
        # Self composite tenant FK: a parent WBS can never cross tenants. Explicit shortened name
        # (the D-022 column-0 convention would render a name > the PG 63-char cap).
        sa.ForeignKeyConstraint(
            ["tenant_id", "parent_id"],
            ["ps_wbs_elements.tenant_id", "ps_wbs_elements.id"],
            name="fk_ps_wbs_elements_parent_id_ps_wbs_elements",
        ),
        # The WBS-of-a-project tree read filters on (tenant, project_id); the parent walk uses
        # (tenant, parent_id) (PERFORMANCE §1).
        sa.Index(
            "ix_ps_wbs_elements_tenant_id_project_id_status",
            "tenant_id",
            "project_id",
            "status",
        ),
        sa.Index("ix_ps_wbs_elements_tenant_id_parent_id", "tenant_id", "parent_id"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    code: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    # Self composite tenant FK (nullable — a top-level WBS has no parent): the WBS tree.
    parent_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    status: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        default=WbsStatus.OPEN.value,
        server_default="OPEN",
    )
    is_billable: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false()
    )
    budget_amount: Mapped[Decimal | None] = mapped_column(MoneyType(), nullable=True)
