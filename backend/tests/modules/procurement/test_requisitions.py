"""Purchase-requisition service tests (PLAN 6.2): CRUD, submit with approval-rule gating
(above-threshold needs approve / below auto-approves), approve/reject, cancel. Exercises the real
service layer under the tenant context (D-025).
"""

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.core.tenancy import tenant_context
from app.modules.procurement import service
from app.modules.procurement.constants import ApprovalDocumentType, RequisitionStatus
from app.modules.procurement.schemas import RequisitionCreate, RequisitionLineCreate
from tests.modules.procurement.conftest import ProcurementSetup
from tests.modules.procurement.factories import build_approval_rule, build_requisition


async def test_create_requisition_claims_number_and_draft(
    db_session: AsyncSession, procurement_setup: ProcurementSetup
) -> None:
    """A new requisition is DRAFT and carries a PR number claimed at creation (D-040)."""
    req = await build_requisition(
        db_session,
        procurement_setup.tenant_id,
        item_id=procurement_setup.item_id,
        uom_id=procurement_setup.uom_id,
    )
    assert req.status == RequisitionStatus.DRAFT.value
    assert req.requisition_number.startswith("PR-")


async def test_create_requisition_no_lines_422(
    db_session: AsyncSession, procurement_setup: ProcurementSetup
) -> None:
    from app.core.exceptions import ValidationFailedError

    with pytest.raises(ValidationFailedError), tenant_context(procurement_setup.tenant_id):
        await service.create_requisition(
            db_session,
            procurement_setup.tenant_id,
            RequisitionCreate(lines=[]),
        )


async def test_submit_below_threshold_auto_approves(
    db_session: AsyncSession, procurement_setup: ProcurementSetup
) -> None:
    """A REQUISITION rule at 1000 vs an estimated total of 50 (10 × 5): submit auto-approves."""
    await build_approval_rule(
        db_session,
        procurement_setup.tenant_id,
        document_type=ApprovalDocumentType.REQUISITION,
        threshold_amount="1000",
    )
    req = await build_requisition(
        db_session,
        procurement_setup.tenant_id,
        item_id=procurement_setup.item_id,
        uom_id=procurement_setup.uom_id,
        quantity="10",
        estimated_unit_cost="5",
    )
    with tenant_context(procurement_setup.tenant_id):
        submitted = await service.submit_requisition(
            db_session, procurement_setup.tenant_id, req.id
        )
    assert submitted.status == RequisitionStatus.APPROVED.value


async def test_submit_above_threshold_awaits_approval(
    db_session: AsyncSession, procurement_setup: ProcurementSetup
) -> None:
    """With a REQUISITION rule at 100 and an estimated total of 500 (100 × 5), submit STAYS
    SUBMITTED awaiting an approver."""
    await build_approval_rule(
        db_session,
        procurement_setup.tenant_id,
        document_type=ApprovalDocumentType.REQUISITION,
        threshold_amount="100",
    )
    req = await build_requisition(
        db_session,
        procurement_setup.tenant_id,
        item_id=procurement_setup.item_id,
        uom_id=procurement_setup.uom_id,
        quantity="100",
        estimated_unit_cost="5",
    )
    with tenant_context(procurement_setup.tenant_id):
        submitted = await service.submit_requisition(
            db_session, procurement_setup.tenant_id, req.id
        )
    assert submitted.status == RequisitionStatus.SUBMITTED.value


async def test_submit_no_rule_auto_approves(
    db_session: AsyncSession, procurement_setup: ProcurementSetup
) -> None:
    """With NO active rule, every submit auto-approves (no gate — documented)."""
    req = await build_requisition(
        db_session,
        procurement_setup.tenant_id,
        item_id=procurement_setup.item_id,
        uom_id=procurement_setup.uom_id,
        quantity="1000",
        estimated_unit_cost="1000",
    )
    with tenant_context(procurement_setup.tenant_id):
        submitted = await service.submit_requisition(
            db_session, procurement_setup.tenant_id, req.id
        )
    assert submitted.status == RequisitionStatus.APPROVED.value


