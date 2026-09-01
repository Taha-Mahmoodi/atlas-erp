"""Partner AP/AR ledger reads (part of finance's cross-module read contract, STRUCTURE §5).

Split out of ``queries/__init__.py`` at the 400-line cap (STRUCTURE §8.4) and re-exported from the
package ``__init__`` so every ``from app.modules.finance.queries import X`` import keeps working
from one surface. These functions let procurement read a vendor's open AP and sales read a
customer's open AR — keyed by the OPAQUE ``partner_id`` (= the vendor/customer master id, never an
FK; D-029) —
without importing finance models (finance is the bottom of the dependency order).

Every function takes an explicit ``tenant_id`` and runs under the caller's tenant context, so the
D-007 filter applies on top of the explicit predicate — ordinary tenant-scoped reads, not a bypass.
"""

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.finance.constants import BillStatus, InvoiceStatus
from app.modules.finance.models import CustomerInvoice, CustomerReceipt, VendorBill


async def get_open_vendor_bills(
    session: AsyncSession, tenant_id: uuid.UUID, partner_id: uuid.UUID
) -> list[VendorBill]:
    """A partner's POSTED vendor bills that still have an open balance (PLAN 4.5, D-029). Exposed
    so procurement (later) can read a vendor's open AP without importing finance models — finance
    is the bottom of the dependency order (STRUCTURE §5). Keyed by the opaque ``partner_id``; never
    an FK to a vendor master. Ordered by due date so the oldest-due bills surface first."""
    stmt = (
        select(VendorBill)
        .where(
            VendorBill.tenant_id == tenant_id,
            VendorBill.partner_id == partner_id,
            VendorBill.status.in_(
                (BillStatus.POSTED.value, BillStatus.PARTIALLY_PAID.value)
            ),
            VendorBill.open_amount > 0,
        )
        .order_by(VendorBill.due_date)
    )
    return list((await session.execute(stmt)).scalars().all())


def _open_customer_invoices_stmt(tenant_id: uuid.UUID, partner_id: uuid.UUID):
    """The SELECT for a partner's open customer invoices (PLAN 4.6, D-029): POSTED/PARTIALLY_PAID
    with a positive open balance, oldest-due first. Shared by the list + the balance sum so they
    can never disagree."""
    return (
        select(CustomerInvoice)
        .where(
            CustomerInvoice.tenant_id == tenant_id,
            CustomerInvoice.partner_id == partner_id,
            CustomerInvoice.status.in_(
                (InvoiceStatus.POSTED.value, InvoiceStatus.PARTIALLY_PAID.value)
            ),
            CustomerInvoice.open_amount > 0,
        )
        .order_by(CustomerInvoice.due_date)
    )


async def get_open_customer_invoices(
    session: AsyncSession, tenant_id: uuid.UUID, partner_id: uuid.UUID
) -> list[CustomerInvoice]:
    """A partner's POSTED customer invoices that still have an open balance (PLAN 4.6, D-029).
    Exposed so sales (later) can read a customer's open AR without importing finance models —
    finance is the bottom of the dependency order (STRUCTURE §5). Keyed by the opaque
    ``partner_id``; never an FK to a customer master. Ordered oldest-due first."""
    stmt = _open_customer_invoices_stmt(tenant_id, partner_id)
    return list((await session.execute(stmt)).scalars().all())


async def customer_open_balance(
    session: AsyncSession, tenant_id: uuid.UUID, partner_id: uuid.UUID
) -> Decimal:
    """The total still-owed AR for a partner across all open invoices (PLAN 4.6, D-029): the sum of
    their ``open_amount`` in transaction currency. Exposed so Sales' credit-limit block can ask
    finance "how much does this customer currently owe?" without importing finance models — the
    bottom-dependency contract (STRUCTURE §5). Sums in Python over the (typically small) open set so
    the exact-decimal MoneyType round-trips identically on both engines (D-015). Returns 0 for a
    partner with no open invoices."""
    invoices = await get_open_customer_invoices(session, tenant_id, partner_id)
    return sum((Decimal(str(inv.open_amount)) for inv in invoices), Decimal(0))


async def customer_unapplied_balance(
    session: AsyncSession, tenant_id: uuid.UUID, partner_id: uuid.UUID
) -> Decimal:
    """A partner's ON-ACCOUNT money: the sum of ``unapplied_amount`` across their receipts (PLAN
    20.4, D-086) — deposits taken before an invoice existed, plus the excess of any over-payment.

    Deliberately a SEPARATE number from ``customer_open_balance`` rather than netted into it. A
    deposit is a liability the property owes back, not a negative receivable, and netting it would
    silently change what Sales' credit-limit block and the aging report mean. Callers that want the
    net exposure subtract the two knowingly. Summed in Python over the (small) receipt set so the
    exact-decimal MoneyType round-trips identically on both engines (D-015); returns 0 for a partner
    holding nothing on account."""
    stmt = select(CustomerReceipt.unapplied_amount).where(
        CustomerReceipt.tenant_id == tenant_id,
        CustomerReceipt.partner_id == partner_id,
        CustomerReceipt.unapplied_amount > 0,
    )
    amounts = (await session.execute(stmt)).scalars().all()
    return sum((Decimal(str(amount)) for amount in amounts), Decimal(0))
