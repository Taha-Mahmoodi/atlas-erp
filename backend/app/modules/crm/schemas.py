"""CRM request/response schemas (Pydantic v2, ApiModel base) for PLAN 12.1.

Create/Update/Read/Filter for the three entities (Lead, Opportunity + lines, Activity), plus the
ACTION payloads (qualify/disqualify a lead, convert a lead → opportunity, move a stage [the kanban
move], convert an opportunity → customer + quote, complete an activity) and the KANBAN BOARD
response
(opportunities grouped by stage).

Read schemas mirror the models field-for-field in snake_case; status/stage/type fields are typed
with
the constants enums (ApiModel ``use_enum_values`` serializes them as their UPPER_SNAKE string,
matching the column). Money/quantity are plain ``Decimal`` (D-015 via the column types;
JSON-serialized
as strings). Create/Update carry only client-settable fields; ids, timestamps, tenant_id, the
auto-numbers, the converted_* fields and the lead's converted_opportunity_id are server-owned. The
``lead_number`` / ``opportunity_number`` are server-assigned so they are absent from Create.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import Field

from app.core.schemas import ApiModel
from app.modules.crm.constants import (
    ActivityStatus,
    ActivityType,
    LeadStatus,
    OpportunityStage,
)

# --- Leads --------------------------------------------------------------------


class LeadCreate(ApiModel):
    """Create a lead. ``company_name`` is required; everything else optional. ``status`` defaults to
    NEW. ``owner_employee_id`` (optional) is validated to exist in hr when set (D-029).
    ``estimated_value`` (optional) pairs with ``currency_code`` (validated in finance when value
    set).
    """

    company_name: str
    contact_name: str | None = None
    email: str | None = None
    phone: str | None = None
    source: str | None = None
    status: LeadStatus = LeadStatus.NEW
    estimated_value: Decimal | None = Field(default=None, ge=0)
    currency_code: str | None = Field(default=None, min_length=3, max_length=3)
    owner_employee_id: uuid.UUID | None = None
    notes: str | None = None


class LeadUpdate(ApiModel):
    """Partial update. ``lead_number`` / ``status`` / ``converted_opportunity_id`` are server-owned
    (status moves via the qualify/disqualify actions, not a free edit) so they are absent here. A
    changed ``owner_employee_id`` is re-validated to exist; a value+currency pair is
    re-validated."""

    company_name: str | None = None
    contact_name: str | None = None
    email: str | None = None
    phone: str | None = None
    source: str | None = None
    estimated_value: Decimal | None = Field(default=None, ge=0)
    currency_code: str | None = Field(default=None, min_length=3, max_length=3)
    owner_employee_id: uuid.UUID | None = None
    notes: str | None = None


class LeadRead(ApiModel):
    id: uuid.UUID
    lead_number: str
    status: LeadStatus
    company_name: str
    contact_name: str | None
    email: str | None
    phone: str | None
    source: str | None
    estimated_value: Decimal | None
    currency_code: str | None
    owner_employee_id: uuid.UUID | None
    notes: str | None
    converted_opportunity_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class LeadFilter(ApiModel):
    """List filters. None means "no constraint"; folded into the cursor's filter fingerprint so a
    cursor cannot cross filtered views."""

    status: LeadStatus | None = None


class ConvertLead(ApiModel):
    """Convert a QUALIFIED lead → a DRAFT opportunity (PLAN 12.1). The
    company/contact/value/currency
    come from the lead; only the opportunity-specific fields are supplied here (all optional —
    ``name`` defaults to the lead's company name; ``expected_close_date`` optional)."""

    name: str | None = None
    expected_close_date: date | None = None
    probability_percent: Decimal | None = Field(default=None, ge=0, le=100)
    notes: str | None = None


# --- Opportunity lines --------------------------------------------------------


class OpportunityLineCreate(ApiModel):
    """One expected product on an opportunity. ``item_id`` is an opaque inventory id (validated,
    D-029). ``quantity`` > 0; ``estimated_unit_price`` >= 0. Becomes a quote line on convert."""

    item_id: uuid.UUID
    description: str | None = None
    quantity: Decimal = Field(gt=0)
    estimated_unit_price: Decimal = Field(ge=0)


class OpportunityLineRead(ApiModel):
    id: uuid.UUID
    line_number: int
    item_id: uuid.UUID
    description: str | None
    quantity: Decimal
    estimated_unit_price: Decimal


# --- Opportunities ------------------------------------------------------------


class OpportunityCreate(ApiModel):
    """Create a DRAFT opportunity (stage PROSPECTING). ``name`` + ``company_name`` +
    ``currency_code``
    are required. ``customer_id`` (optional) links an EXISTING sales customer (validated, D-029);
    when
    NULL the deal is a prospect named by ``company_name`` (convert then creates the customer).
    ``owner_employee_id`` (optional) is validated to exist in hr. ``lines`` (optional) are the
    expected
    products."""

    name: str
    company_name: str
    contact_name: str | None = None
    email: str | None = None
    customer_id: uuid.UUID | None = None
    currency_code: str = Field(min_length=3, max_length=3)
    estimated_value: Decimal = Field(default=Decimal(0), ge=0)
    probability_percent: Decimal | None = Field(default=None, ge=0, le=100)
    expected_close_date: date | None = None
    owner_employee_id: uuid.UUID | None = None
    notes: str | None = None
    lines: list[OpportunityLineCreate] = Field(default_factory=list)


class OpportunityUpdate(ApiModel):
    """Partial header update. ``opportunity_number`` / ``stage`` / ``source_lead_id`` /
    ``converted_*``
    are server-owned (stage moves via the move-stage action) so they are absent. ``lines`` (when
    supplied) replace the lines wholesale (revalidated). A changed ``customer_id`` /
    ``currency_code``
    / ``owner_employee_id`` is re-validated. Only an OPEN (non-terminal) opportunity is editable."""

    name: str | None = None
    company_name: str | None = None
    contact_name: str | None = None
    email: str | None = None
    customer_id: uuid.UUID | None = None
    currency_code: str | None = Field(default=None, min_length=3, max_length=3)
    estimated_value: Decimal | None = Field(default=None, ge=0)
    probability_percent: Decimal | None = Field(default=None, ge=0, le=100)
    expected_close_date: date | None = None
    owner_employee_id: uuid.UUID | None = None
    notes: str | None = None
    lines: list[OpportunityLineCreate] | None = None


class OpportunityRead(ApiModel):
    """Opportunity header without lines — the list-row / kanban-card shape."""

    id: uuid.UUID
    opportunity_number: str
    name: str
    stage: OpportunityStage
    source_lead_id: uuid.UUID | None
    customer_id: uuid.UUID | None
    company_name: str
    contact_name: str | None
    email: str | None
    estimated_value: Decimal
    currency_code: str
    probability_percent: Decimal | None
    expected_close_date: date | None
    owner_employee_id: uuid.UUID | None
    notes: str | None
    converted_customer_id: uuid.UUID | None
    converted_quote_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class OpportunityDetail(OpportunityRead):
    """Opportunity header + its lines — the detail / action-response shape."""

    lines: list[OpportunityLineRead]


class OpportunityFilter(ApiModel):
    """List filters for the opportunities endpoint. None means "no constraint"."""

    stage: OpportunityStage | None = None
    owner_employee_id: uuid.UUID | None = None


class MoveStage(ApiModel):
    """The KANBAN MOVE (PLAN 12.1): move an opportunity to ``stage``. The service validates the
    transition (any open stage → any open stage, or → WON/LOST; a terminal stage cannot move)."""

    stage: OpportunityStage


class ConvertOpportunity(ApiModel):
    """Convert a (non-terminal) opportunity → a sales customer + quote (PLAN 12.1, perm
    crm.opportunity.convert). Parameterless in v1 — the customer/quote are built from the
    opportunity's company/contact/currency/value + its lines. Kept as an explicit body so a later
    version can carry overrides (e.g. a customer_code prefix) without an API change."""


# --- Activities ---------------------------------------------------------------


class ActivityCreate(ApiModel):
    """Create an activity against EXACTLY ONE of a lead OR an opportunity (the service + DB CHECK
    enforce exactly-one-parent). ``activity_type`` + ``subject`` required; ``status`` defaults to
    OPEN. ``owner_employee_id`` (optional) is validated to exist in hr (D-029)."""

    activity_type: ActivityType
    subject: str
    description: str | None = None
    status: ActivityStatus = ActivityStatus.OPEN
    due_date: date | None = None
    lead_id: uuid.UUID | None = None
    opportunity_id: uuid.UUID | None = None
    owner_employee_id: uuid.UUID | None = None


class ActivityUpdate(ApiModel):
    """Partial update. The parent (lead_id/opportunity_id) is immutable (an activity stays attached
    to
    its parent) and ``status`` / ``completed_date`` move via the complete/cancel actions, so all
    three
    are absent here. A changed ``owner_employee_id`` is re-validated."""

    activity_type: ActivityType | None = None
    subject: str | None = None
    description: str | None = None
    due_date: date | None = None
    owner_employee_id: uuid.UUID | None = None


class ActivityRead(ApiModel):
    id: uuid.UUID
    activity_type: ActivityType
    status: ActivityStatus
    subject: str
    description: str | None
    due_date: date | None
    completed_date: date | None
    lead_id: uuid.UUID | None
    opportunity_id: uuid.UUID | None
    owner_employee_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class ActivityFilter(ApiModel):
    """List filters for the activities endpoint. ``lead_id`` / ``opportunity_id`` scope to one
    parent; ``status`` narrows the lifecycle. None means "no constraint"."""

    status: ActivityStatus | None = None
    lead_id: uuid.UUID | None = None
    opportunity_id: uuid.UUID | None = None


class CompleteActivity(ApiModel):
    """Complete an OPEN activity (PLAN 12.1): mark COMPLETED + stamp ``completed_date`` (optional —
    defaults to today)."""

    completed_date: date | None = None


# --- Kanban board (D-057) -----------------------------------------------------


class KanbanColumn(ApiModel):
    """One column of the opportunity kanban board: a stage + the opportunities currently in it (the
    cards), ordered newest first, plus the column's count and total estimated value (the column
    summary the board header shows)."""

    stage: OpportunityStage
    count: int
    total_estimated_value: Decimal
    opportunities: list[OpportunityRead]


class KanbanBoard(ApiModel):
    """The opportunity KANBAN BOARD (PLAN 12.1, D-057): opportunities grouped into a column per
    stage,
    in the declared stage order (open columns then WON/LOST). A BOUNDED view (PERFORMANCE §6): one
    query loads the opportunities, grouped in memory; each column is capped so the board never
    returns
    an unbounded set (``column_limit`` echoes the per-column cap applied)."""

    column_limit: int
    columns: list[KanbanColumn]
