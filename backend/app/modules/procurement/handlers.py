"""Procurement domain-event handlers (D-011) — cross-module subscribers (PLAN 8.3).

``create_requisition_for_planned_buy`` (PLAN 8.3, D-049) subscribes to the manufacturing
``manufacturing.planned_order.buy_converted`` event and creates a DRAFT purchase requisition for the
planned BUY order in the SAME transaction as the convert action. This is the §5-clean planned-BUY →
requisition mechanism: manufacturing OWNS the planned order but MUST NOT call procurement's service
(STRUCTURE §5), so it PUBLISHES the event and procurement handles its OWN requisition creation —
exactly the billing → AR-invoice (sales publishes, finance creates) precedent.

The requisition flows through the normal 6.2 ``create_requisition`` (so it joins the standard
approval chain), and the MRP RUN document is linked to the requisition document
(run → 'planned_to' → requisition) so the plan → requisition flow is renderable in the
DocFlowViewer. The planned order itself is not a document — the MRP run is — so the durable
converted link is this docflow edge (the billing-side precedent, which stores no successor id).

``provision_procurement_for_template`` (PLAN 14.1, D-060) subscribes to the industry module's
``IndustryTemplateApplying`` event and creates procurement's slice — the value-threshold approval
presets — idempotently in the apply's transaction (skip-if-exists per document_type). The §5-clean
provisioning seam: industry publishes, procurement creates its OWN ApprovalRule rows.

Registration: ``app.main.register_event_handlers`` subscribes these at the factory (the D-011 seam),
so the test harness re-registers after its per-test reset (D-025).
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.core.tenancy import system_context
from app.modules.industry.events import IndustryTemplateApplying
from app.modules.manufacturing.constants import PLANNED_ORDER_CONVERTED_LINK
from app.modules.manufacturing.events import PlannedBuyConverted
from app.modules.procurement.constants import ApprovalDocumentType
from app.modules.procurement.models import ApprovalRule
from app.modules.procurement.schemas import RequisitionCreate, RequisitionLineCreate
from app.modules.procurement.service.requisitions import create_requisition


async def create_requisition_for_planned_buy(
    session: AsyncSession, event: PlannedBuyConverted
) -> None:
    """Create a DRAFT requisition for a converted planned BUY order (PLAN 8.3, D-049), in the
    convert action's transaction. One line for the planned item at the net quantity, in the event's
    currency/UoM; then link the MRP run document → 'planned_to' → requisition document so the plan →
    requisition flow renders. A handler exception rolls the whole convert back (D-011)."""
    requisition = await create_requisition(
        session,
        event.tenant_id,
        RequisitionCreate(
            notes="MRP planned-order replenishment",
            lines=[
                RequisitionLineCreate(
                    item_id=event.item_id,
                    description=event.description,
                    quantity=event.quantity,
                    uom_id=event.uom_id,
                    currency_code=event.currency_code,
                )
            ],
        ),
    )
    await docflow.link_documents(
        session,
        event.tenant_id,
        predecessor=event.run_document_id,
        successor=requisition.document_id,
        link_type=PLANNED_ORDER_CONVERTED_LINK,
    )


async def provision_procurement_for_template(
    session: AsyncSession, event: IndustryTemplateApplying
) -> None:
    """Create the procurement slice (value-threshold approval presets) of an applied industry
    template (PLAN 14.1, D-060), idempotently, in the apply's transaction.

    The template's ``approval_presets`` carry a purchase-order and/or requisition threshold + a
    currency; this seeds one ``ApprovalRule`` per supplied threshold (UNIQUE(tenant, document_type),
    so skip-if-exists). Thresholds are STRINGS in the template (D-015 no-float) parsed exactly via
    ``Decimal``. No presets ⇒ no rules (a tenant then needs explicit approval below nothing).
    Runs under ``system_context`` so tenant_id is stamped explicitly."""
    presets = event.template.approval_presets
    if presets is None or presets.currency_code is None:
        return
    tenant_id = event.tenant_id
    wanted: list[tuple[ApprovalDocumentType, str | None]] = [
        (ApprovalDocumentType.PURCHASE_ORDER, presets.purchase_order_threshold),
        (ApprovalDocumentType.REQUISITION, presets.requisition_threshold),
    ]
    with system_context():
        existing_types = {
            doc_type
            for (doc_type,) in (
                await session.execute(
                    select(ApprovalRule.document_type).where(
                        ApprovalRule.tenant_id == tenant_id
                    )
                )
            ).all()
        }
        for document_type, threshold in wanted:
            if threshold is None or document_type.value in existing_types:
                continue
            session.add(
                ApprovalRule(
                    tenant_id=tenant_id,
                    document_type=document_type.value,
                    threshold_amount=Decimal(threshold),
                    currency_code=presets.currency_code,
                )
            )
        await session.flush()
