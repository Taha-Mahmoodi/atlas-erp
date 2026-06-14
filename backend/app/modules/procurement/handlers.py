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

Registration: ``app.main.register_event_handlers`` subscribes this at the factory (the D-011 seam),
so the test harness re-registers after its per-test reset (D-025).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.modules.manufacturing.constants import PLANNED_ORDER_CONVERTED_LINK
from app.modules.manufacturing.events import PlannedBuyConverted
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
