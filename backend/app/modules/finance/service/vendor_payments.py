"""Vendor payment posting + the payment run (PLAN 4.5, AP — D-019 realized FX at clearing).

``create_and_post_payment`` is the payment/payment-run primitive: it validates the cleared bills
(via ``payment_clearing.validated_clearing``), builds the balanced clearing entry with explicit
functional amounts (``payment_clearing.build_payment_lines`` — Dr AP at each bill's frozen rate, Cr
bank at the payment rate, + a realized-FX line so it balances), posts it with ``skip_translation``,
claims the gapless payment number (D-012), reduces each bill's open_amount and flips its status,
records the allocations, links payment->bills (docflow 'pays'), and publishes the posted event.

``run_payment_batch`` groups due open bills by (partner, currency) and pays each group's due bills
in full — one payment per group. The clearing/FX math lives in ``payment_clearing.py`` and the aging
projection in ``ap_aging.py`` (both split out to keep every file under the STRUCTURE §3 cap).
Finance stays the bottom dependency; partner ids stay opaque (D-029).
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.core.events import publish
from app.core.money import currency_decimals, quantize_money
from app.core.numbering import claim_number, ensure_sequence
from app.modules.finance.constants import (
    AP_PAYMENT_DOC_TYPE,
    AP_PAYMENT_NUMBER_PADDING,
    AP_PAYMENT_NUMBER_PREFIX,
    AP_PAYMENT_PAYS_LINK,
    AP_PAYMENT_SEQUENCE_NAME,
    BillStatus,
    DocumentType,
    PaymentStatus,
)
from app.modules.finance.events import VendorPaymentPosted
from app.modules.finance.models import (
    VendorBill,
    VendorPayment,
    VendorPaymentAllocation,
)
from app.modules.finance.payables_schemas import (
    PaymentAllocationCreate,
    VendorPaymentCreate,
)
from app.modules.finance.schemas import JournalEntryCreate
from app.modules.finance.service.journal import create_draft_entry, post_entry
from app.modules.finance.service.payment_clearing import (
    build_payment_lines,
    require_bank_account,
    set_fx_line_currency,
    validated_clearing,
)


async def create_and_post_payment(
    session: AsyncSession, tenant_id: uuid.UUID, payload: VendorPaymentCreate
) -> VendorPayment:
    """Create + post a vendor payment clearing one or more open bills (PLAN 4.5, D-019).

    Validates the bills are open, same partner, same currency, none over-allocated; builds the
    balanced clearing entry (Dr AP, Cr bank, + realized FX), posts it with explicit functional
    amounts (skip_translation), claims the gapless payment number, reduces each bill's open_amount
    and flips its status (PARTIALLY_PAID/PAID), records allocations, links payment->bills (docflow
    'pays'), and publishes ``VendorPaymentPosted``. The caller commits via uow.
    """
    await require_bank_account(session, tenant_id, payload.bank_account_id)
    pairs = await validated_clearing(
        session, tenant_id, payload.partner_id, payload.currency_code, payload.allocations
    )
    payment_amount = quantize_money(payload.amount, currency_decimals(payload.currency_code))

    lines, functional_amounts = await build_payment_lines(
        session,
        tenant_id,
        pairs,
        currency_code=payload.currency_code,
        bank_account_id=payload.bank_account_id,
        payment_amount=payment_amount,
        payment_date=payload.payment_date,
    )

    entry = await create_draft_entry(
        session,
        tenant_id,
        JournalEntryCreate(
            posting_date=payload.payment_date,
            currency_code=payload.currency_code,
            description=f"Vendor payment {payload.partner_name}",
            document_type=DocumentType.PAYMENT,
            lines=lines,
        ),
        functional_amounts=functional_amounts,
    )
    await set_fx_line_currency(session, tenant_id, entry.id)
    await post_entry(session, tenant_id, entry.id, skip_translation=True)

    payment = await _record_payment(
        session, tenant_id, payload, payment_amount, pairs, entry.id, entry.document_id
    )
    return payment


async def _record_payment(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    payload: VendorPaymentCreate,
    payment_amount: Decimal,
    pairs: list[tuple[VendorBill, Decimal]],
    journal_entry_id: uuid.UUID,
    journal_document_id: uuid.UUID,
) -> VendorPayment:
    """Persist the payment document + allocations after its journal posted (PLAN 4.5): register the
    document, claim the number, reduce each cleared bill's open_amount + flip its status, write the
    allocations, link payment->bills, and publish the event. ``pairs`` are the (bill, amount) pairs
    already validated before the journal posted."""
    payment_id = uuid.uuid4()
    document = await docflow.register_document(
        session,
        tenant_id,
        AP_PAYMENT_DOC_TYPE,
        payment_id,
        doc_number=None,
        status=PaymentStatus.POSTED.value,
    )
    await ensure_sequence(
        session,
        tenant_id,
        AP_PAYMENT_SEQUENCE_NAME,
        AP_PAYMENT_NUMBER_PREFIX,
        AP_PAYMENT_NUMBER_PADDING,
        year_reset=True,
    )
    payment_number = await claim_number(
        session, tenant_id, AP_PAYMENT_SEQUENCE_NAME, on_date=payload.payment_date
    )
    payment = VendorPayment(
        id=payment_id,
        tenant_id=tenant_id,
        document_id=document.id,
        partner_id=payload.partner_id,
        partner_name=payload.partner_name,
        payment_number=payment_number,
        payment_date=payload.payment_date,
        currency_code=payload.currency_code,
        bank_account_id=payload.bank_account_id,
        amount=payment_amount,
        journal_entry_id=journal_entry_id,
        status=PaymentStatus.POSTED.value,
        description=payload.description,
    )
    session.add(payment)

    cleared_bill_ids: list[uuid.UUID] = []
    for bill, amount in pairs:
        bill.open_amount = Decimal(str(bill.open_amount)) - amount
        bill.status = (
            BillStatus.PAID.value
            if Decimal(str(bill.open_amount)) == 0
            else BillStatus.PARTIALLY_PAID.value
        )
        session.add(
            VendorPaymentAllocation(
                tenant_id=tenant_id,
                payment_id=payment_id,
                vendor_bill_id=bill.id,
                allocated_amount=amount,
            )
        )
        cleared_bill_ids.append(bill.id)
    await session.flush()

    await docflow.set_document_status(
        session,
        tenant_id,
        payment.document_id,
        status=PaymentStatus.POSTED.value,
        doc_number=payment_number,
    )
    # The journal entry was created INSIDE the payment flow, so wire its docflow link to the
    # payment as well (payment 'posts' its clearing journal entry, mirroring a bill->journal link).
    await docflow.link_documents(
        session,
        tenant_id,
        predecessor=payment.document_id,
        successor=journal_document_id,
        link_type="posts",
    )
    for bill, _amount in pairs:
        await docflow.link_documents(
            session,
            tenant_id,
            predecessor=payment.document_id,
            successor=bill.document_id,
            link_type=AP_PAYMENT_PAYS_LINK,
        )

    publish(
        session,
        VendorPaymentPosted(
            tenant_id=tenant_id,
            payment_id=payment.id,
            payment_number=payment_number,
            journal_entry_id=journal_entry_id,
            partner_id=payment.partner_id,
            currency_code=payment.currency_code,
            amount=payment_amount,
            cleared_bill_ids=tuple(cleared_bill_ids),
        ),
    )
    return payment


async def run_payment_batch(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    up_to_due_date: date,
    bank_account_id: uuid.UUID,
    partner_id: uuid.UUID | None = None,
    payment_date: date | None = None,
) -> list[VendorPayment]:
    """A simple payment run (PLAN 4.5): select POSTED/PARTIALLY_PAID bills with open_amount > 0 due
    on or before ``up_to_due_date`` (optionally one partner), group by (partner, currency), and pay
    each group's due bills IN FULL — one payment per group. Returns the payments created (empty when
    nothing is due). ``payment_date`` defaults to ``up_to_due_date``."""
    run_date = payment_date or up_to_due_date
    stmt = (
        select(VendorBill)
        .where(
            VendorBill.tenant_id == tenant_id,
            VendorBill.status.in_(
                (BillStatus.POSTED.value, BillStatus.PARTIALLY_PAID.value)
            ),
            VendorBill.open_amount > 0,
            VendorBill.due_date <= up_to_due_date,
        )
        .order_by(VendorBill.partner_id, VendorBill.due_date)
    )
    if partner_id is not None:
        stmt = stmt.where(VendorBill.partner_id == partner_id)
    bills = list((await session.execute(stmt)).scalars().all())

    groups: dict[tuple[uuid.UUID, str], list[VendorBill]] = defaultdict(list)
    for bill in bills:
        groups[(bill.partner_id, bill.currency_code)].append(bill)

    payments: list[VendorPayment] = []
    for (group_partner_id, currency_code), group_bills in groups.items():
        allocations = [
            PaymentAllocationCreate(bill_id=bill.id, amount=Decimal(str(bill.open_amount)))
            for bill in group_bills
        ]
        total = sum((Decimal(str(b.open_amount)) for b in group_bills), Decimal(0))
        payment = await create_and_post_payment(
            session,
            tenant_id,
            VendorPaymentCreate(
                partner_id=group_partner_id,
                partner_name=group_bills[0].partner_name,
                payment_date=run_date,
                currency_code=currency_code,
                bank_account_id=bank_account_id,
                amount=total,
                description=f"Payment run {run_date.isoformat()}",
                allocations=allocations,
            ),
        )
        payments.append(payment)
    return payments


async def get_payment_allocations(
    session: AsyncSession, tenant_id: uuid.UUID, payment_id: uuid.UUID
) -> list[VendorPaymentAllocation]:
    stmt = (
        select(VendorPaymentAllocation)
        .where(
            VendorPaymentAllocation.tenant_id == tenant_id,
            VendorPaymentAllocation.payment_id == payment_id,
        )
        .order_by(VendorPaymentAllocation.created_at)
    )
    return list((await session.execute(stmt)).scalars().all())


async def get_vendor_payment(
    session: AsyncSession, tenant_id: uuid.UUID, payment_id: uuid.UUID
) -> VendorPayment:
    from app.core.exceptions import NotFoundError

    payment = await session.get(VendorPayment, payment_id)
    if payment is None or payment.tenant_id != tenant_id:
        raise NotFoundError(
            message="Vendor payment not found", code="finance.vendor_payment_not_found"
        )
    return payment


async def list_vendor_payments(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    cursor: str | None,
    limit: int,
    partner_id: uuid.UUID | None = None,
) -> object:
    """Keyset-paginated payment list, newest payment_date first (D-014). ``partner_id`` folds into
    the cursor fingerprint."""
    from app.core.pagination import OrderKey, SortDirection, filter_fingerprint, paginate

    stmt = select(VendorPayment).where(VendorPayment.tenant_id == tenant_id)
    if partner_id is not None:
        stmt = stmt.where(VendorPayment.partner_id == partner_id)
    return await paginate(
        session,
        stmt,
        order_by=[
            OrderKey(VendorPayment.payment_date, SortDirection.DESC),
            OrderKey(VendorPayment.created_at, SortDirection.DESC),
        ],
        pk=VendorPayment.id,
        cursor=cursor,
        limit=limit,
        filters=filter_fingerprint(partner_id),
    )
