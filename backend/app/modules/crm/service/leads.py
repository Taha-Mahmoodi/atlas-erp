"""Lead business logic (PLAN 12.1, D-057): lead CRUD, qualify/disqualify transitions, and
convert-to-opportunity.

The service layer owns every rule (CLAUDE.md rule 7); the router stays thin. A lead claims its
gapless
LEAD- number at creation (D-040). ``qualify``/``disqualify`` are the status transitions
(NEW/CONTACTED
→ QUALIFIED/DISQUALIFIED). ``convert_lead_to_opportunity`` creates an ``Opportunity`` from a
QUALIFIED
lead, copies the company/contact/value, links ``source_lead_id``, and sets the lead's
``converted_opportunity_id`` + status CONVERTED — the lead → opportunity link (the opportunity is
built
through the opportunity service so its OPP- number + core_documents registration happen
identically).

``from __future__ import annotations`` keeps ``Page[Lead]`` (the ORM model) a string at import; the
router re-validates page items.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.pagination import DEFAULT_LIMIT, OrderKey, SortDirection, filter_fingerprint, paginate
from app.core.schemas import Page
from app.modules.crm.constants import (
    LEAD_NUMBER_PADDING,
    LEAD_NUMBER_PREFIX,
    LEAD_SEQUENCE_NAME,
    LeadStatus,
)
from app.modules.crm.models import Lead, Opportunity
from app.modules.crm.schemas import ConvertLead, LeadCreate, LeadFilter, LeadUpdate
from app.modules.crm.service._shared import (
    claim_lead_or_opportunity_number,
    validate_currency,
    validate_owner,
)
from app.modules.crm.service.opportunities import create_opportunity_from_lead


async def get_lead(session: AsyncSession, tenant_id: uuid.UUID, lead_id: uuid.UUID) -> Lead:
    lead = await session.get(Lead, lead_id)
    if lead is None or lead.tenant_id != tenant_id:
        raise NotFoundError(message="Lead not found", code="crm.lead_not_found")
    return lead


async def _validate_value_currency(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    estimated_value,
    currency_code: str | None,
) -> None:
    """A lead's estimated value needs a currency, and that currency must exist in finance (D-029). A
    value with no currency is rejected; a currency is validated only when supplied."""
    if estimated_value is not None and currency_code is None:
        raise ValidationFailedError(
            message="An estimated value needs a currency code",
            code="crm.currency_required",
        )
    if currency_code is not None:
        await validate_currency(session, tenant_id, currency_code)


async def create_lead(
    session: AsyncSession, tenant_id: uuid.UUID, payload: LeadCreate
) -> Lead:
    """Create a lead (PLAN 12.1). Validates the owner (if set) exists in hr and the value/currency
    pair; claims the gapless LEAD- number at creation. ``status`` defaults to NEW."""
    await validate_owner(session, tenant_id, payload.owner_employee_id)
    await _validate_value_currency(
        session, tenant_id, payload.estimated_value, payload.currency_code
    )
    number = await claim_lead_or_opportunity_number(
        session,
        tenant_id,
        sequence_name=LEAD_SEQUENCE_NAME,
        prefix=LEAD_NUMBER_PREFIX,
        padding=LEAD_NUMBER_PADDING,
        on_date=date.today(),
    )
    lead = Lead(
        tenant_id=tenant_id,
        lead_number=number,
        # ApiModel use_enum_values=True, so the payload enum is already its string value.
        status=payload.status,
        company_name=payload.company_name,
        contact_name=payload.contact_name,
        email=payload.email,
        phone=payload.phone,
        source=payload.source,
        estimated_value=payload.estimated_value,
        currency_code=payload.currency_code,
        owner_employee_id=payload.owner_employee_id,
        notes=payload.notes,
    )
    session.add(lead)
    await session.flush()
    return lead


async def update_lead(
    session: AsyncSession, tenant_id: uuid.UUID, lead_id: uuid.UUID, payload: LeadUpdate
) -> Lead:
    """Partial update of a lead (D-010: mutate the loaded object so the audit diff is captured). The
    status transitions via qualify/disqualify (not a free edit), so it is absent here. A converted
    lead is immutable (it has become an opportunity). A changed owner is re-validated; a changed
    value/currency pair is re-validated."""
    lead = await get_lead(session, tenant_id, lead_id)
    if LeadStatus(lead.status) == LeadStatus.CONVERTED:
        raise ConflictError(
            message="A converted lead cannot be edited",
            code="crm.lead_converted",
            details={"status": lead.status},
        )
    data = payload.model_dump(exclude_unset=True)
    if "owner_employee_id" in data:
        await validate_owner(session, tenant_id, data["owner_employee_id"])
    # Re-validate the value/currency pair against the MERGED state (a partial update may set only
    # one).
    new_value = data.get("estimated_value", lead.estimated_value)
    new_currency = data.get("currency_code", lead.currency_code)
    await _validate_value_currency(session, tenant_id, new_value, new_currency)
    for field, value in data.items():
        setattr(lead, field, value)
    await session.flush()
    return lead


async def qualify_lead(
    session: AsyncSession, tenant_id: uuid.UUID, lead_id: uuid.UUID
) -> Lead:
    """Mark a lead QUALIFIED (PLAN 12.1): allowed from NEW/CONTACTED. A QUALIFIED lead may convert
    to
    an opportunity. Already-qualified is a no-op-friendly conflict; a CONVERTED/DISQUALIFIED lead
    cannot be (re)qualified."""
    lead = await get_lead(session, tenant_id, lead_id)
    if LeadStatus(lead.status) not in (LeadStatus.NEW, LeadStatus.CONTACTED):
        raise ConflictError(
            message=f"A {lead.status} lead cannot be qualified",
            code="crm.lead_not_qualifiable",
            details={"status": lead.status},
        )
    lead.status = LeadStatus.QUALIFIED.value
    await session.flush()
    return lead


async def disqualify_lead(
    session: AsyncSession, tenant_id: uuid.UUID, lead_id: uuid.UUID
) -> Lead:
    """Mark a lead DISQUALIFIED (PLAN 12.1): allowed from any OPEN status (NEW/CONTACTED/QUALIFIED).
    A
    CONVERTED lead cannot be disqualified (it is already an opportunity)."""
    lead = await get_lead(session, tenant_id, lead_id)
    if LeadStatus(lead.status) in (LeadStatus.CONVERTED, LeadStatus.DISQUALIFIED):
        raise ConflictError(
            message=f"A {lead.status} lead cannot be disqualified",
            code="crm.lead_not_disqualifiable",
            details={"status": lead.status},
        )
    lead.status = LeadStatus.DISQUALIFIED.value
    await session.flush()
    return lead


async def convert_lead_to_opportunity(
    session: AsyncSession, tenant_id: uuid.UUID, lead_id: uuid.UUID, payload: ConvertLead
) -> Opportunity:
    """Convert a QUALIFIED lead into a DRAFT opportunity (PLAN 12.1, D-057). Only a QUALIFIED lead
    can
    convert. Builds the opportunity from the lead (company/contact/email/value/currency copied),
    links ``source_lead_id``, and sets the lead's ``converted_opportunity_id`` + status CONVERTED.

    The opportunity is created through the opportunity service so its OPP- number + core_documents
    registration happen identically to a directly-created opportunity. A lead with no currency
    cannot
    convert (the opportunity needs a currency) — rejected with a friendly 422."""
    lead = await get_lead(session, tenant_id, lead_id)
    if LeadStatus(lead.status) != LeadStatus.QUALIFIED:
        raise ConflictError(
            message="Only a qualified lead can be converted to an opportunity",
            code="crm.lead_not_convertible",
            details={"status": lead.status},
        )
    if lead.currency_code is None:
        raise ValidationFailedError(
            message="The lead has no currency; set one before converting",
            code="crm.lead_currency_missing",
        )
    opportunity = await create_opportunity_from_lead(
        session,
        tenant_id,
        lead=lead,
        name=payload.name or lead.company_name,
        expected_close_date=payload.expected_close_date,
        probability_percent=payload.probability_percent,
        notes=payload.notes,
    )
    lead.converted_opportunity_id = opportunity.id
    lead.status = LeadStatus.CONVERTED.value
    await session.flush()
    return opportunity


async def list_leads(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    filters: LeadFilter,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Page[Lead]:
    """Keyset-paginated leads, newest first (D-014). The status filter narrows the set (index-served
    by (tenant, status)) and folds into the cursor fingerprint so a cursor cannot bleed across
    views."""
    stmt = select(Lead).where(Lead.tenant_id == tenant_id)
    if filters.status is not None:
        stmt = stmt.where(Lead.status == LeadStatus(filters.status).value)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(Lead.created_at, SortDirection.DESC)],
        pk=Lead.id,
        cursor=cursor,
        limit=limit,
        filters=filter_fingerprint(filters.status),
    )
