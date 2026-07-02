"""THE convert test (PLAN 12.1, D-057): converting an opportunity → a sales customer + quote via the
event bus, the opportunity WON + converted ids set, the docflow opportunity → quote link, re-convert
rejected, the no-lines guard, and the existing-customer path (quote only).

Convert is dispatched through ``run_in_uow`` so the published ``OpportunityConverted`` reaches
SALES'
handler in the same transaction (the conftest registers the handlers). Per issue #53 these tests
never
assert state in the SAME session AFTER a handler-raised rollback — the negative paths (re-convert,
no-lines) are rejected by the CRM service BEFORE the event publishes, so no handler runs for them.
"""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.core.events import run_in_uow
from app.core.exceptions import ConflictError, ValidationFailedError
from app.core.tenancy import tenant_context
from app.modules.crm import service
from app.modules.crm.constants import OPPORTUNITY_CONVERTED_TO_QUOTE_LINK, OpportunityStage
from app.modules.sales import queries as sales_queries
from app.modules.sales import service as sales_service
from tests.modules.crm.conftest import CrmSetup
from tests.modules.crm.factories import build_opportunity, build_opportunity_with_line

pytestmark = pytest.mark.asyncio


async def _convert(db_session: AsyncSession, tenant_id: uuid.UUID, opportunity_id: uuid.UUID):
    """Run convert in a uow so the OpportunityConverted handler (sales) dispatches in-transaction.
    The
    whole uow (work + handler drain) runs under the tenant context so the handler's writes are
    filtered/stamped (the mrp-convert test precedent)."""
    holder: list = []

    async def work() -> None:
        holder.append(
            await service.convert_opportunity(db_session, tenant_id, opportunity_id)
        )

    with tenant_context(tenant_id):
        await run_in_uow(db_session, work)
    return holder[0]


async def test_convert_prospect_creates_customer_and_quote(
    db_session: AsyncSession, crm_setup: CrmSetup
) -> None:
    """THE key test: a prospect opportunity (no existing customer) → a NEW sales customer + a quote
    are created via the event; the opportunity is WON with converted ids set; the docflow
    opportunity
    → quote edge exists; the quote's lines mirror the opportunity's lines."""
    opportunity = await build_opportunity_with_line(
        db_session, crm_setup.tenant_id, crm_setup, quantity=Decimal("3"), unit_price=Decimal("100")
    )
    converted = await _convert(db_session, crm_setup.tenant_id, opportunity.id)

    assert converted.stage == OpportunityStage.WON.value
    assert converted.converted_customer_id is not None
    assert converted.converted_quote_id is not None

    with tenant_context(crm_setup.tenant_id):
        customer = await sales_queries.get_customer(
            db_session, crm_setup.tenant_id, converted.converted_customer_id
        )
        quote = await sales_service.get_quote(
            db_session, crm_setup.tenant_id, converted.converted_quote_id
        )
        quote_lines = await sales_service.get_quote_lines(
            db_session, crm_setup.tenant_id, quote.id
        )
        chain = await docflow.get_document_chain(
            db_session, crm_setup.tenant_id, opportunity.document_id
        )
    assert customer is not None
    assert customer.customer_code == f"CRM-{opportunity.opportunity_number}"
    assert customer.default_currency_code == "USD"
    assert quote.customer_id == converted.converted_customer_id
    assert len(quote_lines) == 1
    assert quote_lines[0].item_id == crm_setup.item_id
    assert quote_lines[0].quantity == Decimal("3")
    # 3 × 100 = 300 (no discount).
    assert quote.total_amount == Decimal("300")
    link_types = {edge.link_type for edge in chain.edges}
    assert OPPORTUNITY_CONVERTED_TO_QUOTE_LINK in link_types


async def test_convert_existing_customer_only_quotes(
    db_session: AsyncSession, crm_setup: CrmSetup
) -> None:
    """An opportunity already linked to an EXISTING customer: convert creates only the quote (no new
    customer); converted_customer_id is that existing id."""
    opportunity = await build_opportunity_with_line(
        db_session,
        crm_setup.tenant_id,
        crm_setup,
        customer_id=crm_setup.customer_id,
        quantity=Decimal("2"),
        unit_price=Decimal("50"),
    )
    converted = await _convert(db_session, crm_setup.tenant_id, opportunity.id)

    assert converted.stage == OpportunityStage.WON.value
    assert converted.converted_customer_id == crm_setup.customer_id
    with tenant_context(crm_setup.tenant_id):
        quote = await sales_service.get_quote(
            db_session, crm_setup.tenant_id, converted.converted_quote_id
        )
    assert quote.customer_id == crm_setup.customer_id
    assert quote.total_amount == Decimal("100")  # 2 × 50


async def test_reconvert_rejected(db_session: AsyncSession, crm_setup: CrmSetup) -> None:
    """A WON (already-converted) opportunity cannot reconvert — rejected by the service BEFORE any
    event publishes (no handler runs, no #53 post-failure-state concern)."""
    opportunity = await build_opportunity_with_line(db_session, crm_setup.tenant_id, crm_setup)
    await _convert(db_session, crm_setup.tenant_id, opportunity.id)
    with tenant_context(crm_setup.tenant_id), pytest.raises(ConflictError) as exc:
        await service.convert_opportunity(db_session, crm_setup.tenant_id, opportunity.id)
    assert exc.value.code == "crm.opportunity_not_convertible"


async def test_convert_no_lines_rejected(
    db_session: AsyncSession, crm_setup: CrmSetup
) -> None:
    """An opportunity with no expected-product lines cannot convert (a quote needs ≥1 line) —
    rejected by the service before any event publishes."""
    opportunity = await build_opportunity(db_session, crm_setup.tenant_id)
    with tenant_context(crm_setup.tenant_id), pytest.raises(ValidationFailedError) as exc:
        await service.convert_opportunity(db_session, crm_setup.tenant_id, opportunity.id)
    assert exc.value.code == "crm.opportunity_no_lines"


async def test_convert_lost_opportunity_rejected(
    db_session: AsyncSession, crm_setup: CrmSetup
) -> None:
    """A LOST opportunity is not convertible — rejected before publish."""
    opportunity = await build_opportunity_with_line(db_session, crm_setup.tenant_id, crm_setup)
    with tenant_context(crm_setup.tenant_id):
        await service.move_stage(
            db_session, crm_setup.tenant_id, opportunity.id, OpportunityStage.LOST
        )
        await db_session.commit()
        with pytest.raises(ConflictError) as exc:
            await service.convert_opportunity(db_session, crm_setup.tenant_id, opportunity.id)
    assert exc.value.code == "crm.opportunity_not_convertible"
