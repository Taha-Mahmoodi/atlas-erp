"""Journal-entry HTTP layer (D-017), included into the finance router.

Split out of router.py to keep both files under the STRUCTURE §3 400-line cap (the finance router
covers the COA + fiscal-calendar reference endpoints; this sub-router covers journal entries — a
distinct aggregate). Mounted via ``router.include_router(journal_router)`` in router.py, so the
whole module is still ONE surface at ``/api/v1/finance`` — there is no second mount in main.py.

Reads are guarded by ``finance.journal.read``; create/post by ``finance.journal.post`` and reverse
by ``finance.journal.reverse`` (D-009). post/reverse are IDEMPOTENT (D-013): ``capture()`` lands in
the posting uow so the document and the replay record commit atomically. Writes commit through
``run_in_uow`` (D-011) so audit + events ride the transaction.

Journal entries are transactional/fast-changing, so they deliberately carry NO conditional-request
ETag (PERFORMANCE §3 scopes ETags to slow-changing reference data only) — the COA/fiscal/FX/tax
reference lists do.
"""

import uuid
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends

from app.core.deps import CurrentUserDep, SessionDep
from app.core.events import run_in_uow
from app.core.idempotency import Idempotent, IdempotentDep
from app.core.pagination import CursorParams, cursor_params, map_page
from app.core.rbac import require_permission
from app.core.schemas import Page
from app.modules.finance import service
from app.modules.finance.constants import (
    FINANCE_JOURNAL_POST,
    FINANCE_JOURNAL_READ,
    FINANCE_JOURNAL_REVERSE,
)
from app.modules.finance.schemas import (
    JournalEntryCreate,
    JournalEntryDetail,
    JournalEntryRead,
    JournalEntryReverseRequest,
    JournalLineRead,
)

journal_router = APIRouter(tags=["finance-journal"])

CursorParamsDep = Depends(cursor_params)
# Module-level Depends singletons (ruff B008): each is the D-013 reservation guard for its endpoint.
_PostIdempotentDep = Depends(Idempotent("finance.journal.post"))
_ReverseIdempotentDep = Depends(Idempotent("finance.journal.reverse"))


async def _commit[T](session: SessionDep, work: Callable[[], Awaitable[T]]) -> T:
    """Run a service call inside the D-011 uow, returning its ORM result refreshed in the async
    context so a sync ``model_validate`` never trips MissingGreenlet (twin of router._commit)."""
    holder: list[T] = []

    async def _work() -> None:
        result = await work()
        await session.refresh(result)
        holder.append(result)

    await run_in_uow(session, _work)
    return holder[0]


async def _entry_detail(
    session: SessionDep, tenant_id: uuid.UUID, entry_id: uuid.UUID
) -> JournalEntryDetail:
    """Load an entry + its lines into the detail schema. ``refresh`` materializes the server-side
    ``updated_at`` in the async context before the sync ``model_validate`` (else an expired
    attribute triggers an async lazy-load in sync serialization — MissingGreenlet)."""
    entry, lines = await service.get_entry_with_lines(session, tenant_id, entry_id)
    await session.refresh(entry)
    header = JournalEntryRead.model_validate(entry)
    return JournalEntryDetail(
        **header.model_dump(),
        lines=[JournalLineRead.model_validate(line) for line in lines],
    )


@journal_router.post(
    "/journal-entries",
    response_model=JournalEntryRead,
    status_code=201,
    dependencies=[Depends(require_permission(FINANCE_JOURNAL_POST))],
)
async def create_journal_entry(
    payload: JournalEntryCreate,
    current: CurrentUserDep,
    session: SessionDep,
) -> JournalEntryRead:
    """Create a DRAFT entry (no number claimed). journal.post covers create + post."""
    entry = await _commit(
        session, lambda: service.create_draft_entry(session, current.tenant_id, payload)
    )
    return JournalEntryRead.model_validate(entry)


@journal_router.post(
    "/journal-entries/{entry_id}/post",
    response_model=JournalEntryDetail,
    dependencies=[Depends(require_permission(FINANCE_JOURNAL_POST))],
)
async def post_journal_entry(
    entry_id: uuid.UUID,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _PostIdempotentDep,
) -> JournalEntryDetail:
    """Post a draft entry (D-017). IDEMPOTENT (D-013): capture() lands in the posting uow, so the
    document and the replay record commit atomically."""
    holder: dict[str, JournalEntryDetail] = {}

    async def work() -> None:
        await service.post_entry(session, current.tenant_id, entry_id)
        detail = await _entry_detail(session, current.tenant_id, entry_id)
        holder["read"] = await idem.capture(detail)

    await run_in_uow(session, work)
    return holder["read"]


@journal_router.post(
    "/journal-entries/{entry_id}/reverse",
    response_model=JournalEntryDetail,
    dependencies=[Depends(require_permission(FINANCE_JOURNAL_REVERSE))],
)
async def reverse_journal_entry(
    entry_id: uuid.UUID,
    payload: JournalEntryReverseRequest,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _ReverseIdempotentDep,
) -> JournalEntryDetail:
    """Reverse a posted entry (D-017); returns the NEW reversing entry with lines. IDEMPOTENT."""
    holder: dict[str, JournalEntryDetail] = {}

    async def work() -> None:
        reversal = await service.reverse_entry(
            session,
            current.tenant_id,
            entry_id,
            payload.reversal_date,
            payload.description,
        )
        detail = await _entry_detail(session, current.tenant_id, reversal.id)
        holder["read"] = await idem.capture(detail)

    await run_in_uow(session, work)
    return holder["read"]


@journal_router.get(
    "/journal-entries",
    response_model=Page[JournalEntryRead],
    dependencies=[Depends(require_permission(FINANCE_JOURNAL_READ))],
)
async def list_journal_entries(
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
    status: str | None = None,
) -> Page[JournalEntryRead]:
    page = await service.list_entries(
        session,
        current.tenant_id,
        cursor=params.cursor,
        limit=params.limit,
        status=status,
    )
    return map_page(page, JournalEntryRead)


@journal_router.get(
    "/journal-entries/{entry_id}",
    response_model=JournalEntryDetail,
    dependencies=[Depends(require_permission(FINANCE_JOURNAL_READ))],
)
async def get_journal_entry(
    entry_id: uuid.UUID,
    current: CurrentUserDep,
    session: SessionDep,
) -> JournalEntryDetail:
    return await _entry_detail(session, current.tenant_id, entry_id)
