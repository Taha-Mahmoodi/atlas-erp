"""Customer-invoice lifecycle: draft creation + posting through the journal (PLAN 4.6, AR).

The AP ``vendor_bills.py`` mirror with the sign flipped. ``create_customer_invoice`` computes the
output tax (via the shared tax engine) and totals on a DRAFT; ``post_customer_invoice`` builds and
posts the AR journal entry (Dr the AR control for the gross — with the opaque ``partner_id`` stamped
on the AR line, D-029 — Cr each revenue line net, Cr output tax to the tax code's payable account),
claims the gapless system number (D-012), links the invoice document to its journal entry (docflow),
sets ``open_amount`` = gross, and publishes ``CustomerInvoicePosted``. Idempotent at the service
level: a re-post of an already-POSTED invoice returns it unchanged.

The journal engine handles FX translation at posting (D-019): a foreign-currency invoice's
functional amounts are frozen at the posting-date SPOT rate by the same machinery every entry uses.
Finance stays the bottom dependency — this module imports no other module.
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
    AR_INVOICE_DOC_TYPE,
    AR_INVOICE_NUMBER_PADDING,
    AR_INVOICE_NUMBER_PREFIX,
    AR_INVOICE_POSTS_LINK,
    AR_INVOICE_SEQUENCE_NAME,
    AR_PARTNER_TYPE,
    DocumentType,
    InvoiceStatus,
    TaxDirection,
)
from app.modules.finance.events import CustomerInvoicePosted
from app.modules.finance.models import (
    Account,
    CustomerInvoice,
    CustomerInvoiceLine,
    TaxCode,
)
from app.modules.finance.receivables_schemas import CustomerInvoiceCreate
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
            code="finance.ar_account_not_found",
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
            code="finance.ar_tax_code_not_found",
            details={"tax_code_id": str(tax_code_id)},
        )
    return tax_code


async def get_customer_invoice(
    session: AsyncSession, tenant_id: uuid.UUID, invoice_id: uuid.UUID
) -> CustomerInvoice:
    invoice = await session.get(CustomerInvoice, invoice_id)
    if invoice is None or invoice.tenant_id != tenant_id:
        raise NotFoundError(
            message="Customer invoice not found", code="finance.customer_invoice_not_found"
        )
    return invoice


async def get_customer_invoice_lines(
    session: AsyncSession, tenant_id: uuid.UUID, invoice_id: uuid.UUID
) -> list[CustomerInvoiceLine]:
    stmt = (
        select(CustomerInvoiceLine)
        .where(
            CustomerInvoiceLine.tenant_id == tenant_id,
            CustomerInvoiceLine.invoice_id == invoice_id,
        )
        .order_by(CustomerInvoiceLine.line_number)
    )
    return list((await session.execute(stmt)).scalars().all())


async def create_customer_invoice(
    session: AsyncSession, tenant_id: uuid.UUID, payload: CustomerInvoiceCreate
) -> CustomerInvoice:
    """Create a DRAFT customer invoice + lines (PLAN 4.6). Validates the AR control + every line
    account exists; computes output tax per line via the shared tax engine (so net/tax/gross match
    AP) and rolls up the invoice totals. Registers the document in core_documents with NO number
    (claimed at posting, D-012). ``open_amount`` stays 0 until posting. Does NOT post a journal."""
    if not payload.lines:
        raise ValidationFailedError(
            message="A customer invoice needs at least one line",
            code="finance.customer_invoice_no_lines",
        )
    await _require_account(session, tenant_id, payload.ar_account_id, label="AR control")

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
                net, tax_code, direction=TaxDirection.OUTPUT, currency_code=payload.currency_code
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
                "profit_center_id": line.profit_center_id,
                "project_id": line.project_id,
            }
        )

    invoice_id = uuid.uuid4()
    document = await docflow.register_document(
        session,
        tenant_id,
        AR_INVOICE_DOC_TYPE,
        invoice_id,
        doc_number=None,
        status=InvoiceStatus.DRAFT.value,
    )
    invoice = CustomerInvoice(
        id=invoice_id,
        tenant_id=tenant_id,
        document_id=document.id,
        partner_id=payload.partner_id,
        partner_name=payload.partner_name,
        external_ref=payload.external_ref,
        invoice_date=payload.invoice_date,
        due_date=payload.due_date,
        currency_code=payload.currency_code,
        status=InvoiceStatus.DRAFT.value,
        ar_account_id=payload.ar_account_id,
        gross_amount=gross_total,
        tax_amount=tax_total,
        net_amount=net_total,
        open_amount=Decimal(0),
        dunning_level=0,
        description=payload.description,
    )
    session.add(invoice)
    for row in line_rows:
        session.add(CustomerInvoiceLine(tenant_id=tenant_id, invoice_id=invoice_id, **row))
    await session.flush()
    return invoice


def _invoice_journal_lines(
    invoice: CustomerInvoice,
    lines: list[CustomerInvoiceLine],
    tax_account_by_code: dict[uuid.UUID, uuid.UUID],
) -> list[JournalLineCreate]:
    """The balanced AR journal lines for an invoice (PLAN 4.6): Dr the AR control for the gross —
    partner_id stamped on the AR line so the open item is partner-keyed (D-029) — Cr each line's net
    to its revenue account, Cr output tax to the tax code's payable account (one line per line with
    tax). Dimensions ride to the journal line so CO projections see them."""
    journal_lines: list[JournalLineCreate] = [
        JournalLineCreate(
            account_id=invoice.ar_account_id,
            description=f"AR {invoice.partner_name}",
            transaction_debit_amount=invoice.gross_amount,
            partner_type=AR_PARTNER_TYPE,
            partner_id=invoice.partner_id,
        )
    ]
    for line in lines:
        journal_lines.append(
            JournalLineCreate(
                account_id=line.account_id,
                description=line.description,
                transaction_credit_amount=line.net_amount,
                cost_center_id=line.cost_center_id,
                profit_center_id=line.profit_center_id,
                project_id=line.project_id,
            )
        )
        if line.tax_amount and line.tax_code_id is not None:
            journal_lines.append(
                JournalLineCreate(
                    account_id=tax_account_by_code[line.tax_code_id],
                    description="Output tax",
                    transaction_credit_amount=line.tax_amount,
                )
            )
    return journal_lines


async def _resolve_tax_accounts(
    session: AsyncSession, tenant_id: uuid.UUID, lines: list[CustomerInvoiceLine]
) -> dict[uuid.UUID, uuid.UUID]:
    """Map each line's tax_code_id -> its payable (OUTPUT) account (PLAN 4.6). Raises a clear 422 if
    a code that levied tax has no payable account wired (the tax engine would otherwise post to
    None)."""
    accounts: dict[uuid.UUID, uuid.UUID] = {}
    for line in lines:
        if not line.tax_amount or line.tax_code_id is None or line.tax_code_id in accounts:
            continue
        tax_code = await _tax_code(session, tenant_id, line.tax_code_id)
        if tax_code.tax_payable_account_id is None:
            raise ValidationFailedError(
                message=f"Tax code {tax_code.code} has no output-tax (payable) account",
                code="finance.ar_tax_account_unwired",
                details={"tax_code_id": str(line.tax_code_id)},
            )
        accounts[line.tax_code_id] = tax_code.tax_payable_account_id
    return accounts


async def post_customer_invoice(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    invoice_id: uuid.UUID,
    *,
    posting_date: date | None = None,
) -> CustomerInvoice:
    """Post a DRAFT customer invoice to the journal (PLAN 4.6). Idempotent: an already-POSTED
    invoice is returned unchanged. Builds the balanced AR entry (document_type AR_INVOICE), posts it
    via the journal engine (which claims the entry number, resolves the period, and translates FX at
    the posting rate, D-019), claims the invoice's gapless system number, links invoice->journal
    (docflow 'posts'), sets ``open_amount`` = gross + status POSTED, and publishes
    ``CustomerInvoicePosted``. ``posting_date`` defaults to the invoice date."""
    invoice = await get_customer_invoice(session, tenant_id, invoice_id)
    if invoice.status == InvoiceStatus.POSTED.value:
        return invoice
    if invoice.status != InvoiceStatus.DRAFT.value:
        raise ConflictError(
            message="Only a draft customer invoice can be posted",
            code="finance.customer_invoice_not_draft",
            details={"status": invoice.status},
        )

    lines = await get_customer_invoice_lines(session, tenant_id, invoice_id)
    tax_account_by_code = await _resolve_tax_accounts(session, tenant_id, lines)

    entry = await create_draft_entry(
        session,
        tenant_id,
        JournalEntryCreate(
            posting_date=posting_date or invoice.invoice_date,
            currency_code=invoice.currency_code,
            description=f"Customer invoice {invoice.partner_name}",
            document_type=DocumentType.AR_INVOICE,
            lines=_invoice_journal_lines(invoice, lines, tax_account_by_code),
        ),
    )
    await post_entry(session, tenant_id, entry.id)

    await ensure_sequence(
        session,
        tenant_id,
        AR_INVOICE_SEQUENCE_NAME,
        AR_INVOICE_NUMBER_PREFIX,
        AR_INVOICE_NUMBER_PADDING,
        year_reset=True,
    )
    invoice_number = await claim_number(
        session, tenant_id, AR_INVOICE_SEQUENCE_NAME, on_date=invoice.invoice_date
    )

    invoice.invoice_number = invoice_number
    invoice.journal_entry_id = entry.id
    invoice.open_amount = invoice.gross_amount
    invoice.status = InvoiceStatus.POSTED.value
    await session.flush()

    await docflow.set_document_status(
        session,
        tenant_id,
        invoice.document_id,
        status=InvoiceStatus.POSTED.value,
        doc_number=invoice_number,
    )
    await docflow.link_documents(
        session,
        tenant_id,
        predecessor=invoice.document_id,
        successor=entry.document_id,
        link_type=AR_INVOICE_POSTS_LINK,
    )

    publish(
        session,
        CustomerInvoicePosted(
            tenant_id=tenant_id,
            invoice_id=invoice.id,
            invoice_number=invoice_number,
            journal_entry_id=entry.id,
            partner_id=invoice.partner_id,
            currency_code=invoice.currency_code,
            gross_amount=invoice.gross_amount,
            tax_amount=invoice.tax_amount,
            net_amount=invoice.net_amount,
        ),
    )
    return invoice


async def list_customer_invoices(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    cursor: str | None,
    limit: int,
    status: str | None = None,
    partner_id: uuid.UUID | None = None,
) -> object:
    """Keyset-paginated invoice list, newest invoice_date first (D-014). ``status`` + ``partner_id``
    filters fold into the cursor fingerprint. Returns a ``Page`` of ORM objects."""
    from app.core.pagination import OrderKey, SortDirection, filter_fingerprint, paginate

    stmt = select(CustomerInvoice).where(CustomerInvoice.tenant_id == tenant_id)
    if status is not None:
        stmt = stmt.where(CustomerInvoice.status == InvoiceStatus(status).value)
    if partner_id is not None:
        stmt = stmt.where(CustomerInvoice.partner_id == partner_id)
    return await paginate(
        session,
        stmt,
        order_by=[
            OrderKey(CustomerInvoice.invoice_date, SortDirection.DESC),
            OrderKey(CustomerInvoice.created_at, SortDirection.DESC),
        ],
        pk=CustomerInvoice.id,
        cursor=cursor,
        limit=limit,
        filters=filter_fingerprint(status, partner_id),
    )
