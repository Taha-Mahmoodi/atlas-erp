"""Activity CRUD + the exactly-one-parent rule + complete/cancel at the SERVICE layer (PLAN 12.1,
D-057).

The service owns every rule (CLAUDE.md rule 7): exactly-one-parent (lead XOR opportunity, both
existing), owner validation, and the OPEN→COMPLETED/CANCELLED transitions. Service-level tests run
under the tenant context (D-025); the API surface is exercised in test_crm_api.py.
"""

import uuid
from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.tenancy import tenant_context
from app.modules.crm import service
from app.modules.crm.constants import ActivityStatus, ActivityType
from app.modules.crm.schemas import ActivityCreate, ActivityUpdate
from tests.modules.crm.conftest import CrmSetup
from tests.modules.crm.factories import build_activity, build_lead, build_opportunity

pytestmark = pytest.mark.asyncio


async def test_create_activity_against_lead(
    db_session: AsyncSession, crm_setup: CrmSetup
) -> None:
    lead = await build_lead(db_session, crm_setup.tenant_id)
    with tenant_context(crm_setup.tenant_id):
        activity = await service.create_activity(
            db_session,
            crm_setup.tenant_id,
            ActivityCreate(
                activity_type=ActivityType.CALL, subject="Intro call", lead_id=lead.id
            ),
        )
        await db_session.commit()
    assert activity.status == ActivityStatus.OPEN.value
    assert activity.lead_id == lead.id
    assert activity.opportunity_id is None


async def test_create_activity_against_opportunity(
    db_session: AsyncSession, crm_setup: CrmSetup
) -> None:
    opportunity = await build_opportunity(db_session, crm_setup.tenant_id)
    with tenant_context(crm_setup.tenant_id):
        activity = await service.create_activity(
            db_session,
            crm_setup.tenant_id,
            ActivityCreate(
                activity_type=ActivityType.MEETING,
                subject="Demo",
                opportunity_id=opportunity.id,
            ),
        )
        await db_session.commit()
    assert activity.opportunity_id == opportunity.id
    assert activity.lead_id is None


async def test_create_activity_no_parent_rejected(
    db_session: AsyncSession, crm_setup: CrmSetup
) -> None:
    with tenant_context(crm_setup.tenant_id), pytest.raises(ValidationFailedError) as exc:
        await service.create_activity(
            db_session,
            crm_setup.tenant_id,
            ActivityCreate(activity_type=ActivityType.NOTE, subject="Orphan"),
        )
    assert exc.value.code == "crm.activity_parent_invalid"


async def test_create_activity_both_parents_rejected(
    db_session: AsyncSession, crm_setup: CrmSetup
) -> None:
    lead = await build_lead(db_session, crm_setup.tenant_id)
    opportunity = await build_opportunity(db_session, crm_setup.tenant_id)
    with tenant_context(crm_setup.tenant_id), pytest.raises(ValidationFailedError) as exc:
        await service.create_activity(
            db_session,
            crm_setup.tenant_id,
            ActivityCreate(
                activity_type=ActivityType.TASK,
                subject="Both",
                lead_id=lead.id,
                opportunity_id=opportunity.id,
            ),
        )
    assert exc.value.code == "crm.activity_parent_invalid"


async def test_create_activity_unknown_lead_rejected(
    db_session: AsyncSession, crm_setup: CrmSetup
) -> None:
    with tenant_context(crm_setup.tenant_id), pytest.raises(ValidationFailedError) as exc:
        await service.create_activity(
            db_session,
            crm_setup.tenant_id,
            ActivityCreate(
                activity_type=ActivityType.CALL, subject="X", lead_id=uuid.uuid4()
            ),
        )
    assert exc.value.code == "crm.lead_not_found"


