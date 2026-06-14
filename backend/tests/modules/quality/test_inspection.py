"""Inspection-lot service behaviour (PLAN 9.1, D-050): the goods-receipt → OPEN-lot handler, the
accept/reject usage decision, the SCRAP/BLOCK dispositions + their stock effects, the
accepted-needs-no-move invariant, the split validation, idempotency, cancel, and closed-period
rollback.

Inspection lots come from the GR handler (a flagged GR line auto-creates an OPEN lot); decisions go
through the REAL service inside a uow (D-025); the quality conftest's autouse fixture registers the
procurement→inventory + procurement→quality + quality→inventory + inventory→finance handlers, so a
posted flagged GR creates a lot and a reject decision moves stock + posts the write-off exactly as
in
production. These tests assert the resulting state directly (the decision path's failures are
asserted
via FRESH reads after a rolled-back uow — issue #53).
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.core.events import run_in_uow
from app.core.exceptions import ConflictError, ValidationFailedError
from app.core.tenancy import tenant_context
from app.modules.finance import queries as finance_queries
from app.modules.finance import service as finance_service
from app.modules.finance.constants import DocumentType
from app.modules.finance.models import JournalEntry, JournalLine
from app.modules.inventory import queries as inventory_queries
from app.modules.procurement import service as procurement_service
from app.modules.procurement.schemas import GoodsReceiptLineCreate
from app.modules.quality import queries as quality_queries
from app.modules.quality import service
from app.modules.quality.constants import (
    GR_INSPECTED_BY_LOT_LINK,
    InspectionLotStatus,
    RejectDisposition,
)
from app.modules.quality.schemas import InspectionDecideRequest
from tests.modules.procurement.factories import (
    build_goods_receipt,
    build_goods_receipt_setup,
    post_goods_receipt,
)
from tests.modules.quality.conftest import InspectionLotSetup
from tests.modules.quality.factories import build_inspection_lot_setup


async def _on_hand(
    session: AsyncSession, tenant_id: uuid.UUID, item_id: uuid.UUID, bin_id: uuid.UUID | None = None
) -> Decimal:
    with tenant_context(tenant_id):
        return await inventory_queries.on_hand(session, tenant_id, item_id, bin_id=bin_id)


async def _decide(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    lot_id: uuid.UUID,
    payload: InspectionDecideRequest,
    *,
    decided_date: date | None = None,
) -> None:
    """Run the usage decision through the real service inside a uow (D-025) — the full chain
    (decision + any disposition stock move + write-off journal)."""

    async def work() -> None:
        with tenant_context(tenant_id):
            await service.decide(
                session,
                tenant_id,
                lot_id,
                payload,
                decision_by=uuid.uuid4(),
                decided_date=decided_date,
            )

    with tenant_context(tenant_id):
        await run_in_uow(session, work)


async def _writeoff_lines(
    session: AsyncSession, tenant_id: uuid.UUID, account_id: uuid.UUID
) -> list[JournalLine]:
    """The valuation (COGS-doc-type) journal lines posted to one account (the SCRAP write-off hits
    the price-difference account)."""
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
            rows = (
                await session.execute(
                    select(JournalLine).where(
                        JournalLine.journal_entry_id == entry.id,
                        JournalLine.account_id == account_id,
                    )
                )
            ).scalars().all()
            lines.extend(rows)
        return lines


# --- The GR handler creates lots ----------------------------------------------


async def test_flagged_goods_receipt_creates_open_inspection_lot(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """A goods receipt with requires_inspection=True posts → an OPEN inspection lot exists with the
    right item / quantity / bin, and the GR document → 'inspected_by' → lot docflow edge is written
    (D-050)."""
    setup = await build_inspection_lot_setup(db_session, tenant_a, receive_quantity="10")
    with tenant_context(tenant_a):
        lot = await service.get_inspection_lot(db_session, tenant_a, setup.lot_id)
        assert lot.status == InspectionLotStatus.OPEN.value
        assert lot.item_id == setup.item_id
        assert Decimal(str(lot.quantity)) == Decimal(10)
        assert lot.bin_id == setup.bin_id
        assert lot.source_document_id == setup.gr_document_id
        assert lot.lot_number.startswith("QL")
        chain = await docflow.get_document_chain(db_session, tenant_a, setup.gr_document_id)
    assert any(
        edge.link_type == GR_INSPECTED_BY_LOT_LINK
        and edge.successor_document_id == lot.document_id
        for edge in chain.edges
    )


async def test_unflagged_goods_receipt_creates_no_lot(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """A GR line WITHOUT requires_inspection creates NO inspection lot (D-050)."""
    gr_setup = await build_goods_receipt_setup(db_session, tenant_a, po_quantity="10")
    gr = await build_goods_receipt(
        db_session,
        tenant_a,
        po_id=gr_setup.po_id,
        warehouse_id=gr_setup.warehouse_id,
        lines=[
            GoodsReceiptLineCreate(
                purchase_order_line_id=gr_setup.po_line_id,
                bin_id=gr_setup.bin_id,
                received_quantity=Decimal(10),
                # requires_inspection omitted → defaults False
            )
        ],
    )
    await post_goods_receipt(db_session, tenant_a, gr.id)
    with tenant_context(tenant_a):
        gr_reloaded = await procurement_service.get_goods_receipt(db_session, tenant_a, gr.id)
        lots = await quality_queries.lots_for_goods_receipt(
            db_session, tenant_a, gr_reloaded.document_id
        )
    assert lots == []


# --- Accept (no stock move) ---------------------------------------------------


async def test_accept_sets_accepted_and_moves_no_stock(
    db_session: AsyncSession, inspection_lot_setup: InspectionLotSetup
) -> None:
    """An ACCEPT (rejected=0) → status ACCEPTED, both quantities recorded, and NO stock change — the
    accepted stock is already received and usable (D-050 accepted-needs-no-move)."""
    setup = inspection_lot_setup
    before = await _on_hand(db_session, setup.tenant_id, setup.item_id)
    await _decide(
        db_session,
        setup.tenant_id,
        setup.lot_id,
        InspectionDecideRequest(
            accepted_quantity=setup.lot_quantity, rejected_quantity=Decimal(0)
        ),
    )
    after = await _on_hand(db_session, setup.tenant_id, setup.item_id)
    assert after == before  # no move
    with tenant_context(setup.tenant_id):
        lot = await service.get_inspection_lot(db_session, setup.tenant_id, setup.lot_id)
    assert lot.status == InspectionLotStatus.ACCEPTED.value
    assert Decimal(str(lot.accepted_quantity)) == setup.lot_quantity
    assert Decimal(str(lot.rejected_quantity)) == Decimal(0)
    assert lot.disposition is None
    assert lot.decided_date is not None


# --- Reject SCRAP (ADJUSTMENT-out write-off) ----------------------------------


async def test_reject_scrap_writes_off_stock_and_posts_journal(
    db_session: AsyncSession, inspection_lot_setup: InspectionLotSetup
) -> None:
    """A REJECT with SCRAP → status REJECTED, an ADJUSTMENT-out reduces on-hand by the rejected
    quantity, and the write-off journal credits the price-difference account (D-050)."""
    setup = inspection_lot_setup
    before = await _on_hand(db_session, setup.tenant_id, setup.item_id)
    await _decide(
        db_session,
        setup.tenant_id,
        setup.lot_id,
        InspectionDecideRequest(
            accepted_quantity=Decimal(0),
            rejected_quantity=setup.lot_quantity,
            disposition=RejectDisposition.SCRAP,
        ),
    )
    after = await _on_hand(db_session, setup.tenant_id, setup.item_id)
    assert after == before - setup.lot_quantity  # written off
    with tenant_context(setup.tenant_id):
        lot = await service.get_inspection_lot(db_session, setup.tenant_id, setup.lot_id)
    assert lot.status == InspectionLotStatus.REJECTED.value
    assert lot.disposition == RejectDisposition.SCRAP.value
    # The write-off offsets to the price-difference account (an ADJUSTMENT-down, D-020).
    lines = await _writeoff_lines(
        db_session, setup.tenant_id, setup.price_difference_account_id
    )
    assert lines, "expected a write-off journal line on the price-difference account"


# --- Reject BLOCK (TRANSFER to the blocked bin) -------------------------------


async def test_reject_block_transfers_to_blocked_bin(
    db_session: AsyncSession, inspection_lot_setup: InspectionLotSetup
) -> None:
    """A REJECT with BLOCK → a TRANSFER to the blocked bin: TOTAL on-hand unchanged (value-neutral),
    but the stock leaves the usable receiving bin and lands in the blocked bin (D-050)."""
    setup = inspection_lot_setup
    total_before = await _on_hand(db_session, setup.tenant_id, setup.item_id)
    receiving_before = await _on_hand(
        db_session, setup.tenant_id, setup.item_id, bin_id=setup.bin_id
    )
    await _decide(
        db_session,
        setup.tenant_id,
        setup.lot_id,
        InspectionDecideRequest(
            accepted_quantity=Decimal(0),
            rejected_quantity=setup.lot_quantity,
            disposition=RejectDisposition.BLOCK,
            blocked_bin_id=setup.blocked_bin_id,
        ),
    )
    total_after = await _on_hand(db_session, setup.tenant_id, setup.item_id)
    receiving_after = await _on_hand(
        db_session, setup.tenant_id, setup.item_id, bin_id=setup.bin_id
    )
    blocked_after = await _on_hand(
        db_session, setup.tenant_id, setup.item_id, bin_id=setup.blocked_bin_id
    )
    assert total_after == total_before  # value-neutral transfer
    assert receiving_after == receiving_before - setup.lot_quantity  # left the usable bin
    assert blocked_after == setup.lot_quantity  # landed in the blocked bin
    with tenant_context(setup.tenant_id):
        lot = await service.get_inspection_lot(db_session, setup.tenant_id, setup.lot_id)
    assert lot.status == InspectionLotStatus.REJECTED.value
    assert lot.disposition == RejectDisposition.BLOCK.value


# --- Partial accept/reject ----------------------------------------------------


async def test_partial_accept_reject_records_split_and_scraps_rejected(
    db_session: AsyncSession, inspection_lot_setup: InspectionLotSetup
) -> None:
    """A partial decision (some accepted, some rejected with SCRAP) → status REJECTED with both
    quantities recorded; only the rejected portion is scrapped (D-050)."""
    setup = inspection_lot_setup
    before = await _on_hand(db_session, setup.tenant_id, setup.item_id)
    await _decide(
        db_session,
        setup.tenant_id,
        setup.lot_id,
        InspectionDecideRequest(
            accepted_quantity=Decimal(7),
            rejected_quantity=Decimal(3),
            disposition=RejectDisposition.SCRAP,
        ),
    )
    after = await _on_hand(db_session, setup.tenant_id, setup.item_id)
    assert after == before - Decimal(3)  # only the rejected 3 are scrapped
    with tenant_context(setup.tenant_id):
        lot = await service.get_inspection_lot(db_session, setup.tenant_id, setup.lot_id)
    assert lot.status == InspectionLotStatus.REJECTED.value
    assert Decimal(str(lot.accepted_quantity)) == Decimal(7)
    assert Decimal(str(lot.rejected_quantity)) == Decimal(3)


# --- Validation ---------------------------------------------------------------


async def test_split_must_equal_lot_quantity(
    db_session: AsyncSession, inspection_lot_setup: InspectionLotSetup
) -> None:
    """accepted + rejected must equal the lot quantity (else 422)."""
    setup = inspection_lot_setup
    with pytest.raises(ValidationFailedError) as exc:
        await _decide(
            db_session,
            setup.tenant_id,
            setup.lot_id,
            InspectionDecideRequest(
                accepted_quantity=Decimal(5), rejected_quantity=Decimal(3)
            ),
        )
    assert exc.value.code == "quality.decision_quantity_mismatch"


async def test_reject_requires_disposition(
    db_session: AsyncSession, inspection_lot_setup: InspectionLotSetup
) -> None:
    """A rejection with no disposition is a 422."""
    setup = inspection_lot_setup
    with pytest.raises(ValidationFailedError) as exc:
        await _decide(
            db_session,
            setup.tenant_id,
            setup.lot_id,
            InspectionDecideRequest(
                accepted_quantity=Decimal(0), rejected_quantity=setup.lot_quantity
            ),
        )
    assert exc.value.code == "quality.disposition_required"


async def test_return_to_vendor_disposition_not_implemented(
    db_session: AsyncSession, inspection_lot_setup: InspectionLotSetup
) -> None:
    """RETURN_TO_VENDOR is declared but not implemented in v1 → 422."""
    setup = inspection_lot_setup
    with pytest.raises(ValidationFailedError) as exc:
        await _decide(
            db_session,
            setup.tenant_id,
            setup.lot_id,
            InspectionDecideRequest(
                accepted_quantity=Decimal(0),
                rejected_quantity=setup.lot_quantity,
                disposition=RejectDisposition.RETURN_TO_VENDOR,
            ),
        )
    assert exc.value.code == "quality.disposition_not_implemented"


async def test_block_requires_blocked_bin(
    db_session: AsyncSession, inspection_lot_setup: InspectionLotSetup
) -> None:
    """A BLOCK with no destination bin is a 422."""
    setup = inspection_lot_setup
    with pytest.raises(ValidationFailedError) as exc:
        await _decide(
            db_session,
            setup.tenant_id,
            setup.lot_id,
            InspectionDecideRequest(
                accepted_quantity=Decimal(0),
                rejected_quantity=setup.lot_quantity,
                disposition=RejectDisposition.BLOCK,
            ),
        )
    assert exc.value.code == "quality.blocked_bin_required"


# --- Idempotency / lifecycle --------------------------------------------------


async def test_decided_lot_cannot_be_re_decided(
    db_session: AsyncSession, inspection_lot_setup: InspectionLotSetup
) -> None:
    """A decided (terminal) lot cannot be decided again → 409."""
    setup = inspection_lot_setup
    await _decide(
        db_session,
        setup.tenant_id,
        setup.lot_id,
        InspectionDecideRequest(
            accepted_quantity=setup.lot_quantity, rejected_quantity=Decimal(0)
        ),
    )
    with pytest.raises(ConflictError) as exc:
        await _decide(
            db_session,
            setup.tenant_id,
            setup.lot_id,
            InspectionDecideRequest(
                accepted_quantity=setup.lot_quantity, rejected_quantity=Decimal(0)
            ),
        )
    assert exc.value.code == "quality.lot_not_open"


async def test_cancel_open_lot(
    db_session: AsyncSession, inspection_lot_setup: InspectionLotSetup
) -> None:
    """An OPEN lot cancels (moves no stock); a decided lot cannot be cancelled."""
    setup = inspection_lot_setup
    before = await _on_hand(db_session, setup.tenant_id, setup.item_id)

    async def work() -> None:
        with tenant_context(setup.tenant_id):
            await service.cancel_lot(db_session, setup.tenant_id, setup.lot_id)

    with tenant_context(setup.tenant_id):
        await run_in_uow(db_session, work)
        lot = await service.get_inspection_lot(db_session, setup.tenant_id, setup.lot_id)
    assert lot.status == InspectionLotStatus.CANCELLED.value
    after = await _on_hand(db_session, setup.tenant_id, setup.item_id)
    assert after == before  # nothing moved


# --- Closed-period rollback ---------------------------------------------------


async def test_scrap_into_closed_period_rolls_back(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """A SCRAP write-off dated into a CLOSED period trips the move's journal period trigger and
    rolls
    the WHOLE decision back — the lot stays OPEN and no stock is written off (D-050 all-or-nothing).
    Asserted via FRESH reads after the rolled-back uow (issue #53)."""
    setup = await build_inspection_lot_setup(db_session, tenant_a, receive_quantity="10")
    before = await _on_hand(db_session, tenant_a, setup.item_id)
    # Close the period the decision will post into.
    scrap_date = date(2026, 3, 15)
    with tenant_context(tenant_a):
        period = await finance_queries.find_period_for_date(db_session, tenant_a, scrap_date)
        await finance_service.close_period(db_session, tenant_a, period.id)
        await db_session.commit()

    with pytest.raises(Exception):  # noqa: B017 - period trigger / service error
        await _decide(
            db_session,
            tenant_a,
            setup.lot_id,
            InspectionDecideRequest(
                accepted_quantity=Decimal(0),
                rejected_quantity=setup.lot_quantity,
                disposition=RejectDisposition.SCRAP,
            ),
            decided_date=scrap_date,
        )

    # Nothing moved; the lot is still OPEN (fresh reads after the rolled-back uow).
    after = await _on_hand(db_session, tenant_a, setup.item_id)
    assert after == before
    with tenant_context(tenant_a):
        lot = await service.get_inspection_lot(db_session, tenant_a, setup.lot_id)
    assert lot.status == InspectionLotStatus.OPEN.value
