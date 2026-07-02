"""Opportunity → customer + quote conversion (PLAN 12.1, D-057) — THE headline cross-module flow.

``convert_opportunity`` is the CRM side of the convert. It MUST NOT import sales/service (STRUCTURE
§5): converting an opportunity creates a SALES Customer + Quote, both sales-owned writes. So this
service VALIDATES + PUBLISHES ``OpportunityConverted`` and SALES' ``handlers.py`` (subscribed at the
D-011 seam) creates the customer (if the opportunity is not already linked to one) + the quote
through
SALES' OWN service in the SAME transaction (drained by ``run_in_uow`` after this returns, before
commit) and writes the convert docflow edges. Any handler failure rolls the WHOLE convert back
(D-011) — atomic.

IDEMPOTENT / NON-REPEATABLE (D-057). A WON opportunity has already converted; re-convert is rejected
(``require_open_for_convert`` guards on the terminal stages). A LOST opportunity is not convertible.

RECORDING THE CONVERT LINK (D-057, the billing-side precedent). The DURABLE link is the docflow
edges
the sales handler writes (opportunity document → customer / → quote). CRM ALSO records
``converted_customer_id`` / ``converted_quote_id`` on the opportunity for the API: it pre-generates
the
new customer id + the quote id (passed in the event so the handler creates them with those exact
ids),
so CRM knows both ids deterministically before the handler runs — no read-back, no sales→crm import.
For an opportunity already linked to an existing customer, only the quote is created and
``converted_customer_id`` is that existing id.

THE QUOTE LINES (D-057). The opportunity's lines (expected products) become the quote lines — each
line's item + estimated quantity + estimated unit price, with the item's BASE UoM resolved via
``inventory/queries.get_base_uom`` (a quote line needs a UoM). A quote needs at least one line with
a
real item, so an opportunity with NO lines cannot convert (a friendly 422) — the
"single-line-from-estimated_value" fallback is not viable in v1 because a quote line must reference
a
real inventory item (recorded in D-057); the operator adds at least one expected-product line before
converting.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import publish
from app.core.exceptions import ValidationFailedError
from app.modules.crm.constants import OpportunityStage
from app.modules.crm.events import ConvertedQuoteLine, OpportunityConverted
from app.modules.crm.models import Opportunity
from app.modules.crm.service.opportunities import (
    get_opportunity,
    get_opportunity_lines,
    require_open_for_convert,
)
from app.modules.inventory import queries as inventory_queries


def _derive_customer_code(opportunity_number: str) -> str:
    """A deterministic, unique customer code for a NEW customer created on convert: ``CRM-<OPP no>``
    (the opportunity number is already unique per tenant + gapless). Documented so the convert is
    reproducible and a duplicate-code conflict can only mean a re-convert (which is already
    blocked)."""
    return f"CRM-{opportunity_number}"


async def _build_quote_lines(
    session: AsyncSession, tenant_id: uuid.UUID, opportunity_id: uuid.UUID
) -> list[ConvertedQuoteLine]:
    """Turn the opportunity's lines into quote-line specs (D-057): each line's item + base UoM +
    quantity + estimated unit price. The item's BASE UoM is resolved via inventory/queries (a quote
    line needs a UoM); an item with no resolvable base UoM is a hard 422 (it cannot be quoted)."""
    lines = await get_opportunity_lines(session, tenant_id, opportunity_id)
    specs: list[ConvertedQuoteLine] = []
    for line in lines:
        uom_id = await inventory_queries.get_base_uom(session, tenant_id, line.item_id)
        if uom_id is None:
            raise ValidationFailedError(
                message="An expected-product item has no base unit of measure; cannot quote it",
                code="crm.item_uom_missing",
                details={"item_id": str(line.item_id)},
            )
        specs.append(
            ConvertedQuoteLine(
                item_id=line.item_id,
                uom_id=uom_id,
                quantity=Decimal(str(line.quantity)),
                unit_price=Decimal(str(line.estimated_unit_price)),
                description=line.description,
            )
        )
    return specs


async def convert_opportunity(
    session: AsyncSession, tenant_id: uuid.UUID, opportunity_id: uuid.UUID
) -> Opportunity:
    """Convert a (non-terminal) opportunity → a sales customer + quote (PLAN 12.1, D-057), run
    inside
    ``run_in_uow`` by the router so the published event is dispatched in the same transaction.

    Steps: load the opportunity; reject if already WON/LOST (re-convert / not-convertible). Build
    the
    quote-line specs from the opportunity lines (rejecting a no-line opportunity — a quote needs ≥1
    line). Pre-generate the quote id (and, for a prospect, the new customer id). PUBLISH
    ``OpportunityConverted`` carrying everything sales needs. Set the opportunity stage WON +
    ``converted_customer_id`` (the existing or pre-generated customer id) + ``converted_quote_id``.
    The
    sales handler then creates the customer (if new) + quote with those exact ids and writes the
    convert docflow edges, in this same transaction — any failure rolls the whole convert back."""
    opportunity = await get_opportunity(session, tenant_id, opportunity_id)
    await require_open_for_convert(opportunity)

    quote_lines = await _build_quote_lines(session, tenant_id, opportunity_id)
    if not quote_lines:
        raise ValidationFailedError(
            message="The opportunity has no expected-product lines; add at least one before "
            "converting",
            code="crm.opportunity_no_lines",
        )

    existing_customer_id = opportunity.customer_id
    # Pre-generate the ids so CRM records the converted_* columns deterministically (the handler
    # creates the customer/quote WITH these ids — no read-back, no sales→crm import). A new customer
    # id only when there is no existing customer.
    new_customer_id = uuid.uuid4() if existing_customer_id is None else None
    quote_id = uuid.uuid4()

    publish(
        session,
        OpportunityConverted(
            tenant_id=tenant_id,
            opportunity_id=opportunity.id,
            opportunity_number=opportunity.opportunity_number,
            document_id=opportunity.document_id,
            existing_customer_id=existing_customer_id,
            new_customer_id=new_customer_id,
            quote_id=quote_id,
            customer_code=_derive_customer_code(opportunity.opportunity_number),
            company_name=opportunity.company_name,
            contact_name=opportunity.contact_name,
            email=opportunity.email,
            currency_code=opportunity.currency_code,
            lines=tuple(quote_lines),
        ),
    )

    opportunity.stage = OpportunityStage.WON.value
    opportunity.converted_customer_id = existing_customer_id or new_customer_id
    opportunity.converted_quote_id = quote_id
    await session.flush()
    return opportunity
