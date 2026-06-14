"""Shared CRM validation + numbering helpers for the lead / opportunity / activity services (PLAN
12.1), kept in one private module so the aggregate services stay small and the cross-module
validation
rules live in ONE place — greppable and consistent.

Every cross-module check goes through the owning module's queries contract (D-029), never a
cross-module FK: an ``owner_employee_id`` is validated via ``hr/queries.employee_exists``, a
currency
via ``finance/queries.currency_exists``, an opportunity LINE's item via
``inventory/queries.item_exists``,
and an opportunity's existing ``customer_id`` via ``sales/queries.customer_exists``. The numbering
helper wraps ensure_sequence + claim_number so leads and opportunities claim their gapless number at
creation identically (D-012/D-040).
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationFailedError
from app.core.numbering import claim_number, ensure_sequence
from app.modules.finance import queries as finance_queries
from app.modules.hr import queries as hr_queries
from app.modules.inventory import queries as inventory_queries
from app.modules.sales import queries as sales_queries


async def validate_owner(
    session: AsyncSession, tenant_id: uuid.UUID, owner_employee_id: uuid.UUID | None
) -> None:
    """A supplied ``owner_employee_id`` must exist in hr (D-029): validated via the hr queries
    contract, never a cross-module FK. None is skipped (the owner is optional)."""
    if owner_employee_id is None:
        return
    if not await hr_queries.employee_exists(session, tenant_id, owner_employee_id):
        raise ValidationFailedError(
            message="Referenced employee does not exist",
            code="crm.owner_not_found",
            details={"owner_employee_id": str(owner_employee_id)},
        )


async def validate_currency(
    session: AsyncSession, tenant_id: uuid.UUID, currency_code: str
) -> None:
    """The currency must exist in finance's catalog (D-029, via finance/queries)."""
    if not await finance_queries.currency_exists(session, tenant_id, currency_code):
        raise ValidationFailedError(
            message=f"Currency {currency_code} does not exist in the finance catalog",
            code="crm.currency_not_found",
            details={"currency_code": currency_code},
        )


async def validate_item(
    session: AsyncSession, tenant_id: uuid.UUID, item_id: uuid.UUID
) -> None:
    """An opportunity line's item must exist in inventory (D-029, via inventory/queries)."""
    if not await inventory_queries.item_exists(session, tenant_id, item_id):
        raise ValidationFailedError(
            message="Referenced inventory item does not exist",
            code="crm.item_not_found",
            details={"item_id": str(item_id)},
        )


async def validate_existing_customer(
    session: AsyncSession, tenant_id: uuid.UUID, customer_id: uuid.UUID | None
) -> None:
    """A supplied (existing) ``customer_id`` must exist in sales (D-029, via sales/queries). None is
    skipped (the opportunity is for a prospect — convert creates the customer)."""
    if customer_id is None:
        return
    if not await sales_queries.customer_exists(session, tenant_id, customer_id):
        raise ValidationFailedError(
            message="Referenced customer does not exist",
            code="crm.customer_not_found",
            details={"customer_id": str(customer_id)},
        )


async def claim_lead_or_opportunity_number(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    sequence_name: str,
    prefix: str,
    padding: int,
    on_date: date,
) -> str:
    """Ensure the (year-resetting) sequence exists and claim the next gapless number (D-012/D-040:
    claimed at creation, so a lead/opportunity is referenceable immediately). The claim runs in the
    caller's transaction, so gaplessness for committed rows falls out of ACID."""
    await ensure_sequence(session, tenant_id, sequence_name, prefix, padding, year_reset=True)
    return await claim_number(session, tenant_id, sequence_name, on_date=on_date)
