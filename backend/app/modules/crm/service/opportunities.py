"""Opportunity business logic (PLAN 12.1, D-057): opportunity CRUD + lines, the kanban move-stage,
the kanban board, and the from-lead builder.

The service layer owns every rule (CLAUDE.md rule 7); the router stays thin. An opportunity
registers
in core_documents (so the convert handler can write the convert docflow edges) and claims its
gapless
OPP- number at creation (D-040). ``move_stage`` is the kanban move (validated transitions: any open
stage → any open stage, or → WON/LOST; a terminal stage cannot move). ``kanban_board`` groups the
opportunities into a column per stage (ONE bounded query, grouped in memory — PERFORMANCE §6). Lines
(optional expected products) are validated (item exists, quantity > 0, price >= 0) and become the
quote
lines on convert.

``from __future__ import annotations`` keeps ``Page[Opportunity]`` a string at import.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.core.exceptions import ConflictError, NotFoundError
from app.core.pagination import DEFAULT_LIMIT, OrderKey, SortDirection, filter_fingerprint, paginate
from app.core.schemas import Page
from app.modules.crm.constants import (
    KANBAN_STAGE_ORDER,
    OPPORTUNITY_DOC_TYPE,
    OPPORTUNITY_NUMBER_PADDING,
    OPPORTUNITY_NUMBER_PREFIX,
    OPPORTUNITY_SEQUENCE_NAME,
    TERMINAL_OPPORTUNITY_STAGES,
    OpportunityStage,
)
from app.modules.crm.models import Lead, Opportunity, OpportunityLine
from app.modules.crm.schemas import (
    OpportunityCreate,
    OpportunityFilter,
    OpportunityLineCreate,
    OpportunityUpdate,
)
from app.modules.crm.service._shared import (
    claim_lead_or_opportunity_number,
    validate_currency,
    validate_existing_customer,
    validate_item,
    validate_owner,
)

# Default per-column cap for the kanban board: a generous bound so a column never streams an
# unbounded
# set yet the board shows a full screen of cards (PERFORMANCE §6).
DEFAULT_KANBAN_COLUMN_LIMIT = 100


async def get_opportunity(
    session: AsyncSession, tenant_id: uuid.UUID, opportunity_id: uuid.UUID
) -> Opportunity:
    opportunity = await session.get(Opportunity, opportunity_id)
    if opportunity is None or opportunity.tenant_id != tenant_id:
        raise NotFoundError(
            message="Opportunity not found", code="crm.opportunity_not_found"
        )
    return opportunity


async def get_opportunity_lines(
    session: AsyncSession, tenant_id: uuid.UUID, opportunity_id: uuid.UUID
) -> list[OpportunityLine]:
    stmt = (
        select(OpportunityLine)
        .where(
            OpportunityLine.tenant_id == tenant_id,
            OpportunityLine.opportunity_id == opportunity_id,
        )
        .order_by(OpportunityLine.line_number)
    )
    return list((await session.execute(stmt)).scalars().all())


async def _validate_lines(
    session: AsyncSession, tenant_id: uuid.UUID, lines: list[OpportunityLineCreate]
) -> None:
    """Each opportunity line's item must exist (quantity > 0 / price >= 0 are schema-enforced + DB
    CHECKs); validated up front so a bad line is a friendly 422 before any write."""
    for line in lines:
        await validate_item(session, tenant_id, line.item_id)


def _write_lines(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    opportunity_id: uuid.UUID,
    lines: list[OpportunityLineCreate],
) -> None:
    for index, line in enumerate(lines, start=1):
        session.add(
            OpportunityLine(
                tenant_id=tenant_id,
                opportunity_id=opportunity_id,
                line_number=index,
                item_id=line.item_id,
                description=line.description,
                quantity=Decimal(str(line.quantity)),
                estimated_unit_price=Decimal(str(line.estimated_unit_price)),
            )
        )


async def _new_opportunity(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    name: str,
    company_name: str,
    contact_name: str | None,
    email: str | None,
    customer_id: uuid.UUID | None,
    currency_code: str,
    estimated_value: Decimal,
    probability_percent: Decimal | None,
    expected_close_date: date | None,
    owner_employee_id: uuid.UUID | None,
    notes: str | None,
    source_lead_id: uuid.UUID | None,
    lines: list[OpportunityLineCreate],
) -> Opportunity:
    """Build a DRAFT opportunity (stage PROSPECTING): register its core_documents entry, claim the
    gapless OPP- number, write the header + lines. Shared by the direct create and the from-lead
    convert. Assumes the caller has already validated owner/customer/currency/lines."""
    opportunity_id = uuid.uuid4()
    number = await claim_lead_or_opportunity_number(
        session,
        tenant_id,
        sequence_name=OPPORTUNITY_SEQUENCE_NAME,
        prefix=OPPORTUNITY_NUMBER_PREFIX,
        padding=OPPORTUNITY_NUMBER_PADDING,
        on_date=date.today(),
    )
    document = await docflow.register_document(
        session,
        tenant_id,
        OPPORTUNITY_DOC_TYPE,
        opportunity_id,
        doc_number=number,
        status=OpportunityStage.PROSPECTING.value,
    )
    opportunity = Opportunity(
        id=opportunity_id,
        tenant_id=tenant_id,
        document_id=document.id,
        opportunity_number=number,
        name=name,
        stage=OpportunityStage.PROSPECTING.value,
        source_lead_id=source_lead_id,
        customer_id=customer_id,
        company_name=company_name,
        contact_name=contact_name,
        email=email,
        estimated_value=estimated_value,
        currency_code=currency_code,
        probability_percent=probability_percent,
        expected_close_date=expected_close_date,
        owner_employee_id=owner_employee_id,
        notes=notes,
    )
    session.add(opportunity)
    _write_lines(session, tenant_id, opportunity_id, lines)
    await session.flush()
    return opportunity


async def create_opportunity(
    session: AsyncSession, tenant_id: uuid.UUID, payload: OpportunityCreate
) -> Opportunity:
    """Create a DRAFT opportunity (PLAN 12.1). Validates the owner (hr), the existing customer
    (sales,
    when set), the currency (finance) and each line's item (inventory); registers the document,
    claims
    the OPP- number, writes the header + lines."""
    await validate_owner(session, tenant_id, payload.owner_employee_id)
    await validate_existing_customer(session, tenant_id, payload.customer_id)
    await validate_currency(session, tenant_id, payload.currency_code)
    await _validate_lines(session, tenant_id, payload.lines)
    return await _new_opportunity(
        session,
        tenant_id,
        name=payload.name,
        company_name=payload.company_name,
        contact_name=payload.contact_name,
        email=payload.email,
        customer_id=payload.customer_id,
        currency_code=payload.currency_code,
        estimated_value=Decimal(str(payload.estimated_value)),
        probability_percent=payload.probability_percent,
        expected_close_date=payload.expected_close_date,
        owner_employee_id=payload.owner_employee_id,
        notes=payload.notes,
        source_lead_id=None,
        lines=payload.lines,
    )


async def create_opportunity_from_lead(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    lead: Lead,
    name: str,
    expected_close_date: date | None,
    probability_percent: Decimal | None,
    notes: str | None,
) -> Opportunity:
    """Build a DRAFT opportunity from a QUALIFIED lead (PLAN 12.1, D-057). Copies the lead's
    company/contact/email/value/currency; links ``source_lead_id``. The lead carries no expected
    products, so the opportunity starts with no lines (the operator adds them before converting, or
    the
    convert builds a single quote line from ``estimated_value``). The lead's owner carries over (it
    is
    already validated on the lead)."""
    return await _new_opportunity(
        session,
        tenant_id,
        name=name,
        company_name=lead.company_name,
        contact_name=lead.contact_name,
        email=lead.email,
        customer_id=None,
        currency_code=lead.currency_code,
        estimated_value=Decimal(str(lead.estimated_value or 0)),
        probability_percent=probability_percent,
        expected_close_date=expected_close_date,
        owner_employee_id=lead.owner_employee_id,
        notes=notes,
        source_lead_id=lead.id,
        lines=[],
    )


async def update_opportunity(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    opportunity_id: uuid.UUID,
    payload: OpportunityUpdate,
) -> Opportunity:
    """Partial header update of an OPEN opportunity (D-010: mutate the loaded object). The stage
    moves
    via move-stage (absent here). A WON/LOST opportunity is immutable (the deal is closed). When
    ``lines`` is supplied they are replaced wholesale (revalidated). A changed
    customer/currency/owner
    is re-validated."""
    opportunity = await get_opportunity(session, tenant_id, opportunity_id)
    if OpportunityStage(opportunity.stage) in TERMINAL_OPPORTUNITY_STAGES:
        raise ConflictError(
            message="A closed (won or lost) opportunity cannot be edited",
            code="crm.opportunity_closed",
            details={"stage": opportunity.stage},
        )
    data = payload.model_dump(exclude_unset=True)
    new_lines = data.pop("lines", None)
    if "owner_employee_id" in data:
        await validate_owner(session, tenant_id, data["owner_employee_id"])
    if "customer_id" in data:
        await validate_existing_customer(session, tenant_id, data["customer_id"])
    if data.get("currency_code") is not None:
        await validate_currency(session, tenant_id, data["currency_code"])
    else:
        data.pop("currency_code", None)
    for field, value in data.items():
        setattr(opportunity, field, value)
    if new_lines is not None:
        line_payloads = [OpportunityLineCreate.model_validate(line) for line in payload.lines]
        await _validate_lines(session, tenant_id, line_payloads)
        for existing in await get_opportunity_lines(session, tenant_id, opportunity_id):
            await session.delete(existing)
        await session.flush()
        _write_lines(session, tenant_id, opportunity_id, line_payloads)
    await session.flush()
    return opportunity


async def move_stage(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    opportunity_id: uuid.UUID,
    stage: OpportunityStage,
) -> Opportunity:
    """The KANBAN MOVE (PLAN 12.1, D-057): move an opportunity to ``stage``. Allowed: any OPEN stage
    →
    any OPEN stage (forward or backward — a deal can slip), or any OPEN stage → WON/LOST (closing
    it).
    A terminal stage (WON/LOST) cannot move (the deal is closed). Moving to the SAME stage is a
    no-op
    conflict. WON is normally reached via convert, but a manual move to WON is allowed (a deal can
    be
    won without a CRM-driven quote)."""
    opportunity = await get_opportunity(session, tenant_id, opportunity_id)
    current = OpportunityStage(opportunity.stage)
    target = OpportunityStage(stage)
    if current in TERMINAL_OPPORTUNITY_STAGES:
        raise ConflictError(
            message=f"A {current.value} opportunity is closed and cannot move stage",
            code="crm.opportunity_stage_terminal",
            details={"stage": current.value},
        )
    if target == current:
        raise ConflictError(
            message="The opportunity is already in that stage",
            code="crm.opportunity_stage_unchanged",
            details={"stage": current.value},
        )
    opportunity.stage = target.value
    await session.flush()
    await docflow.set_document_status(
        session, tenant_id, opportunity.document_id, status=target.value
    )
    return opportunity


async def list_opportunities(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    filters: OpportunityFilter,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Page[Opportunity]:
    """Keyset-paginated opportunities, newest first (D-014). The stage + owner filters narrow the
    set
    (index-served by (tenant, stage) / (tenant, owner_employee_id)) and fold into the cursor
    fingerprint."""
    stmt = select(Opportunity).where(Opportunity.tenant_id == tenant_id)
    if filters.stage is not None:
        stmt = stmt.where(Opportunity.stage == OpportunityStage(filters.stage).value)
    if filters.owner_employee_id is not None:
        stmt = stmt.where(Opportunity.owner_employee_id == filters.owner_employee_id)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(Opportunity.created_at, SortDirection.DESC)],
        pk=Opportunity.id,
        cursor=cursor,
        limit=limit,
        filters=filter_fingerprint(filters.stage, filters.owner_employee_id),
    )


async def kanban_board(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    owner_employee_id: uuid.UUID | None = None,
    column_limit: int = DEFAULT_KANBAN_COLUMN_LIMIT,
) -> dict[OpportunityStage, list[Opportunity]]:
    """The opportunity KANBAN board grouped by stage (PLAN 12.1, D-057): a dict of stage → its cards
    (newest first), one entry per stage in ``KANBAN_STAGE_ORDER`` (empty stages included). ONE
    bounded
    query loads the opportunities (optionally narrowed to one owner), grouped in memory (PERFORMANCE
    §6: no per-stage N+1); each column is sliced to ``column_limit``. The router builds the
    ``KanbanBoard`` response (counts + totals + the read schema) from this."""
    from app.modules.crm import queries as crm_queries

    rows = await crm_queries.opportunities_by_stage(
        session, tenant_id, owner_employee_id=owner_employee_id, per_stage_limit=column_limit
    )
    grouped: dict[OpportunityStage, list[Opportunity]] = {stage: [] for stage in KANBAN_STAGE_ORDER}
    for opportunity in rows:
        stage = OpportunityStage(opportunity.stage)
        column = grouped.setdefault(stage, [])
        if len(column) < column_limit:
            column.append(opportunity)
    return grouped


async def require_open_for_convert(opportunity: Opportunity) -> None:
    """Guard reused by the convert service: a WON/LOST opportunity cannot (re)convert — a converted
    (WON) opportunity is idempotent-rejected, a LOST deal is not convertible (D-057)."""
    if OpportunityStage(opportunity.stage) in TERMINAL_OPPORTUNITY_STAGES:
        raise ConflictError(
            message=f"A {opportunity.stage} opportunity cannot be converted",
            code="crm.opportunity_not_convertible",
            details={"stage": opportunity.stage},
        )
