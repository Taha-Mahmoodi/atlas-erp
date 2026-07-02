"""Customer-master service tests (PLAN 7.1): CRUD + validation (code unique, currency exists,
terms/credit >= 0, group exists, status transitions) + the queries read surface."""

import uuid
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.tenancy import tenant_context
from app.modules.sales import queries, service
from app.modules.sales.constants import CustomerStatus
from app.modules.sales.schemas import CustomerCreate, CustomerUpdate
from tests.modules.sales.factories import (
    build_customer,
    build_customer_group,
    build_sales_setup,
    seed_currency,
)


async def test_create_defaults(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    await seed_currency(db_session, tenant_a)
    customer = await build_customer(db_session, tenant_a)
    assert customer.status == CustomerStatus.ACTIVE.value
    assert customer.payment_terms_days == 30
    assert Decimal(str(customer.credit_limit)) == Decimal("0")  # cash-only default (D-043)
    assert customer.customer_group_id is None


async def test_duplicate_code_conflicts(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    await seed_currency(db_session, tenant_a)
    await build_customer(db_session, tenant_a, customer_code="C-001")
    with tenant_context(tenant_a), pytest.raises(ConflictError):
        await service.create_customer(
            db_session,
            tenant_a,
            CustomerCreate(customer_code="C-001", name="Other", default_currency_code="USD"),
        )


async def test_unknown_currency_rejected(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    with tenant_context(tenant_a), pytest.raises(ValidationFailedError):
        await service.create_customer(
            db_session,
            tenant_a,
            CustomerCreate(customer_code="C-001", name="Acme", default_currency_code="EUR"),
        )


async def test_unknown_group_rejected(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    await seed_currency(db_session, tenant_a)
    with tenant_context(tenant_a), pytest.raises(NotFoundError):
        await service.create_customer(
            db_session,
            tenant_a,
            CustomerCreate(
                customer_code="C-001",
                name="Acme",
                default_currency_code="USD",
                customer_group_id=uuid.uuid4(),
            ),
        )


async def test_group_membership(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    await seed_currency(db_session, tenant_a)
    group = await build_customer_group(db_session, tenant_a)
    customer = await build_customer(db_session, tenant_a, customer_group_id=group.id)
    assert customer.customer_group_id == group.id


async def test_negative_terms_or_credit_rejected_by_schema() -> None:
    with pytest.raises(ValidationError):
        CustomerCreate(
            customer_code="C-1", name="x", default_currency_code="USD", payment_terms_days=-1
        )
    with pytest.raises(ValidationError):
        CustomerCreate(
            customer_code="C-1", name="x", default_currency_code="USD", credit_limit=Decimal("-1")
        )


async def test_status_transitions_unrestricted(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    await seed_currency(db_session, tenant_a)
    customer = await build_customer(db_session, tenant_a)
    for target in (CustomerStatus.BLOCKED, CustomerStatus.INACTIVE, CustomerStatus.ACTIVE):
        with tenant_context(tenant_a):
            updated = await service.update_customer(
                db_session, tenant_a, customer.id, CustomerUpdate(status=target)
            )
        assert updated.status == target.value


async def test_update_credit_limit_and_currency(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    await seed_currency(db_session, tenant_a)
    await seed_currency(db_session, tenant_a, code="EUR", name="Euro")
    customer = await build_customer(db_session, tenant_a)
    with tenant_context(tenant_a):
        updated = await service.update_customer(
            db_session,
            tenant_a,
            customer.id,
            CustomerUpdate(credit_limit=Decimal("5000"), default_currency_code="EUR"),
        )
    assert Decimal(str(updated.credit_limit)) == Decimal("5000")
    assert updated.default_currency_code == "EUR"


async def test_queries_read_surface(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    """The cross-module read interface 7.2-7.4 + finance AR reporting use (D-029)."""
    setup = await build_sales_setup(db_session, tenant_a)
    customer = await build_customer(
        db_session,
        tenant_a,
        credit_limit=Decimal("2500"),
        payment_terms_days=45,
        status=CustomerStatus.BLOCKED,
    )
    with tenant_context(tenant_a):
        assert await queries.customer_exists(db_session, tenant_a, customer.id) is True
        assert await queries.customer_exists(db_session, tenant_a, uuid.uuid4()) is False
        # The partner_id IS the customer id (D-029).
        resolved = await queries.get_customer_for_partner(db_session, tenant_a, customer.id)
        assert resolved is not None and resolved.id == customer.id
        assert await queries.customer_credit_limit(db_session, tenant_a, customer.id) == Decimal(
            "2500"
        )
        assert await queries.customer_payment_terms_days(db_session, tenant_a, customer.id) == 45
        assert (
            await queries.customer_default_currency(db_session, tenant_a, customer.id)
            == setup.currency_code
        )
        assert (
            await queries.customer_status(db_session, tenant_a, customer.id)
            == CustomerStatus.BLOCKED
        )
