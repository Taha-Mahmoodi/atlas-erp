"""Sales domain-event handlers (D-011) — cross-module subscribers.

``create_customer_and_quote_for_conversion`` subscribes to CRM's ``OpportunityConverted`` and
creates
the sales Customer (when the opportunity is not already linked to one) + the sales Quote in the SAME
transaction as the CRM convert action (PLAN 12.1, D-057). This is the §5-clean opportunity →
customer +
quote mechanism: CRM OWNS the opportunity but MUST NOT call sales' service (STRUCTURE §5), so CRM
PUBLISHES the event and SALES handles its OWN customer + quote creation — exactly the billing →
AR-invoice (sales publishes, finance creates) / planned-buy → requisition (manufacturing publishes,
procurement creates) precedent, here with the roles flipped (CRM publishes, sales creates).

SALES importing ``crm/events`` is the sanctioned events-only import (STRUCTURE §5 / D-011): an event
carries no behaviour, so this subscriber imports the typed event class without any crm logic. SALES
does NOT import crm/queries or crm/models — CRM pre-generated the customer/quote ids and passed them
in
the event, so the handler needs nothing back from CRM (no sales→crm read, no cycle, D-057).

The customer + quote are created through SALES' OWN service (``create_customer`` /
``create_quote``),
never raw inserts, so every customer/quote invariant fires (code uniqueness, currency existence,
item
existence, line pricing). The convert docflow edges (opportunity document → 'converted_to_customer'
→
customer document; → 'converted_to_quote' → quote document) make the opportunity → customer/quote
flow
renderable in the DocFlowViewer — the DURABLE convert link (not a cross-module FK, the billing-side
precedent). A handler exception (a duplicate customer code on re-convert, an unknown item, an
unpriceable line) rolls the WHOLE convert back (D-011).

Registration: ``app.main.register_event_handlers`` subscribes this at the factory (the D-011 seam),
so
the test harness re-registers after its per-test ``clear_subscriptions`` reset (D-025).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.modules.crm.constants import OPPORTUNITY_CONVERTED_TO_QUOTE_LINK
from app.modules.crm.events import OpportunityConverted
from app.modules.sales.schemas import CustomerCreate, QuoteCreate, QuoteLineCreate
from app.modules.sales.service.customers import create_customer
from app.modules.sales.service.quotes import create_quote


async def create_customer_and_quote_for_conversion(
    session: AsyncSession, event: OpportunityConverted
) -> None:
    """Create the customer (if new) + the quote for a converted opportunity (PLAN 12.1, D-057), in
    the
    convert's transaction.

    When ``existing_customer_id`` is None the opportunity is for a PROSPECT: create the sales
    Customer
    with the supplied ``new_customer_id`` + ``customer_code`` (the customer's default currency is
    the
    deal currency). When ``existing_customer_id`` is set the deal is for an EXISTING customer — skip
    creation, quote against it. A Customer is a MASTER (not a docflow document — no core_documents
    entry), so there is no opportunity → customer docflow edge; the convert's customer link is the
    opportunity's recorded ``converted_customer_id`` (the opaque id, D-029).

    Then create the sales Quote with the supplied ``quote_id`` from the event's lines (each item +
    base UoM + quantity + unit price → a quote line, priced + totalled by the sales quote service),
    and link the opportunity document → 'converted_to_quote' → quote document (the quote IS a
    docflow
    document — the durable convert link, D-057). Both creations go through SALES' own service so
    every
    invariant fires; both share the session, so they land in the same transaction as the CRM convert
    (a failure rolls the whole convert back, D-011)."""
    customer_id = event.existing_customer_id
    if customer_id is None:
        customer = await create_customer(
            session,
            event.tenant_id,
            CustomerCreate(
                customer_code=event.customer_code,
                name=event.company_name,
                default_currency_code=event.currency_code,
                email=event.email,
            ),
            customer_id=event.new_customer_id,
        )
        customer_id = customer.id

    quote = await create_quote(
        session,
        event.tenant_id,
        QuoteCreate(
            customer_id=customer_id,
            currency_code=event.currency_code,
            lines=[
                QuoteLineCreate(
                    item_id=line.item_id,
                    description=line.description,
                    quantity=line.quantity,
                    uom_id=line.uom_id,
                    unit_price=line.unit_price,
                )
                for line in event.lines
            ],
        ),
        quote_id=event.quote_id,
    )
    await docflow.link_documents(
        session,
        event.tenant_id,
        predecessor=event.document_id,
        successor=quote.document_id,
        link_type=OPPORTUNITY_CONVERTED_TO_QUOTE_LINK,
    )
