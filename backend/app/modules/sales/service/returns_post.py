"""Sales-return (RMA) POST (PLAN 7.4, D-046) — the heart — split from ``returns.py`` at the 400-line
cap (STRUCTURE §8.4, the delivery_post precedent). The DRAFT create + helpers + ``cancel_return``
stay in ``returns.py``; the reads in ``returns_reads.py``; the post path + its post-only helpers
live
here. ``__init__`` re-exports all three as one ``service`` surface (``service.post_return``).

``post_return`` is the heart: in ONE transaction it PUBLISHES TWO events —

  ``ReturnReceived`` → inventory's handler creates one stock RECEIPT move per line (goods back into
  the bin, ``valuation_offset_account_id`` = the item-category COGS account so the costing posts Dr
  Inventory / Cr COGS — REVERSING the original issue's COGS); and

  ``ReturnCredited`` → finance's handler creates + posts the AR credit note (Dr revenue / Cr AR
  control + reverse output tax — reversing the billing's revenue + AR).

— raises each order line's returned_quantity and sets the return POSTED. A closed return period
trips
a move's valuation journal OR the credit note's journal trigger and rolls the WHOLE post back. The
return is the EXACT reverse of the order-to-cash legs: it sends inventory back UP, COGS back DOWN,
revenue back DOWN and AR back DOWN — so a full return nets the O2C accounts to zero (D-046).

Sales resolves the COGS account (the valuation offset), the goods' current book unit cost, and the
AR
control + sales-revenue accounts from inventory/finance QUERIES up front (downward reads), then
publishes — never importing inventory/finance service (STRUCTURE §5).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.core.events import publish
from app.core.exceptions import ConflictError, ValidationFailedError
from app.modules.finance import queries as finance_queries
from app.modules.inventory import queries as inventory_queries
from app.modules.sales import queries as sales_queries
from app.modules.sales.constants import (
    ORDER_RETURNED_BY_RETURN_LINK,
    ReturnStatus,
)
from app.modules.sales.events import (
    BillingInvoiceLine,
    ReturnCredited,
    ReturnMove,
    ReturnReceived,
)
from app.modules.sales.models import SalesOrder, SalesOrderLine, SalesReturn, SalesReturnLine
from app.modules.sales.service.orders import get_sales_order_lines
from app.modules.sales.service.returns_reads import get_return, get_return_lines


def _require_postable(sales_return: SalesReturn, return_id: uuid.UUID) -> None:
    status = ReturnStatus(sales_return.status)
    if status == ReturnStatus.POSTED:
        raise ConflictError(
            message="The return is already posted",
            code="sales.return_already_posted",
            details={"return_id": str(return_id)},
        )
    if status != ReturnStatus.DRAFT:
        raise ConflictError(
            message=f"A {sales_return.status} return cannot be posted",
            code="sales.return_not_postable",
            details={"return_id": str(return_id), "status": sales_return.status},
        )


async def _cogs_account_for_item(
    session: AsyncSession, tenant_id: uuid.UUID, item_id: uuid.UUID
) -> uuid.UUID:
    """The item-category COGS account (the valuation-offset OVERRIDE the RECEIPT credits so the
    return reverses the original issue's COGS). Raises 422 when the category has not wired it — the
    return cannot post without somewhere to reverse COGS to."""
    accounts = await inventory_queries.get_category_accounts(session, tenant_id, item_id)
    cogs_account_id = accounts[1] if accounts is not None else None
    if cogs_account_id is None:
        raise ValidationFailedError(
            message="The item's category has no COGS account to reverse the return into",
            code="sales.return_cogs_unwired",
            details={"item_id": str(item_id)},
        )
    return cogs_account_id


async def _build_moves_and_invoice_lines(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    sales_return: SalesReturn,
    lines: list[SalesReturnLine],
    order_lines: dict[uuid.UUID, SalesOrderLine],
) -> tuple[list[ReturnMove], list[BillingInvoiceLine], uuid.UUID]:
    """Raise each order line's returned_quantity and build BOTH event payloads: the RECEIPT moves
    (goods back at the item's current book cost) and the credit-note revenue lines (net + tax code).
    Returns (moves, invoice_lines, cogs_account_id). The COGS override is the item-category COGS
    account; v1 returns a single account on the event (the lines share a costing category — the
    single-revenue-account scope mirror); the per-line account is asserted consistent."""
    moves: list[ReturnMove] = []
    invoice_lines: list[BillingInvoiceLine] = []
    cogs_account_id: uuid.UUID | None = None
    for line in lines:
        order_line = order_lines[line.sales_order_line_id]
        new_returned = Decimal(str(order_line.returned_quantity)) + Decimal(
            str(line.quantity)
        )
        # #75: the create-path check reads the persisted column, which another document may
        # have raised since this DRAFT was created — re-check the cap at post time.
        if new_returned > Decimal(str(order_line.invoiced_quantity)):
            raise ValidationFailedError(
                message="Posting this return would exceed the order line's invoiced quantity",
                code="sales.over_return",
                details={
                    "sales_order_line_id": str(order_line.id),
                    "invoiced_quantity": str(order_line.invoiced_quantity),
                    "returned_quantity": str(order_line.returned_quantity),
                    "quantity": str(line.quantity),
                },
            )
        order_line.returned_quantity = new_returned
        line_cogs = await _cogs_account_for_item(session, tenant_id, line.item_id)
        if cogs_account_id is None:
            cogs_account_id = line_cogs
        elif cogs_account_id != line_cogs:
            raise ValidationFailedError(
                message="A return's lines must share one COGS account in v1",
                code="sales.return_mixed_cogs",
                details={"item_id": str(line.item_id)},
            )
        unit_cost = await inventory_queries.current_unit_cost(
            session, tenant_id, line.item_id, sales_return.warehouse_id
        )
        moves.append(
            ReturnMove(
                item_id=line.item_id,
                bin_id=line.bin_id,
                quantity=Decimal(str(line.quantity)),
                unit_cost=Decimal(str(unit_cost)),
                lot_code=line.lot_code,
                serial_code=line.serial_code,
            )
        )
        invoice_lines.append(
            BillingInvoiceLine(
                item_id=line.item_id,
                net_amount=Decimal(str(line.line_amount)),
                tax_code_id=line.tax_code_id,
            )
        )
    assert cogs_account_id is not None  # at least one line (create validated non-empty)
    return moves, invoice_lines, cogs_account_id


async def post_return(
    session: AsyncSession, tenant_id: uuid.UUID, return_id: uuid.UUID
) -> SalesReturn:
    """Post a DRAFT return (PLAN 7.4, D-046) — the heart. In ONE transaction: PUBLISH
    ``ReturnReceived`` (inventory receives stock back, Dr Inventory / Cr COGS via the COGS-offset
    override — reversing the issue) AND ``ReturnCredited`` (finance posts the AR credit note, Dr
    revenue / Cr AR — reversing the billing); raise each order line's returned_quantity; link
    docflow
    order → return; set the return POSTED. A closed return period trips a move's OR the credit
    note's
    journal trigger and rolls it ALL back.

    Only a DRAFT return posts; a POSTED one is idempotent-rejected (terminal). The caller commits
    via
    uow; the published events drain in the same uow."""
    sales_return = await get_return(session, tenant_id, return_id)
    _require_postable(sales_return, return_id)

    # Resolve the AR control + revenue accounts UP FRONT (downward reads) — a missing posting
    # default
    # raises 422 here, so the post fails before any state change (D-046).
    ar_account_id = await finance_queries.ar_control_account(session, tenant_id)
    revenue_account_id = await finance_queries.sales_revenue_account(session, tenant_id)

    lines = await get_return_lines(session, tenant_id, return_id)
    order_lines = {
        line.id: line
        for line in await get_sales_order_lines(session, tenant_id, sales_return.sales_order_id)
    }
    moves, invoice_lines, cogs_account_id = await _build_moves_and_invoice_lines(
        session, tenant_id, sales_return, lines, order_lines
    )

    customer = await sales_queries.get_customer(session, tenant_id, sales_return.customer_id)
    partner_name = customer.name if customer is not None else ""

    sales_return.status = ReturnStatus.POSTED.value
    sales_return.posted_at = datetime.now()
    await session.flush()
    await docflow.set_document_status(
        session, tenant_id, sales_return.document_id, status=ReturnStatus.POSTED.value
    )
    order = await session.get(SalesOrder, sales_return.sales_order_id)
    if order is not None:
        await docflow.link_documents(
            session,
            tenant_id,
            predecessor=order.document_id,
            successor=sales_return.document_id,
            link_type=ORDER_RETURNED_BY_RETURN_LINK,
        )

    move_date = sales_return.return_date.isoformat()
    publish(
        session,
        ReturnReceived(
            tenant_id=tenant_id,
            return_id=sales_return.id,
            return_number=sales_return.return_number,
            document_id=sales_return.document_id,
            warehouse_id=sales_return.warehouse_id,
            move_date=move_date,
            cogs_account_id=cogs_account_id,
            moves=tuple(moves),
        ),
    )
    publish(
        session,
        ReturnCredited(
            tenant_id=tenant_id,
            return_id=sales_return.id,
            return_number=sales_return.return_number,
            document_id=sales_return.document_id,
            partner_id=sales_return.customer_id,
            partner_name=partner_name,
            credit_note_date=sales_return.return_date,
            currency_code=sales_return.currency_code,
            ar_account_id=ar_account_id,
            revenue_account_id=revenue_account_id,
            lines=tuple(invoice_lines),
        ),
    )
    return sales_return
