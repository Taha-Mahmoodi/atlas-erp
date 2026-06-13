"""Sales-order business logic (PLAN 7.2): create from scratch, update, cancel + reads, plus the
shared line/total writer both the from-scratch and convert paths use.

Lifecycle (constants.SalesOrderStatus) — states SET in 7.2: DRAFT → (confirm) CONFIRMED or
CREDIT_BLOCKED, plus CANCELLED. PARTIALLY_DELIVERED / DELIVERED / INVOICED / CLOSED are driven by
7.3/7.4 (declared in constants, transitions land later). The confirm gate (ATP + credit) lives in
``order_confirm.py``; the quote→order conversion lives in ``conversions.py``; the shared writer +
the document reads live here so both paths produce identical order rows.

Source-control rule at create: the customer must be ACTIVE (not BLOCKED/INACTIVE → 422
sales.customer_not_active — the soft block, distinct from the credit-limit block). ``line_amount`` =
qty × unit_price − discount; ``total_amount`` = Σ line_amount; ``payment_terms_days`` is snapshot
from the customer at create. The SO number is claimed AT CREATION (D-012/D-040). An order starts
DRAFT; confirmation is the gate.
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
from app.modules.sales import queries as sales_queries
from app.modules.sales.constants import (
    SALES_ORDER_DOC_TYPE,
    SALES_ORDER_NUMBER_PADDING,
    SALES_ORDER_NUMBER_PREFIX,
    SALES_ORDER_SEQUENCE_NAME,
    SalesOrderStatus,
)
from app.modules.sales.models import SalesOrder, SalesOrderLine
from app.modules.sales.schemas import SalesOrderCreate, SalesOrderUpdate
from app.modules.sales.service._shared import (
    LineInput,
    build_line_input,
    claim_document_number,
    require_active_customer,
    resolve_currency,
    validate_quantity,
)


async def get_sales_order(
    session: AsyncSession, tenant_id: uuid.UUID, order_id: uuid.UUID
) -> SalesOrder:
    order = await session.get(SalesOrder, order_id)
    if order is None or order.tenant_id != tenant_id:
        raise NotFoundError(message="Sales order not found", code="sales.order_not_found")
    return order


async def get_sales_order_lines(
    session: AsyncSession, tenant_id: uuid.UUID, order_id: uuid.UUID
) -> list[SalesOrderLine]:
    stmt = (
        select(SalesOrderLine)
        .where(SalesOrderLine.tenant_id == tenant_id, SalesOrderLine.order_id == order_id)
        .order_by(SalesOrderLine.line_number)
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
            message="A sales order needs at least one line", code="sales.order_no_lines"
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
            tax_code_id=getattr(line, "tax_code_id", None),
        )
        for line in payload_lines
    ]


def _write_lines(
    session: AsyncSession, tenant_id: uuid.UUID, order_id: uuid.UUID, lines: list[LineInput]
) -> Decimal:
    total = Decimal(0)
    for index, line in enumerate(lines, start=1):
        total += line.line_amount
        session.add(
            SalesOrderLine(
                tenant_id=tenant_id,
                order_id=order_id,
                line_number=index,
                item_id=line.item_id,
                description=line.description,
                ordered_quantity=line.quantity,
                uom_id=line.uom_id,
                unit_price=line.unit_price,
                discount_type=line.discount_type,
                discount_value=line.discount_value,
                line_amount=line.line_amount,
                delivered_quantity=Decimal(0),
                invoiced_quantity=Decimal(0),
                tax_code_id=line.tax_code_id,
            )
        )
    return total


async def write_sales_order(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    customer_id: uuid.UUID,
    currency_code: str,
    order_date: date,
    requested_date: date | None,
    notes: str | None,
    lines: list[LineInput],
    source_quote_id: uuid.UUID | None = None,
) -> SalesOrder:
    """Write a DRAFT order header + lines (the shared writer for from-scratch + convert paths).
    Snapshots the customer's payment-terms, claims the SO number + registers the document AT
    CREATION
    (D-012/D-040), and computes ``total_amount``. The caller has already validated the customer is
    ACTIVE and resolved/priced the lines."""
    if not lines:
        raise ValidationFailedError(
            message="A sales order needs at least one line", code="sales.order_no_lines"
        )
    terms = await sales_queries.customer_payment_terms_days(session, tenant_id, customer_id)

    order_id = uuid.uuid4()
    document = await docflow.register_document(
        session,
        tenant_id,
        SALES_ORDER_DOC_TYPE,
        order_id,
        doc_number=None,
        status=SalesOrderStatus.DRAFT.value,
    )
    number = await claim_document_number(
        session,
        tenant_id,
        sequence_name=SALES_ORDER_SEQUENCE_NAME,
        prefix=SALES_ORDER_NUMBER_PREFIX,
        padding=SALES_ORDER_NUMBER_PADDING,
        on_date=order_date,
    )
    order = SalesOrder(
        id=order_id,
        tenant_id=tenant_id,
        document_id=document.id,
        order_number=number,
        status=SalesOrderStatus.DRAFT.value,
        customer_id=customer_id,
        currency_code=currency_code,
        order_date=order_date,
        requested_date=requested_date,
        payment_terms_days=terms or 0,
        total_amount=Decimal(0),
        source_quote_id=source_quote_id,
        credit_check_status=None,
        notes=notes,
    )
    session.add(order)
    order.total_amount = _write_lines(session, tenant_id, order_id, lines)
    await session.flush()
    await docflow.set_document_status(
        session, tenant_id, document.id, doc_number=number, status=SalesOrderStatus.DRAFT.value
    )
    return order


async def create_sales_order(
    session: AsyncSession, tenant_id: uuid.UUID, payload: SalesOrderCreate
) -> SalesOrder:
    """Create a DRAFT order from scratch (PLAN 7.2). Validates the customer is ACTIVE, resolves the
    currency (supplied or the customer's default), prices each line (resolver default + discount),
    then writes the document via the shared writer."""
    await require_active_customer(session, tenant_id, payload.customer_id)
    order_date = payload.order_date or date.today()
    currency = await resolve_currency(
        session, tenant_id, payload.customer_id, payload.currency_code
    )
    lines = await _build_lines(
        session,
        tenant_id,
        customer_id=payload.customer_id,
        currency_code=currency,
        on_date=order_date,
        payload_lines=payload.lines,
    )
    return await write_sales_order(
        session,
        tenant_id,
        customer_id=payload.customer_id,
        currency_code=currency,
        order_date=order_date,
        requested_date=payload.requested_date,
        notes=payload.notes,
        lines=lines,
    )


async def update_sales_order(
    session: AsyncSession, tenant_id: uuid.UUID, order_id: uuid.UUID, payload: SalesOrderUpdate
) -> SalesOrder:
    """Partial header update of a DRAFT order (PLAN 7.2). When ``lines`` is supplied they are
    replaced wholesale (revalidated + repriced + the total recomputed). Only a DRAFT order is
    editable — a CONFIRMED order is a firm commitment."""
    order = await get_sales_order(session, tenant_id, order_id)
    if SalesOrderStatus(order.status) != SalesOrderStatus.DRAFT:
        raise ConflictError(
            message="Only a draft sales order can be edited",
            code="sales.order_not_draft",
            details={"status": order.status},
        )
    data = payload.model_dump(exclude_unset=True)
    new_lines = data.pop("lines", None)
    if "currency_code" in data and data["currency_code"] is not None:
        order.currency_code = await resolve_currency(
            session, tenant_id, order.customer_id, data.pop("currency_code")
        )
    else:
        data.pop("currency_code", None)
    for field, value in data.items():
        setattr(order, field, value)
    if new_lines is not None:
        lines = await _build_lines(
            session,
            tenant_id,
            customer_id=order.customer_id,
            currency_code=order.currency_code,
            on_date=order.order_date,
            payload_lines=payload.lines,
        )
        for existing in await get_sales_order_lines(session, tenant_id, order_id):
            await session.delete(existing)
        await session.flush()
        order.total_amount = _write_lines(session, tenant_id, order_id, lines)
    await session.flush()
    return order


async def cancel_sales_order(
    session: AsyncSession, tenant_id: uuid.UUID, order_id: uuid.UUID
) -> SalesOrder:
    """Cancel an order (PLAN 7.2). Forbidden once any delivery (7.3) or invoice (7.4) exists, or if
    already terminal — a delivered/invoiced order is corrected downstream, never cancelled. A DRAFT,
    CONFIRMED or CREDIT_BLOCKED order with no fulfilment can be cancelled."""
    order = await get_sales_order(session, tenant_id, order_id)
    status = SalesOrderStatus(order.status)
    if status in (
        SalesOrderStatus.PARTIALLY_DELIVERED,
        SalesOrderStatus.DELIVERED,
        SalesOrderStatus.INVOICED,
        SalesOrderStatus.CLOSED,
        SalesOrderStatus.CANCELLED,
    ):
        raise ConflictError(
            message=f"A {order.status} sales order cannot be cancelled",
            code="sales.order_not_cancellable",
            details={"status": order.status},
        )
    # Defence in depth: even for a CONFIRMED order with no status advance yet, refuse if a line has
    # been (partially) delivered or invoiced (7.3/7.4 raise the line columns).
    for line in await get_sales_order_lines(session, tenant_id, order_id):
        if Decimal(str(line.delivered_quantity)) > 0 or Decimal(str(line.invoiced_quantity)) > 0:
            raise ConflictError(
                message="A sales order with delivered or invoiced lines cannot be cancelled",
                code="sales.order_not_cancellable",
                details={"order_id": str(order_id)},
            )
    order.status = SalesOrderStatus.CANCELLED.value
    await session.flush()
    await docflow.set_document_status(
        session, tenant_id, order.document_id, status=SalesOrderStatus.CANCELLED.value
    )
    return order


def validate_line_quantity(quantity: Decimal) -> Decimal:
    """Re-exported for the conversion path (a quote line's quantity is revalidated > 0)."""
    return validate_quantity(quantity)


async def list_sales_orders(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    status: SalesOrderStatus | None = None,
    customer_id: uuid.UUID | None = None,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Page[SalesOrder]:
    """Keyset-paginated order list, newest first (D-014). status + customer filters fold into the
    cursor fingerprint; the (tenant, status) / (tenant, customer_id, status) indexes serve the
    filtered page (PERFORMANCE §1)."""
    stmt = select(SalesOrder).where(SalesOrder.tenant_id == tenant_id)
    if status is not None:
        stmt = stmt.where(SalesOrder.status == SalesOrderStatus(status).value)
    if customer_id is not None:
        stmt = stmt.where(SalesOrder.customer_id == customer_id)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(SalesOrder.created_at, SortDirection.DESC)],
        pk=SalesOrder.id,
        cursor=cursor,
        limit=limit,
        filters=filter_fingerprint(status, customer_id),
    )
