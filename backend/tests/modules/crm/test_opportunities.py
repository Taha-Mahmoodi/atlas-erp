"""Opportunity CRUD + lines + the kanban move-stage + the kanban board at the SERVICE layer (PLAN
12.1, D-057).

The service owns every rule (CLAUDE.md rule 7): a gapless OPP- number + core_documents registration,
owner/customer/currency/item validation, the kanban move-stage transitions (any open → any open, or
→
WON/LOST; terminal stages frozen), and the kanban board grouping by stage. Service-level tests run
under the tenant context (D-025); the API surface is exercised in test_crm_api.py.
"""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.tenancy import tenant_context
from app.modules.crm import service
from app.modules.crm.constants import KANBAN_STAGE_ORDER, OpportunityStage
from app.modules.crm.schemas import (
    OpportunityCreate,
    OpportunityLineCreate,
    OpportunityUpdate,
)
from tests.modules.crm.conftest import CrmSetup
from tests.modules.crm.factories import build_opportunity, build_opportunity_with_line

pytestmark = pytest.mark.asyncio


async def test_create_opportunity_with_lines(
    db_session: AsyncSession, crm_setup: CrmSetup
) -> None:
    with tenant_context(crm_setup.tenant_id):
        opportunity = await service.create_opportunity(
            db_session,
            crm_setup.tenant_id,
            OpportunityCreate(
                name="Deal",
                company_name="Prospect",
                currency_code="USD",
                estimated_value=Decimal("9000"),
                lines=[
                    OpportunityLineCreate(
                        item_id=crm_setup.item_id,
                        quantity=Decimal("2"),
                        estimated_unit_price=Decimal("150"),
                    )
                ],
            ),
        )
        await db_session.commit()
        lines = await service.get_opportunity_lines(
            db_session, crm_setup.tenant_id, opportunity.id
        )
    assert opportunity.opportunity_number.startswith("OPP-")
    assert opportunity.stage == OpportunityStage.PROSPECTING.value
    assert len(lines) == 1
    assert lines[0].item_id == crm_setup.item_id
    assert lines[0].quantity == Decimal("2")


async def test_create_opportunity_unknown_item_rejected(
    db_session: AsyncSession, crm_setup: CrmSetup
) -> None:
    with tenant_context(crm_setup.tenant_id), pytest.raises(ValidationFailedError) as exc:
        await service.create_opportunity(
            db_session,
            crm_setup.tenant_id,
            OpportunityCreate(
                name="Deal",
                company_name="Prospect",
                currency_code="USD",
                lines=[
                    OpportunityLineCreate(
                        item_id=uuid.uuid4(),
                        quantity=Decimal("1"),
                        estimated_unit_price=Decimal("1"),
                    )
                ],
            ),
        )
    assert exc.value.code == "crm.item_not_found"


async def test_create_opportunity_unknown_customer_rejected(
    db_session: AsyncSession, crm_setup: CrmSetup
) -> None:
    with tenant_context(crm_setup.tenant_id), pytest.raises(ValidationFailedError) as exc:
        await service.create_opportunity(
            db_session,
            crm_setup.tenant_id,
            OpportunityCreate(
                name="Deal",
                company_name="P",
                currency_code="USD",
                customer_id=uuid.uuid4(),
            ),
        )
    assert exc.value.code == "crm.customer_not_found"


async def test_update_replaces_lines(db_session: AsyncSession, crm_setup: CrmSetup) -> None:
    opportunity = await build_opportunity_with_line(db_session, crm_setup.tenant_id, crm_setup)
    with tenant_context(crm_setup.tenant_id):
        await service.update_opportunity(
            db_session,
            crm_setup.tenant_id,
            opportunity.id,
            OpportunityUpdate(
                lines=[
                    OpportunityLineCreate(
                        item_id=crm_setup.item_id,
                        quantity=Decimal("5"),
                        estimated_unit_price=Decimal("10"),
                    ),
                    OpportunityLineCreate(
                        item_id=crm_setup.item_id,
                        quantity=Decimal("1"),
                        estimated_unit_price=Decimal("20"),
                    ),
                ]
            ),
        )
        await db_session.commit()
        lines = await service.get_opportunity_lines(
            db_session, crm_setup.tenant_id, opportunity.id
        )
    assert [line.line_number for line in lines] == [1, 2]
    assert lines[0].quantity == Decimal("5")


