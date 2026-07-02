"""Sales-return (RMA) create / cancel (PLAN 7.4, D-046): create a DRAFT return against a sales
order,
cancel a DRAFT. The POST path (the heart) + its helpers live in ``returns_post.py`` and the reads in
``returns_reads.py`` (split at the 400-line cap, STRUCTURE §8.4); the package ``__init__``
re-exports
all three as one ``service`` surface.

A return records goods coming BACK from the customer — the reverse of a delivery. ``create_return``
writes a DRAFT (validates the order's lines were delivered + invoiced, each returned quantity ≤ the
order line's invoiced-not-yet-returned quantity → over-return 422 ``sales.over_return``, the
receiving
bin exists) and claims the RMA number at creation (D-040). No stock moves / credit note yet — that
is
POST (``returns_post.post_return``).

Cross-module rule (STRUCTURE §5 / D-046): sales NEVER calls inventory/finance service — the stock
RECEIPT goes through the event bus to inventory's handler (Dr Inventory / Cr COGS via the
COGS-offset
override) and the AR credit note through the event bus to finance's handler (Dr revenue / Cr AR).
Sales reads bins via inventory/queries (downward reads), updates its OWN order/return rows.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.core.exceptions import ConflictError, ValidationFailedError
from app.core.money import quantize_for_currency
from app.modules.inventory import queries as inventory_queries
from app.modules.sales.constants import (
    RETURN_DOC_TYPE,
    RETURN_NUMBER_PADDING,
    RETURN_NUMBER_PREFIX,
    RETURN_SEQUENCE_NAME,
    ReturnStatus,
)
from app.modules.sales.models import SalesOrder, SalesOrderLine, SalesReturn, SalesReturnLine
from app.modules.sales.schemas import ReturnCreate
from app.modules.sales.service._shared import claim_document_number
from app.modules.sales.service.orders import get_sales_order_lines
from app.modules.sales.service.returns_reads import get_return


@dataclass(frozen=True)
class _ReturnLineInput:
    """One validated return line: the order line returned against, the snapshot item/price/tax from
    it, the receiving bin, the returned quantity, the computed credit line amount, and
    lot/serial."""

    sales_order_line_id: uuid.UUID
    item_id: uuid.UUID
    bin_id: uuid.UUID
    quantity: Decimal
    unit_price: Decimal
    line_amount: Decimal
    tax_code_id: uuid.UUID | None
    lot_code: str | None
    serial_code: str | None


async def _require_returnable_order(
    session: AsyncSession, tenant_id: uuid.UUID, order_id: uuid.UUID
) -> SalesOrder:
    order = await session.get(SalesOrder, order_id)
    if order is None or order.tenant_id != tenant_id:
        raise ValidationFailedError(
            message="Referenced sales order does not exist",
            code="sales.order_not_found",
            details={"sales_order_id": str(order_id)},
        )
    return order


def _validate_quantity(quantity: Decimal) -> Decimal:
    qty = Decimal(str(quantity))
    if qty <= 0:
        raise ValidationFailedError(
            message="A return line quantity must be greater than zero",
            code="sales.line_quantity_invalid",
            details={"quantity": str(qty)},
        )
    return qty


async def _validate_return_line(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    order_id: uuid.UUID,
    order_lines: dict[uuid.UUID, SalesOrderLine],
    payload_line: object,
    currency_code: str,
) -> _ReturnLineInput:
    """Validate one return line against its order line: the line belongs to the order, the qty is >
    0
    and within the still-open-to-return quantity = INVOICED − RETURNED (over-return REJECTED 422
    ``sales.over_return`` — a credit note must reduce a real invoice, so the cap is invoiced, not
    delivered, D-046), and the receiving bin exists in inventory (D-029). Snapshots the priced
    fields
    from the order line."""
    order_line = order_lines.get(payload_line.sales_order_line_id)  # type: ignore[attr-defined]
    if order_line is None:
        raise ValidationFailedError(
            message="The return line does not belong to this sales order",
            code="sales.return_line_not_on_order",
            details={
                "sales_order_id": str(order_id),
                "sales_order_line_id": str(
                    payload_line.sales_order_line_id  # type: ignore[attr-defined]
                ),
            },
        )
    qty = _validate_quantity(payload_line.quantity)  # type: ignore[attr-defined]
    open_qty = Decimal(str(order_line.invoiced_quantity)) - Decimal(
        str(order_line.returned_quantity)
    )
    if qty > open_qty:
        raise ValidationFailedError(
            message="The returned quantity exceeds the invoiced-not-yet-returned quantity",
            code="sales.over_return",
            details={
                "sales_order_line_id": str(order_line.id),
                "open_quantity": str(open_qty),
                "quantity": str(qty),
            },
        )
    bin_id = payload_line.bin_id  # type: ignore[attr-defined]
    if not await inventory_queries.bin_exists(session, tenant_id, bin_id):
        raise ValidationFailedError(
            message="The receiving bin does not exist in inventory",
            code="sales.return_bin_not_found",
            details={"bin_id": str(bin_id)},
        )
    unit_price = Decimal(str(order_line.unit_price))
    line_amount = quantize_for_currency(qty * unit_price, currency_code)
    return _ReturnLineInput(
        sales_order_line_id=order_line.id,
        item_id=order_line.item_id,
        bin_id=bin_id,
        quantity=qty,
        unit_price=unit_price,
        line_amount=line_amount,
        tax_code_id=order_line.tax_code_id,
        lot_code=payload_line.lot_code,  # type: ignore[attr-defined]
        serial_code=payload_line.serial_code,  # type: ignore[attr-defined]
    )


async def create_return(
    session: AsyncSession, tenant_id: uuid.UUID, payload: ReturnCreate
) -> SalesReturn:
    """Create a DRAFT return against a sales order (PLAN 7.4). Validates each line belongs to the
    order and does not over-return its invoiced-not-yet-returned quantity (over-return → 422
    ``sales.over_return``) and the receiving bin exists. Snapshots the customer from the order + the
    priced fields per line from the order line, claims the RMA number (D-040), links order → return.
    No stock moves / credit note yet — that is POST."""
    if not payload.lines:
        raise ValidationFailedError(
            message="A return needs at least one line",
            code="sales.return_no_lines",
        )
    order = await _require_returnable_order(session, tenant_id, payload.sales_order_id)
    order_lines = {
        line.id: line for line in await get_sales_order_lines(session, tenant_id, order.id)
    }
    return_date = payload.return_date or date.today()

    validated = [
        await _validate_return_line(
            session, tenant_id, order.id, order_lines, line, order.currency_code
        )
        for line in payload.lines
    ]
    total = sum((line.line_amount for line in validated), Decimal(0))

    return_id = uuid.uuid4()
    document = await docflow.register_document(
        session,
        tenant_id,
        RETURN_DOC_TYPE,
        return_id,
        doc_number=None,
        status=ReturnStatus.DRAFT.value,
    )
    number = await claim_document_number(
        session,
        tenant_id,
        sequence_name=RETURN_SEQUENCE_NAME,
        prefix=RETURN_NUMBER_PREFIX,
        padding=RETURN_NUMBER_PADDING,
        on_date=return_date,
    )
    sales_return = SalesReturn(
        id=return_id,
        tenant_id=tenant_id,
        document_id=document.id,
        return_number=number,
        status=ReturnStatus.DRAFT.value,
        sales_order_id=order.id,
        customer_id=order.customer_id,
        warehouse_id=payload.warehouse_id,
        currency_code=order.currency_code,
        return_date=return_date,
        reason=payload.reason,
        total_amount=total,
        notes=payload.notes,
    )
    session.add(sales_return)
    for index, line in enumerate(validated, start=1):
        session.add(
            SalesReturnLine(
                tenant_id=tenant_id,
                return_id=return_id,
                line_number=index,
                sales_order_line_id=line.sales_order_line_id,
                item_id=line.item_id,
                bin_id=line.bin_id,
                quantity=line.quantity,
                unit_price=line.unit_price,
                line_amount=line.line_amount,
                tax_code_id=line.tax_code_id,
                lot_code=line.lot_code,
                serial_code=line.serial_code,
            )
        )
    await session.flush()
    await docflow.set_document_status(
        session, tenant_id, document.id, doc_number=number, status=ReturnStatus.DRAFT.value
    )
    return sales_return


async def cancel_return(
    session: AsyncSession, tenant_id: uuid.UUID, return_id: uuid.UUID
) -> SalesReturn:
    """Cancel a DRAFT return (PLAN 7.4). A POSTED return is TERMINAL — it received stock + posted a
    credit note, so it is never cancelled. Cancelling a DRAFT moves/credits nothing."""
    sales_return = await get_return(session, tenant_id, return_id)
    if ReturnStatus(sales_return.status) != ReturnStatus.DRAFT:
        raise ConflictError(
            message=f"A {sales_return.status} return cannot be cancelled",
            code="sales.return_not_cancellable",
            details={"return_id": str(return_id), "status": sales_return.status},
        )
    sales_return.status = ReturnStatus.CANCELLED.value
    await session.flush()
    await docflow.set_document_status(
        session, tenant_id, sales_return.document_id, status=ReturnStatus.CANCELLED.value
    )
    return sales_return
