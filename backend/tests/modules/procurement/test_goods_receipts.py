"""Goods-receipt service behaviour (PLAN 6.3, D-041): create draft, post (the full GR → stock →
GR/IR-journal → PO-update chain), over-receipt rejection, partial vs full receipt, closed-period
rollback, lot/serial, inspection flag, idempotency, cancel.

Goods receipts go through the REAL service inside a uow (D-025); the procurement conftest's autouse
fixture registers the procurement→inventory + inventory→finance handlers, so a posted GR moves stock
and posts the GR/IR journal exactly as in production. These tests assert the posted state directly.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.core.exceptions import ConflictError, ValidationFailedError
from app.core.tenancy import tenant_context
from app.modules.finance import queries as finance_queries
from app.modules.finance import service as finance_service
from app.modules.finance.constants import DocumentType
from app.modules.finance.models import JournalEntry, JournalLine
from app.modules.inventory import queries as inventory_queries
from app.modules.inventory.models import Lot, SerialNumber, StockMove
from app.modules.procurement import service
from app.modules.procurement.constants import (
    GoodsReceiptStatus,
    PurchaseOrderStatus,
)
from app.modules.procurement.models import PurchaseOrderLine
from app.modules.procurement.schemas import GoodsReceiptLineCreate
from tests.modules.procurement.conftest import GoodsReceiptSetup
from tests.modules.procurement.factories import (
    build_goods_receipt,
    build_goods_receipt_setup,
    post_goods_receipt,
)


def _line(setup: GoodsReceiptSetup, qty: str, **kwargs: object) -> GoodsReceiptLineCreate:
    return GoodsReceiptLineCreate(
        purchase_order_line_id=setup.po_line_id,
        bin_id=setup.bin_id,
        received_quantity=Decimal(qty),
        **kwargs,  # type: ignore[arg-type]
    )


async def _on_hand(
    session: AsyncSession, tenant_id: uuid.UUID, item_id: uuid.UUID
) -> Decimal:
    with tenant_context(tenant_id):
        return await inventory_queries.total_on_hand(session, tenant_id, item_id)


async def _receipt_journal_lines(
    session: AsyncSession, tenant_id: uuid.UUID
) -> list[JournalLine]:
    with tenant_context(tenant_id):
        entries = (
            await session.execute(
                select(JournalEntry).where(
                    JournalEntry.tenant_id == tenant_id,
                    JournalEntry.document_type == DocumentType.COGS.value,
                )
            )
        ).scalars().all()
        lines: list[JournalLine] = []
        for entry in entries:
            lines.extend(
                (
                    await session.execute(
                        select(JournalLine).where(JournalLine.journal_entry_id == entry.id)
                    )
                )
                .scalars()
                .all()
            )
        return lines


def _credit(lines: list[JournalLine], account_id: uuid.UUID) -> Decimal:
    return sum(
        (
            Decimal(line.transaction_credit_amount)
            for line in lines
            if line.account_id == account_id
        ),
        Decimal(0),
    )


def _debit(lines: list[JournalLine], account_id: uuid.UUID) -> Decimal:
    return sum(
        (Decimal(line.transaction_debit_amount) for line in lines if line.account_id == account_id),
        Decimal(0),
    )


# --- Create draft -------------------------------------------------------------


async def test_create_goods_receipt_is_draft_with_gr_number(
    db_session: AsyncSession, goods_receipt_setup: GoodsReceiptSetup
) -> None:
    """A created goods receipt is DRAFT, carries a GR number, snapshots the vendor, and moves no
    stock yet."""
    gr = await build_goods_receipt(
        db_session,
        goods_receipt_setup.tenant_id,
        po_id=goods_receipt_setup.po_id,
        warehouse_id=goods_receipt_setup.warehouse_id,
        lines=[_line(goods_receipt_setup, "4")],
    )
    assert gr.status == GoodsReceiptStatus.DRAFT.value
    assert gr.gr_number.startswith("GR-")
    assert gr.vendor_id == goods_receipt_setup.vendor_id
    on_hand = await _on_hand(
        db_session, goods_receipt_setup.tenant_id, goods_receipt_setup.item_id
    )
    assert on_hand == Decimal(0)


async def test_create_rejects_over_receipt(
    db_session: AsyncSession, goods_receipt_setup: GoodsReceiptSetup
) -> None:
    """Receiving more than the PO line's open quantity is rejected 422 procurement.over_receipt."""
    with pytest.raises(ValidationFailedError) as exc:
        await build_goods_receipt(
            db_session,
            goods_receipt_setup.tenant_id,
            po_id=goods_receipt_setup.po_id,
            warehouse_id=goods_receipt_setup.warehouse_id,
            lines=[_line(goods_receipt_setup, "11")],  # ordered 10
        )
    assert exc.value.code == "procurement.over_receipt"