async def test_create_completed_note_stamps_date(
    db_session: AsyncSession, crm_setup: CrmSetup
) -> None:
    lead = await build_lead(db_session, crm_setup.tenant_id)
    with tenant_context(crm_setup.tenant_id):
        activity = await service.create_activity(
            db_session,
            crm_setup.tenant_id,
            ActivityCreate(
                activity_type=ActivityType.NOTE,
                subject="Logged",
                status=ActivityStatus.COMPLETED,
                lead_id=lead.id,
            ),
        )
        await db_session.commit()
    assert activity.status == ActivityStatus.COMPLETED.value
    assert activity.completed_date is not None


async def test_complete_activity(db_session: AsyncSession, crm_setup: CrmSetup) -> None:
    lead = await build_lead(db_session, crm_setup.tenant_id)
    activity = await build_activity(db_session, crm_setup.tenant_id, lead_id=lead.id)
    with tenant_context(crm_setup.tenant_id):
        completed = await service.complete_activity(
            db_session, crm_setup.tenant_id, activity.id, completed_date=date(2026, 6, 1)
        )
        await db_session.commit()
    assert completed.status == ActivityStatus.COMPLETED.value
    assert completed.completed_date == date(2026, 6, 1)


async def test_cancel_activity(db_session: AsyncSession, crm_setup: CrmSetup) -> None:
    lead = await build_lead(db_session, crm_setup.tenant_id)
    activity = await build_activity(db_session, crm_setup.tenant_id, lead_id=lead.id)
    with tenant_context(crm_setup.tenant_id):
        cancelled = await service.cancel_activity(db_session, crm_setup.tenant_id, activity.id)
        await db_session.commit()
    assert cancelled.status == ActivityStatus.CANCELLED.value


async def test_complete_already_completed_rejected(
    db_session: AsyncSession, crm_setup: CrmSetup
) -> None:
    lead = await build_lead(db_session, crm_setup.tenant_id)
    activity = await build_activity(db_session, crm_setup.tenant_id, lead_id=lead.id)
    with tenant_context(crm_setup.tenant_id):
        await service.complete_activity(db_session, crm_setup.tenant_id, activity.id)
        await db_session.commit()
        with pytest.raises(ConflictError) as exc:
            await service.complete_activity(db_session, crm_setup.tenant_id, activity.id)
    assert exc.value.code == "crm.activity_not_completable"


async def test_update_terminal_activity_rejected(
    db_session: AsyncSession, crm_setup: CrmSetup
) -> None:
    lead = await build_lead(db_session, crm_setup.tenant_id)
    activity = await build_activity(db_session, crm_setup.tenant_id, lead_id=lead.id)
    with tenant_context(crm_setup.tenant_id):
        await service.cancel_activity(db_session, crm_setup.tenant_id, activity.id)
        await db_session.commit()
        with pytest.raises(ConflictError) as exc:
            await service.update_activity(
                db_session,
                crm_setup.tenant_id,
                activity.id,
                ActivityUpdate(subject="X"),
            )
    assert exc.value.code == "crm.activity_not_open"


async def test_get_missing_activity_404(
    db_session: AsyncSession, crm_setup: CrmSetup
) -> None:
    with tenant_context(crm_setup.tenant_id), pytest.raises(NotFoundError) as exc:
        await service.get_activity(db_session, crm_setup.tenant_id, uuid.uuid4())
    assert exc.value.code == "crm.activity_not_found"


async def test_list_activities_scoped_to_parent(
    db_session: AsyncSession, crm_setup: CrmSetup
) -> None:
    lead = await build_lead(db_session, crm_setup.tenant_id)
    opportunity = await build_opportunity(db_session, crm_setup.tenant_id)
    await build_activity(db_session, crm_setup.tenant_id, lead_id=lead.id, subject="L")
    await build_activity(
        db_session, crm_setup.tenant_id, opportunity_id=opportunity.id, subject="O"
    )
    with tenant_context(crm_setup.tenant_id):
        from app.modules.crm.schemas import ActivityFilter

        page = await service.list_activities(
            db_session, crm_setup.tenant_id, filters=ActivityFilter(lead_id=lead.id)
        )
    assert {a.subject for a in page.items} == {"L"}
