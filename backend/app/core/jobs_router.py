"""Core-level background-job polling endpoints (PLAN 4P.5, PERFORMANCE §3 — closes #26).

JUSTIFIED ADDITION to core (D-027/D-032 precedent, like security_router.py and
docflow_router.py): jobs are cross-cutting platform infrastructure owned by no business
module — any module's long-running operation returns a job id that polls HERE. Guarded by
``get_current_user`` only: submitting was already permission-guarded per endpoint, and the
D-007 tenant scoping below means a principal can only ever see their own tenant's jobs.
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.core.deps import CurrentUserDep, SessionDep
from app.core.exceptions import NotFoundError
from app.core.jobs import Job
from app.core.pagination import (
    CursorParams,
    OrderKey,
    SortDirection,
    cursor_params,
    filter_fingerprint,
    map_page,
    paginate,
)
from app.core.schemas import JobRead, Page

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])

CursorParamsDep = Depends(cursor_params)


@router.get("", response_model=Page[JobRead])
async def list_jobs(
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
    status: str | None = None,
    job_type: str | None = None,
) -> Page[JobRead]:
    """The tenant's jobs, newest first, optionally filtered by status and/or job_type
    (both folded into the cursor fingerprint per D-014)."""
    stmt = select(Job).where(Job.tenant_id == current.tenant_id)
    if status is not None:
        stmt = stmt.where(Job.status == status)
    if job_type is not None:
        stmt = stmt.where(Job.job_type == job_type)
    page = await paginate(
        session,
        stmt,
        order_by=[OrderKey(Job.created_at, SortDirection.DESC)],
        pk=Job.id,
        cursor=params.cursor,
        limit=params.limit,
        filters=filter_fingerprint(status, job_type),
    )
    return map_page(page, JobRead)


@router.get("/{job_id}", response_model=JobRead)
async def get_job(job_id: uuid.UUID, current: CurrentUserDep, session: SessionDep) -> JobRead:
    """Poll one job: status, result (once COMPLETED), error (once FAILED), timing. 404 for an
    unknown id — including another tenant's job (the D-007 filter + explicit check)."""
    job = await session.get(Job, job_id)
    if job is None or job.tenant_id != current.tenant_id:
        raise NotFoundError(message="Job not found", code="jobs.not_found")
    return JobRead.model_validate(job)