async def test_move_stage_open_to_open(db_session: AsyncSession, crm_setup: CrmSetup) -> None:
    opportunity = await build_opportunity(db_session, crm_setup.tenant_id)
    with tenant_context(crm_setup.tenant_id):
        moved = await service.move_stage(
            db_session, crm_setup.tenant_id, opportunity.id, OpportunityStage.PROPOSAL
        )
        await db_session.commit()
    assert moved.stage == OpportunityStage.PROPOSAL.value


async def test_move_stage_to_lost_is_terminal(
    db_session: AsyncSession, crm_setup: CrmSetup
) -> None:
    opportunity = await build_opportunity(db_session, crm_setup.tenant_id)
    with tenant_context(crm_setup.tenant_id):
        await service.move_stage(
            db_session, crm_setup.tenant_id, opportunity.id, OpportunityStage.LOST
        )
        await db_session.commit()
        with pytest.raises(ConflictError) as exc:
            await service.move_stage(
                db_session, crm_setup.tenant_id, opportunity.id, OpportunityStage.PROPOSAL
            )
    assert exc.value.code == "crm.opportunity_stage_terminal"


async def test_move_stage_same_stage_rejected(
    db_session: AsyncSession, crm_setup: CrmSetup
) -> None:
    opportunity = await build_opportunity(db_session, crm_setup.tenant_id)
    with tenant_context(crm_setup.tenant_id), pytest.raises(ConflictError) as exc:
        await service.move_stage(
            db_session, crm_setup.tenant_id, opportunity.id, OpportunityStage.PROSPECTING
        )
    assert exc.value.code == "crm.opportunity_stage_unchanged"


async def test_update_closed_opportunity_rejected(
    db_session: AsyncSession, crm_setup: CrmSetup
) -> None:
    opportunity = await build_opportunity(db_session, crm_setup.tenant_id)
    with tenant_context(crm_setup.tenant_id):
        await service.move_stage(
            db_session, crm_setup.tenant_id, opportunity.id, OpportunityStage.WON
        )
        await db_session.commit()
        with pytest.raises(ConflictError) as exc:
            await service.update_opportunity(
                db_session, crm_setup.tenant_id, opportunity.id, OpportunityUpdate(name="X")
            )
    assert exc.value.code == "crm.opportunity_closed"


async def test_kanban_board_groups_by_stage(
    db_session: AsyncSession, crm_setup: CrmSetup
) -> None:
    """THE kanban test: the board returns a column per stage and the cards land in their stage."""
    prospecting = await build_opportunity(db_session, crm_setup.tenant_id, name="P")
    proposal = await build_opportunity(db_session, crm_setup.tenant_id, name="Q")
    with tenant_context(crm_setup.tenant_id):
        await service.move_stage(
            db_session, crm_setup.tenant_id, proposal.id, OpportunityStage.PROPOSAL
        )
        await db_session.commit()
        board = await service.kanban_board(db_session, crm_setup.tenant_id)
    # Every stage is a column (empty ones included), in the declared order.
    assert list(board.keys()) == list(KANBAN_STAGE_ORDER)
    assert [o.id for o in board[OpportunityStage.PROSPECTING]] == [prospecting.id]
    assert [o.id for o in board[OpportunityStage.PROPOSAL]] == [proposal.id]
    assert board[OpportunityStage.WON] == []


async def test_get_missing_opportunity_404(
    db_session: AsyncSession, crm_setup: CrmSetup
) -> None:
    with tenant_context(crm_setup.tenant_id), pytest.raises(NotFoundError) as exc:
        await service.get_opportunity(db_session, crm_setup.tenant_id, uuid.uuid4())
    assert exc.value.code == "crm.opportunity_not_found"


async def test_list_opportunities_filtered_by_stage(
    db_session: AsyncSession, crm_setup: CrmSetup
) -> None:
    await build_opportunity(db_session, crm_setup.tenant_id, name="A")
    proposal = await build_opportunity(db_session, crm_setup.tenant_id, name="B")
    with tenant_context(crm_setup.tenant_id):
        await service.move_stage(
            db_session, crm_setup.tenant_id, proposal.id, OpportunityStage.PROPOSAL
        )
        await db_session.commit()
        from app.modules.crm.schemas import OpportunityFilter

        page = await service.list_opportunities(
            db_session,
            crm_setup.tenant_id,
            filters=OpportunityFilter(stage=OpportunityStage.PROPOSAL),
        )
    assert {o.id for o in page.items} == {proposal.id}