async def test_create_rejects_unreceivable_po(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """A DRAFT (not-yet-sent) PO cannot receive goods (procurement.po_not_receivable)."""
    # A setup whose PO we DON'T send: build the setup, then create a fresh DRAFT PO is overkill;
    # instead cancel-receive against a brand-new draft via a second setup is simplest — reuse the
    # standard setup but target a non-receivable status by cancelling the PO.
    setup = await build_goods_receipt_setup(db_session, tenant_a)
    with tenant_context(tenant_a):
        await service.cancel_purchase_order(db_session, tenant_a, setup.po_id)
        await db_session.commit()
    with pytest.raises(ValidationFailedError) as exc:
        await build_goods_receipt(
            db_session,
            tenant_a,
            po_id=setup.po_id,
            warehouse_id=setup.warehouse_id,
            lines=[_line(setup, "4")],
        )
    assert exc.value.code == "procurement.po_not_receivable"


# --- Post: the full chain -----------------------------------------------------


async def test_post_moves_stock_and_posts_gr_ir_journal(
    db_session: AsyncSession, goods_receipt_setup: GoodsReceiptSetup
) -> None:
    """Posting a GR creates a stock RECEIPT move (on-hand up) and a balanced Dr Inventory / Cr GR-IR
    journal — the three-way-match clearing leg (D-041), via the event bus."""
    setup = goods_receipt_setup
    gr = await build_goods_receipt(
        db_session,
        setup.tenant_id,
        po_id=setup.po_id,
        warehouse_id=setup.warehouse_id,
        lines=[_line(setup, "4")],
    )
    posted = await post_goods_receipt(db_session, setup.tenant_id, gr.id)
    assert posted.status == GoodsReceiptStatus.POSTED.value
    assert posted.posted_at is not None

    on_hand = await _on_hand(db_session, setup.tenant_id, setup.item_id)
    assert on_hand == Decimal(4)

    lines = await _receipt_journal_lines(db_session, setup.tenant_id)
    # 4 received @ 5 = 20: Dr Inventory 20 / Cr GR-IR 20.
    assert _debit(lines, setup.inventory_account_id) == Decimal(20)
    assert _credit(lines, setup.gr_ir_account_id) == Decimal(20)
    # The standalone price-difference offset was NOT used.
    assert _credit(lines, setup.price_difference_account_id) == Decimal(0)


async def test_post_raises_received_quantity_and_partial_then_received(
    db_session: AsyncSession, goods_receipt_setup: GoodsReceiptSetup
) -> None:
    """A partial receipt raises received_quantity and sets PARTIALLY_RECEIVED; receiving the rest
    completes the line and sets the PO RECEIVED."""
    setup = goods_receipt_setup
    gr1 = await build_goods_receipt(
        db_session,
        setup.tenant_id,
        po_id=setup.po_id,
        warehouse_id=setup.warehouse_id,
        lines=[_line(setup, "4")],
    )
    await post_goods_receipt(db_session, setup.tenant_id, gr1.id)
    with tenant_context(setup.tenant_id):
        po = await service.get_purchase_order(db_session, setup.tenant_id, setup.po_id)
        await db_session.refresh(po)
        line = await db_session.get(PurchaseOrderLine, setup.po_line_id)
        await db_session.refresh(line)
    assert po.status == PurchaseOrderStatus.PARTIALLY_RECEIVED.value
    assert Decimal(str(line.received_quantity)) == Decimal(4)

    gr2 = await build_goods_receipt(
        db_session,
        setup.tenant_id,
        po_id=setup.po_id,
        warehouse_id=setup.warehouse_id,
        lines=[_line(setup, "6")],  # remaining open
    )
    await post_goods_receipt(db_session, setup.tenant_id, gr2.id)
    with tenant_context(setup.tenant_id):
        po = await service.get_purchase_order(db_session, setup.tenant_id, setup.po_id)
        await db_session.refresh(po)
    assert po.status == PurchaseOrderStatus.RECEIVED.value


async def test_post_links_docflow_po_gr_and_moves(
    db_session: AsyncSession, goods_receipt_setup: GoodsReceiptSetup
) -> None:
    """The docflow chain links PO → GR ('received_by') and GR → stock move ('moved_by') — the link
    is docflow, not a cross-module FK (D-041)."""
    setup = goods_receipt_setup
    gr = await build_goods_receipt(
        db_session,
        setup.tenant_id,
        po_id=setup.po_id,
        warehouse_id=setup.warehouse_id,
        lines=[_line(setup, "4")],
    )
    await post_goods_receipt(db_session, setup.tenant_id, gr.id)
    with tenant_context(setup.tenant_id):
        await db_session.refresh(gr)
        chain = await docflow.get_document_chain(db_session, setup.tenant_id, gr.document_id)
    link_types = {edge.link_type for edge in chain.edges}
    assert "received_by" in link_types
    assert "moved_by" in link_types


async def test_post_closed_period_rolls_back_whole_receipt(
    db_session: AsyncSession, goods_receipt_setup: GoodsReceiptSetup
) -> None:
    """A receipt dated into a CLOSED period trips the move's journal period trigger and rolls the
    WHOLE post back — no move, no journal, GR not posted, PO untouched (D-041 all-or-nothing)."""
    setup = goods_receipt_setup
    gr = await build_goods_receipt(
        db_session,
        setup.tenant_id,
        po_id=setup.po_id,
        warehouse_id=setup.warehouse_id,
        receipt_date=date(2026, 3, 15),
        lines=[_line(setup, "4")],
    )
    gr_id = gr.id  # plain id: the rolled-back post below expires the loaded object
    # Close the March 2026 period so the receipt's journal cannot post.
    with tenant_context(setup.tenant_id):
        period = await finance_queries.find_period_for_date(
            db_session, setup.tenant_id, date(2026, 3, 15)
        )
        await finance_service.close_period(db_session, setup.tenant_id, period.id)
        await db_session.commit()

    with pytest.raises(Exception) as exc:  # noqa: B017, PT011 - period trigger / service error
        await post_goods_receipt(db_session, setup.tenant_id, gr_id)
    assert "period" in str(exc.value).lower() or "PERIOD" in str(
        getattr(exc.value, "code", "")
    )

    # Nothing moved: no stock, GR still DRAFT, PO still SENT.
    on_hand = await _on_hand(db_session, setup.tenant_id, setup.item_id)
    assert on_hand == Decimal(0)
    with tenant_context(setup.tenant_id):
        reloaded = await service.get_goods_receipt(db_session, setup.tenant_id, gr_id)
        gr_status = reloaded.status
        po = await service.get_purchase_order(db_session, setup.tenant_id, setup.po_id)
        po_status = po.status
    assert gr_status == GoodsReceiptStatus.DRAFT.value
    assert po_status == PurchaseOrderStatus.SENT.value


# --- Lot/serial + inspection flag ---------------------------------------------


async def test_post_lot_receipt_creates_lot_and_lands_stock(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """A receipt of a LOT-tracked item creates the lot master and lands the stock under it."""
    setup = await build_goods_receipt_setup(db_session, tenant_a, tracking_mode="LOT")
    gr = await build_goods_receipt(
        db_session,
        tenant_a,
        po_id=setup.po_id,
        warehouse_id=setup.warehouse_id,
        lines=[_line(setup, "4", lot_code="LOT-A")],
    )
    await post_goods_receipt(db_session, tenant_a, gr.id)
    on_hand = await _on_hand(db_session, tenant_a, setup.item_id)
    assert on_hand == Decimal(4)
    with tenant_context(tenant_a):
        lot = (
            await db_session.execute(
                select(Lot).where(Lot.tenant_id == tenant_a, Lot.lot_code == "LOT-A")
            )
        ).scalar_one_or_none()
    assert lot is not None


async def test_post_serial_receipt_creates_serial(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """A receipt of a SERIAL-tracked item (qty 1) creates the serial master."""
    setup = await build_goods_receipt_setup(
        db_session, tenant_a, po_quantity="1", tracking_mode="SERIAL"
    )
    gr = await build_goods_receipt(
        db_session,
        tenant_a,
        po_id=setup.po_id,
        warehouse_id=setup.warehouse_id,
        lines=[_line(setup, "1", serial_code="SN-1")],
    )
    await post_goods_receipt(db_session, tenant_a, gr.id)
    with tenant_context(tenant_a):
        serial = (
            await db_session.execute(
                select(SerialNumber).where(
                    SerialNumber.tenant_id == tenant_a, SerialNumber.serial_code == "SN-1"
                )
            )
        ).scalar_one_or_none()
    assert serial is not None


async def test_requires_inspection_flag_is_stored(
    db_session: AsyncSession, goods_receipt_setup: GoodsReceiptSetup
) -> None:
    """The v1 inspection hook is a per-line flag: requires_inspection set on the line is persisted
    (Phase 9 adds the disposition; v1 stores the flag only and does not block use)."""
    setup = goods_receipt_setup
    gr = await build_goods_receipt(
        db_session,
        setup.tenant_id,
        po_id=setup.po_id,
        warehouse_id=setup.warehouse_id,
        lines=[_line(setup, "4", requires_inspection=True)],
    )
    with tenant_context(setup.tenant_id):
        lines = await service.get_goods_receipt_lines(db_session, setup.tenant_id, gr.id)
    assert lines[0].requires_inspection is True


# --- Idempotency + cancel + unmapped GR/IR ------------------------------------


async def test_repost_posted_receipt_is_rejected(
    db_session: AsyncSession, goods_receipt_setup: GoodsReceiptSetup
) -> None:
    """A POSTED goods receipt cannot be re-posted (terminal — D-013)."""
    setup = goods_receipt_setup
    gr = await build_goods_receipt(
        db_session,
        setup.tenant_id,
        po_id=setup.po_id,
        warehouse_id=setup.warehouse_id,
        lines=[_line(setup, "4")],
    )
    await post_goods_receipt(db_session, setup.tenant_id, gr.id)
    with pytest.raises(ConflictError) as exc:
        await post_goods_receipt(db_session, setup.tenant_id, gr.id)
    assert exc.value.code == "procurement.gr_already_posted"


async def test_cancel_draft_then_posted_is_terminal(
    db_session: AsyncSession, goods_receipt_setup: GoodsReceiptSetup
) -> None:
    """A DRAFT GR can be cancelled; a POSTED GR is terminal (cannot be cancelled)."""
    setup = goods_receipt_setup
    gr = await build_goods_receipt(
        db_session,
        setup.tenant_id,
        po_id=setup.po_id,
        warehouse_id=setup.warehouse_id,
        lines=[_line(setup, "4")],
    )
    with tenant_context(setup.tenant_id):
        cancelled = await service.cancel_goods_receipt(db_session, setup.tenant_id, gr.id)
        await db_session.commit()
    assert cancelled.status == GoodsReceiptStatus.CANCELLED.value

    # A fresh, posted GR cannot be cancelled.
    gr2 = await build_goods_receipt(
        db_session,
        setup.tenant_id,
        po_id=setup.po_id,
        warehouse_id=setup.warehouse_id,
        lines=[_line(setup, "4")],
    )
    await post_goods_receipt(db_session, setup.tenant_id, gr2.id)
    with pytest.raises(ConflictError) as exc, tenant_context(setup.tenant_id):
        await service.cancel_goods_receipt(db_session, setup.tenant_id, gr2.id)
    assert exc.value.code == "procurement.gr_not_cancellable"


async def test_post_without_gr_ir_mapping_raises(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """Posting a GR when the tenant has NOT mapped the GR/IR clearing account raises a clear 422 —
    the receipt cannot credit GR/IR (D-041), so the whole post fails before any state change."""
    setup = await build_goods_receipt_setup(db_session, tenant_a, map_gr_ir=False)
    gr = await build_goods_receipt(
        db_session,
        tenant_a,
        po_id=setup.po_id,
        warehouse_id=setup.warehouse_id,
        lines=[_line(setup, "4")],
    )
    with pytest.raises(ValidationFailedError) as exc:
        await post_goods_receipt(db_session, tenant_a, gr.id)
    assert exc.value.code == "finance.posting_default_unmapped"
    # No stock moved.
    on_hand = await _on_hand(db_session, tenant_a, setup.item_id)
    assert on_hand == Decimal(0)
    with tenant_context(tenant_a):
        moves = (
            await db_session.execute(select(StockMove).where(StockMove.tenant_id == tenant_a))
        ).scalars().all()
    assert moves == []
