"""Bank reconciliation HTTP layer (PLAN 4.9), included into the finance router.

A sibling sub-router exactly like ap_router/ar_router (one surface at ``/api/v1/finance``).
Reads are guarded by ``finance.bank.read``, the CSV import by ``finance.bank.import``, and
every reconciliation action (suggest/confirm/reject/clear) by ``finance.bank.reconcile``
(D-009). Writes commit through ``run_in_uow`` (D-011).

**The import sync/background split** (PERFORMANCE §3): THIS router counts the CSV's data rows —
up to ``BANK_IMPORT_SYNC_MAX_LINES`` (1000) the import runs inline and returns 201 with the
statement; above that it submits a ``finance.bank_statement_import`` job and returns
202 {job_id} for /api/v1/jobs polling. Both paths share one IDEMPOTENT endpoint (D-013): the
capture commits atomically with the statement (or the PENDING job row, so a replayed key
returns the SAME job id). Clearing posts a journal entry, so it is idempotent too;
suggest-matches is rerun-safe by construction (already-suggested lines are untouched).
"""

import uuid

from fastapi import APIRouter, Depends, Response

from app.core.deps import CurrentUserDep, SessionDep, SessionFactoryDep
from app.core.events import run_in_uow
from app.core.idempotency import Idempotent, IdempotentDep
from app.core.jobs import schedule_job, submit_job
from app.core.pagination import CursorParams, cursor_params, map_page
from app.core.rbac import require_permission
from app.core.schemas import JobSubmitted, Page
from app.modules.finance import service
from app.modules.finance.bank_schemas import (
    BankStatementDetail,
    BankStatementImportRequest,
    BankStatementLineRead,
    BankStatementRead,
    ClearLineRequest,
    StatementProgressRead,
    SuggestMatchesResult,
)
from app.modules.finance.constants import (
    BANK_IMPORT_SYNC_MAX_LINES,
    BANK_STATEMENT_IMPORT_JOB,
    FINANCE_BANK_IMPORT,
    FINANCE_BANK_READ,
    FINANCE_BANK_RECONCILE,
)
from app.modules.finance.service.bank_csv import count_csv_data_rows

bank_router = APIRouter(tags=["finance-bank"])

CursorParamsDep = Depends(cursor_params)
_ImportIdempotentDep = Depends(Idempotent("finance.bank.statement_import"))
_ClearIdempotentDep = Depends(Idempotent("finance.bank.line_clear"))
_ReadGuard = Depends(require_permission(FINANCE_BANK_READ))
_ReconcileGuard = Depends(require_permission(FINANCE_BANK_RECONCILE))


async def _import_inline(
    payload: BankStatementImportRequest,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep,
) -> BankStatementRead:
    holder: dict[str, BankStatementRead] = {}

    async def work() -> None:
        statement = await service.import_statement(
            session,
            current.tenant_id,
            bank_account_id=payload.bank_account_id,
            statement_date=payload.statement_date,
            opening_balance=payload.opening_balance,
            closing_balance=payload.closing_balance,
            currency_code=payload.currency_code,
            csv_text=payload.csv_text,
            source_filename=payload.source_filename,
        )
        await session.refresh(statement)
        holder["read"] = await idem.capture(
            BankStatementRead.model_validate(statement), status_code=201
        )

    await run_in_uow(session, work)
    return holder["read"]


async def _import_background(
    payload: BankStatementImportRequest,
    current: CurrentUserDep,
    session: SessionDep,
    factory: SessionFactoryDep,
    idem: IdempotentDep,
) -> JobSubmitted:
    holder: dict[str, JobSubmitted] = {}
    job_id_holder: dict[str, uuid.UUID] = {}

    async def work() -> None:
        job = await submit_job(
            session,
            current.tenant_id,
            BANK_STATEMENT_IMPORT_JOB,
            {
                "bank_account_id": str(payload.bank_account_id),
                "statement_date": payload.statement_date.isoformat(),
                "opening_balance": str(payload.opening_balance),
                "closing_balance": str(payload.closing_balance),
                "currency_code": payload.currency_code,
                "csv_text": payload.csv_text,
                "source_filename": payload.source_filename,
            },
            submitted_by=current.user_id,
        )
        # The handler stamps import_job_id on the statement, but a job cannot know its own id
        # from the payload alone — write it back (full reassignment so the JSON change flushes).
        job.payload = {**job.payload, "job_id": str(job.id)}
        job_id_holder["job_id"] = job.id
        holder["read"] = await idem.capture(
            JobSubmitted(job_id=job.id, status=job.status), status_code=202
        )

    await run_in_uow(session, work)
    schedule_job(job_id_holder["job_id"], factory)
    return holder["read"]


@bank_router.post(
    "/bank-statements",
    response_model=BankStatementRead | JobSubmitted,
    status_code=201,
    dependencies=[Depends(require_permission(FINANCE_BANK_IMPORT))],
)
async def import_bank_statement(
    payload: BankStatementImportRequest,
    current: CurrentUserDep,
    session: SessionDep,
    factory: SessionFactoryDep,
    response: Response,
    idem: IdempotentDep = _ImportIdempotentDep,
) -> BankStatementRead | JobSubmitted:
    """Import a statement CSV (module docstring): ≤1000 data rows inline (201 statement),
    larger submitted as a background job (202 {job_id}). IDEMPOTENT (D-013)."""
    if count_csv_data_rows(payload.csv_text) > BANK_IMPORT_SYNC_MAX_LINES:
        response.status_code = 202
        return await _import_background(payload, current, session, factory, idem)
    return await _import_inline(payload, current, session, idem)


