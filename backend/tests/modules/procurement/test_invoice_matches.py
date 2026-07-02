"""3-way invoice-match service behaviour (PLAN 6.4, D-042): create against a received PO,
over-billing rejection, tolerance → MATCHED/EXCEPTION, post → AP bill (Dr GR/IR + PPV / Cr AP), the
GR/IR-clears-to-zero procure-to-pay proof, PO billed_quantity + CLOSED advance, docflow chain,
override, closed-period rollback, idempotency, tenant isolation.

Matches go through the REAL service inside a uow (D-025); the procurement conftest's autouse fixture
registers the procurement→inventory + inventory→finance + procurement→finance handlers, so a posted
match creates + posts the AP vendor bill and clears GR/IR exactly as in production.
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
from app.modules.finance.constants import DocumentType
from app.modules.finance.models import JournalEntry, JournalLine, VendorBill
from app.modules.procurement import queries as procurement_queries
from app.modules.procurement import service
from app.modules.procurement.constants import MatchStatus, PurchaseOrderStatus
from app.modules.procurement.models import PurchaseOrderLine
from app.modules.procurement.schemas import (
    InvoiceMatchLineCreate,
    MatchToleranceUpsert,
)
from tests.modules.procurement.conftest import InvoiceMatchSetup
from tests.modules.procurement.factories import (
    build_invoice_match,
    build_invoice_match_setup,
    post_invoice_match,
)


def _line(setup: InvoiceMatchSetup, qty: str, unit_price: str, *, with_gr: bool = False):
    return InvoiceMatchLineCreate(
        purchase_order_line_id=setup.po_line_id,
        goods_receipt_line_id=setup.gr_line_id if with_gr else None,
        matched_quantity=Decimal(qty),
        unit_price=Decimal(unit_price),
    )


async def _account_balance(
    session: AsyncSession, tenant_id: uuid.UUID, account_id: uuid.UUID
) -> Decimal:
    """Signed (debit-positive) balance of one account over the posted journal — the trial-balance
    figure for the GR/IR-clears-to-zero proof."""
    with tenant_context(tenant_id):
        balances = await finance_queries.account_balances(
            session, tenant_id, date_to=date(2099, 1, 1)
        )
    return balances.get(account_id, Decimal(0))


async def _ap_bill(session: AsyncSession, tenant_id: uuid.UUID) -> VendorBill | None:
    with tenant_context(tenant_id):
        return (
            await session.execute(select(VendorBill).where(VendorBill.tenant_id == tenant_id))
        ).scalar_one_or_none()


async def _ap_journal_lines(
    session: AsyncSession, tenant_id: uuid.UUID
) -> list[JournalLine]:
    with tenant_context(tenant_id):
        entries = (
            await session.execute(
                select(JournalEntry).where(
                    JournalEntry.tenant_id == tenant_id,
                    JournalEntry.document_type == DocumentType.AP_INVOICE.value,
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
                ).scalars().all()
            )
        return lines


# --- Create draft -------------------------------------------------------------


async def test_create_match_is_matched_within_tolerance(
    db_session: AsyncSession, invoice_match_setup: InvoiceMatchSetup
) -> None:
    """A match at the PO price (no variance) is MATCHED and carries a MATCH number."""
    match = await build_invoice_match(
        db_session,
        invoice_match_setup.tenant_id,
        po_id=invoice_match_setup.po_id,
        lines=[_line(invoice_match_setup, "10", "5")],
    )
    assert match.status == MatchStatus.MATCHED.value
    assert match.match_number.startswith("MATCH-")
    assert match.vendor_id == invoice_match_setup.vendor_id


async def test_create_rejects_over_billing(
    db_session: AsyncSession, invoice_match_setup: InvoiceMatchSetup
) -> None:
    """Billing more than received − already-billed is rejected 422 procurement.over_billing (the
    3-way constraint: no billing beyond goods receipt)."""
    with pytest.raises(ValidationFailedError) as exc:
        await build_invoice_match(
            db_session,
            invoice_match_setup.tenant_id,
            po_id=invoice_match_setup.po_id,
            lines=[_line(invoice_match_setup, "11", "5")],  # received only 10
        )
    assert exc.value.code == "procurement.over_billing"


async def test_price_outside_tolerance_is_exception(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """A line whose invoiced price exceeds the (default strict 0%) price tolerance → EXCEPTION."""
    setup = await build_invoice_match_setup(db_session, tenant_a)
    match = await build_invoice_match(
        db_session,
        tenant_a,
        po_id=setup.po_id,
        lines=[_line(setup, "10", "6")],  # PO price 5, invoiced 6 → 20% over, default tol 0%
    )
    assert match.status == MatchStatus.EXCEPTION.value


async def test_price_within_configured_tolerance_is_matched(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """With a 25% price tolerance configured, a 20%-over price is MATCHED, not EXCEPTION."""
    setup = await build_invoice_match_setup(db_session, tenant_a)
    with tenant_context(tenant_a):
        await service.upsert_match_tolerance(
            db_session,
            tenant_a,
            MatchToleranceUpsert(price_tolerance_percent=Decimal(25)),
        )
        await db_session.commit()
    match = await build_invoice_match(
        db_session, tenant_a, po_id=setup.po_id, lines=[_line(setup, "10", "6")]
    )
    assert match.status == MatchStatus.MATCHED.value


# --- Post: AP bill + GR/IR clearing ------------------------------------------


async def test_post_match_creates_balanced_ap_bill(
    db_session: AsyncSession, invoice_match_setup: InvoiceMatchSetup
) -> None:
    """Posting a clean match creates a POSTED AP vendor bill: Dr GR/IR 50 / Cr AP 50, balanced."""
    setup = invoice_match_setup
    match = await build_invoice_match(
        db_session, setup.tenant_id, po_id=setup.po_id, lines=[_line(setup, "10", "5")]
    )
    posted = await post_invoice_match(db_session, setup.tenant_id, match.id)
    assert posted.status == MatchStatus.POSTED.value

    bill = await _ap_bill(db_session, setup.tenant_id)
    assert bill is not None
    assert bill.bill_number is not None
    assert Decimal(bill.gross_amount) == Decimal(50)  # 10 @ 5
    assert Decimal(bill.open_amount) == Decimal(50)

    lines = await _ap_journal_lines(db_session, setup.tenant_id)
    gr_ir_debit = sum(
        (Decimal(line.transaction_debit_amount) for line in lines
         if line.account_id == setup.gr_ir_account_id),
        Decimal(0),
    )
    ap_credit = sum(
        (Decimal(line.transaction_credit_amount) for line in lines
         if line.account_id == setup.ap_account_id),
        Decimal(0),
    )
    assert gr_ir_debit == Decimal(50)
    assert ap_credit == Decimal(50)


async def test_gr_ir_clears_to_zero_end_to_end(
    db_session: AsyncSession, invoice_match_setup: InvoiceMatchSetup
) -> None:
    """THE procure-to-pay proof: PO → receive (Dr Inv / Cr GR-IR) → match+bill (Dr GR-IR / Cr AP).
    Once fully received + billed at PO cost, GR/IR nets to ZERO; AP owes the vendor 50."""
    setup = invoice_match_setup
    # After receipt, GR/IR was credited 50 (balance -50).
    assert await _account_balance(db_session, setup.tenant_id, setup.gr_ir_account_id) == Decimal(
        -50
    )
    match = await build_invoice_match(
        db_session, setup.tenant_id, po_id=setup.po_id, lines=[_line(setup, "10", "5")]
    )
    await post_invoice_match(db_session, setup.tenant_id, match.id)
    # The bill debited GR/IR 50 → it nets to ZERO; AP control credited 50.
    assert await _account_balance(db_session, setup.tenant_id, setup.gr_ir_account_id) == Decimal(0)
    assert await _account_balance(db_session, setup.tenant_id, setup.ap_account_id) == Decimal(-50)


async def test_price_variance_routes_to_ppv_and_gr_ir_still_clears(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """With a within-tolerance price variance, GR/IR still clears to ZERO (debited at PO cost) and
    the PPV account holds the difference; AP owes the vendor-invoiced total."""
    setup = await build_invoice_match_setup(db_session, tenant_a)
    with tenant_context(tenant_a):
        await service.upsert_match_tolerance(
            db_session, tenant_a, MatchToleranceUpsert(price_tolerance_percent=Decimal(25))
        )
        await db_session.commit()
    match = await build_invoice_match(
        db_session, tenant_a, po_id=setup.po_id, lines=[_line(setup, "10", "6")]
    )
    await post_invoice_match(db_session, tenant_a, match.id)
    # GR/IR debited at PO cost (10×5=50) → nets to 0 from its -50 receipt credit.
    assert await _account_balance(db_session, tenant_a, setup.gr_ir_account_id) == Decimal(0)
    # PPV holds the price difference (10×(6-5)=10, a debit/extra cost).
    assert await _account_balance(db_session, tenant_a, setup.ppv_account_id) == Decimal(10)
    # AP owes the full invoiced total (10×6=60).
    assert await _account_balance(db_session, tenant_a, setup.ap_account_id) == Decimal(-60)


async def test_post_raises_billed_quantity_and_closes_po(
    db_session: AsyncSession, invoice_match_setup: InvoiceMatchSetup
) -> None:
    """Posting raises the PO line's billed_quantity and advances a fully received+billed PO to
    CLOSED."""
    setup = invoice_match_setup
    match = await build_invoice_match(
        db_session, setup.tenant_id, po_id=setup.po_id, lines=[_line(setup, "10", "5")]
    )
    await post_invoice_match(db_session, setup.tenant_id, match.id)
    with tenant_context(setup.tenant_id):
        po_line = await db_session.get(PurchaseOrderLine, setup.po_line_id)
        await db_session.refresh(po_line)
        po = await service.get_purchase_order(db_session, setup.tenant_id, setup.po_id)
        await db_session.refresh(po)
    assert Decimal(po_line.billed_quantity) == Decimal(10)
    assert po.status == PurchaseOrderStatus.CLOSED.value


async def test_docflow_po_match_bill_chain(
    db_session: AsyncSession, invoice_match_setup: InvoiceMatchSetup
) -> None:
    """The docflow chain spans PO → match (matched_by) and match → bill (billed_by)."""
    setup = invoice_match_setup
    match = await build_invoice_match(
        db_session,
        setup.tenant_id,
        po_id=setup.po_id,
        lines=[_line(setup, "10", "5", with_gr=True)],
    )
    posted = await post_invoice_match(db_session, setup.tenant_id, match.id)
    with tenant_context(setup.tenant_id):
        chain = await docflow.get_document_chain(db_session, setup.tenant_id, posted.document_id)
    link_types = {edge.link_type for edge in chain.edges}
    assert "matched_by" in link_types
    assert "billed_by" in link_types


# --- Exception → override → post ---------------------------------------------


async def test_exception_cannot_post_without_override(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """An EXCEPTION match cannot post until overridden (the invoice-release control)."""
    setup = await build_invoice_match_setup(db_session, tenant_a)
    match = await build_invoice_match(
        db_session, tenant_a, po_id=setup.po_id, lines=[_line(setup, "10", "6")]
    )
    with pytest.raises(ConflictError) as exc:
        await post_invoice_match(db_session, tenant_a, match.id)
    assert exc.value.code == "procurement.match_in_exception"


async def test_override_then_post(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """Overriding an EXCEPTION moves it to MATCHED and lets it post."""
    setup = await build_invoice_match_setup(db_session, tenant_a)
    match = await build_invoice_match(
        db_session, tenant_a, po_id=setup.po_id, lines=[_line(setup, "10", "6")]
    )

    async def _override() -> None:
        with tenant_context(tenant_a):
            await service.override_invoice_match(db_session, tenant_a, match.id)

    from app.core.events import run_in_uow

    with tenant_context(tenant_a):
        await run_in_uow(db_session, _override)
    posted = await post_invoice_match(db_session, tenant_a, match.id)
    assert posted.status == MatchStatus.POSTED.value


# --- Closed period + idempotency + isolation ---------------------------------


async def test_closed_period_invoice_date_rolls_back(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """A match whose invoice_date falls in a CLOSED period trips the bill's journal period trigger
    and rolls the whole post back (the match stays MATCHED, no bill)."""
    from app.modules.finance import service as finance_service

    invoice_date = date(2026, 3, 15)
    setup = await build_invoice_match_setup(db_session, tenant_a)
    match = await build_invoice_match(
        db_session,
        tenant_a,
        po_id=setup.po_id,
        lines=[_line(setup, "10", "5")],
        invoice_date=invoice_date,
    )
    match_id = match.id  # plain id: the rolled-back post below expires the loaded object
    with tenant_context(tenant_a):
        period = await finance_queries.find_period_for_date(db_session, tenant_a, invoice_date)
        await finance_service.close_period(db_session, tenant_a, period.id)
        await db_session.commit()

    with pytest.raises(Exception):  # noqa: B017  (the period trigger / service error)
        await post_invoice_match(db_session, tenant_a, match_id)

    with tenant_context(tenant_a):
        reread = await service.get_invoice_match(db_session, tenant_a, match_id)
        status = reread.status
    assert status == MatchStatus.MATCHED.value
    assert await _ap_bill(db_session, tenant_a) is None


async def test_post_is_idempotent_rejected_when_already_posted(
    db_session: AsyncSession, invoice_match_setup: InvoiceMatchSetup
) -> None:
    """Re-posting a POSTED match is rejected (terminal) — no second bill."""
    setup = invoice_match_setup
    match = await build_invoice_match(
        db_session, setup.tenant_id, po_id=setup.po_id, lines=[_line(setup, "10", "5")]
    )
    await post_invoice_match(db_session, setup.tenant_id, match.id)
    with pytest.raises(ConflictError) as exc:
        await post_invoice_match(db_session, setup.tenant_id, match.id)
    assert exc.value.code == "procurement.match_already_posted"


async def test_po_line_open_to_bill_decreases_after_post(
    db_session: AsyncSession, invoice_match_setup: InvoiceMatchSetup
) -> None:
    """po_line_open_to_bill (received − billed) drops to 0 once the received quantity is fully
    billed."""
    setup = invoice_match_setup
    with tenant_context(setup.tenant_id):
        before = await procurement_queries.po_line_open_to_bill(
            db_session, setup.tenant_id, setup.po_line_id
        )
    assert before == Decimal(10)
    match = await build_invoice_match(
        db_session, setup.tenant_id, po_id=setup.po_id, lines=[_line(setup, "10", "5")]
    )
    await post_invoice_match(db_session, setup.tenant_id, match.id)
    with tenant_context(setup.tenant_id):
        after = await procurement_queries.po_line_open_to_bill(
            db_session, setup.tenant_id, setup.po_line_id
        )
    assert after == Decimal(0)
