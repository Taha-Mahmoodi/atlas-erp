"""Sales-quotation service tests (PLAN 7.2): CRUD, price defaulting from the resolver, line
discounts, the send/accept/reject lifecycle, expiry handling, and convert-to-order with docflow."""

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.core.exceptions import ConflictError, ValidationFailedError
from app.core.tenancy import tenant_context
from app.modules.sales import service
from app.modules.sales.constants import (
    QUOTE_CONVERTED_TO_ORDER_LINK,
    DiscountType,
    QuoteStatus,
    SalesOrderStatus,
)
from app.modules.sales.schemas import (
    ConvertQuoteToOrder,
    QuoteCreate,
    QuoteLineCreate,
)
from tests.modules.sales.factories import (
    SalesSetup,
    build_customer,
    build_price_list,
    build_price_list_item,
    build_quote,
    build_sales_setup,
)


async def _setup(session: AsyncSession, tenant_id: uuid.UUID) -> tuple[SalesSetup, uuid.UUID]:
    setup = await build_sales_setup(session, tenant_id)
    customer = await build_customer(session, tenant_id, customer_code="QC-1")
    return setup, customer.id


async def test_create_quote_numbers_and_totals(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    setup, customer_id = await _setup(db_session, tenant_a)
    quote = await build_quote(
        db_session,
        tenant_a,
        customer_id=customer_id,
        item_id=setup.item_id,
        uom_id=setup.uom_id,
        quantity="4",
        unit_price="25",
    )
    assert quote.status == QuoteStatus.DRAFT.value
    assert quote.quote_number.startswith("QUO-")
    assert Decimal(str(quote.total_amount)) == Decimal("100")  # 4 × 25


async def test_unit_price_defaults_from_resolver(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    setup, customer_id = await _setup(db_session, tenant_a)
    price_list = await build_price_list(db_session, tenant_a, code="PL-Q")
    await build_price_list_item(
        db_session, tenant_a, price_list.id, setup.item_id, unit_price="12"
    )
    with tenant_context(tenant_a):
        quote = await service.create_quote(
            db_session,
            tenant_a,
            QuoteCreate(
                customer_id=customer_id,
                lines=[
                    QuoteLineCreate(item_id=setup.item_id, quantity=Decimal("3"),
                    uom_id=setup.uom_id)
                ],
            ),
        )
        lines = await service.get_quote_lines(db_session, tenant_a, quote.id)
    assert Decimal(str(lines[0].unit_price)) == Decimal("12")  # resolver default
    assert Decimal(str(lines[0].line_amount)) == Decimal("36")  # 3 × 12


async def test_no_price_no_list_rejected(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    setup, customer_id = await _setup(db_session, tenant_a)
    with tenant_context(tenant_a), pytest.raises(ValidationFailedError) as exc:
        await service.create_quote(
            db_session,
            tenant_a,
            QuoteCreate(
                customer_id=customer_id,
                lines=[
                    QuoteLineCreate(item_id=setup.item_id, quantity=Decimal("1"),
                    uom_id=setup.uom_id)
                ],
            ),
        )
    assert exc.value.code == "sales.price_unresolved"


async def test_percent_discount(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    setup, customer_id = await _setup(db_session, tenant_a)
    quote = await build_quote(
        db_session,
        tenant_a,
        customer_id=customer_id,
        item_id=setup.item_id,
        uom_id=setup.uom_id,
        quantity="10",
        unit_price="10",
        discount_type=DiscountType.PERCENT,
        discount_value=Decimal("10"),
    )
    # 10 × 10 = 100, less 10% = 90
    assert Decimal(str(quote.total_amount)) == Decimal("90")


async def test_amount_discount(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    setup, customer_id = await _setup(db_session, tenant_a)
    quote = await build_quote(
        db_session,
        tenant_a,
        customer_id=customer_id,
        item_id=setup.item_id,
        uom_id=setup.uom_id,
        quantity="5",
        unit_price="10",
        discount_type=DiscountType.AMOUNT,
        discount_value=Decimal("2"),
    )
    # 5 × 10 = 50, less 2/unit × 5 = 40
    assert Decimal(str(quote.total_amount)) == Decimal("40")


async def test_send_accept_lifecycle(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    setup, customer_id = await _setup(db_session, tenant_a)
    quote = await build_quote(
        db_session, tenant_a, customer_id=customer_id, item_id=setup.item_id, uom_id=setup.uom_id
    )
    with tenant_context(tenant_a):
        sent = await service.send_quote(db_session, tenant_a, quote.id)
        assert sent.status == QuoteStatus.SENT.value
        accepted = await service.accept_quote(db_session, tenant_a, quote.id)
        assert accepted.status == QuoteStatus.ACCEPTED.value


async def test_accept_requires_sent(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    setup, customer_id = await _setup(db_session, tenant_a)
    quote = await build_quote(
        db_session, tenant_a, customer_id=customer_id, item_id=setup.item_id, uom_id=setup.uom_id
    )
    with tenant_context(tenant_a), pytest.raises(ConflictError):
        await service.accept_quote(db_session, tenant_a, quote.id)  # still DRAFT


async def test_reject(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    setup, customer_id = await _setup(db_session, tenant_a)
    quote = await build_quote(
        db_session, tenant_a, customer_id=customer_id, item_id=setup.item_id, uom_id=setup.uom_id
    )
    with tenant_context(tenant_a):
        await service.send_quote(db_session, tenant_a, quote.id)
        rejected = await service.reject_quote(db_session, tenant_a, quote.id)
        assert rejected.status == QuoteStatus.REJECTED.value


async def test_lazy_expiry_on_access(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    setup, customer_id = await _setup(db_session, tenant_a)
    yesterday = date.today() - timedelta(days=1)
    quote = await build_quote(
        db_session,
        tenant_a,
        customer_id=customer_id,
        item_id=setup.item_id,
        uom_id=setup.uom_id,
        valid_until=yesterday,
    )
    with tenant_context(tenant_a):
        refreshed = await service.get_quote(db_session, tenant_a, quote.id)
        swept = await service.mark_expired_if_lapsed(db_session, tenant_a, refreshed)
        assert swept.status == QuoteStatus.EXPIRED.value


async def test_convert_to_order_links_docflow(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    setup, customer_id = await _setup(db_session, tenant_a)
    quote = await build_quote(
        db_session,
        tenant_a,
        customer_id=customer_id,
        item_id=setup.item_id,
        uom_id=setup.uom_id,
        quantity="6",
        unit_price="15",
    )
    with tenant_context(tenant_a):
        await service.send_quote(db_session, tenant_a, quote.id)
        await service.accept_quote(db_session, tenant_a, quote.id)
        order = await service.convert_quote_to_order(
            db_session, tenant_a, quote.id, ConvertQuoteToOrder()
        )
    assert order.status == SalesOrderStatus.DRAFT.value
    assert order.source_quote_id == quote.id
    assert Decimal(str(order.total_amount)) == Decimal("90")  # 6 × 15 carried from the quote
    converted = await service.get_quote(db_session, tenant_a, quote.id)
    assert converted.status == QuoteStatus.CONVERTED.value
    with tenant_context(tenant_a):
        chain = await docflow.get_document_chain(db_session, tenant_a, quote.document_id)
    assert QUOTE_CONVERTED_TO_ORDER_LINK in {e.link_type for e in chain.edges}


async def test_convert_requires_accepted(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    setup, customer_id = await _setup(db_session, tenant_a)
    quote = await build_quote(
        db_session, tenant_a, customer_id=customer_id, item_id=setup.item_id, uom_id=setup.uom_id
    )
    with tenant_context(tenant_a), pytest.raises(ConflictError):
        await service.convert_quote_to_order(
            db_session, tenant_a, quote.id, ConvertQuoteToOrder()
        )  # still DRAFT
