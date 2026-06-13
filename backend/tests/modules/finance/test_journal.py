"""Universal-journal service + API behavior (D-017/D-018), SQLite.

Proves the posting protocol, reversal-only correction, idempotent posting, the close-period
seam, gapless numbering, and statement-readiness denormalization. DB-trigger backstops are
proven separately in test_journal_db_guards.py (raw SQL, both engines).
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import run_in_uow, subscribe
from app.core.exceptions import ConflictError, ValidationFailedError
from app.core.tenancy import tenant_context
from app.modules.finance import service
from app.modules.finance.constants import EntryStatus
from app.modules.finance.events import JournalEntryPosted
from app.modules.finance.models import JournalEntry, JournalLine
from app.modules.finance.schemas import JournalEntryCreate, JournalLineCreate
from tests.modules.finance.conftest import JournalSetup

_PD = date(2026, 3, 15)  # a date inside the open 2026 fiscal year


def _balanced_payload(setup: JournalSetup, amount: str = "100.00") -> JournalEntryCreate:
    """Dr Cash / Cr Sales for ``amount`` — a balanced two-line entry."""
    return JournalEntryCreate(
        posting_date=_PD,
        currency_code="USD",
        description="Test entry",
        lines=[
            JournalLineCreate(
                account_id=setup.accounts["1000"],
                transaction_debit_amount=Decimal(amount),
            ),
            JournalLineCreate(
                account_id=setup.accounts["4000"],
                transaction_credit_amount=Decimal(amount),
            ),
        ],
    )


async def _create_draft(
    session: AsyncSession, setup: JournalSetup, amount: str = "100.00"
) -> JournalEntry:
    with tenant_context(setup.tenant_id):
        entry = await service.create_draft_entry(
            session, setup.tenant_id, _balanced_payload(setup, amount)
        )
        await session.commit()
    return entry


# --- draft creation -----------------------------------------------------------


async def test_create_balanced_draft_succeeds(
    db_session: AsyncSession, journal_setup: JournalSetup
) -> None:
    entry = await _create_draft(db_session, journal_setup)
    assert entry.status == EntryStatus.DRAFT.value
    assert entry.entry_number is None  # number claimed only at posting (D-012)
    with tenant_context(journal_setup.tenant_id):
        lines = (
            await db_session.execute(
                select(JournalLine).where(JournalLine.journal_entry_id == entry.id)
            )
        ).scalars().all()
    assert len(lines) == 2
    assert all(not line.is_posted for line in lines)
    # v1: functional == transaction (FX in 4.3).
    assert lines[0].functional_debit_amount == lines[0].transaction_debit_amount


async def test_create_unbalanced_draft_rejected_at_service(
    db_session: AsyncSession, journal_setup: JournalSetup
) -> None:
    payload = _balanced_payload(journal_setup)
    payload.lines[1].transaction_credit_amount = Decimal("99.00")  # no longer balances
    with tenant_context(journal_setup.tenant_id), pytest.raises(ValidationFailedError) as exc:
        await service.create_draft_entry(db_session, journal_setup.tenant_id, payload)
    assert exc.value.code == "finance.journal_unbalanced"


async def test_two_sided_line_rejected_at_service(
    db_session: AsyncSession, journal_setup: JournalSetup
) -> None:
    payload = _balanced_payload(journal_setup)
    payload.lines[0].transaction_credit_amount = Decimal("1.00")  # now both sides > 0
    with tenant_context(journal_setup.tenant_id), pytest.raises(ValidationFailedError) as exc:
        await service.create_draft_entry(db_session, journal_setup.tenant_id, payload)
    assert exc.value.code == "finance.journal_line_not_one_sided"


async def test_too_few_lines_rejected(
    db_session: AsyncSession, journal_setup: JournalSetup
) -> None:
    payload = JournalEntryCreate(
        posting_date=_PD,
        currency_code="USD",
        lines=[
            JournalLineCreate(
                account_id=journal_setup.accounts["1000"],
                transaction_debit_amount=Decimal("1.00"),
            )
        ],
    )
    with tenant_context(journal_setup.tenant_id), pytest.raises(ValidationFailedError) as exc:
        await service.create_draft_entry(db_session, journal_setup.tenant_id, payload)
    assert exc.value.code == "finance.journal_too_few_lines"


async def test_non_postable_account_rejected(
    db_session: AsyncSession, journal_setup: JournalSetup
) -> None:
    # Make 4000 non-postable, then a line on it must be refused.
    from app.modules.finance.models import Account

    with tenant_context(journal_setup.tenant_id):
        sales = await db_session.get(Account, journal_setup.accounts["4000"])
        sales.is_postable = False
        await db_session.commit()
    with tenant_context(journal_setup.tenant_id), pytest.raises(ValidationFailedError) as exc:
        await service.create_draft_entry(
            db_session, journal_setup.tenant_id, _balanced_payload(journal_setup)
        )
    assert exc.value.code == "finance.journal_account_not_postable"


# --- posting protocol ---------------------------------------------------------


async def test_post_assigns_number_and_denormalizes_lines(
    db_session: AsyncSession, journal_setup: JournalSetup
) -> None:
    entry = await _create_draft(db_session, journal_setup)
    captured: list[JournalEntryPosted] = []

    async def _capture(session: AsyncSession, event: JournalEntryPosted) -> None:
        captured.append(event)

    subscribe(JournalEntryPosted.key, _capture)

    with tenant_context(journal_setup.tenant_id):
        async def work() -> None:
            await service.post_entry(db_session, journal_setup.tenant_id, entry.id)

        await run_in_uow(db_session, work)
        await db_session.refresh(entry)
        lines = (
            await db_session.execute(
                select(JournalLine).where(JournalLine.journal_entry_id == entry.id)
            )
        ).scalars().all()

    assert entry.status == EntryStatus.POSTED.value
    assert entry.entry_number == "JE-2026-00001"
    assert entry.posted_at is not None
    assert entry.fiscal_period_id is not None
    # Statement-readiness: every line carries the denormalized projection fields (D-021).
    for line in lines:
        assert line.is_posted is True
        assert line.posting_date == _PD
        assert line.fiscal_period_id == entry.fiscal_period_id
    # JournalEntryPosted fired with the entry id and balanced total.
    assert len(captured) == 1
    assert captured[0].entry_id == entry.id
    assert captured[0].total_functional_amount == Decimal("100.00")


async def test_post_registers_and_numbers_document(
    db_session: AsyncSession, journal_setup: JournalSetup
) -> None:
    from app.core.docflow import Document

    entry = await _create_draft(db_session, journal_setup)
    with tenant_context(journal_setup.tenant_id):
        await run_in_uow(
            db_session,
            lambda: service.post_entry(db_session, journal_setup.tenant_id, entry.id),
        )
        await db_session.refresh(entry)
        document = await db_session.get(Document, entry.document_id)
    assert document is not None
    assert document.doc_number == "JE-2026-00001"
    assert document.status == EntryStatus.POSTED.value


async def test_post_non_draft_rejected(
    db_session: AsyncSession, journal_setup: JournalSetup
) -> None:
    entry = await _create_draft(db_session, journal_setup)
    with tenant_context(journal_setup.tenant_id):
        await run_in_uow(
            db_session,
            lambda: service.post_entry(db_session, journal_setup.tenant_id, entry.id),
        )
        with pytest.raises(ConflictError) as exc:
            await service.post_entry(db_session, journal_setup.tenant_id, entry.id)
    assert exc.value.code == "finance.journal_not_draft"


async def test_post_to_closed_period_rejected_at_service(
    db_session: AsyncSession, journal_setup: JournalSetup
) -> None:
    # Close the March period, then posting an entry dated in March is refused at the service.
    with tenant_context(journal_setup.tenant_id):
        periods = (
            await service.list_fiscal_periods(
                db_session, journal_setup.tenant_id, journal_setup.fiscal_year_id
            )
        ).items
        march = next(p for p in periods if p.start_date == date(2026, 3, 1))
        await service.close_period(db_session, journal_setup.tenant_id, march.id)
        await db_session.commit()
    entry = await _create_draft(db_session, journal_setup)
    with tenant_context(journal_setup.tenant_id), pytest.raises(ValidationFailedError) as exc:
        await service.post_entry(db_session, journal_setup.tenant_id, entry.id)
    assert exc.value.code == "finance.period_closed"


async def test_post_with_no_covering_period_rejected(
    db_session: AsyncSession, journal_setup: JournalSetup
) -> None:
    payload = _balanced_payload(journal_setup)
    payload.posting_date = date(2099, 1, 1)  # no period covers this
    with tenant_context(journal_setup.tenant_id):
        entry = await service.create_draft_entry(db_session, journal_setup.tenant_id, payload)
        await db_session.commit()
        with pytest.raises(ValidationFailedError) as exc:
            await service.post_entry(db_session, journal_setup.tenant_id, entry.id)
    assert exc.value.code == "finance.period_closed"


# --- gapless numbering --------------------------------------------------------


async def test_gapless_numbering_across_three_posts(
    db_session: AsyncSession, journal_setup: JournalSetup
) -> None:
    numbers: list[str] = []
    for _ in range(3):
        entry = await _create_draft(db_session, journal_setup)
        with tenant_context(journal_setup.tenant_id):
            await run_in_uow(
                db_session,
                lambda eid=entry.id: service.post_entry(
                    db_session, journal_setup.tenant_id, eid
                ),
            )
            await db_session.refresh(entry)
        numbers.append(entry.entry_number)
    assert numbers == ["JE-2026-00001", "JE-2026-00002", "JE-2026-00003"]


async def test_rolled_back_post_does_not_burn_a_number(
    db_session: AsyncSession, journal_setup: JournalSetup
) -> None:
    # A draft whose period is closed fails to post; the next good post must still get 00001.
    with tenant_context(journal_setup.tenant_id):
        periods = (
            await service.list_fiscal_periods(
                db_session, journal_setup.tenant_id, journal_setup.fiscal_year_id
            )
        ).items
        feb = next(p for p in periods if p.start_date == date(2026, 2, 1))
        await service.close_period(db_session, journal_setup.tenant_id, feb.id)
        await db_session.commit()

    bad = _balanced_payload(journal_setup)
    bad.posting_date = date(2026, 2, 10)
    with tenant_context(journal_setup.tenant_id):
        bad_entry = await service.create_draft_entry(
            db_session, journal_setup.tenant_id, bad
        )
        await db_session.commit()

        async def bad_work() -> None:
            await service.post_entry(db_session, journal_setup.tenant_id, bad_entry.id)

        with pytest.raises(ValidationFailedError):
            await run_in_uow(db_session, bad_work)

    good = await _create_draft(db_session, journal_setup)
    with tenant_context(journal_setup.tenant_id):
        await run_in_uow(
            db_session,
            lambda: service.post_entry(db_session, journal_setup.tenant_id, good.id),
        )
        await db_session.refresh(good)
    assert good.entry_number == "JE-2026-00001"


# --- reversal -----------------------------------------------------------------


async def test_reverse_swaps_sides_and_links(
    db_session: AsyncSession, journal_setup: JournalSetup
) -> None:
    from app.core.docflow import get_document_chain

    entry = await _create_draft(db_session, journal_setup)
    with tenant_context(journal_setup.tenant_id):
        await run_in_uow(
            db_session,
            lambda: service.post_entry(db_session, journal_setup.tenant_id, entry.id),
        )

        holder: dict[str, JournalEntry] = {}

        async def work() -> None:
            holder["rev"] = await service.reverse_entry(
                db_session, journal_setup.tenant_id, entry.id, date(2026, 4, 1)
            )

        await run_in_uow(db_session, work)
        reversal = holder["rev"]
        await db_session.refresh(entry)
        await db_session.refresh(reversal)

        original_lines = (
            await db_session.execute(
                select(JournalLine)
                .where(JournalLine.journal_entry_id == entry.id)
                .order_by(JournalLine.line_number)
            )
        ).scalars().all()
        reversal_lines = (
            await db_session.execute(
                select(JournalLine)
                .where(JournalLine.journal_entry_id == reversal.id)
                .order_by(JournalLine.line_number)
            )
        ).scalars().all()
        chain = await get_document_chain(
            db_session, journal_setup.tenant_id, entry.document_id
        )

    assert entry.status == EntryStatus.REVERSED.value
    assert entry.reversed_by_entry_id == reversal.id
    assert reversal.status == EntryStatus.POSTED.value
    assert reversal.reverses_entry_id == entry.id
    assert reversal.entry_number == "JE-2026-00002"  # original was 00001
    # Debit/credit swapped per line.
    for orig, rev in zip(original_lines, reversal_lines, strict=True):
        assert rev.transaction_debit_amount == orig.transaction_credit_amount
        assert rev.transaction_credit_amount == orig.transaction_debit_amount
    # docflow chain links the two documents with a 'reverses' edge.
    assert len(chain.nodes) == 2
    assert any(edge.link_type == "reverses" for edge in chain.edges)


async def test_reverse_non_posted_rejected(
    db_session: AsyncSession, journal_setup: JournalSetup
) -> None:
    entry = await _create_draft(db_session, journal_setup)  # still DRAFT
    with tenant_context(journal_setup.tenant_id), pytest.raises(ConflictError) as exc:
        await service.reverse_entry(
            db_session, journal_setup.tenant_id, entry.id, date(2026, 4, 1)
        )
    assert exc.value.code == "finance.journal_not_posted"


# --- close-period seam --------------------------------------------------------


async def test_close_period_with_draft_in_it_rejected(
    db_session: AsyncSession, journal_setup: JournalSetup
) -> None:
    await _create_draft(db_session, journal_setup)  # DRAFT dated 2026-03-15
    with tenant_context(journal_setup.tenant_id):
        periods = (
            await service.list_fiscal_periods(
                db_session, journal_setup.tenant_id, journal_setup.fiscal_year_id
            )
        ).items
        march = next(p for p in periods if p.start_date == date(2026, 3, 1))
        with pytest.raises(ValidationFailedError) as exc:
            await service.close_period(db_session, journal_setup.tenant_id, march.id)
    assert exc.value.code == "finance.period_has_draft_entries"


async def test_close_period_succeeds_after_posting_the_draft(
    db_session: AsyncSession, journal_setup: JournalSetup
) -> None:
    entry = await _create_draft(db_session, journal_setup)
    with tenant_context(journal_setup.tenant_id):
        await run_in_uow(
            db_session,
            lambda: service.post_entry(db_session, journal_setup.tenant_id, entry.id),
        )
        periods = (
            await service.list_fiscal_periods(
                db_session, journal_setup.tenant_id, journal_setup.fiscal_year_id
            )
        ).items
        march = next(p for p in periods if p.start_date == date(2026, 3, 1))
        closed = await service.close_period(db_session, journal_setup.tenant_id, march.id)
    assert closed.status == "CLOSED"
