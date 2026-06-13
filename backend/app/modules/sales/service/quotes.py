"""Sales-quotation business logic (PLAN 7.2): create, send, accept/reject, update, cancel, expiry
handling + reads.

Lifecycle (constants.QuoteStatus): DRAFT → SENT → ACCEPTED/REJECTED, DRAFT/SENT → EXPIRED (on
``valid_until`` lapse), DRAFT/SENT/ACCEPTED → CANCELLED, ACCEPTED → CONVERTED (the conversion
service flips this). All transitions are wholly sales-internal — sending/accepting a quote moves no
money or stock, so MANAGE covers every action (no committing gate).

The QUO number is claimed AT CREATION (D-012/D-040) and the document is registered in core_documents
then. Lines default their ``unit_price`` from the price resolver (D-043) and compute their net
amount from the optional per-line discount; the header ``total_amount`` is the maintained Σ
line_amount. Idempotency (D-013) is owned by the endpoints.

**Expiry (decided here, kept simple).** A quote past ``valid_until`` is EXPIRED. There is no
background sweep in v1: ``mark_expired_if_lapsed`` is a lazy check the read paths call so a
DRAFT/SENT
quote whose validity has lapsed is moved to EXPIRED on next access, and ``mark_quote_expired`` is
the
explicit action. An ACCEPTED/CONVERTED/REJECTED/CANCELLED quote is never auto-expired (it has
already
left the open window).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.pagination import (
    DEFAULT_LIMIT,
    OrderKey,
    SortDirection,
    filter_fingerprint,
    paginate,
)
from app.core.schemas import Page
from app.modules.sales.constants import (
    QUOTE_DOC_TYPE,
    QUOTE_NUMBER_PADDING,
    QUOTE_NUMBER_PREFIX,
    QUOTE_SEQUENCE_NAME,
    QuoteStatus,
)
from app.modules.sales.models import Quote, QuoteLine
from app.modules.sales.schemas import QuoteCreate, QuoteUpdate
from app.modules.sales.service._shared import (
    LineInput,
    build_line_input,
    claim_document_number,
    require_customer_exists,
    resolve_currency,
)


async def get_quote(session: AsyncSession, tenant_id: uuid.UUID, quote_id: uuid.UUID) -> Quote:
    quote = await session.get(Quote, quote_id)
    if quote is None or quote.tenant_id != tenant_id:
        raise NotFoundError(message="Quote not found", code="sales.quote_not_found")
    return quote


async def get_quote_lines(
    session: AsyncSession, tenant_id: uuid.UUID, quote_id: uuid.UUID
) -> list[QuoteLine]:
    stmt = (
        select(QuoteLine)
        .where(QuoteLine.tenant_id == tenant_id, QuoteLine.quote_id == quote_id)
        .order_by(QuoteLine.line_number)
    )
    return list((await session.execute(stmt)).scalars().all())


async def _build_lines(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    customer_id: uuid.UUID,
    currency_code: str,
    on_date: date,
    payload_lines: list,
) -> list[LineInput]:
    if not payload_lines:
        raise ValidationFailedError(
            message="A quote needs at least one line", code="sales.quote_no_lines"
        )
    return [
        await build_line_input(
            session,
            tenant_id,
            customer_id=customer_id,
            currency_code=currency_code,
            on_date=on_date,
            item_id=line.item_id,
            description=line.description,
            quantity=Decimal(str(line.quantity)),
            uom_id=line.uom_id,
            unit_price=line.unit_price,
            discount_type=line.discount_type,
            discount_value=line.discount_value,
        )
        for line in payload_lines
    ]


def _write_lines(
    session: AsyncSession, tenant_id: uuid.UUID, quote_id: uuid.UUID, lines: list[LineInput]
) -> Decimal:
    total = Decimal(0)
    for index, line in enumerate(lines, start=1):
        total += line.line_amount
        session.add(
            QuoteLine(
                tenant_id=tenant_id,
                quote_id=quote_id,
                line_number=index,
                item_id=line.item_id,
                description=line.description,
                quantity=line.quantity,
                uom_id=line.uom_id,
                unit_price=line.unit_price,
                discount_type=line.discount_type,
                discount_value=line.discount_value,
                line_amount=line.line_amount,
            )
        )
    return total


async def create_quote(
    session: AsyncSession, tenant_id: uuid.UUID, payload: QuoteCreate
) -> Quote:
    """Create a DRAFT quote + lines (PLAN 7.2). Validates the customer exists, resolves the currency
    (supplied or the customer's default), prices each line (resolver default + discount), computes
    the total, and claims the QUO number + registers the document AT CREATION (D-012/D-040)."""
    await require_customer_exists(session, tenant_id, payload.customer_id)
    quote_date = payload.quote_date or date.today()
    currency = await resolve_currency(
        session, tenant_id, payload.customer_id, payload.currency_code
    )
    lines = await _build_lines(
        session,
        tenant_id,
        customer_id=payload.customer_id,
        currency_code=currency,
        on_date=quote_date,
        payload_lines=payload.lines,
    )

    quote_id = uuid.uuid4()
    document = await docflow.register_document(
        session, tenant_id, QUOTE_DOC_TYPE, quote_id, doc_number=None,
        status=QuoteStatus.DRAFT.value
    )
    number = await claim_document_number(
        session,
        tenant_id,
        sequence_name=QUOTE_SEQUENCE_NAME,
        prefix=QUOTE_NUMBER_PREFIX,
        padding=QUOTE_NUMBER_PADDING,
        on_date=quote_date,
    )
    quote = Quote(
        id=quote_id,
        tenant_id=tenant_id,
        document_id=document.id,
        quote_number=number,
        status=QuoteStatus.DRAFT.value,
        customer_id=payload.customer_id,
        currency_code=currency,
        quote_date=quote_date,
        valid_until=payload.valid_until,
        total_amount=Decimal(0),
        notes=payload.notes,
    )
    session.add(quote)
    quote.total_amount = _write_lines(session, tenant_id, quote_id, lines)
    await session.flush()
    await docflow.set_document_status(
        session, tenant_id, document.id, doc_number=number, status=QuoteStatus.DRAFT.value
    )
    return quote


async def update_quote(
    session: AsyncSession, tenant_id: uuid.UUID, quote_id: uuid.UUID, payload: QuoteUpdate
) -> Quote:
    """Partial header update of a DRAFT quote (PLAN 7.2). When ``lines`` is supplied they are
    replaced wholesale (revalidated + repriced + the total recomputed). Only a DRAFT quote is
    editable."""
    quote = await get_quote(session, tenant_id, quote_id)
    if QuoteStatus(quote.status) != QuoteStatus.DRAFT:
        raise ConflictError(
            message="Only a draft quote can be edited",
            code="sales.quote_not_draft",
            details={"status": quote.status},
        )
    data = payload.model_dump(exclude_unset=True)
    new_lines = data.pop("lines", None)
    if "currency_code" in data and data["currency_code"] is not None:
        quote.currency_code = await resolve_currency(
            session, tenant_id, quote.customer_id, data.pop("currency_code")
        )
    else:
        data.pop("currency_code", None)
    for field, value in data.items():
        setattr(quote, field, value)
    if new_lines is not None:
        lines = await _build_lines(
            session,
            tenant_id,
            customer_id=quote.customer_id,
            currency_code=quote.currency_code,
            on_date=quote.quote_date,
            payload_lines=payload.lines,
        )
        for existing in await get_quote_lines(session, tenant_id, quote_id):
            await session.delete(existing)
        await session.flush()
        quote.total_amount = _write_lines(session, tenant_id, quote_id, lines)
    await session.flush()
    return quote


async def _set_status(
    session: AsyncSession, tenant_id: uuid.UUID, quote: Quote, status: QuoteStatus
) -> Quote:
    quote.status = status.value
    await session.flush()
    await docflow.set_document_status(session, tenant_id, quote.document_id, status=status.value)
    return quote


async def send_quote(session: AsyncSession, tenant_id: uuid.UUID, quote_id: uuid.UUID) -> Quote:
    """Issue a DRAFT quote to the customer (PLAN 7.2): DRAFT → SENT. Only a DRAFT quote is
    sendable."""
    quote = await get_quote(session, tenant_id, quote_id)
    if QuoteStatus(quote.status) != QuoteStatus.DRAFT:
        raise ConflictError(
            message="Only a draft quote can be sent",
            code="sales.quote_not_sendable",
            details={"status": quote.status},
        )
    return await _set_status(session, tenant_id, quote, QuoteStatus.SENT)


async def accept_quote(session: AsyncSession, tenant_id: uuid.UUID, quote_id: uuid.UUID) -> Quote:
    """Record the customer's acceptance (PLAN 7.2): SENT → ACCEPTED. Only a SENT quote can be
    accepted; an ACCEPTED quote is the only state convertible to an order."""
    quote = await get_quote(session, tenant_id, quote_id)
    if QuoteStatus(quote.status) != QuoteStatus.SENT:
        raise ConflictError(
            message="Only a sent quote can be accepted",
            code="sales.quote_not_acceptable",
            details={"status": quote.status},
        )
    return await _set_status(session, tenant_id, quote, QuoteStatus.ACCEPTED)


async def reject_quote(session: AsyncSession, tenant_id: uuid.UUID, quote_id: uuid.UUID) -> Quote:
    """Record the customer's rejection (PLAN 7.2): SENT → REJECTED; terminal."""
    quote = await get_quote(session, tenant_id, quote_id)
    if QuoteStatus(quote.status) != QuoteStatus.SENT:
        raise ConflictError(
            message="Only a sent quote can be rejected",
            code="sales.quote_not_rejectable",
            details={"status": quote.status},
        )
    return await _set_status(session, tenant_id, quote, QuoteStatus.REJECTED)


async def cancel_quote(session: AsyncSession, tenant_id: uuid.UUID, quote_id: uuid.UUID) -> Quote:
    """Cancel a quote (PLAN 7.2). Allowed from DRAFT/SENT/ACCEPTED; a CONVERTED quote (it has a
    successor order) and a terminal one cannot be cancelled."""
    quote = await get_quote(session, tenant_id, quote_id)
    if QuoteStatus(quote.status) in (
        QuoteStatus.CONVERTED,
        QuoteStatus.REJECTED,
        QuoteStatus.EXPIRED,
        QuoteStatus.CANCELLED,
    ):
        raise ConflictError(
            message=f"A {quote.status} quote cannot be cancelled",
            code="sales.quote_not_cancellable",
            details={"status": quote.status},
        )
    return await _set_status(session, tenant_id, quote, QuoteStatus.CANCELLED)


async def mark_quote_expired(
    session: AsyncSession, tenant_id: uuid.UUID, quote_id: uuid.UUID
) -> Quote:
    """Explicitly mark a DRAFT/SENT quote EXPIRED (PLAN 7.2): only an OPEN quote whose
    ``valid_until``
    has passed can be expired. Raises if there is no expiry date or it has not lapsed, or the quote
    has already left the open window."""
    quote = await get_quote(session, tenant_id, quote_id)
    if QuoteStatus(quote.status) not in (QuoteStatus.DRAFT, QuoteStatus.SENT):
        raise ConflictError(
            message="Only an open (draft or sent) quote can expire",
            code="sales.quote_not_expirable",
            details={"status": quote.status},
        )
    if quote.valid_until is None or quote.valid_until >= date.today():
        raise ValidationFailedError(
            message="The quote has no past validity date",
            code="sales.quote_not_lapsed",
            details={"valid_until": str(quote.valid_until)},
        )
    return await _set_status(session, tenant_id, quote, QuoteStatus.EXPIRED)


async def mark_expired_if_lapsed(
    session: AsyncSession, tenant_id: uuid.UUID, quote: Quote
) -> Quote:
    """Lazy expiry on access: if ``quote`` is DRAFT/SENT and its ``valid_until`` has passed, move it
    to EXPIRED in the caller's transaction; otherwise return it unchanged. The read paths call this
    so an open quote whose validity has lapsed is reflected as EXPIRED without a background
    sweep."""
    if (
        QuoteStatus(quote.status) in (QuoteStatus.DRAFT, QuoteStatus.SENT)
        and quote.valid_until is not None
        and quote.valid_until < date.today()
    ):
        return await _set_status(session, tenant_id, quote, QuoteStatus.EXPIRED)
    return quote


async def list_quotes(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    status: QuoteStatus | None = None,
    customer_id: uuid.UUID | None = None,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Page[Quote]:
    """Keyset-paginated quote list, newest first (D-014). status + customer filters fold into the
    cursor fingerprint; the (tenant, status) / (tenant, customer_id, status) indexes serve the
    filtered page (PERFORMANCE §1)."""
    stmt = select(Quote).where(Quote.tenant_id == tenant_id)
    if status is not None:
        stmt = stmt.where(Quote.status == QuoteStatus(status).value)
    if customer_id is not None:
        stmt = stmt.where(Quote.customer_id == customer_id)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(Quote.created_at, SortDirection.DESC)],
        pk=Quote.id,
        cursor=cursor,
        limit=limit,
        filters=filter_fingerprint(status, customer_id),
    )
