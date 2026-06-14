"""Customer-master business logic (PLAN 7.1): customer CRUD.

The service layer owns every rule (CLAUDE.md rule 7); the router stays thin. Rules enforced here:

- ``customer_code`` uniqueness per tenant (friendly ConflictError before the DB UNIQUE would raise);
- ``default_currency_code`` must exist in finance's currency catalog (D-029, via
  ``finance/queries.currency_exists`` — never a cross-module FK);
- ``customer_group_id`` (when set) must reference an existing group in the tenant;
- ``payment_terms_days`` >= 0 and ``credit_limit`` >= 0 (schema bounds them too; the DB CHECKs are
  the backstop);
- ``status`` transitions are UNRESTRICTED between ACTIVE/BLOCKED/INACTIVE (constants.CustomerStatus
  documents why — a block/retire must be reversible; 7.2 reads the status to refuse orders against
  non-ACTIVE customers, but the master itself imposes no terminal state).

Near-symmetric with the procurement vendor service. ``from __future__ import annotations`` keeps
``Page[Customer]`` (the ORM model) a string at import; the router re-validates page items.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.pagination import (
    DEFAULT_LIMIT,
    OrderKey,
    SortDirection,
    filter_fingerprint,
    paginate,
)
from app.core.schemas import Page
from app.modules.finance import queries as finance_queries
from app.modules.sales.constants import CustomerStatus
from app.modules.sales.models import Customer
from app.modules.sales.schemas import CustomerCreate, CustomerFilter, CustomerUpdate
from app.modules.sales.service.customer_groups import get_customer_group


async def _customer_by_code(
    session: AsyncSession, tenant_id: uuid.UUID, customer_code: str
) -> Customer | None:
    stmt = select(Customer).where(
        Customer.tenant_id == tenant_id, Customer.customer_code == customer_code
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _validate_currency(
    session: AsyncSession, tenant_id: uuid.UUID, currency_code: str
) -> None:
    """The customer's default currency must exist in finance's catalog (D-029): validated through
    the finance queries contract, never a cross-module FK."""
    if not await finance_queries.currency_exists(session, tenant_id, currency_code):
        raise ValidationFailedError(
            message=f"Currency {currency_code} does not exist in the finance catalog",
            code="sales.currency_not_found",
            details={"currency_code": currency_code},
        )


async def _validate_group(
    session: AsyncSession, tenant_id: uuid.UUID, group_id: uuid.UUID
) -> None:
    """A referenced ``customer_group_id`` must exist in the tenant (intra-module read; the composite
    tenant FK is the DB backstop). Raises a friendly NotFoundError up front."""
    await get_customer_group(session, tenant_id, group_id)


async def get_customer(
    session: AsyncSession, tenant_id: uuid.UUID, customer_id: uuid.UUID
) -> Customer:
    customer = await session.get(Customer, customer_id)
    if customer is None or customer.tenant_id != tenant_id:
        raise NotFoundError(message="Customer not found", code="sales.customer_not_found")
    return customer


async def create_customer(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    payload: CustomerCreate,
    *,
    customer_id: uuid.UUID | None = None,
) -> Customer:
    """Create a customer. Rejects a duplicate customer_code; validates the default currency exists
    in finance and the customer group (if given) exists. ``status`` defaults to ACTIVE;
    ``payment_terms_days`` to NET30, ``credit_limit`` to 0 = cash-only (schema).

    ``customer_id`` (optional) lets a caller supply the PK instead of letting it default — used by
    the
    CRM convert handler (D-057), which pre-generates the id so the converting opportunity can record
    ``converted_customer_id`` deterministically. None keeps the default uuid4 (the normal path)."""
    if await _customer_by_code(session, tenant_id, payload.customer_code) is not None:
        raise ConflictError(
            message=f"A customer with code {payload.customer_code} already exists",
            code="sales.customer_code_conflict",
            details={"customer_code": payload.customer_code},
        )
    await _validate_currency(session, tenant_id, payload.default_currency_code)
    if payload.customer_group_id is not None:
        await _validate_group(session, tenant_id, payload.customer_group_id)
    customer = Customer(
        **({"id": customer_id} if customer_id is not None else {}),
        tenant_id=tenant_id,
        customer_code=payload.customer_code,
        name=payload.name,
        status=CustomerStatus(payload.status).value,
        customer_group_id=payload.customer_group_id,
        default_currency_code=payload.default_currency_code,
        payment_terms_days=payload.payment_terms_days,
        credit_limit=payload.credit_limit,
        tax_reference=payload.tax_reference,
        email=payload.email,
        phone=payload.phone,
        address=payload.address,
        notes=payload.notes,
    )
    session.add(customer)
    await session.flush()
    return customer


async def update_customer(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    customer_id: uuid.UUID,
    payload: CustomerUpdate,
) -> Customer:
    """Partial update of a customer (D-010: mutate the loaded object so the audit diff is captured).
    ``customer_code`` is immutable and absent from the schema; a changed ``default_currency_code``
    is re-validated against finance; a changed ``customer_group_id`` is re-validated to exist (None
    clears membership, no validation); ``status`` may move freely between the three states."""
    customer = await get_customer(session, tenant_id, customer_id)
    data = payload.model_dump(exclude_unset=True)
    if data.get("default_currency_code") is not None:
        await _validate_currency(session, tenant_id, data["default_currency_code"])
    if data.get("customer_group_id") is not None:
        await _validate_group(session, tenant_id, data["customer_group_id"])
    if data.get("status") is not None:
        data["status"] = CustomerStatus(data["status"]).value
    for field, value in data.items():
        setattr(customer, field, value)
    await session.flush()
    return customer


async def list_customers(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    filters: CustomerFilter,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Page[Customer]:
    """Keyset-paginated customer list ordered by customer_code (D-014). The optional status filter
    narrows the set and folds into the cursor fingerprint so a cursor cannot bleed across views (the
    (tenant_id, status) index serves the filtered page, PERFORMANCE §1)."""
    stmt = select(Customer).where(Customer.tenant_id == tenant_id)
    if filters.status is not None:
        stmt = stmt.where(Customer.status == CustomerStatus(filters.status).value)
    fingerprint = filter_fingerprint(filters.status)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(Customer.customer_code, SortDirection.ASC)],
        pk=Customer.id,
        cursor=cursor,
        limit=limit,
        filters=fingerprint,
    )