@bank_router.get(
    "/bank-statements",
    response_model=Page[BankStatementRead],
    dependencies=[_ReadGuard],
)
async def list_bank_statements(
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
    bank_account_id: uuid.UUID | None = None,
) -> Page[BankStatementRead]:
    page = await service.list_bank_statements(
        session,
        current.tenant_id,
        cursor=params.cursor,
        limit=params.limit,
        bank_account_id=bank_account_id,
    )
    return map_page(page, BankStatementRead)


@bank_router.get(
    "/bank-statements/{statement_id}",
    response_model=BankStatementDetail,
    dependencies=[_ReadGuard],
)
async def get_bank_statement(
    statement_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> BankStatementDetail:
    """Statement header + progress counts (one grouped count query, PERFORMANCE §2)."""
    statement = await service.get_bank_statement(session, current.tenant_id, statement_id)
    await session.refresh(statement)
    progress = await service.statement_progress(session, current.tenant_id, statement_id)
    header = BankStatementRead.model_validate(statement)
    return BankStatementDetail(
        **header.model_dump(),
        progress=StatementProgressRead(
            total=progress.total,
            unmatched=progress.unmatched,
            suggested=progress.suggested,
            matched=progress.matched,
            cleared=progress.cleared,
            resolved=progress.resolved,
        ),
    )


@bank_router.get(
    "/bank-statements/{statement_id}/lines",
    response_model=Page[BankStatementLineRead],
    dependencies=[_ReadGuard],
)
async def list_bank_statement_lines(
    statement_id: uuid.UUID,
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
    status: str | None = None,
) -> Page[BankStatementLineRead]:
    # 404 on an unknown/foreign statement (vs a silent empty page); 1 extra query, budget ≤3.
    await service.get_bank_statement(session, current.tenant_id, statement_id)
    page = await service.list_statement_lines(
        session,
        current.tenant_id,
        statement_id,
        cursor=params.cursor,
        limit=params.limit,
        status=status,
    )
    return map_page(page, BankStatementLineRead)


@bank_router.post(
    "/bank-statements/{statement_id}/suggest-matches",
    response_model=SuggestMatchesResult,
    dependencies=[_ReconcileGuard],
)
async def suggest_matches(
    statement_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> SuggestMatchesResult:
    """Run the match rules over the statement's UNMATCHED lines. Rerun-safe: resolved and
    already-suggested lines are untouched, so no Idempotency-Key is required."""
    holder: dict[str, SuggestMatchesResult] = {}

    async def work() -> None:
        result = await service.suggest_matches(session, current.tenant_id, statement_id)
        holder["read"] = SuggestMatchesResult(**result)

    await run_in_uow(session, work)
    return holder["read"]


async def _line_action(
    session: SessionDep, work_result: object
) -> BankStatementLineRead:
    await session.refresh(work_result)
    return BankStatementLineRead.model_validate(work_result)


@bank_router.post(
    "/bank-statement-lines/{line_id}/confirm-match",
    response_model=BankStatementLineRead,
    dependencies=[_ReconcileGuard],
)
async def confirm_match(
    line_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> BankStatementLineRead:
    """SUGGESTED -> MATCHED. A replayed confirm hits the status guard (409), no double effect."""
    holder: dict[str, BankStatementLineRead] = {}

    async def work() -> None:
        line = await service.confirm_match(session, current.tenant_id, line_id)
        holder["read"] = await _line_action(session, line)

    await run_in_uow(session, work)
    return holder["read"]


@bank_router.post(
    "/bank-statement-lines/{line_id}/reject-suggestion",
    response_model=BankStatementLineRead,
    dependencies=[_ReconcileGuard],
)
async def reject_suggestion(
    line_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> BankStatementLineRead:
    """SUGGESTED -> UNMATCHED, releasing the journal line for other matches."""
    holder: dict[str, BankStatementLineRead] = {}

    async def work() -> None:
        line = await service.reject_suggestion(session, current.tenant_id, line_id)
        holder["read"] = await _line_action(session, line)

    await run_in_uow(session, work)
    return holder["read"]


@bank_router.post(
    "/bank-statement-lines/{line_id}/clear",
    response_model=BankStatementLineRead,
    dependencies=[_ReconcileGuard],
)
async def clear_line(
    line_id: uuid.UUID,
    payload: ClearLineRequest,
    current: CurrentUserDep,
    session: SessionDep,
    idem: IdempotentDep = _ClearIdempotentDep,
) -> BankStatementLineRead:
    """Post a clearing entry for an UNMATCHED bank-only line (fee/interest). IDEMPOTENT
    (D-013): it creates a financial document, so a retried request replays, never double-posts."""
    holder: dict[str, BankStatementLineRead] = {}

    async def work() -> None:
        line = await service.clear_unmatched_line(
            session, current.tenant_id, line_id, contra_account_id=payload.contra_account_id
        )
        read = await _line_action(session, line)
        holder["read"] = await idem.capture(read)

    await run_in_uow(session, work)
    return holder["read"]
