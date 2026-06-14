"""Projects request/response schemas (Pydantic v2, ApiModel base) for PLAN 11.1.

Create/Update/Read/Filter for the two masters (Project, WbsElement) plus the project COST REPORT
schemas. Money amounts are ``Decimal`` strings (D-015); a ``code`` is immutable so it is absent from
the Update schemas (the work-centre precedent). The Read schemas carry the server-derived fields
(timestamps). The cost report carries per-WBS rows + a rolled-up project total, each with budget,
actual cost, hours and variance (budget − actual).
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from app.core.schemas import ApiModel
from app.modules.projects.constants import ProjectStatus, WbsStatus

# --- Project ------------------------------------------------------------------


class ProjectCreate(ApiModel):
    """Create a project. ``code`` is user-supplied + unique per tenant; ``customer_id`` /
    ``cost_center_id`` (optional) are validated to exist (sales / finance) when set (D-029)."""

    code: str
    name: str
    description: str | None = None
    status: ProjectStatus = ProjectStatus.PLANNING
    customer_id: uuid.UUID | None = None
    cost_center_id: uuid.UUID | None = None
    start_date: date | None = None
    end_date: date | None = None
    budget_amount: Decimal | None = None
    is_active: bool = True


class ProjectUpdate(ApiModel):
    """Partial update. ``code`` is immutable (absent here); a changed ``customer_id`` /
    ``cost_center_id`` is re-validated. All fields optional — only the set ones change
    (exclude_unset)."""

    name: str | None = None
    description: str | None = None
    status: ProjectStatus | None = None
    customer_id: uuid.UUID | None = None
    cost_center_id: uuid.UUID | None = None
    start_date: date | None = None
    end_date: date | None = None
    budget_amount: Decimal | None = None
    is_active: bool | None = None


class ProjectRead(ApiModel):
    id: uuid.UUID
    code: str
    name: str
    description: str | None
    status: ProjectStatus
    customer_id: uuid.UUID | None
    cost_center_id: uuid.UUID | None
    start_date: date | None
    end_date: date | None
    budget_amount: Decimal | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ProjectFilter(ApiModel):
    """List filters. None means "no constraint"; folded into the cursor's filter fingerprint so a
    cursor cannot cross filtered views."""

    status: ProjectStatus | None = None


# --- WBS element --------------------------------------------------------------


class WbsElementCreate(ApiModel):
    """Create a WBS element under a project. ``code`` is user-supplied + unique within the project;
    ``parent_id`` (optional) must belong to the same project and not create a cycle."""

    code: str
    name: str
    parent_id: uuid.UUID | None = None
    status: WbsStatus = WbsStatus.OPEN
    is_billable: bool = False
    budget_amount: Decimal | None = None


class WbsElementUpdate(ApiModel):
    """Partial update. ``code`` and ``project_id`` are immutable (absent here); a changed
    ``parent_id`` is re-validated (same project, exists, no cycle)."""

    name: str | None = None
    parent_id: uuid.UUID | None = None
    status: WbsStatus | None = None
    is_billable: bool | None = None
    budget_amount: Decimal | None = None


class WbsElementRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    code: str
    name: str
    parent_id: uuid.UUID | None
    status: WbsStatus
    is_billable: bool
    budget_amount: Decimal | None
    created_at: datetime
    updated_at: datetime


class WbsElementFilter(ApiModel):
    status: WbsStatus | None = None


# --- Project cost report (D-056) ----------------------------------------------


class WbsCostLine(ApiModel):
    """One WBS element's line in the project cost report: its budget, actual cost (the sum of POSTED
    journal lines tagged with this WBS id — finance/queries), approved hours (hr/queries) and
    variance (budget − actual). A WBS with no postings shows zero actual / zero hours."""

    wbs_element_id: uuid.UUID
    code: str
    name: str
    status: WbsStatus
    parent_id: uuid.UUID | None
    budget_amount: Decimal
    actual_cost: Decimal
    hours: Decimal
    variance: Decimal


class ProjectCostReport(ApiModel):
    """The project cost report (PLAN 11.1, D-056): per-WBS cost lines + a rolled-up project total.

    ``lines`` is one ``WbsCostLine`` per WBS element of the project (ordered by code). The
    ``total_*`` fields roll the lines up to the project: ``total_budget`` is the project's own
    ``budget_amount`` when set else the sum of the WBS budgets (documented in the service);
    ``total_actual_cost`` / ``total_hours`` sum the lines; ``total_variance`` = total_budget −
    total_actual_cost. ``as_of_date`` (optional) is the cumulative-to date the actuals were summed
    through (None = all postings)."""

    project_id: uuid.UUID
    project_code: str
    project_name: str
    project_status: ProjectStatus
    as_of_date: date | None
    total_budget: Decimal
    total_actual_cost: Decimal
    total_hours: Decimal
    total_variance: Decimal
    lines: list[WbsCostLine]