async def test_approve_and_reject_submitted(
    db_session: AsyncSession, procurement_setup: ProcurementSetup
) -> None:
    """A SUBMITTED requisition can be approved (→ APPROVED) or rejected (→ REJECTED)."""
    await build_approval_rule(
        db_session,
        procurement_setup.tenant_id,
        document_type=ApprovalDocumentType.REQUISITION,
        threshold_amount="0",
    )
    cases = ((True, RequisitionStatus.APPROVED), (False, RequisitionStatus.REJECTED))
    for approved, expected in cases:
        req = await build_requisition(
            db_session,
            procurement_setup.tenant_id,
            item_id=procurement_setup.item_id,
            uom_id=procurement_setup.uom_id,
        )
        with tenant_context(procurement_setup.tenant_id):
            await service.submit_requisition(db_session, procurement_setup.tenant_id, req.id)
            decided = await service.decide_requisition(
                db_session, procurement_setup.tenant_id, req.id, approved=approved
            )
        assert decided.status == expected.value


async def test_decide_non_submitted_conflict(
    db_session: AsyncSession, procurement_setup: ProcurementSetup
) -> None:
    """Approving a DRAFT requisition (never submitted) is a ConflictError."""
    req = await build_requisition(
        db_session,
        procurement_setup.tenant_id,
        item_id=procurement_setup.item_id,
        uom_id=procurement_setup.uom_id,
    )
    with pytest.raises(ConflictError), tenant_context(procurement_setup.tenant_id):
        await service.decide_requisition(
            db_session, procurement_setup.tenant_id, req.id, approved=True
        )


async def test_update_only_draft(
    db_session: AsyncSession, procurement_setup: ProcurementSetup
) -> None:
    """A submitted (then approved) requisition can no longer be edited."""
    req = await build_requisition(
        db_session,
        procurement_setup.tenant_id,
        item_id=procurement_setup.item_id,
        uom_id=procurement_setup.uom_id,
    )
    with tenant_context(procurement_setup.tenant_id):
        await service.submit_requisition(db_session, procurement_setup.tenant_id, req.id)
        from app.modules.procurement.schemas import RequisitionUpdate

        with pytest.raises(ConflictError):
            await service.update_requisition(
                db_session,
                procurement_setup.tenant_id,
                req.id,
                RequisitionUpdate(notes="late edit"),
            )


async def test_update_replaces_lines(
    db_session: AsyncSession, procurement_setup: ProcurementSetup
) -> None:
    """Supplying lines on a DRAFT update replaces them wholesale (renumbered from 1)."""
    req = await build_requisition(
        db_session,
        procurement_setup.tenant_id,
        item_id=procurement_setup.item_id,
        uom_id=procurement_setup.uom_id,
    )
    from app.modules.procurement.schemas import RequisitionUpdate

    with tenant_context(procurement_setup.tenant_id):
        await service.update_requisition(
            db_session,
            procurement_setup.tenant_id,
            req.id,
            RequisitionUpdate(
                lines=[
                    RequisitionLineCreate(
                        item_id=procurement_setup.item_id,
                        quantity=Decimal("3"),
                        uom_id=procurement_setup.uom_id,
                        currency_code="USD",
                    ),
                    RequisitionLineCreate(
                        item_id=procurement_setup.item_id,
                        quantity=Decimal("7"),
                        uom_id=procurement_setup.uom_id,
                        currency_code="USD",
                    ),
                ]
            ),
        )
        lines = await service.get_requisition_lines(
            db_session, procurement_setup.tenant_id, req.id
        )
    assert [line.line_number for line in lines] == [1, 2]
    assert {Decimal(str(line.quantity)) for line in lines} == {Decimal("3"), Decimal("7")}


async def test_cancel_draft(
    db_session: AsyncSession, procurement_setup: ProcurementSetup
) -> None:
    req = await build_requisition(
        db_session,
        procurement_setup.tenant_id,
        item_id=procurement_setup.item_id,
        uom_id=procurement_setup.uom_id,
    )
    with tenant_context(procurement_setup.tenant_id):
        cancelled = await service.cancel_requisition(
            db_session, procurement_setup.tenant_id, req.id
        )
    assert cancelled.status == RequisitionStatus.CANCELLED.value
