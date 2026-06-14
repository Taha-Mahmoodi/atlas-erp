"""Lead CRUD + qualify/disqualify + convert-to-opportunity at the SERVICE layer (PLAN 12.1, D-057).

The service owns every rule (CLAUDE.md rule 7): a gapless LEAD- number, owner/value-currency
validation, the NEW→CONTACTED→QUALIFIED→CONVERTED/DISQUALIFIED transitions, and the lead →
opportunity
convert (links + status). Service-level tests run under the tenant context (D-025); the API surface
is
exercised in test_crm_api.py.
"""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.tenancy import tenant_context
from app.modules.crm import service
from app.modules.crm.constants import LeadStatus, OpportunityStage
from app.modules.crm.schemas import ConvertLead, LeadCreate, LeadUpdate
from tests.modules.crm.conftest import CrmSetup
from tests.modules.crm.factories import build_lead

pytestmark = pytest.mark.asyncio


async def test_create_lead_claims_number_and_defaults(
    db_session: AsyncSession, crm_setup: CrmSetup
) -> None:
    with tenant_context(crm_setup.tenant_id):
        lead = await service.create_lead(
            db_session,
            crm_setup.tenant_id,
            LeadCreate(company_name="Acme", estimated_value=Decimal("1000"), currency_code="USD"),
        )
        await db_session.commit()
    assert lead.lead_number.startswith("LEAD-")
    assert lead.status == LeadStatus.NEW.value
    assert lead.company_name == "Acme"


async def test_create_lead_value_without_currency_rejected(
    db_session: AsyncSession, crm_setup: CrmSetup
) -> None:
    with tenant_context(crm_setup.tenant_id), pytest.raises(ValidationFailedError) as exc:
        await service.create_lead(
            db_session,
            crm_setup.tenant_id,
            LeadCreate(company_name="Acme", estimated_value=Decimal("1000")),
        )
    assert exc.value.code == "crm.currency_required"


async def test_create_lead_unknown_owner_rejected(
    db_session: AsyncSession, crm_setup: CrmSetup
) -> None:
    with tenant_context(crm_setup.tenant_id), pytest.raises(ValidationFailedError) as exc:
        await service.create_lead(
            db_session,
            crm_setup.tenant_id,
            LeadCreate(company_name="Acme", owner_employee_id=uuid.uuid4()),
        )
    assert exc.value.code == "crm.owner_not_found"


async def test_create_lead_unknown_currency_rejected(
    db_session: AsyncSession, crm_setup: CrmSetup
) -> None:
    with tenant_context(crm_setup.tenant_id), pytest.raises(ValidationFailedError) as exc:
        await service.create_lead(
            db_session,
            crm_setup.tenant_id,
            LeadCreate(company_name="Acme", estimated_value=Decimal("1"), currency_code="ZZZ"),
        )
    assert exc.value.code == "crm.currency_not_found"


async def test_update_lead_mutates_loaded_object(
    db_session: AsyncSession, crm_setup: CrmSetup
) -> None:
    lead = await build_lead(db_session, crm_setup.tenant_id)
    with tenant_context(crm_setup.tenant_id):
        updated = await service.update_lead(
            db_session,
            crm_setup.tenant_id,
            lead.id,
            LeadUpdate(company_name="Renamed", contact_name="Jane"),
        )
        await db_session.commit()
    assert updated.company_name == "Renamed"
    assert updated.contact_name == "Jane"


async def test_qualify_then_convert_links_and_sets_status(
    db_session: AsyncSession, crm_setup: CrmSetup
) -> None:
    """THE lead-pipeline test: qualify → convert creates the opportunity, links source_lead_id, and
    sets the lead's converted_opportunity_id + status CONVERTED."""
    lead = await build_lead(
        db_session, crm_setup.tenant_id, owner_employee_id=crm_setup.employee_id
    )
    with tenant_context(crm_setup.tenant_id):
        await service.qualify_lead(db_session, crm_setup.tenant_id, lead.id)
        opportunity = await service.convert_lead_to_opportunity(
            db_session, crm_setup.tenant_id, lead.id, ConvertLead()
        )
        await db_session.commit()
        refreshed = await service.get_lead(db_session, crm_setup.tenant_id, lead.id)
    assert opportunity.opportunity_number.startswith("OPP-")
    assert opportunity.stage == OpportunityStage.PROSPECTING.value
    assert opportunity.source_lead_id == lead.id
    assert opportunity.company_name == lead.company_name
    assert opportunity.currency_code == "USD"
    assert opportunity.owner_employee_id == crm_setup.employee_id
    assert refreshed.status == LeadStatus.CONVERTED.value
    assert refreshed.converted_opportunity_id == opportunity.id


