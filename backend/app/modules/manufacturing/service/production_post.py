"""Production-order POSTING flows (PLAN 8.2, D-048) — the heart: issue components to WIP + finish to
stock, both through the EVENT BUS (manufacturing publishes; inventory's handlers create the moves
with the WIP-offset override; the moves' costing events → finance posts the WIP journals).

Split from ``production_orders.py`` at the 400-line cap (the sales delivery_post precedent). The
DRAFT lifecycle (create+explode/release/cancel) stays there; the issue/finish POST paths live here.
``__init__`` re-exports both halves as one ``service`` surface.

THE WIP ACCOUNTING (D-048), the manufacturing↔inventory↔finance seam:

- **issue_components** — for each component to issue, PUBLISH ``ComponentsIssued`` → inventory's
  handler creates an ISSUE move (from the component's bin, qty, valuation_offset = the WIP account)
  → Dr WIP / Cr Inventory at the component's moving-average/FIFO cost. The order raises each
  component's ``issued_quantity`` and its ``accumulated_wip_cost`` (by the issued book value — read
  pre-publish from inventory's current_unit_cost, which equals the MAV issue cost) and goes
  IN_PROGRESS. Over-issue beyond required is a 422 (v1 policy: issued ≤ required). Atomic; a closed
  period or insufficient stock rolls the whole issue back (the move guard raises — issue #53: tests
  must NOT assert post-failure state on the same session).
- **finish_order** — compute the finished unit cost = accumulated WIP / ordered quantity, PUBLISH
  ``OrderFinished`` → inventory's handler creates a RECEIPT move (to the finished bin, finished qty,
  unit_cost = WIP per unit, valuation_offset = the WIP account) → Dr Inventory / Cr WIP. The order
  raises ``finished_quantity`` and DRAINS the absorbed WIP from ``accumulated_wip_cost``. On the
  FINAL finish, any residual WIP (over/under-absorption / rounding) is carried on the event so
  FINANCE's handler flushes it to the production-variance account — WIP nets to ZERO at completion —
  and the order goes FINISHED. Atomic; a closed period rolls the whole finish back.

§5: this module imports only inventory/queries + finance/queries + the manufacturing events — never
inventory/finance SERVICE (verified). The moves + journals are inventory's/finance's own work,
triggered by the events.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.core.events import publish
from app.core.exceptions import ConflictError, ValidationFailedError
from app.core.money import quantize_for_currency
from app.modules.finance import queries as finance_queries
from app.modules.inventory import queries as inventory_queries
from app.modules.inventory.constants import DEFAULT_COSTING_CURRENCY
from app.modules.manufacturing.constants import ProductionOrderStatus
from app.modules.manufacturing.events import (
    ComponentIssueMove,
    ComponentsIssued,
    FinishedReceiptMove,
    OrderFinished,
)
from app.modules.manufacturing.models import ProductionOrder, ProductionOrderComponent
from app.modules.manufacturing.schemas import FinishOrderRequest, IssueComponentsRequest
from app.modules.manufacturing.service.production_orders import (
    get_production_order,
    production_order_components,
)


async def _costing_currency(session: AsyncSession, tenant_id: uuid.UUID) -> str:
    func_code = await finance_queries.functional_currency_or_none(session, tenant_id)
    return func_code or DEFAULT_COSTING_CURRENCY


async def issue_components(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    order_id: uuid.UUID,
    payload: IssueComponentsRequest,
) -> ProductionOrder:
    """Issue components to WIP (D-048) — the heart's first half. For each component to issue,
    publish ``ComponentsIssued`` so inventory's handler creates the ISSUE move (Dr WIP / Cr
    Inventory via the WIP-offset override); raise the component's ``issued_quantity`` and the
    order's
    ``accumulated_wip_cost``; move the order IN_PROGRESS. With no ``lines`` the FULL remaining
    required of every component is issued from its default bin ("issue all required"). Over-issue
    past required is a 422 (v1: issued ≤ required). Atomic — a closed period or insufficient stock
    rolls the whole issue back."""
    order = await get_production_order(session, tenant_id, order_id)
    status = ProductionOrderStatus(order.status)
    if status not in (ProductionOrderStatus.RELEASED, ProductionOrderStatus.IN_PROGRESS):
        raise ConflictError(
            message=f"Components cannot be issued to a {order.status} production order",
            code="manufacturing.production_order_not_issuable",
            details={"order_id": str(order_id), "status": order.status},
        )
    wip_account_id = await finance_queries.wip_clearing_account(session, tenant_id)
    rows = await production_order_components(session, tenant_id, order_id)
    components = {row.line_number: row for row in rows}
    move_date = payload.move_date or date.today()
    currency_code = await _costing_currency(session, tenant_id)

    requested = _resolve_issue_lines(payload, components)
    moves: list[ComponentIssueMove] = []
    wip_added = Decimal(0)
    for component, qty, bin_id, lot_code, serial_code in requested:
        _check_over_issue(component, qty)
        lot_id, serial_id = await _resolve_issue_tracking(
            session, tenant_id, component.component_item_id, lot_code, serial_code
        )
        # The issued WIP value = the component's current book cost × qty, quantized to the currency
        # (the MAV issue posts at avg_unit_cost, so this equals the WIP debit the move will post).
        # The finished receipt later enters at accumulated_wip / produced qty, so WIP clears.
        unit_cost = await inventory_queries.current_unit_cost(
            session, tenant_id, component.component_item_id, order.warehouse_id
        )
        wip_added += quantize_for_currency(qty * unit_cost, currency_code)
        component.issued_quantity = Decimal(component.issued_quantity) + qty
        moves.append(
            ComponentIssueMove(
                item_id=component.component_item_id,
                bin_id=bin_id,
                quantity=qty,
                lot_id=lot_id,
                serial_id=serial_id,
            )
        )

    order.accumulated_wip_cost = Decimal(order.accumulated_wip_cost) + wip_added
    order.status = ProductionOrderStatus.IN_PROGRESS.value
    await session.flush()
    await docflow.set_document_status(
        session, tenant_id, order.document_id, status=ProductionOrderStatus.IN_PROGRESS.value
    )
    publish(
        session,
        ComponentsIssued(
            tenant_id=tenant_id,
            production_order_id=order.id,
            order_number=order.order_number,
            document_id=order.document_id,
            warehouse_id=order.warehouse_id,
            move_date=move_date.isoformat(),
            wip_account_id=wip_account_id,
            moves=tuple(moves),
        ),
    )
    return order


def _resolve_issue_lines(
    payload: IssueComponentsRequest,
    components: dict[int, ProductionOrderComponent],
) -> list[tuple[ProductionOrderComponent, Decimal, uuid.UUID, str | None, str | None]]:
    """Resolve the (component, qty, bin, lot, serial) tuples to issue. With explicit ``lines`` each
    names a component by line_number (422 if unknown) and its qty/bin/lot/serial; with no lines the
    FULL remaining required of every component is issued from its default bin. A line with qty <= 0
    is rejected; a component fully issued is skipped on "issue all required" (no zero move)."""
    if payload.lines:
        resolved = []
        for line in payload.lines:
            component = components.get(line.component_line_number)
            if component is None:
                raise ValidationFailedError(
                    message="No such component line on this production order",
                    code="manufacturing.component_line_not_found",
                    details={"component_line_number": line.component_line_number},
                )
            qty = Decimal(line.quantity)
            if qty <= 0:
                raise ValidationFailedError(
                    message="Issue quantity must be greater than zero",
                    code="manufacturing.issue_quantity_invalid",
                    details={"component_line_number": line.component_line_number},
                )
            resolved.append(
                (component, qty, line.bin_id or component.bin_id, line.lot_code, line.serial_code)
            )
        return resolved
    resolved = []
    for component in components.values():
        remaining = Decimal(component.required_quantity) - Decimal(component.issued_quantity)
        if remaining > 0:
            resolved.append((component, remaining, component.bin_id, None, None))
    if not resolved:
        raise ValidationFailedError(
            message="Every component is already fully issued",
            code="manufacturing.nothing_to_issue",
        )
    return resolved


def _check_over_issue(component: ProductionOrderComponent, qty: Decimal) -> None:
    """v1 over-issue policy: issued + qty must not exceed required (422). Beyond-required issuance
    is a later flag — keeping issued ≤ required makes the WIP math bounded by the BOM explosion."""
    new_issued = Decimal(component.issued_quantity) + qty
    if new_issued > Decimal(component.required_quantity):
        raise ValidationFailedError(
            message="Issuing this quantity would exceed the component's required quantity",
            code="manufacturing.over_issue",
            details={
                "component_line_number": component.line_number,
                "required": str(component.required_quantity),
                "already_issued": str(component.issued_quantity),
                "requested": str(qty),
            },
        )


async def _resolve_issue_tracking(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    item_id: uuid.UUID,
    lot_code: str | None,
    serial_code: str | None,
) -> tuple[uuid.UUID | None, uuid.UUID | None]:
    """An ISSUE references an EXISTING lot/serial BY ID (it creates none), so resolve any supplied
    code to its inventory id via inventory/queries; an unresolvable code fails loud (422), rolling
    the issue back."""
    lot_id: uuid.UUID | None = None
    serial_id: uuid.UUID | None = None
    if lot_code is not None:
        lot_id = await inventory_queries.lot_id_for_code(session, tenant_id, item_id, lot_code)
        if lot_id is None:
            raise ValidationFailedError(
                message="The referenced lot does not exist for this component",
                code="manufacturing.issue_lot_not_found",
                details={"item_id": str(item_id), "lot_code": lot_code},
            )
    if serial_code is not None:
        serial_id = await inventory_queries.serial_id_for_code(
            session, tenant_id, item_id, serial_code
        )
        if serial_id is None:
            raise ValidationFailedError(
                message="The referenced serial does not exist for this component",
                code="manufacturing.issue_serial_not_found",
                details={"item_id": str(item_id), "serial_code": serial_code},
            )
    return lot_id, serial_id


async def finish_order(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    order_id: uuid.UUID,
    payload: FinishOrderRequest,
) -> ProductionOrder:
    """Finish a production order to stock (D-048) — the heart's second half. Computes the finished
    unit cost = accumulated WIP / ordered quantity, publishes ``OrderFinished`` so inventory's
    handler creates the finished RECEIPT move (Dr Inventory / Cr WIP via the WIP-offset override);
    raises ``finished_quantity`` and drains the absorbed WIP. On the FINAL finish any residual WIP
    is carried on the event so finance flushes it to the production-variance account (WIP nets to
    ZERO), and the order goes FINISHED. Atomic — a closed period rolls the whole finish back. An
    order must
    be IN_PROGRESS (components issued) to finish."""
    order = await get_production_order(session, tenant_id, order_id)
    status = ProductionOrderStatus(order.status)
    if status != ProductionOrderStatus.IN_PROGRESS:
        raise ConflictError(
            message=f"A {order.status} production order cannot be finished",
            code="manufacturing.production_order_not_finishable",
            details={"order_id": str(order_id), "status": order.status},
        )
    finished_qty = Decimal(payload.finished_quantity)
    if finished_qty <= 0:
        raise ValidationFailedError(
            message="Finished quantity must be greater than zero",
            code="manufacturing.finish_quantity_invalid",
            details={"finished_quantity": str(finished_qty)},
        )
    new_finished = Decimal(order.finished_quantity) + finished_qty
    if new_finished > Decimal(order.quantity):
        raise ValidationFailedError(
            message="Finishing this quantity would exceed the ordered quantity",
            code="manufacturing.over_finish",
            details={
                "ordered": str(order.quantity),
                "already_finished": str(order.finished_quantity),
                "requested": str(finished_qty),
            },
        )

    wip_account_id = await finance_queries.wip_clearing_account(session, tenant_id)
    currency_code = await _costing_currency(session, tenant_id)
    is_final = new_finished == Decimal(order.quantity)
    accumulated = Decimal(order.accumulated_wip_cost)
    # The finished goods enter at a UNIFORM per-unit WIP cost = accumulated WIP / the WHOLE ordered
    # quantity, quantized to the currency — so every produced unit carries the same standard cost.
    # The receipt value for this batch = unit_cost × finished_qty. On the FINAL finish any residual
    # (accumulated WIP minus the total received across all finishes, a quantization difference or
    # genuine over/under-absorption) flushes to the variance account so WIP nets to EXACTLY zero.
    unit_cost = quantize_for_currency(accumulated / Decimal(order.quantity), currency_code)
    finished_value = quantize_for_currency(unit_cost * finished_qty, currency_code)

    order.finished_quantity = new_finished
    order.accumulated_wip_cost = accumulated - finished_value

    variance_amount = Decimal(0)
    variance_account_id: uuid.UUID | None = None
    if is_final:
        # The residual still on the order after this receipt drains: positive = WIP carries a
        # leftover DEBIT (cost overran → Dr variance / Cr WIP), negative = leftover CREDIT (under).
        variance_amount = quantize_for_currency(
            Decimal(order.accumulated_wip_cost), currency_code
        )
        order.accumulated_wip_cost = Decimal(0)
        order.status = ProductionOrderStatus.FINISHED.value
        order.finished_at = datetime.now()
        if variance_amount != 0:
            variance_account_id = await finance_queries.production_variance_account(
                session, tenant_id
            )
    await session.flush()
    if is_final:
        await docflow.set_document_status(
            session, tenant_id, order.document_id, status=ProductionOrderStatus.FINISHED.value
        )

    publish(
        session,
        OrderFinished(
            tenant_id=tenant_id,
            production_order_id=order.id,
            order_number=order.order_number,
            document_id=order.document_id,
            warehouse_id=order.warehouse_id,
            move_date=(payload.move_date or date.today()).isoformat(),
            wip_account_id=wip_account_id,
            variance_account_id=variance_account_id,
            variance_amount=variance_amount,
            currency_code=currency_code,
            item_id=order.item_id,
            move=FinishedReceiptMove(
                item_id=order.item_id,
                bin_id=payload.finished_bin_id,
                quantity=finished_qty,
                unit_cost=unit_cost,
                lot_code=payload.lot_code,
                serial_code=payload.serial_code,
            ),
        ),
    )
    return order
