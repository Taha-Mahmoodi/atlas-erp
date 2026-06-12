"""Vendor-bill lifecycle: draft creation + posting through the journal (PLAN 4.5, AP).

A vendor bill is the AP-side document. ``create_vendor_bill`` computes input tax (via the shared
tax engine) and totals on a DRAFT; ``post_vendor_bill`` builds and posts the AP journal entry
(Dr each expense/asset line net, Dr input tax to the tax code's receivable account, Cr the AP
control for the gross — with the opaque ``partner_id`` stamped on the AP line, D-029), claims the
gapless system number (D-012), links the bill document to its journal entry (docflow), sets
``open_amount`` = gross, and publishes ``VendorBillPosted``. Idempotent at the service level: a
re-post of an already-POSTED bill returns it unchanged.

The journal engine handles FX translation at posting (D-019): a foreign-currency bill's functional
amounts are frozen at the posting-date SPOT rate by the same machinery every entry uses. Finance
stays the bottom dependency — this module imports no other module.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.core.events import publish
from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.money import quantize_for_currency
from app.core.numbering import claim_number, ensure_sequence
from app.modules.finance.constants import (
    AP_BILL_DOC_TYPE,
    AP_BILL_NUMBER_PADDING,
    AP_BILL_NUMBER_PREFIX,
    AP_BILL_POSTS_LINK,
    AP_BILL_SEQUENCE_NAME,
    AP_PARTNER_TYPE,
    BillStatus,
    DocumentType,
    TaxDirection,
)
from app.modules.finance.events import VendorBillPosted
from app.modules.finance.models import (
    Account,
    TaxCode,
    VendorBill,
    VendorBillLine,
)
from app.modules.finance.payables_schemas import VendorBillCreate
from app.modules.finance.schemas import JournalEntryCreate, JournalLineCreate
from app.modules.finance.service.journal import create_draft_entry, post_entry
from app.modules.finance.service.tax import calculate_line_tax


async def _require_account(
    session: AsyncSession, tenant_id: uuid.UUID, account_id: uuid.UUID, *, label: str
) -> Account:
    account = (
        await session.execute(
            select(Account).where(Account.tenant_id == tenant_id, Account.id == account_id)
        )
    ).scalar_one_or_none()
    if account is None:
        raise ValidationFailedError(
            message=f"The {label} account does not exist in this tenant",
            code="finance.ap_account_not_found",
            details={"account_id": str(account_id)},
        )
    return account


async def _tax_code(
    session: AsyncSession, tenant_id: uuid.UUID, tax_code_id: uuid.UUID
) -> TaxCode:
    tax_code = (
        await session.execute(
            select(TaxCode).where(TaxCode.tenant_id == tenant_id, TaxCode.id == tax_code_id)
        )
    ).scalar_one_or_none()
    if tax_code is None:
        raise ValidationFailedError(
            message="A line references an unknown tax code",
            code="finance.ap_tax_code_not_found",
            details={"tax_code_id": str(tax_code_id)},
        )
    return tax_code


async def get_vendor_bill(
    session: AsyncSession, tenant_id: uuid.UUID, bill_id: uuid.UUID
) -> VendorBill:
    bill = await session.get(VendorBill, bill_id)
    if bill is None or bill.tenant_id != tenant_id:
        raise NotFoundError(message="Vendor bill not found", code="finance.vendor_bill_not_found")
    return bill


async def get_vendor_bill_lines(
    session: AsyncSession, tenant_id: uuid.UUID, bill_id: uuid.UUID
) -> list[VendorBillLine]:
    stmt = (
        select(VendorBillLine)
        .where(VendorBillLine.tenant_id == tenant_id, VendorBillLine.bill_id == bill_id)
        .order_by(VendorBillLine.line_number)
    )
    return list((await session.execute(stmt)).scalars().all())


async def create_vendor_bill(
    session: AsyncSession, tenant_id: uuid.UUID, payload: VendorBillCreate
) -> VendorBill:
    """Create a DRAFT vendor bill + lines (PLAN 4.5). Validates the AP control + every line account
    exists; computes input tax per line via the shared tax engine (so net/tax/gross match Sales/AR)
    and rolls up the bill totals. Registers the document in core_documents with NO number (claimed
    at posting, D-012). ``open_amount`` stays 0 until posting. Does NOT post a journal entry."""
    if not payload.lines:
        raise ValidationFailedError(
            message="A vendor bill needs at least one line",
            code="finance.vendor_bill_no_lines",
        )
    await _require_account(session, tenant_id, payload.ap_account_id, label="AP control")

    gross_total = Decimal(0)
    tax_total = Decimal(0)
    net_total = Decimal(0)
    line_rows: list[dict[str, object]] = []
    for index, line in enumerate(payload.lines, start=1):
        await _require_account(session, tenant_id, line.account_id, label="line")
        net = quantize_for_currency(line.net_amount, payload.currency_code)
        tax_amount = Decimal(0)
        if line.tax_code_id is not None:
            tax_code = await _tax_code(session, tenant_id, line.tax_code_id)
            calc = calculate_line_tax(
                net, tax_code, direction=TaxDirection.INPUT, currency_code=payload.currency_code
            )
            net = calc.net_amount
            tax_amount = calc.tax_amount
        net_total += net
        tax_total += tax_amount
        gross_total += net + tax_amount
        line_rows.append(
            {
                "line_number": index,
                "account_id": line.account_id,
                "description": line.description,
                "net_amount": net,
                "tax_code_id": line.tax_code_id,
                "tax_amount": tax_amount,
                "cost_center_id": line.cost_center_id,
                "project_id": line.project_id,
            }
        )

    bill_id = uuid.uuid4()
    document = await docflow.register_document(
        session,
        tenant_id,
        AP_BILL_DOC_TYPE,
        bill_id,
        doc_number=None,
        status=BillStatus.DRAFT.value,
    )
    bill = VendorBill(
        id=bill_id,
        tenant_id=tenant_id,
        document_id=document.id,
        partner_id=payload.partner_id,
        partner_name=payload.partner_name,
        bill_external_ref=payload.bill_external_ref,
        bill_date=payload.bill_date,
        due_date=payload.due_date,
        currency_code=payload.currency_code,
        status=BillStatus.DRAFT.value,
        ap_account_id=payload.ap_account_id,
        gross_amount=gross_total,
        tax_amount=tax_total,
        net_amount=net_total,
        open_amount=Decimal(0),
        description=payload.description,
    )
    session.add(bill)
    for row in line_rows:
        session.add(VendorBillLine(tenant_id=tenant_id, bill_id=bill_id, **row))
    await session.flush()
    return bill


def _bill_journal_lines(
    bill: VendorBill, lines: list[VendorBillLine], tax_account_by_code: dict[uuid.UUID, uuid.UUID]
) -> list[JournalLineCreate]:
    """The balanced AP journal lines for a bill (PLAN 4.5): Dr each line's net to its expense/asset
    account, Dr input tax to the tax code's receivable account (one line per line with tax), Cr the
    AP control for the gross — partner_id stamped on the AP line so the open item is partner-keyed
    (D-029). Dimensions ride to the journal line so CO projections see them."""
    journal_lines: list[JournalLineCreate] = []
    for line in lines:
        journal_lines.append(
            JournalLineCreate(
                account_id=line.account_id,
                description=line.description,
                transaction_debit_amount=line.net_amount,
                cost_center_id=line.cost_center_id,
                project_id=line.project_id,
            )
        )
        if line.tax_amount and line.tax_code_id is not None:
            journal_lines.append(
                JournalLineCreate(
                    account_id=tax_account_by_code[line.tax_code_id],
                    description="Input tax",
                    transaction_debit_amount=line.tax_amount,
                )
            )
    journal_lines.append(
        JournalLineCreate(
            account_id=bill.ap_account_id,
            description=f"AP {bill.partner_name}",
            transaction_credit_amount=bill.gross_amount,
            partner_type=AP_PARTNER_TYPE,
            partner_id=bill.partner_id,
        )
    )
    return journal_lines


async def _resolve_tax_accounts(
    session: AsyncSession, tenant_id: uuid.UUID, lines: list[VendorBillLine]
) -> dict[uuid.UUID, uuid.UUID]:
    """Map each line's tax_code_id -> its receivable (INPUT) account (PLAN 4.5). Raises a clear 422
    if a code that levied tax has no receivable account wired (the tax engine would otherwise post
    to None)."""
    accounts: dict[uuid.UUID, uuid.UUID] = {}
    for line in lines:
        if not line.tax_amount or line.tax_code_id is None or line.tax_code_id in accounts:
            continue
        tax_code = await _tax_code(session, tenant_id, line.tax_code_id)
        if tax_code.tax_receivable_account_id is None:
            raise ValidationFailedError(
                message=f"Tax code {tax_code.code} has no input-tax (receivable) account",
                code="finance.ap_tax_account_unwired",
                details={"tax_code_id": str(line.tax_code_id)},
            )
        accounts[line.tax_code_id] = tax_code.tax_receivable_account_id
    return accounts


async def post_vendor_bill(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    bill_id: uuid.UUID,
    *,
    posting_date: date | None = None,
) -> VendorBill:
    """Post a DRAFT vendor bill to the journal (PLAN 4.5). Idempotent: an already-POSTED bill is
    returned unchanged. Builds the balanced AP entry (document_type AP_BILL), posts it via the
    journal engine (which claims the entry number, resolves the period, and translates FX at the
    posting rate, D-019), claims the bill's gapless system number, links bill->journal (docflow
    'posts'), sets ``open_amount`` = gross + status POSTED, and publishes ``VendorBillPosted``.
    ``posting_date`` defaults to the bill date."""
    bill = await get_vendor_bill(session, tenant_id, bill_id)
    if bill.status == BillStatus.POSTED.value:
        return bill
    if bill.status != BillStatus.DRAFT.value:
        raise ConflictError(
            message="Only a draft vendor bill can be posted",
            code="finance.vendor_bill_not_draft",
            details={"status": bill.status},
        )

    lines = await get_vendor_bill_lines(session, tenant_id, bill_id)
    tax_account_by_code = await _resolve_tax_accounts(session, tenant_id, lines)

    entry = await create_draft_entry(
        session,
        tenant_id,
        JournalEntryCreate(
            posting_date=posting_date or bill.bill_date,
            currency_code=bill.currency_code,
            description=f"Vendor bill {bill.partner_name}",
            document_type=DocumentType.AP_INVOICE,
            lines=_bill_journal_lines(bill, lines, tax_account_by_code),
        ),
    )
    await post_entry(session, tenant_id, entry.id)

    await ensure_sequence(
        session,
        tenant_id,
        AP_BILL_SEQUENCE_NAME,
        AP_BILL_NUMBER_PREFIX,
        AP_BILL_NUMBER_PADDING,
        year_reset=True,
    )
    bill_number = await claim_number(
        session, tenant_id, AP_BILL_SEQUENCE_NAME, on_date=bill.bill_date
    )

    bill.bill_number = bill_number
    bill.journal_entry_id = entry.id
    bill.open_amount = bill.gross_amount
    bill.status = BillStatus.POSTED.value
    await session.flush()

    await docflow.set_document_status(
        session, tenant_id, bill.document_id, status=BillStatus.POSTED.value, doc_number=bill_number
    )
    await docflow.link_documents(
        session,
        tenant_id,
        predecessor=bill.document_id,
        successor=entry.document_id,
        link_type=AP_BILL_POSTS_LINK,
    )

    publish(
        session,
        VendorBillPosted(
            tenant_id=tenant_id,
            bill_id=bill.id,
            bill_number=bill_number,
            journal_entry_id=entry.id,
            partner_id=bill.partner_id,
            currency_code=bill.currency_code,
            gross_amount=bill.gross_amount,
            tax_amount=bill.tax_amount,
            net_amount=bill.net_amount,
        ),
    )
    return bill


async def list_vendor_bills(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    cursor: str | None,
    limit: int,
    status: str | None = None,
    partner_id: uuid.UUID | None = None,
) -> object:
    """Keyset-paginated bill list, newest bill_date first (D-014). ``status`` + ``partner_id``
    filters fold into the cursor fingerprint. Returns a ``Page`` of ORM objects."""
    from app.core.pagination import OrderKey, SortDirection, filter_fingerprint, paginate

    stmt = select(VendorBill).where(VendorBill.tenant_id == tenant_id)
    if status is not None:
        stmt = stmt.where(VendorBill.status == BillStatus(status).value)
    if partner_id is not None:
        stmt = stmt.where(VendorBill.partner_id == partner_id)
    return await paginate(
        session,
        stmt,
        order_by=[
            OrderKey(VendorBill.bill_date, SortDirection.DESC),
            OrderKey(VendorBill.created_at, SortDirection.DESC),
        ],
        pk=VendorBill.id,
        cursor=cursor,
        limit=limit,
        filters=filter_fingerprint(status, partner_id),
    )