async def test_convert_unqualified_lead_rejected(
    db_session: AsyncSession, crm_setup: CrmSetup
) -> None:
    lead = await build_lead(db_session, crm_setup.tenant_id)
    with tenant_context(crm_setup.tenant_id), pytest.raises(ConflictError) as exc:
        await service.convert_lead_to_opportunity(
            db_session, crm_setup.tenant_id, lead.id, ConvertLead()
        )
    assert exc.value.code == "crm.lead_not_convertible"


async def test_convert_lead_without_currency_rejected(
    db_session: AsyncSession, crm_setup: CrmSetup
) -> None:
    lead = await build_lead(
        db_session, crm_setup.tenant_id, estimated_value=None, currency_code=None
    )
    with tenant_context(crm_setup.tenant_id):
        await service.qualify_lead(db_session, crm_setup.tenant_id, lead.id)
        with pytest.raises(ValidationFailedError) as exc:
            await service.convert_lead_to_opportunity(
                db_session, crm_setup.tenant_id, lead.id, ConvertLead()
            )
    assert exc.value.code == "crm.lead_currency_missing"


async def test_qualify_already_converted_rejected(
    db_session: AsyncSession, crm_setup: CrmSetup
) -> None:
    lead = await build_lead(db_session, crm_setup.tenant_id)
    with tenant_context(crm_setup.tenant_id):
        await service.qualify_lead(db_session, crm_setup.tenant_id, lead.id)
        await service.convert_lead_to_opportunity(
            db_session, crm_setup.tenant_id, lead.id, ConvertLead()
        )
        await db_session.commit()
        with pytest.raises(ConflictError) as exc:
            await service.qualify_lead(db_session, crm_setup.tenant_id, lead.id)
    assert exc.value.code == "crm.lead_not_qualifiable"


async def test_disqualify_lead(db_session: AsyncSession, crm_setup: CrmSetup) -> None:
    lead = await build_lead(db_session, crm_setup.tenant_id)
    with tenant_context(crm_setup.tenant_id):
        disqualified = await service.disqualify_lead(db_session, crm_setup.tenant_id, lead.id)
        await db_session.commit()
    assert disqualified.status == LeadStatus.DISQUALIFIED.value


async def test_update_converted_lead_rejected(
    db_session: AsyncSession, crm_setup: CrmSetup
) -> None:
    lead = await build_lead(db_session, crm_setup.tenant_id)
    with tenant_context(crm_setup.tenant_id):
        await service.qualify_lead(db_session, crm_setup.tenant_id, lead.id)
        await service.convert_lead_to_opportunity(
            db_session, crm_setup.tenant_id, lead.id, ConvertLead()
        )
        await db_session.commit()
        with pytest.raises(ConflictError) as exc:
            await service.update_lead(
                db_session, crm_setup.tenant_id, lead.id, LeadUpdate(company_name="X")
            )
    assert exc.value.code == "crm.lead_converted"


async def test_get_missing_lead_404(db_session: AsyncSession, crm_setup: CrmSetup) -> None:
    with tenant_context(crm_setup.tenant_id), pytest.raises(NotFoundError) as exc:
        await service.get_lead(db_session, crm_setup.tenant_id, uuid.uuid4())
    assert exc.value.code == "crm.lead_not_found"


async def test_list_leads_filtered_by_status(
    db_session: AsyncSession, crm_setup: CrmSetup
) -> None:
    await build_lead(db_session, crm_setup.tenant_id, company_name="A")
    qualified = await build_lead(db_session, crm_setup.tenant_id, company_name="B")
    with tenant_context(crm_setup.tenant_id):
        await service.qualify_lead(db_session, crm_setup.tenant_id, qualified.id)
        await db_session.commit()
        from app.modules.crm.schemas import LeadFilter

        page = await service.list_leads(
            db_session, crm_setup.tenant_id, filters=LeadFilter(status=LeadStatus.QUALIFIED)
        )
    statuses = {lead.status for lead in page.items}
    assert statuses == {LeadStatus.QUALIFIED.value}
