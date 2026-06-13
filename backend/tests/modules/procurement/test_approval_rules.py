"""Approval-rule tests (PLAN 6.2, D-040): CRUD + the requires_approval value-threshold evaluator,
incl. the no-rule case (no gate), the inactive-rule case, the at/above vs below boundary, and the
currency-mismatch case (no applicable rule). Exercises the real service layer (D-025).
"""

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.core.tenancy import tenant_context
from app.modules.procurement import service
from app.modules.procurement.constants import ApprovalDocumentType
from app.modules.procurement.schemas import ApprovalRuleCreate
from tests.modules.procurement.conftest import ProcurementSetup
from tests.modules.procurement.factories import build_approval_rule


async def test_no_rule_no_approval(
    db_session: AsyncSession, procurement_setup: ProcurementSetup
) -> None:
    """With no active rule, requires_approval is always False (no gate)."""
    with tenant_context(procurement_setup.tenant_id):
        needs = await service.requires_approval(
            db_session,
            procurement_setup.tenant_id,
            ApprovalDocumentType.PURCHASE_ORDER,
            Decimal("1000000"),
            "USD",
        )
    assert needs is False


async def test_threshold_boundary(
    db_session: AsyncSession, procurement_setup: ProcurementSetup
) -> None:
    """At or above the threshold needs approval; below does not."""
    await build_approval_rule(
        db_session,
        procurement_setup.tenant_id,
        document_type=ApprovalDocumentType.PURCHASE_ORDER,
        threshold_amount="100",
    )
    with tenant_context(procurement_setup.tenant_id):
        at = await service.requires_approval(
            db_session,
            procurement_setup.tenant_id,
            ApprovalDocumentType.PURCHASE_ORDER,
            Decimal("100"),
            "USD",
        )
        below = await service.requires_approval(
            db_session,
            procurement_setup.tenant_id,
            ApprovalDocumentType.PURCHASE_ORDER,
            Decimal("99.99"),
            "USD",
        )
    assert at is True
    assert below is False


async def test_inactive_rule_ignored(
    db_session: AsyncSession, procurement_setup: ProcurementSetup
) -> None:
    """An inactive rule does not gate."""
    await build_approval_rule(
        db_session,
        procurement_setup.tenant_id,
        document_type=ApprovalDocumentType.PURCHASE_ORDER,
        threshold_amount="1",
        is_active=False,
    )
    with tenant_context(procurement_setup.tenant_id):
        needs = await service.requires_approval(
            db_session,
            procurement_setup.tenant_id,
            ApprovalDocumentType.PURCHASE_ORDER,
            Decimal("1000"),
            "USD",
        )
    assert needs is False


async def test_currency_mismatch_no_gate(
    db_session: AsyncSession, procurement_setup: ProcurementSetup
) -> None:
    """A rule in USD does not apply to a document in another currency (v1 single-currency rule)."""
    await build_approval_rule(
        db_session,
        procurement_setup.tenant_id,
        document_type=ApprovalDocumentType.PURCHASE_ORDER,
        threshold_amount="10",
        currency_code="USD",
    )
    with tenant_context(procurement_setup.tenant_id):
        needs = await service.requires_approval(
            db_session,
            procurement_setup.tenant_id,
            ApprovalDocumentType.PURCHASE_ORDER,
            Decimal("1000"),
            "EUR",
        )
    assert needs is False


async def test_rule_per_document_type_unique(
    db_session: AsyncSession, procurement_setup: ProcurementSetup
) -> None:
    """A second rule for the same document_type is a ConflictError."""
    await build_approval_rule(
        db_session,
        procurement_setup.tenant_id,
        document_type=ApprovalDocumentType.PURCHASE_ORDER,
        threshold_amount="100",
    )
    with pytest.raises(ConflictError), tenant_context(procurement_setup.tenant_id):
        await service.create_approval_rule(
            db_session,
            procurement_setup.tenant_id,
            ApprovalRuleCreate(
                document_type=ApprovalDocumentType.PURCHASE_ORDER,
                threshold_amount=Decimal("200"),
                currency_code="USD",
            ),
        )


async def test_separate_rules_per_type(
    db_session: AsyncSession, procurement_setup: ProcurementSetup
) -> None:
    """REQUISITION and PURCHASE_ORDER each get a rule slot; evaluation reads the right one."""
    await build_approval_rule(
        db_session,
        procurement_setup.tenant_id,
        document_type=ApprovalDocumentType.REQUISITION,
        threshold_amount="50",
    )
    await build_approval_rule(
        db_session,
        procurement_setup.tenant_id,
        document_type=ApprovalDocumentType.PURCHASE_ORDER,
        threshold_amount="500",
    )
    with tenant_context(procurement_setup.tenant_id):
        req_needs = await service.requires_approval(
            db_session,
            procurement_setup.tenant_id,
            ApprovalDocumentType.REQUISITION,
            Decimal("100"),
            "USD",
        )
        po_needs = await service.requires_approval(
            db_session,
            procurement_setup.tenant_id,
            ApprovalDocumentType.PURCHASE_ORDER,
            Decimal("100"),
            "USD",
        )
    assert req_needs is True  # 100 >= 50
    assert po_needs is False  # 100 < 500
